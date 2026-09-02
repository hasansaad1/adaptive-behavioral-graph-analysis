"""Part B feature matrices from existing run-3 22-node tensors."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from abrg.features import node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.transitions import N_NODES

assert len(GRAPH_CATEGORY_UNIVERSE) == N_NODES
assert node_feature_dim() == 10

# F4 definitions (stated for README / SUMMARY):
# For each node i with out-row A[i,:]:
#   out_degree_share = (# nonzero A[i,j], j!=i) / (N-1)
#   out_entropy      = -sum_j p_j log(p_j) where p = A[i,:] / sum(A[i,:]) if sum>0 else 0
#   max_out_share    = max_j A[i,j]  (0 if empty row)
F4_DEF = (
    "per node i: out_degree_share = nnz(A[i, ≠i])/(N-1); "
    "out_entropy = H(normalize(A[i,:])); max_out_share = max(A[i,:]); "
    "concat over 22 nodes → 66 dims"
)


def adj_matrix(
    edge_index: torch.Tensor, edge_weight: torch.Tensor, n: int = N_NODES
) -> np.ndarray:
    A = np.zeros((n, n), dtype=np.float64)
    if edge_index.numel() == 0:
        return A
    src = edge_index[0].cpu().numpy()
    dst = edge_index[1].cpu().numpy()
    w = edge_weight.cpu().numpy().astype(np.float64)
    for i, j, ww in zip(src, dst, w):
        A[int(i), int(j)] = float(ww)
    return A


def adj_pooled_66(A: np.ndarray) -> np.ndarray:
    n = A.shape[0]
    out = np.zeros(n * 3, dtype=np.float64)
    for i in range(n):
        row = A[i].copy()
        # exclude self for degree count (self may be 0 in proximity graphs)
        mask = np.ones(n, dtype=bool)
        mask[i] = False
        nnz = int(np.count_nonzero(row[mask]))
        out_degree_share = nnz / max(n - 1, 1)
        s = float(row.sum())
        if s > 0:
            p = row / s
            p = p[p > 0]
            entropy = float(-(p * np.log(p)).sum())
            max_share = float(row.max())
        else:
            entropy = 0.0
            max_share = 0.0
        out[i * 3] = out_degree_share
        out[i * 3 + 1] = entropy
        out[i * 3 + 2] = max_share
    return out


def node_pool_mean(x: np.ndarray) -> np.ndarray:
    """OCPool-style mean over nodes → 10 dims."""
    return x.mean(axis=0)


def build_feature_row(t: dict[str, Any], kind: str) -> np.ndarray:
    x = t["x"].detach().cpu().numpy().astype(np.float64)
    assert x.shape == (N_NODES, 10), f"expected (22,10), got {x.shape}"
    A = adj_matrix(t["edge_index"], t["edge_weight"])
    if kind == "F1_adj_only":
        return A.reshape(-1)  # 484
    if kind == "F2_node_only":
        return x.reshape(-1)  # 220
    if kind == "F3_full":
        return np.concatenate([x.reshape(-1), A.reshape(-1)])  # 704
    if kind == "F4_adj_pooled":
        return adj_pooled_66(A)  # 66
    if kind == "F5_node_mean_plus_adj_pooled":
        return np.concatenate([node_pool_mean(x), adj_pooled_66(A)])  # 76
    raise ValueError(kind)


FEATURE_KINDS = (
    "F1_adj_only",
    "F2_node_only",
    "F3_full",
    "F4_adj_pooled",
    "F5_node_mean_plus_adj_pooled",
)

FEATURE_DIMS = {
    "F1_adj_only": 484,
    "F2_node_only": 220,
    "F3_full": 704,
    "F4_adj_pooled": 66,
    "F5_node_mean_plus_adj_pooled": 76,
}


def matrix_for_apps(
    tensors: dict[str, dict[str, Any]],
    shas: list[str],
    kind: str,
) -> np.ndarray:
    rows = [build_feature_row(tensors[s], kind) for s in shas]
    X = np.stack(rows, axis=0)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    expected = FEATURE_DIMS[kind]
    assert X.shape[1] == expected, f"{kind}: got {X.shape[1]} != {expected}"
    return X


def covariates(tensors: dict[str, dict[str, Any]], shas: list[str]) -> dict[str, list[float]]:
    return {
        "mapped_events": [float(tensors[s]["n_mapped"]) for s in shas],
        "total_events": [float(tensors[s]["n_events"]) for s in shas],
        "active_nodes": [float(tensors[s]["n_active"]) for s in shas],
        "edge_count": [float(tensors[s]["n_edges"]) for s in shas],
        "density": [float(tensors[s]["density"]) for s in shas],
        "static_norm": [float(tensors[s]["static_norm"]) for s in shas],
    }
