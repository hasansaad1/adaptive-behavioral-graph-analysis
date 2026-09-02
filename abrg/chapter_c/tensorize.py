"""Dense tensorization and distance utilities for Chapter C references."""

from __future__ import annotations

import math
from typing import Literal

import numpy as np

from abrg.features import graph_to_tensors, node_feature_dim
from abrg.graph import ABRGGraph
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

Channel = Literal["w_cum", "w_rec", "both"]
N = len(GRAPH_CATEGORY_UNIVERSE)
F = node_feature_dim()


def _adj_dense(graph: ABRGGraph, channel: Literal["w_cum", "w_rec"]) -> np.ndarray:
    """N×N outgoing-share adjacency for one weight channel; topology requires w_cum>0."""
    cats = list(GRAPH_CATEGORY_UNIVERSE)
    cat_to_idx = {c: i for i, c in enumerate(cats)}
    totals: dict[int, float] = {}
    pairs: list[tuple[int, int, float]] = []
    for (u, v), edge in graph.edges.items():
        if float(edge.w_cum) <= 0.0:
            continue
        if u not in cat_to_idx or v not in cat_to_idx:
            continue
        w = float(getattr(edge, channel))
        ui = cat_to_idx[u]
        vi = cat_to_idx[v]
        totals[ui] = totals.get(ui, 0.0) + w
        pairs.append((ui, vi, w))
    A = np.zeros((N, N), dtype=np.float64)
    for ui, vi, w in pairs:
        denom = totals.get(ui, 0.0)
        A[ui, vi] = (w / denom) if denom > 0.0 else 0.0
    return A


def session_blocks(
    graph: ABRGGraph,
    *,
    channel: Channel,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Returns (node_block [N*F], adj_block flat).
    adj_block is N*N for w_cum|w_rec, or 2*N*N for both (cum then rec).
    Node features always from graph_to_tensors(normalize=True, edge_weight_channel=w_cum)
    so static/dynamic fusion matches Chapter A layout; only adj channel varies.
    """
    x, _, _, _ = graph_to_tensors(graph, normalize=True, edge_weight_channel="w_cum")
    node = x.detach().cpu().numpy().astype(np.float64).reshape(-1)
    if channel == "w_cum":
        adj = _adj_dense(graph, "w_cum").reshape(-1)
    elif channel == "w_rec":
        adj = _adj_dense(graph, "w_rec").reshape(-1)
    elif channel == "both":
        adj = np.concatenate(
            [_adj_dense(graph, "w_cum").reshape(-1), _adj_dense(graph, "w_rec").reshape(-1)]
        )
    else:
        raise ValueError(channel)
    return node, adj


def session_vector(graph: ABRGGraph, *, channel: Channel) -> np.ndarray:
    node, adj = session_blocks(graph, channel=channel)
    return np.concatenate([node, adj])


def mean_reference(vectors: list[np.ndarray]) -> np.ndarray:
    if not vectors:
        raise ValueError("empty reference")
    return np.mean(np.stack(vectors, axis=0), axis=0)


def split_blocks(vec: np.ndarray, *, channel: Channel) -> tuple[np.ndarray, np.ndarray]:
    n_node = N * F
    return vec[:n_node], vec[n_node:]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 and nb == 0.0:
        return 0.0
    if na == 0.0 or nb == 0.0:
        return 1.0
    sim = float(np.dot(a, b) / (na * nb))
    sim = max(-1.0, min(1.0, sim))
    return 1.0 - sim


def _frobenius(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def distances(
    a: np.ndarray,
    b: np.ndarray,
    *,
    channel: Channel,
) -> dict[str, float]:
    """Cosine and Frobenius on combined, node, and adjacency blocks."""
    an, aa = split_blocks(a, channel=channel)
    bn, ba = split_blocks(b, channel=channel)
    return {
        "cosine_combined": _cosine(a, b),
        "frobenius_combined": _frobenius(a, b),
        "cosine_node": _cosine(an, bn),
        "frobenius_node": _frobenius(an, bn),
        "cosine_adj": _cosine(aa, ba),
        "frobenius_adj": _frobenius(aa, ba),
    }


def median_iqr(xs: list[float] | np.ndarray) -> dict[str, float]:
    arr = np.asarray(list(xs), dtype=np.float64)
    if arr.size == 0:
        return {"median": float("nan"), "q1": float("nan"), "q3": float("nan"), "iqr": float("nan"), "n": 0}
    q1, med, q3 = np.percentile(arr, [25, 50, 75])
    return {
        "median": float(med),
        "q1": float(q1),
        "q3": float(q3),
        "iqr": float(q3 - q1),
        "n": int(arr.size),
    }


def pooled_curve_band(
    per_app_curves: dict[str, list[float]],
) -> dict[str, list[float]]:
    """Align by k index (0-based into transitions); median + IQR across apps present at k."""
    if not per_app_curves:
        return {"k": [], "median": [], "q1": [], "q3": []}
    max_len = max(len(v) for v in per_app_curves.values())
    ks: list[float] = []
    meds: list[float] = []
    q1s: list[float] = []
    q3s: list[float] = []
    for i in range(max_len):
        vals = [v[i] for v in per_app_curves.values() if len(v) > i and math.isfinite(v[i])]
        if not vals:
            continue
        q1, med, q3 = np.percentile(vals, [25, 50, 75])
        ks.append(float(i + 1))  # k = number of sessions in R_k
        meds.append(float(med))
        q1s.append(float(q1))
        q3s.append(float(q3))
    return {"k": ks, "median": meds, "q1": q1s, "q3": q3s}
