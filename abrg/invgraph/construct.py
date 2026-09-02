"""Stage 2 — three edge variants on fixed B_docfreq K=1000 nodes/features."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

import numpy as np
import torch

from abrg.androct.run_gae_run2 import _dist
from abrg.apigraph.extract import category_for_callee
from abrg.invgraph import K_BURST, V3_LOOKBACK
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

NODE_FEAT_DIM = 1 + 1 + 1 + len(GRAPH_CATEGORY_UNIVERSE)  # 25
assert NODE_FEAT_DIM == 25, f"node_feat_dim must be 25, got {NODE_FEAT_DIM}"
CAT_INDEX = {c: i for i, c in enumerate(GRAPH_CATEGORY_UNIVERSE)}
STATIC_GLOBAL_DIM = 4

Variant = Literal["V1_proximity", "V2_invocation", "V3_invocation_projected"]


def _static_global(app: Any) -> np.ndarray:
    n_perm = float(getattr(app, "n_perm", 0) or 0)
    n_comp = float(getattr(app, "n_components", 0) or 0)
    static_norm = float(getattr(app, "static_norm", 0.0) or 0.0)
    n_cats = float(getattr(app, "n_cats_nonzero_static", 0) or 0)
    return np.asarray([n_perm, n_comp, static_norm, n_cats], dtype=np.float32)


def _node_features(
    callee_seq: list[str],
    vocab: list[str],
    index: dict[str, int],
) -> tuple[np.ndarray, dict[str, Any]]:
    K = len(vocab)
    stream = [index[c] for c in callee_seq if c in index]
    n_total = len(callee_seq)
    n_inv = len(stream)
    oov_rate = 1.0 - (n_inv / n_total) if n_total else 1.0

    act_count = np.zeros(K, dtype=np.float64)
    first_pos = np.full(K, -1.0, dtype=np.float64)
    for t, ni in enumerate(stream):
        act_count[ni] += 1.0
        if first_pos[ni] < 0:
            first_pos[ni] = float(t)

    total_act = act_count.sum()
    act_share = act_count / total_act if total_act > 0 else act_count
    active = (act_count > 0).astype(np.float64)
    denom = max(n_inv - 1, 1)
    first_norm = np.zeros(K, dtype=np.float64)
    for i in range(K):
        if first_pos[i] >= 0:
            first_norm[i] = first_pos[i] / denom

    onehot = np.zeros((K, len(GRAPH_CATEGORY_UNIVERSE)), dtype=np.float64)
    for i, callee in enumerate(vocab):
        cat = category_for_callee(callee)
        if cat in CAT_INDEX:
            onehot[i, CAT_INDEX[cat]] = 1.0

    x = np.concatenate(
        [act_share[:, None], active[:, None], first_norm[:, None], onehot],
        axis=1,
    ).astype(np.float32)
    meta = {
        "n_active": int(active.sum()),
        "n_inv_events": n_inv,
        "n_total_events": n_total,
        "oov_rate": float(oov_rate),
        "stream": stream,
    }
    return x, meta


def _normalize_out_shares(w: dict[tuple[int, int], float]) -> tuple[torch.Tensor, torch.Tensor]:
    out_sum: dict[int, float] = defaultdict(float)
    for (u, _), ww in w.items():
        out_sum[u] += ww
    srcs: list[int] = []
    dsts: list[int] = []
    weights: list[float] = []
    for (u, v), ww in w.items():
        srcs.append(u)
        dsts.append(v)
        weights.append(ww / out_sum[u] if out_sum[u] > 0 else 0.0)
    if srcs:
        return (
            torch.tensor([srcs, dsts], dtype=torch.long),
            torch.tensor(weights, dtype=torch.float32),
        )
    return torch.zeros(2, 0, dtype=torch.long), torch.zeros(0, dtype=torch.float32)


def _edges_proximity(stream: list[int], *, k_burst: int = K_BURST) -> dict[tuple[int, int], float]:
    w: dict[tuple[int, int], float] = defaultdict(float)
    for i, u in enumerate(stream):
        for j in range(i + 1, min(i + 1 + k_burst, len(stream))):
            v = stream[j]
            if u != v:
                w[(u, v)] += 1.0
    return w


def _edges_invocation_fixed(
    pairs: list[tuple[str, str]],
    index: dict[str, int],
) -> tuple[dict[tuple[int, int], float], dict[str, int]]:
    w: dict[tuple[int, int], float] = defaultdict(float)
    n_lines = len(pairs)
    n_both_inv = 0
    n_edge = 0
    n_callee_oov = 0
    n_callee_inv_caller_oov = 0
    for u_s, v_s in pairs:
        u_in = u_s in index
        v_in = v_s in index
        if not v_in:
            n_callee_oov += 1
            continue
        if not u_in:
            n_callee_inv_caller_oov += 1
            continue
        n_both_inv += 1
        u, v = index[u_s], index[v_s]
        if u != v:
            w[(u, v)] += 1.0
            n_edge += 1
    stats = {
        "n_call_lines": n_lines,
        "n_both_inv": n_both_inv,
        "n_directed_edge_increments": n_edge,
        "n_dropped": n_lines - n_both_inv,
        "n_callee_oov": n_callee_oov,
        "n_callee_inv_caller_oov": n_callee_inv_caller_oov,
        "drop_rate": 1.0 - (n_both_inv / n_lines) if n_lines else float("nan"),
    }
    return w, stats


def _edges_projected(
    pairs: list[tuple[str, str]],
    index: dict[str, int],
    *,
    lookback: int = V3_LOOKBACK,
) -> tuple[dict[tuple[int, int], float], dict[str, int]]:
    """
    V2 edges plus: when callee∈vocab and caller∉vocab, use nearest prior
    in-vocabulary method sighting within `lookback` as caller proxy.
    History records in-vocab callers/callees in chronological order.
    """
    w: dict[tuple[int, int], float] = defaultdict(float)
    history: list[int] = []
    n_v2 = 0
    n_projected = 0
    n_lines = len(pairs)
    n_unresolved = 0
    for u_s, v_s in pairs:
        v_in = v_s in index
        u_in = u_s in index
        if v_in:
            v = index[v_s]
            if u_in:
                u = index[u_s]
                if u != v:
                    w[(u, v)] += 1.0
                    n_v2 += 1
            else:
                # lookback in history
                found = False
                window = history[-lookback:] if lookback > 0 else history
                for h in reversed(window):
                    if h != v:
                        w[(h, v)] += 1.0
                        n_projected += 1
                        found = True
                        break
                if not found:
                    n_unresolved += 1
        # update history with in-vocab endpoints (order: caller then callee)
        if u_in:
            history.append(index[u_s])
        if v_in:
            history.append(index[v_s])
    stats = {
        "n_call_lines": n_lines,
        "n_v2_style_edges": n_v2,
        "n_projected_edges": n_projected,
        "n_unresolved_callee_inv": n_unresolved,
        "lookback": lookback,
        "n_edges_raw": n_v2 + n_projected,
    }
    return w, stats


def build_variant_tensors(
    pairs: list[tuple[str, str]],
    vocab: list[str],
    *,
    app: Any,
    variant: Variant,
) -> dict[str, Any]:
    assert NODE_FEAT_DIM == 25
    K = len(vocab)
    index = {c: i for i, c in enumerate(vocab)}
    callee_seq = [c for _, c in pairs]
    x, meta = _node_features(callee_seq, vocab, index)

    edge_stats: dict[str, Any] = {}
    if variant == "V1_proximity":
        w = _edges_proximity(meta["stream"], k_burst=K_BURST)
        edge_stats = {"variant": variant, "k_burst": K_BURST}
    elif variant == "V2_invocation":
        w, edge_stats = _edges_invocation_fixed(pairs, index)
        edge_stats["variant"] = variant
    elif variant == "V3_invocation_projected":
        w, edge_stats = _edges_projected(pairs, index, lookback=V3_LOOKBACK)
        edge_stats["variant"] = variant
    else:
        raise ValueError(variant)

    # drop unused stream from meta for tensor dict
    stream = meta.pop("stream")
    del stream

    edge_index, edge_weight = _normalize_out_shares(w)
    n_edges = int(edge_index.size(1))
    possible = K * (K - 1)
    density = n_edges / possible if possible else 0.0

    # degree stats for this graph
    out_deg = np.zeros(K, dtype=np.float64)
    in_deg = np.zeros(K, dtype=np.float64)
    if n_edges:
        src = edge_index[0].numpy()
        dst = edge_index[1].numpy()
        for u in src:
            out_deg[u] += 1
        for v in dst:
            in_deg[v] += 1

    return {
        "x": torch.from_numpy(x),
        "edge_index": edge_index,
        "edge_weight": edge_weight,
        "static_global": torch.from_numpy(_static_global(app)),
        "n_active": meta["n_active"],
        "n_edges": n_edges,
        "density": density,
        "n_inv_events": meta["n_inv_events"],
        "n_total_events": meta["n_total_events"],
        "oov_rate": meta["oov_rate"],
        "node_feat_dim": NODE_FEAT_DIM,
        "static_global_dim": STATIC_GLOBAL_DIM,
        "K": K,
        "variant": variant,
        "edge_stats": edge_stats,
        "mean_out_degree_active": float(out_deg[out_deg > 0].mean()) if (out_deg > 0).any() else 0.0,
        "mean_in_degree_active": float(in_deg[in_deg > 0].mean()) if (in_deg > 0).any() else 0.0,
        "unique_edge_keys": frozenset(w.keys()),
    }


def construction_stats(
    tensors: dict[str, dict[str, Any]],
    partitions: dict[str, list[str]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    corpus_edges: set[tuple[int, int]] = set()
    for part, shas in partitions.items():
        edg = [float(tensors[s]["n_edges"]) for s in shas]
        dens = [float(tensors[s]["density"]) for s in shas]
        act = [float(tensors[s]["n_active"]) for s in shas]
        out_d = [float(tensors[s]["mean_out_degree_active"]) for s in shas]
        in_d = [float(tensors[s]["mean_in_degree_active"]) for s in shas]
        frac_le2 = sum(1 for e in edg if e <= 2) / len(edg) if edg else float("nan")
        for s in shas:
            corpus_edges |= set(tensors[s].get("unique_edge_keys") or [])
        # drop rates if present
        drop = [
            float(tensors[s]["edge_stats"].get("drop_rate", float("nan")))
            for s in shas
            if "drop_rate" in tensors[s].get("edge_stats", {})
        ]
        proj = [
            float(tensors[s]["edge_stats"].get("n_projected_edges", 0))
            for s in shas
        ]
        v2e = [
            float(tensors[s]["edge_stats"].get("n_v2_style_edges", float("nan")))
            for s in shas
        ]
        out[part] = {
            "edges": _dist(edg),
            "density": _dist(dens),
            "active_nodes": _dist(act),
            "fraction_graphs_edges_le_2": frac_le2,
            "mean_out_degree_active": _dist(out_d),
            "mean_in_degree_active": _dist(in_d),
            "n": len(shas),
        }
        if drop:
            out[part]["drop_rate"] = _dist(drop)
        if any(np.isfinite(v2e)):
            out[part]["n_projected_edges"] = _dist(proj)
            out[part]["n_v2_style_edges"] = _dist([x for x in v2e if np.isfinite(x)])
    out["corpus_n_distinct_edges"] = len(corpus_edges)
    return out
