"""Part A — 22-category invocation-transition matrices."""

from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any

import torch

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist
from abrg.api_category_map import categorize_callee
from abrg.features import node_feature_dim
from abrg.invgraph.extract import extract_invocation_pairs
from abrg.registry import DROPPED_CATEGORIES, GRAPH_CATEGORY_UNIVERSE
from abrg.transitions import (
    BASELINE_EDGE,
    DROP_ASYMMETRY_WARN,
    N_NODES,
    STRUCTURAL_EDGE_PASS,
)

assert len(GRAPH_CATEGORY_UNIVERSE) == N_NODES
CAT_INDEX = {c: i for i, c in enumerate(GRAPH_CATEGORY_UNIVERSE)}
_GRAPH = frozenset(GRAPH_CATEGORY_UNIVERSE)


@lru_cache(maxsize=500_000)
def categories_for_method(method: str) -> frozenset[str]:
    """
    Map normalized `Class.method` via categorize_callee → graph categories.
    Returns possibly multiple categories (cartesian product used for edges).
    """
    cls, _, meth = method.rpartition(".")
    if not cls or not meth:
        return frozenset()
    cats = categorize_callee(cls, meth) - DROPPED_CATEGORIES
    cats &= _GRAPH
    return frozenset(cats)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _count_pairs_and_weights(
    pairs: list[tuple[str, str]],
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], float], dict[str, int]]:
    """
    Single pass: accumulate weights with self-loops and without.
    Multi-category → cartesian product of edges (stated in README).
    """
    w_with: dict[tuple[int, int], float] = defaultdict(float)
    w_no: dict[tuple[int, int], float] = defaultdict(float)
    n_lines = len(pairs)
    n_caller_unmapped = 0
    n_callee_unmapped = 0
    n_either_unmapped = 0
    n_both_mapped = 0
    n_self_loop_increments = 0
    n_edge_increments_with = 0
    n_edge_increments_no = 0

    for caller_m, callee_m in pairs:
        c_cats = categories_for_method(caller_m)
        v_cats = categories_for_method(callee_m)
        caller_um = len(c_cats) == 0
        callee_um = len(v_cats) == 0
        if caller_um:
            n_caller_unmapped += 1
        if callee_um:
            n_callee_unmapped += 1
        if caller_um or callee_um:
            n_either_unmapped += 1
            continue
        n_both_mapped += 1
        for cu in c_cats:
            for cv in v_cats:
                u, v = CAT_INDEX[cu], CAT_INDEX[cv]
                w_with[(u, v)] += 1.0
                n_edge_increments_with += 1
                if u == v:
                    n_self_loop_increments += 1
                else:
                    w_no[(u, v)] += 1.0
                    n_edge_increments_no += 1

    stats = {
        "n_call_lines": n_lines,
        "n_caller_unmapped": n_caller_unmapped,
        "n_callee_unmapped": n_callee_unmapped,
        "n_either_unmapped": n_either_unmapped,
        "n_both_mapped": n_both_mapped,
        "caller_unmapped_rate": n_caller_unmapped / n_lines if n_lines else float("nan"),
        "callee_unmapped_rate": n_callee_unmapped / n_lines if n_lines else float("nan"),
        "either_unmapped_rate": n_either_unmapped / n_lines if n_lines else float("nan"),
        "n_self_loop_increments": n_self_loop_increments,
        "n_edge_increments_with_self": n_edge_increments_with,
        "n_edge_increments_no_self": n_edge_increments_no,
    }
    return w_with, w_no, stats


def _normalize_shares(w: dict[tuple[int, int], float]) -> tuple[torch.Tensor, torch.Tensor]:
    out_sum: dict[int, float] = defaultdict(float)
    for (u, _), ww in w.items():
        out_sum[u] += ww
    srcs, dsts, weights = [], [], []
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


def _tensor_from_weights(
    base: dict[str, Any],
    w: dict[tuple[int, int], float],
    st: dict[str, Any],
    *,
    keep_self_loops: bool,
    sha: str,
) -> dict[str, Any]:
    x = base["x"]
    feat_dim = int(x.shape[1])
    ei, ew = _normalize_shares(w)
    n_edges = int(ei.size(1))
    possible = N_NODES * N_NODES if keep_self_loops else N_NODES * (N_NODES - 1)
    density = n_edges / possible if possible else 0.0
    return {
        "x": x,
        "edge_index": ei,
        "edge_weight": ew,
        "static_global": torch.tensor([float(base["static_norm"])], dtype=torch.float32),
        "n_active": int(base["n_active"]),
        "n_edges": n_edges,
        "density": density,
        "n_mapped": int(base["n_mapped"]),
        "n_events": int(base["n_events"]),
        "static_norm": float(base["static_norm"]),
        "caller_unmapped_rate": float(st["caller_unmapped_rate"]),
        "callee_unmapped_rate": float(st["callee_unmapped_rate"]),
        "either_unmapped_rate": float(st["either_unmapped_rate"]),
        "label": base.get("label"),
        "sha256": sha,
        "node_feat_dim": feat_dim,
    }


