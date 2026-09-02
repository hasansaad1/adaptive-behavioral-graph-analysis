"""Degeneracy diagnostics for GLocalKD."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
from torch_geometric.loader import DataLoader

from abrg.glocalkd import (
    FRAC_NEAR_ZERO_MAX,
    LOSS_RATIO_DEGENERATE,
    PREDICTOR_VAR_MEAN_MIN,
    TARGET_VAR_MEAN_MIN,
)
from abrg.glocalkd.models import GLocalGCN


def _dist(xs: list[float] | np.ndarray) -> dict[str, float]:
    arr = np.asarray(xs, dtype=float)
    if arr.size == 0:
        return {
            "median": float("nan"),
            "iqr": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "mean": float("nan"),
        }
    q1, med, q3 = np.percentile(arr, [25, 50, 75]).tolist()
    return {
        "median": float(med),
        "iqr": float(q3 - q1),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
    }


@torch.no_grad()
def representation_variance(
    model: GLocalGCN,
    loader: DataLoader,
    device: torch.device,
) -> dict[str, Any]:
    """Variance per dim of graph embeddings on loader; mean across dims."""
    model.eval()
    hs: list[torch.Tensor] = []
    for batch in loader:
        batch = batch.to(device)
        _, h = model(batch.x, batch.edge_index, batch.batch)
        hs.append(h.cpu())
    if not hs:
        return {"var_per_dim": [], "var_mean": float("nan"), "n": 0}
    H = torch.cat(hs, dim=0).numpy()
    var = H.var(axis=0)
    return {
        "var_per_dim": [float(v) for v in var.tolist()],
        "var_mean": float(var.mean()),
        "n": int(H.shape[0]),
        "emb_dim": int(H.shape[1]),
    }


@torch.no_grad()
def train_score_distribution(
    target: GLocalGCN,
    predictor: GLocalGCN,
    loader: DataLoader,
    device: torch.device,
) -> dict[str, Any]:
    from abrg.glocalkd.score import score_graphs

    out = score_graphs(target, predictor, loader, device)
    scores = out["s_graph"]
    frac_near_zero = float(np.mean(np.asarray(scores) < 1e-6)) if scores else float("nan")
    return {
        "s_graph_dist": _dist(scores),
        "frac_score_below_1e-6": frac_near_zero,
        "n": len(scores),
    }


def diagnose(
    *,
    target: GLocalGCN,
    predictor: GLocalGCN,
    train_loader: DataLoader,
    loss_curve: list[float],
    device: torch.device,
) -> dict[str, Any]:
    tgt_var = representation_variance(target, train_loader, device)
    pred_var = representation_variance(predictor, train_loader, device)
    score_dist = train_score_distribution(target, predictor, train_loader, device)

    if loss_curve:
        initial = float(loss_curve[0])
        final = float(loss_curve[-1])
        ratio = final / initial if initial > 0 else float("nan")
    else:
        initial = final = ratio = float("nan")

    flags = {
        "target_near_constant": bool(
            not np.isnan(tgt_var["var_mean"]) and tgt_var["var_mean"] < TARGET_VAR_MEAN_MIN
        ),
        "predictor_near_constant": bool(
            not np.isnan(pred_var["var_mean"]) and pred_var["var_mean"] < PREDICTOR_VAR_MEAN_MIN
        ),
        "loss_collapsed": bool(
            loss_curve and not np.isnan(ratio) and ratio < LOSS_RATIO_DEGENERATE
        ),
        "too_many_near_zero_train_scores": bool(
            score_dist["frac_score_below_1e-6"] > FRAC_NEAR_ZERO_MAX
        ),
    }
    degenerate = any(flags.values())
    return {
        "target_repr": tgt_var,
        "predictor_repr": pred_var,
        "train_s_graph": score_dist,
        "loss": {
            "initial": initial,
            "final": final,
            "ratio_final_over_initial": ratio,
            "curve": loss_curve,
        },
        "flags": flags,
        "DEGENERATE": degenerate,
        "thresholds": {
            "TARGET_VAR_MEAN_MIN": TARGET_VAR_MEAN_MIN,
            "PREDICTOR_VAR_MEAN_MIN": PREDICTOR_VAR_MEAN_MIN,
            "LOSS_RATIO_DEGENERATE": LOSS_RATIO_DEGENERATE,
            "FRAC_NEAR_ZERO_MAX": FRAC_NEAR_ZERO_MAX,
        },
    }
