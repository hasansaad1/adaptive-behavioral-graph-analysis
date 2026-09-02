"""Assemble node feature matrix X and GAE tensors (v0.2.1 normalization at tensor-build time)."""

from __future__ import annotations

import math

import numpy as np
import torch

from abrg.graph import ABRGGraph
from abrg.registry import GRAPH_CATEGORY_UNIVERSE, GATE_V_DIM


def node_feature_dim() -> int:
    # s_v, declared_v, gate_v[GATE_V_DIM], reach_v, epoch_v, act_v, sess_v, rec_v
    return 4 + GATE_V_DIM + 3


def feature_vector_labels(*, normalize: bool = True) -> list[str]:
    act_label = "act_v_frac" if normalize else "act_v_log"
    labels = ["s_v", "declared_v"]
    labels.extend(f"gate_v[{i}]" for i in range(GATE_V_DIM))
    labels.extend(["reach_v", "epoch_v", act_label, "sess_v", "rec_v"])
    return labels


def _act_fractions(graph: ABRGGraph, categories: list[str]) -> np.ndarray:
    """v0.2.1: fraction of total events per node (replaces log1p for GAE input)."""
    counts = np.array([graph.nodes[c].act_count for c in categories], dtype=np.float64)
    total = counts.sum()
    if total <= 0.0:
        return np.zeros(len(categories), dtype=np.float32)
    return (counts / total).astype(np.float32)


def _act_log1p(graph: ABRGGraph, categories: list[str]) -> np.ndarray:
    """Pre-v0.2.1: log1p(act_count) fed to GAE."""
    return np.array(
        [math.log1p(graph.nodes[c].act_count) for c in categories],
        dtype=np.float32,
    )


def _outgoing_weight_totals(
    graph: ABRGGraph,
    cat_to_idx: dict[str, int],
    *,
    weight_attr: str = "w_cum",
) -> dict[int, float]:
    totals: dict[int, float] = {}
    for (u, v), edge in graph.edges.items():
        if u not in cat_to_idx or v not in cat_to_idx:
            continue
        w = float(getattr(edge, weight_attr))
        if w <= 0.0:
            continue
        ui = cat_to_idx[u]
        totals[ui] = totals.get(ui, 0.0) + w
    return totals


def _edge_tensors(
    graph: ABRGGraph,
    cat_to_idx: dict[str, int],
    *,
    normalize: bool,
    edge_weight_channel: str = "w_cum",
) -> tuple[list[int], list[int], list[float]]:
    """
    Edge structure from stored raw weights (w_cum by default).
    normalize=True  → edge_weight = transition probability per source (v0.2.1)
    normalize=False → edge_weight = raw channel weight (pre-v0.2.1)
    edge_weight_channel: "w_cum" (default) or "w_rec" — structure still requires w_cum>0.
    """
    if edge_weight_channel not in ("w_cum", "w_rec"):
        raise ValueError(f"edge_weight_channel must be w_cum|w_rec, got {edge_weight_channel!r}")
    out_totals = (
        _outgoing_weight_totals(graph, cat_to_idx, weight_attr=edge_weight_channel)
        if normalize
        else {}
    )
    src: list[int] = []
    dst: list[int] = []
    weights: list[float] = []
    for (u, v), edge in graph.edges.items():
        # Structure always from w_cum>0 so topology matches origin graphs.
        if float(edge.w_cum) <= 0.0:
            continue
        if u not in cat_to_idx or v not in cat_to_idx:
            continue
        w = float(getattr(edge, edge_weight_channel))
        ui = cat_to_idx[u]
        if normalize:
            total_out = out_totals.get(ui, 0.0)
            weight = (w / total_out) if total_out > 0.0 else 0.0
        else:
            weight = w
        src.append(ui)
        dst.append(cat_to_idx[v])
        weights.append(weight)
    return src, dst, weights


def graph_to_tensors(
    graph: ABRGGraph,
    *,
    normalize: bool = True,
    edge_weight_channel: str = "w_cum",
    categories: list[str] | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, list[str]]:
    """
    Build GAE inputs from a graph. Stored graph values remain raw; feeding transform is here only.

    Args:
        normalize: If True (v0.2.1), feed act_v as event fraction and edges as transition
            probabilities. If False (pre-v0.2.1 A/B), feed act_v as log1p(act_count) and
            edge_weight as raw channel weight.
        edge_weight_channel: "w_cum" (default) or "w_rec" for encoder edge weights.
        categories: ordered node labels (default: full GRAPH_CATEGORY_UNIVERSE). Pass a
            subset to temporarily drop never-active categories from the GAE tensor.

    Returns:
        x: [N, F] node features
        edge_index: [2, E] directed edges (structure)
        edge_weight: [E] fed weights (probs or raw)
        categories: ordered node labels matching row index
    """
    categories = list(categories) if categories is not None else list(GRAPH_CATEGORY_UNIVERSE)
    n = len(categories)
    f_dim = node_feature_dim()
    x = np.zeros((n, f_dim), dtype=np.float32)
    cat_to_idx = {c: i for i, c in enumerate(categories)}
    act_vals = _act_fractions(graph, categories) if normalize else _act_log1p(graph, categories)

    for i, cat in enumerate(categories):
        node = graph.nodes[cat]
        offset = 0
        x[i, offset] = node.s_v
        offset += 1
        x[i, offset] = node.declared_v
        offset += 1
        for g in range(GATE_V_DIM):
            x[i, offset + g] = node.gate_v[g]
        offset += GATE_V_DIM
        x[i, offset] = node.reach_v
        offset += 1
        x[i, offset] = node.epoch_v
        offset += 1
        x[i, offset] = act_vals[i]
        offset += 1
        x[i, offset] = node.sess_v
        offset += 1
        x[i, offset] = node.rec_v

    src, dst, weights = _edge_tensors(
        graph, cat_to_idx, normalize=normalize, edge_weight_channel=edge_weight_channel
    )
    if src:
        edge_index = torch.tensor([src, dst], dtype=torch.long)
        edge_weight = torch.tensor(weights, dtype=torch.float32)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)
        edge_weight = torch.zeros(0, dtype=torch.float32)

    return torch.tensor(x, dtype=torch.float32), edge_index, edge_weight, categories


def categories_active_in_corpus(records) -> list[str]:
    """Universe categories that appear with act_count>0 on at least one record graph."""
    seen: set[str] = set()
    for rec in records:
        if rec.graph is None:
            continue
        for cat, node in rec.graph.nodes.items():
            if node.act_count > 0:
                seen.add(cat)
    return [c for c in GRAPH_CATEGORY_UNIVERSE if c in seen]


def snapshot_raw_w_cum(graph: ABRGGraph) -> dict[tuple[str, str], float]:
    """Copy stored w_cum for stored-vs-fed verification (graph must not be mutated by tensorization)."""
    return {(u, v): float(e.w_cum) for (u, v), e in graph.edges.items()}