def build_both_variants(
    *,
    base_tensors: dict[str, dict[str, Any]],
    pairs: dict[str, list[tuple[str, str]]],
    shas: list[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """One categorization pass → with_self and no_self tensors + per-sha drop stats."""
    feat_dim = node_feature_dim()
    assert feat_dim == 10
    out_with: dict[str, dict[str, Any]] = {}
    out_no: dict[str, dict[str, Any]] = {}
    per_sha_drop: dict[str, dict[str, Any]] = {}
    for i, sha in enumerate(shas):
        base = base_tensors[sha]
        assert base["x"].shape == (N_NODES, feat_dim), f"{sha}: x {tuple(base['x'].shape)}"
        w_with, w_no, st = _count_pairs_and_weights(pairs[sha])
        out_with[sha] = _tensor_from_weights(base, w_with, st, keep_self_loops=True, sha=sha)
        out_no[sha] = _tensor_from_weights(base, w_no, st, keep_self_loops=False, sha=sha)
        per_sha_drop[sha] = st
        if (i + 1) % 500 == 0:
            print(f"  … invocation graphs {i+1}/{len(shas)}", flush=True)
    return out_with, out_no, per_sha_drop


def drop_accounting(
    per_sha_drop: dict[str, dict[str, Any]],
    partitions: dict[str, list[str]],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for part, shas in partitions.items():
        caller = [float(per_sha_drop[s]["caller_unmapped_rate"]) for s in shas]
        callee = [float(per_sha_drop[s]["callee_unmapped_rate"]) for s in shas]
        either = [float(per_sha_drop[s]["either_unmapped_rate"]) for s in shas]
        n_lines = sum(int(per_sha_drop[s]["n_call_lines"]) for s in shas)
        n_cu = sum(int(per_sha_drop[s]["n_caller_unmapped"]) for s in shas)
        n_vu = sum(int(per_sha_drop[s]["n_callee_unmapped"]) for s in shas)
        n_eu = sum(int(per_sha_drop[s]["n_either_unmapped"]) for s in shas)
        out[part] = {
            "caller_unmapped_rate_per_app": _dist(caller),
            "callee_unmapped_rate_per_app": _dist(callee),
            "either_unmapped_rate_per_app": _dist(either),
            "corpus_caller_unmapped_rate": n_cu / n_lines if n_lines else float("nan"),
            "corpus_callee_unmapped_rate": n_vu / n_lines if n_lines else float("nan"),
            "corpus_either_unmapped_rate": n_eu / n_lines if n_lines else float("nan"),
            "n_lines": n_lines,
        }
    tb = out["train_benign"]["corpus_either_unmapped_rate"]
    tm = out["test_malware"]["corpus_either_unmapped_rate"]
    teb = out["test_benign"]["corpus_either_unmapped_rate"]
    out["asymmetry"] = {
        "either_unmapped_train_benign_vs_test_malware": abs(tb - tm),
        "either_unmapped_test_benign_vs_test_malware": abs(teb - tm),
        "warn_threshold": DROP_ASYMMETRY_WARN,
        "asymmetric_train_vs_malware": abs(tb - tm) > DROP_ASYMMETRY_WARN,
        "asymmetric_testb_vs_malware": abs(teb - tm) > DROP_ASYMMETRY_WARN,
    }
    return out


def construction_stats(
    tensors: dict[str, dict[str, Any]],
    partitions: dict[str, list[str]],
) -> dict[str, Any]:
    out = {}
    for part, shas in partitions.items():
        edg = [float(tensors[s]["n_edges"]) for s in shas]
        dens = [float(tensors[s]["density"]) for s in shas]
        out[part] = {
            "edges": _dist(edg),
            "density": _dist(dens),
            "fraction_graphs_edges_le_2": sum(1 for e in edg if e <= 2) / len(edg),
            "n": len(shas),
        }
    return out


def compute_floors(
    tensors: dict[str, dict[str, Any]],
    test_b: list[str],
    test_m: list[str],
) -> dict[str, Any]:
    labels = [0] * len(test_b) + [1] * len(test_m)
    shas = test_b + test_m

    def block(name: str, key: str) -> dict[str, Any]:
        scores = [float(tensors[s][key]) for s in shas]
        b = _auc_with_bootstrap(scores, labels)
        return {
            "metric": name,
            "auc": b["auc"],
            "auc_floor": b["auc_floor"],
            "direction": b["direction"],
            "ci95_floor": b["ci95_floor"],
        }

    return {
        "edge_count": block("edge_count", "n_edges"),
        "graph_density": block("graph_density", "density"),
        "active_nodes": block("active_nodes", "n_active"),
        "mapped_events": block("mapped_events", "n_mapped"),
        "total_events": block("total_events", "n_events"),
        "caller_unmapped_rate": block("caller_unmapped_rate", "caller_unmapped_rate"),
    }


def gate_part_a(floors: dict[str, Any], drop: dict[str, Any]) -> dict[str, Any]:
    ec = float(floors["edge_count"]["auc_floor"])
    dens = float(floors["graph_density"]["auc_floor"])
    moved = ec >= STRUCTURAL_EDGE_PASS or dens >= STRUCTURAL_EDGE_PASS
    asym = drop["asymmetry"]
    symmetric = not asym["asymmetric_testb_vs_malware"]
    continue_ok = moved and symmetric
    if moved and not symmetric:
        verdict = (
            "STOP — edge floors moved but caller/either-unmapped rate is class-asymmetric"
        )
    elif not moved:
        verdict = "STOP — edge_count/density remain ~0.50–0.53"
    else:
        verdict = "PASS"
    return {
        "continue_to_models": continue_ok,
        "edge_count": ec,
        "density": dens,
        "moved_ge_0.60": moved,
        "drop_symmetric": symmetric,
        "asymmetry": asym,
        "baselines": BASELINE_EDGE,
        "threshold": STRUCTURAL_EDGE_PASS,
        "verdict": verdict,
        "downstream_self_loops": False,
    }


def run_part_a(
    *,
    all_apps: list[Any],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[transitions/A] load run2 tensors (node features)", flush=True)
    bundle = load_corpus_cache(androct_run2_output_dir())
    base = bundle.tensors
    sample = base[train_shas[0]]
    assert int(sample["x"].shape[1]) == node_feature_dim() == 10

    print("[transitions/A] invocation pairs (cache)", flush=True)
    pairs = extract_invocation_pairs(all_apps)

    partitions = {
        "train_benign": train_shas,
        "test_benign": test_b,
        "test_malware": test_m,
    }
    all_shas = train_shas + test_b + test_m

    print("[transitions/A] build with/without self-loops (single pass)", flush=True)
    tensors_with, tensors_no, per_drop = build_both_variants(
        base_tensors=base, pairs=pairs, shas=all_shas
    )
    drop = drop_accounting(per_drop, partitions)
    n_self = sum(int(per_drop[s]["n_self_loop_increments"]) for s in all_shas)

    variants = {}
    for name, tensors in (("with_self_loops", tensors_with), ("no_self_loops", tensors_no)):
        stats = construction_stats(tensors, partitions)
        floors = compute_floors(tensors, test_b, test_m)
        variants[name] = {
            "tensors": tensors,
            "drop": drop,
            "stats": stats,
            "floors": floors,
            "n_self_loop_increments_corpus": n_self,
        }
        _write_json(out_dir / f"{name}_drop.json", drop)
        _write_json(out_dir / f"{name}_stats.json", stats)
        _write_json(out_dir / f"{name}_floors.json", floors)
        print(
            f"  {name}: edge_floor={floors['edge_count']['auc_floor']:.4f} "
            f"either_um train={drop['train_benign']['corpus_either_unmapped_rate']:.4f} "
            f"test_m={drop['test_malware']['corpus_either_unmapped_rate']:.4f}",
            flush=True,
        )

    primary = variants["no_self_loops"]
    gate = gate_part_a(primary["floors"], primary["drop"])
    _write_json(out_dir / "gate.json", gate)
    print(f"[transitions/A] GATE: {gate['verdict']}", flush=True)

    summary = {
        "node_feat_dim": 10,
        "cartesian_multi_category": True,
        "downstream_variant": "no_self_loops",
        "with_self_loops": {
            "floors": variants["with_self_loops"]["floors"],
            "drop": variants["with_self_loops"]["drop"],
            "stats": variants["with_self_loops"]["stats"],
            "n_self_loop_increments_corpus": n_self,
        },
        "no_self_loops": {
            "floors": primary["floors"],
            "drop": primary["drop"],
            "stats": primary["stats"],
            "n_self_loop_increments_corpus": n_self,
        },
        "gate": gate,
    }
    _write_json(out_dir / "partA_summary.json", summary)
    return {
        "summary": summary,
        "tensors_no_self": primary["tensors"],
        "gate": gate,
    }
