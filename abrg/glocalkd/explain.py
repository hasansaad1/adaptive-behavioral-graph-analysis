"""Per-node deviation explainability tables."""

from __future__ import annotations

from typing import Any

import numpy as np

from abrg.registry import GRAPH_CATEGORY_UNIVERSE


def node_deviation_table(
    *,
    node_scores_benign: list[np.ndarray],
    node_scores_malware: list[np.ndarray],
    kind: str,
    top_k: int = 20,
) -> dict[str, Any]:
    """
    Mean per-node score for test benign vs malware; ranked by |Δ|.
    T22: label with GRAPH_CATEGORY_UNIVERSE.
    T1K: label with vocab index 0..K-1.
    """
    if not node_scores_benign or not node_scores_malware:
        return {"error": "empty node scores"}
    n_nodes = int(node_scores_benign[0].shape[0])
    B = np.stack(node_scores_benign, axis=0)  # (n_b, N)
    M = np.stack(node_scores_malware, axis=0)
    mean_b = B.mean(axis=0)
    mean_m = M.mean(axis=0)
    delta = mean_m - mean_b  # malware − benign

    if kind == "T22":
        names = list(GRAPH_CATEGORY_UNIVERSE)
        if len(names) != n_nodes:
            names = [f"node_{i}" for i in range(n_nodes)]
    else:
        names = [f"api_{i}" for i in range(n_nodes)]

    rows = []
    for i in range(n_nodes):
        rows.append(
            {
                "node_idx": i,
                "name": names[i],
                "mean_test_benign": float(mean_b[i]),
                "mean_test_malware": float(mean_m[i]),
                "delta_malware_minus_benign": float(delta[i]),
                "abs_delta": float(abs(delta[i])),
            }
        )
    rows_sorted = sorted(rows, key=lambda r: -r["abs_delta"])
    return {
        "kind": kind,
        "n_nodes": n_nodes,
        "n_test_benign": len(node_scores_benign),
        "n_test_malware": len(node_scores_malware),
        "all_nodes_ranked": rows_sorted,
        "top_k": rows_sorted[:top_k],
        "full_t22_table": rows if kind == "T22" else None,
    }
