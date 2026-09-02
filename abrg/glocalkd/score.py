"""Anomaly scores and AUC reporting."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import torch
from scipy.stats import spearmanr
from torch_geometric.loader import DataLoader

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.glocalkd import OCPOOL_MEAN_RAW, SIZE_FLOOR
from abrg.glocalkd.models import GLocalGCN

ScoreVariant = Literal["s_graph", "mean_s_node", "max_s_node", "s_graph_plus_mean_node"]


def _rho(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    r, _ = spearmanr(xs, ys)
    return float(r)


def leak_spearman(scores: list[float], cov: dict[str, list[float]]) -> dict[str, float]:
    return {k: _rho(scores, v) for k, v in cov.items()}


@torch.no_grad()
def score_graphs(
    target: GLocalGCN,
    predictor: GLocalGCN,
    loader: DataLoader,
    device: torch.device,
    *,
    shas_in_order: list[str] | None = None,
) -> dict[str, Any]:
    """
    Per-graph scores (loader must be shuffle=False; order matches shas_in_order).
    s_graph = mean_dim ||h - hhat||^2
    s_node_i = mean_dim ||z_i - zhat_i||^2
    """
    target.eval()
    predictor.eval()
    s_graph: list[float] = []
    mean_node: list[float] = []
    max_node: list[float] = []
    combined: list[float] = []
    per_graph_node_scores: list[np.ndarray] = []

    for batch in loader:
        batch = batch.to(device)
        z_t, h_t = target(batch.x, batch.edge_index, batch.batch)
        z_s, h_s = predictor(batch.x, batch.edge_index, batch.batch)
        node_sq = ((z_s - z_t) ** 2).mean(dim=-1)
        graph_sq = ((h_s - h_t) ** 2).mean(dim=-1)

        batch_idx = batch.batch.cpu().numpy()
        node_sq_np = node_sq.cpu().numpy()
        n_graphs = int(batch.num_graphs)
        for g in range(n_graphs):
            mask = batch_idx == g
            ns = node_sq_np[mask]
            per_graph_node_scores.append(ns.copy())
            mn = float(ns.mean()) if len(ns) else 0.0
            mx = float(ns.max()) if len(ns) else 0.0
            sg = float(graph_sq[g].item())
            s_graph.append(sg)
            mean_node.append(mn)
            max_node.append(mx)
            combined.append(sg + mn)

    shas = list(shas_in_order) if shas_in_order is not None else []
    if shas and len(shas) != len(s_graph):
        raise RuntimeError(f"sha/score length mismatch {len(shas)} vs {len(s_graph)}")

    return {
        "s_graph": s_graph,
        "mean_s_node": mean_node,
        "max_s_node": max_node,
        "s_graph_plus_mean_node": combined,
        "per_graph_node_scores": per_graph_node_scores,
        "shas": shas,
    }


def eval_scores(
    scores: list[float],
    labels: list[int],
    cov: dict[str, list[float]],
) -> dict[str, Any]:
    auc = _auc_with_bootstrap(scores, labels)
    floor = float(auc["auc_floor"])
    return {
        "auc": auc,
        "leak_spearman": leak_spearman(scores, cov),
        "gate": {
            "clears_size_floor_0.7025": bool(floor > SIZE_FLOOR),
            "clears_OCPool_mean_0.7765": bool(floor > OCPOOL_MEAN_RAW),
            "is_result": bool(floor > SIZE_FLOOR),
        },
        "inverted": bool(auc.get("direction") == "benign_higher_score"),
    }
