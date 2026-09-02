"""Stage 3 — structural floors and gate on edge variants."""

from __future__ import annotations

from typing import Any

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.invgraph import (
    BASELINE_EDGE,
    STRUCTURAL_EDGE_PASS,
    V1_EDGE_FLOOR_TARGET,
    V1_EDGE_FLOOR_TOL,
)


def compute_floors(
    tensors: dict[str, dict[str, Any]],
    test_benign_shas: list[str],
    test_malware_shas: list[str],
) -> dict[str, Any]:
    labels = [0] * len(test_benign_shas) + [1] * len(test_malware_shas)
    shas = test_benign_shas + test_malware_shas

    def vals(key: str) -> list[float]:
        return [float(tensors[s][key]) for s in shas]

    def block(name: str, scores: list[float]) -> dict[str, Any]:
        b = _auc_with_bootstrap(scores, labels)
        return {
            "metric": name,
            "auc": b["auc"],
            "auc_floor": b["auc_floor"],
            "direction": b["direction"],
            "ci95_floor": b["ci95_floor"],
        }

    return {
        "edge_count": block("edge_count", vals("n_edges")),
        "graph_density": block("graph_density", vals("density")),
        "active_nodes": block("active_nodes", vals("n_active")),
        "in_vocab_events": block("in_vocab_events", vals("n_inv_events")),
        "total_events": block("total_events", vals("n_total_events")),
        "oov_rate": block("oov_rate", vals("oov_rate")),
    }


def check_v1_reproduces(floors_v1: dict[str, Any]) -> dict[str, Any]:
    edge = float(floors_v1["edge_count"]["auc_floor"])
    ok = abs(edge - V1_EDGE_FLOOR_TARGET) <= V1_EDGE_FLOOR_TOL
    return {
        "v1_edge_floor": edge,
        "target": V1_EDGE_FLOOR_TARGET,
        "tol": V1_EDGE_FLOOR_TOL,
        "ok": ok,
        "message": (
            "V1 proximity edge floor matches B_docfreq control"
            if ok
            else f"STOP: V1 edge floor {edge:.4f} != B_docfreq ~{V1_EDGE_FLOOR_TARGET}"
        ),
    }


def gate_decision(floors_by_variant: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    PASS if V2 or V3 has edge_count or density floor >= STRUCTURAL_EDGE_PASS (0.60).
    V1 is the proximity control only.
    """
    per = {}
    any_pass = False
    for name in ("V2_invocation", "V3_invocation_projected"):
        if name not in floors_by_variant:
            continue
        f = floors_by_variant[name]
        ec = float(f["edge_count"]["auc_floor"])
        dens = float(f["graph_density"]["auc_floor"])
        moved = ec >= STRUCTURAL_EDGE_PASS or dens >= STRUCTURAL_EDGE_PASS
        per[name] = {
            "edge_count": ec,
            "graph_density": dens,
            "moved_ge_0.60": moved,
        }
        if moved:
            any_pass = True
    return {
        "continue_to_stage4": any_pass,
        "threshold": STRUCTURAL_EDGE_PASS,
        "baselines": BASELINE_EDGE,
        "per_variant_v2_v3": per,
        "verdict": (
            "PASS"
            if any_pass
            else "STOP — V2/V3 edge_count and density remain near chance (~0.50–0.53)"
        ),
    }


def pick_best_variant(floors_by_variant: dict[str, dict[str, Any]]) -> str:
    """Best = argmax among V2/V3 of max(edge_count, density)."""
    best = None
    best_score = -1.0
    for name in ("V2_invocation", "V3_invocation_projected"):
        f = floors_by_variant[name]
        score = max(
            float(f["edge_count"]["auc_floor"]),
            float(f["graph_density"]["auc_floor"]),
        )
        if score > best_score:
            best_score = score
            best = name
    assert best is not None
    return best
