"""Stage 2 — API-level graph construction for fixed vocabulary K."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import torch

from abrg.androct.run_gae_run2 import _dist
from abrg.apigraph import K_BURST
from abrg.apigraph.extract import category_for_callee
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

# activity share, binary active, first-occurrence, 22-category one-hot
NODE_FEAT_DIM = 1 + 1 + 1 + len(GRAPH_CATEGORY_UNIVERSE)  # 25
CAT_INDEX = {c: i for i, c in enumerate(GRAPH_CATEGORY_UNIVERSE)}


def _static_global(app: Any) -> np.ndarray:
    """
    App-level manifest features as a global graph attribute (not per-node).
    Dims: n_permissions, n_components (sum category reach_v), static_norm,
    n_cats_nonzero_static. Per-node permission mapping was not attempted.
    """
    n_perm = float(getattr(app, "n_perm", 0) or 0)
    n_comp = float(getattr(app, "n_components", 0) or 0)
    static_norm = float(getattr(app, "static_norm", 0.0) or 0.0)
    n_cats = float(getattr(app, "n_cats_nonzero_static", 0) or 0)
    return np.asarray([n_perm, n_comp, static_norm, n_cats], dtype=np.float32)


STATIC_GLOBAL_DIM = 4


def build_graph_tensors(
    sequence: list[str],
    vocab: list[str],
    *,
    app: Any,
    k_burst: int = K_BURST,
) -> dict[str, Any]:
    """
    Fixed K nodes (vocab order). OOV calls dropped.
    Edges: k-burst sequence proximity; w_cum then out-share normalize.
    """
    K = len(vocab)
    index = {c: i for i, c in enumerate(vocab)}
    # in-vocab event stream (indices)
    stream = [index[c] for c in sequence if c in index]
    n_total = len(sequence)
    n_inv = len(stream)
    oov_rate = 1.0 - (n_inv / n_total) if n_total else 1.0

    act_count = np.zeros(K, dtype=np.float64)
    first_pos = np.full(K, -1.0, dtype=np.float64)
    for t, ni in enumerate(stream):
        act_count[ni] += 1.0
        if first_pos[ni] < 0:
            first_pos[ni] = float(t)

    # shares-not-counts
    total_act = act_count.sum()
    act_share = act_count / total_act if total_act > 0 else act_count
    active = (act_count > 0).astype(np.float64)
    # first-occurrence normalised to [0,1] over in-vocab trace
    denom = max(n_inv - 1, 1)
    first_norm = np.zeros(K, dtype=np.float64)
    for i in range(K):
        if first_pos[i] >= 0:
            first_norm[i] = first_pos[i] / denom

    # category one-hot
    onehot = np.zeros((K, len(GRAPH_CATEGORY_UNIVERSE)), dtype=np.float64)
    for i, callee in enumerate(vocab):
        cat = category_for_callee(callee)
        if cat in CAT_INDEX:
            onehot[i, CAT_INDEX[cat]] = 1.0

    x = np.concatenate(
        [
            act_share[:, None],
            active[:, None],
            first_norm[:, None],
            onehot,
        ],
        axis=1,
    ).astype(np.float32)

    # edges k-burst
    w: dict[tuple[int, int], float] = defaultdict(float)
    for i, u in enumerate(stream):
        for j in range(i + 1, min(i + 1 + k_burst, len(stream))):
            v = stream[j]
            if u != v:
                w[(u, v)] += 1.0

    # out-share normalize
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
        edge_index = torch.tensor([srcs, dsts], dtype=torch.long)
        edge_weight = torch.tensor(weights, dtype=torch.float32)
    else:
        edge_index = torch.zeros(2, 0, dtype=torch.long)
        edge_weight = torch.zeros(0, dtype=torch.float32)

    n_active = int(active.sum())
    n_edges = int(edge_index.size(1))
    possible = K * (K - 1)
    density = n_edges / possible if possible else 0.0

    return {
        "x": torch.from_numpy(x),
        "edge_index": edge_index,
        "edge_weight": edge_weight,
        "static_global": torch.from_numpy(_static_global(app)),
        "n_active": n_active,
        "n_edges": n_edges,
        "density": density,
        "n_inv_events": n_inv,
        "n_total_events": n_total,
        "oov_rate": float(oov_rate),
        "node_feat_dim": NODE_FEAT_DIM,
        "static_global_dim": STATIC_GLOBAL_DIM,
        "K": K,
    }


def construction_stats(
    tensors: dict[str, dict[str, Any]],
    partitions: dict[str, list[str]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part, shas in partitions.items():
        act = [float(tensors[s]["n_active"]) for s in shas]
        edg = [float(tensors[s]["n_edges"]) for s in shas]
        dens = [float(tensors[s]["density"]) for s in shas]
        frac_le2 = sum(1 for e in edg if e <= 2) / len(edg) if edg else float("nan")
        out[part] = {
            "active_nodes": _dist(act),
            "edges": _dist(edg),
            "density": _dist(dens),
            "fraction_graphs_edges_le_2": frac_le2,
            "n": len(shas),
        }
    return out
