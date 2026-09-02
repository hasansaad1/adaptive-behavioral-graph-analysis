"""Degeneracy diagnostics, Spearman leak, AUC helpers for OCGTL."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from scipy.stats import spearmanr
from torch import Tensor

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist
from abrg.ocgtl import (
    COLLAPSE_FRAC_THRESHOLD,
    COLLAPSE_SCORE_EPS,
    ENCODER_AGREE_COS_THRESHOLD,
)


def leak_spearman(scores: list[float], apps: list, tensors: dict[str, dict]) -> dict[str, float]:
    def rho(xs: list[float], ys: list[float]) -> float:
        if len(xs) < 3:
            return float("nan")
        r, _ = spearmanr(xs, ys)
        return float(r)

    return {
        "mapped_event_count": rho(scores, [float(getattr(a, "n_mapped", tensors[a.sha256].get("n_mapped", 0))) for a in apps]),
        "total_event_count": rho(scores, [float(getattr(a, "n_events", tensors[a.sha256].get("n_events", 0))) for a in apps]),
        "active_nodes": rho(scores, [float(tensors[a.sha256]["n_active"]) for a in apps]),
        "edge_count": rho(scores, [float(tensors[a.sha256]["n_edges"]) for a in apps]),
        "graph_density": rho(scores, [float(tensors[a.sha256]["density"]) for a in apps]),
        "static_feature_norm": rho(
            scores,
            [
                float(
                    getattr(
                        a,
                        "static_norm",
                        tensors[a.sha256].get("static_slice_norm", tensors[a.sha256].get("static_norm", 0.0)),
                    )
                )
                for a in apps
            ],
        ),
    }


def degeneracy_report(
    *,
    emb: Tensor,
    scores_train: list[float],
    train_losses: list[float],
    mode: str,
) -> dict[str, Any]:
    """
    emb: [N, K, D] for OCGTL/GTL or [N, D] for K1.
    """
    scores = np.asarray(scores_train, dtype=np.float64)
    frac_low = float((scores < COLLAPSE_SCORE_EPS).mean()) if len(scores) else float("nan")
    score_dist = _dist(scores.tolist()) if len(scores) else {}

    flags: list[str] = []
    per_encoder_var: list[dict[str, Any]] = []

    if emb.ndim == 2:
        var_per_dim = emb.var(dim=0, unbiased=False).numpy()
        per_encoder_var.append(
            {
                "encoder": 0,
                "mean_var": float(var_per_dim.mean()),
                "var_per_dim": var_per_dim.tolist(),
            }
        )
        encoder_agree = {"mean_pairwise_cos": float("nan"), "iqr": float("nan"), "n_pairs": 0}
    else:
        n, k, d = emb.shape
        for i in range(k):
            var_per_dim = emb[:, i, :].var(dim=0, unbiased=False).numpy()
            per_encoder_var.append(
                {
                    "encoder": i,
                    "role": "reference" if i == 0 else f"transform_{i}",
                    "mean_var": float(var_per_dim.mean()),
                    "var_per_dim": var_per_dim.tolist(),
                }
            )
        # Pairwise cosine between encoders for the same graph
        cos_vals: list[float] = []
        for i in range(k):
            for j in range(i + 1, k):
                a = F.normalize(emb[:, i, :], p=2, dim=-1)
                b = F.normalize(emb[:, j, :], p=2, dim=-1)
                cos_vals.extend((a * b).sum(dim=-1).tolist())
        arr = np.asarray(cos_vals, dtype=np.float64)
        q1, q3 = (np.percentile(arr, [25, 75]) if len(arr) else (float("nan"), float("nan")))
        encoder_agree = {
            "mean_pairwise_cos": float(np.mean(arr)) if len(arr) else float("nan"),
            "iqr": float(q3 - q1) if len(arr) else float("nan"),
            "n_pairs": int(len(arr)),
        }
        if encoder_agree["mean_pairwise_cos"] >= ENCODER_AGREE_COS_THRESHOLD:
            flags.append("encoder_agreement_collapse")

    if frac_low >= COLLAPSE_FRAC_THRESHOLD:
        flags.append("frac_train_score_lt_1e-6")

    mean_vars = [e["mean_var"] for e in per_encoder_var]
    if mean_vars and max(mean_vars) < 1e-6:
        flags.append("embedding_variance_collapse")

    collapse = len(flags) > 0
    return {
        "mode": mode,
        "per_encoder_variance": per_encoder_var,
        "mean_var_across_encoders": float(np.mean(mean_vars)) if mean_vars else float("nan"),
        "encoder_agreement": encoder_agree,
        "train_score_dist": score_dist,
        "frac_train_score_lt_1e-6": frac_low,
        "train_losses": train_losses,
        "final_to_initial_loss_ratio": (
            float(train_losses[-1] / train_losses[0])
            if train_losses and train_losses[0] != 0
            else float("nan")
        ),
        "collapse_flags": flags,
        "COLLAPSE_DETECTED": collapse,
        "ocgin_compare_frac_train_score_lt_1e-6": frac_low,
    }


def evaluate_partitions(
    scores_train: list[float],
    scores_tb: list[float],
    scores_tm: list[float],
) -> dict[str, Any]:
    labels = [0] * len(scores_tb) + [1] * len(scores_tm)
    scores = scores_tb + scores_tm
    auc = _auc_with_bootstrap(scores, labels)
    inverted = auc.get("direction") == "benign_higher_score"
    return {
        "auc": auc,
        "direction_inverted": inverted,
        "score_distributions": {
            "train_benign": _dist(scores_train),
            "test_benign": _dist(scores_tb),
            "test_malware": _dist(scores_tm),
        },
    }
