"""Per-population size floors (mapped-event count)."""

from __future__ import annotations

from typing import Any

from abrg.androct.run_gae_run2 import _auc_with_bootstrap


def mapped_event_floor(
    tensors: dict[str, dict[str, Any]],
    test_shas: list[str],
    labels: list[int],
) -> dict[str, Any]:
    scores = [float(tensors[s]["n_mapped"]) for s in test_shas]
    block = _auc_with_bootstrap(scores, labels)
    return {
        "metric": "mapped_event_count",
        "auc_floor": block["auc_floor"],
        "direction": block["direction"],
        "ci95_floor": block["ci95_floor"],
        "n": block["n"],
    }


def labels_for_shas(shas: list[str], by_sha: dict[str, Any]) -> list[int]:
    return [1 if by_sha[s].label == "malware" else 0 for s in shas]
