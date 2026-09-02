"""Size floors and coverage helpers for validation grid."""

from __future__ import annotations

from typing import Any

from abrg.androct.run_gae_run2 import _auc_with_bootstrap


def coverage_frac(sequences: dict[str, list[str]], vocab: list[str], shas: list[str]) -> dict[str, float]:
    vset = frozenset(vocab)
    total = 0
    inv = 0
    for sha in shas:
        seq = sequences[sha]
        total += len(seq)
        inv += sum(1 for c in seq if c in vset)
    frac = inv / total if total else float("nan")
    return {
        "in_vocab_events": inv,
        "total_events": total,
        "coverage_frac": frac,
        "oov_frac": 1.0 - frac if total else float("nan"),
    }


def size_floors(
    tensors: dict[str, dict[str, Any]],
    test_b: list[str],
    test_m: list[str],
) -> dict[str, Any]:
    labels = [0] * len(test_b) + [1] * len(test_m)
    shas = test_b + test_m

    def block(key: str, name: str) -> dict[str, Any]:
        scores = [float(tensors[s][key]) for s in shas]
        b = _auc_with_bootstrap(scores, labels)
        return {
            "metric": name,
            "auc_floor": b["auc_floor"],
            "direction": b["direction"],
            "ci95_floor": b["ci95_floor"],
        }

    return {
        "in_vocab_events": block("n_inv_events", "in_vocab_events"),
        "total_events": block("n_total_events", "total_events"),
        "active_nodes": block("n_active", "active_nodes"),
        "oov_rate": block("oov_rate", "oov_rate"),
    }
