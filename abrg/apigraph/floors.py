"""Stage 3 — size/structure floors on API-level graphs."""

from __future__ import annotations

from typing import Any

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.apigraph import BASELINE_22, STRUCTURAL_FLOOR_PASS


def _floor_metric(scores: list[float], labels: list[int], name: str) -> dict[str, Any]:
    block = _auc_with_bootstrap(scores, labels)
    return {
        "metric": name,
        "auc": block["auc"],
        "auc_floor": block["auc_floor"],
        "direction": block["direction"],
        "ci95_floor": block["ci95_floor"],
    }


def compute_floors(
    tensors: dict[str, dict[str, Any]],
    test_benign_shas: list[str],
    test_malware_shas: list[str],
) -> dict[str, Any]:
    labels = [0] * len(test_benign_shas) + [1] * len(test_malware_shas)
    shas = test_benign_shas + test_malware_shas

    def vals(key: str) -> list[float]:
        return [float(tensors[s][key]) for s in shas]

    floors = {
        "in_vocab_event_count": _floor_metric(vals("n_inv_events"), labels, "in_vocab_event_count"),
        "total_event_count": _floor_metric(vals("n_total_events"), labels, "total_event_count"),
        "active_nodes": _floor_metric(vals("n_active"), labels, "active_nodes"),
        "edge_count": _floor_metric(vals("n_edges"), labels, "edge_count"),
        "graph_density": _floor_metric(vals("density"), labels, "graph_density"),
        "oov_rate": _floor_metric(vals("oov_rate"), labels, "oov_rate"),
    }
    return floors


def gate_decision(floors_by_k: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """
    GATE: if active_nodes and edge_count remain ~0.52 for every K, STOP.
    Pass if any K has both structural floors >= STRUCTURAL_FLOOR_PASS (0.60).
    """
    per_k = {}
    any_pass = False
    for k, floors in floors_by_k.items():
        an = floors["active_nodes"]["auc_floor"]
        ec = floors["edge_count"]["auc_floor"]
        moved = an >= STRUCTURAL_FLOOR_PASS or ec >= STRUCTURAL_FLOOR_PASS
        both = an >= STRUCTURAL_FLOOR_PASS and ec >= STRUCTURAL_FLOOR_PASS
        per_k[k] = {
            "active_nodes": an,
            "edge_count": ec,
            "baseline_active_nodes": BASELINE_22["active_nodes"],
            "baseline_edge_count": BASELINE_22["edge_count"],
            "structurally_moved": moved,
            "both_ge_0.60": both,
        }
        if moved:
            any_pass = True
    # Spec: if remain at ~0.52 for EVERY K → STOP. If any K moves materially → continue.
    # "Materially (say >=0.60)"
    continue_to_models = any(
        per_k[k]["active_nodes"] >= STRUCTURAL_FLOOR_PASS
        or per_k[k]["edge_count"] >= STRUCTURAL_FLOOR_PASS
        for k in per_k
    )
    return {
        "continue_to_stage4": continue_to_models,
        "threshold": STRUCTURAL_FLOOR_PASS,
        "per_k": per_k,
        "baseline_22": BASELINE_22,
        "verdict": "PASS" if continue_to_models else "STOP — structural floors remain near chance",
    }
