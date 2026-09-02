"""Tensor vectorization helpers (Run 3.5 compatible)."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from abrg.androct.run_gae_run3_5 import _vectorize
from abrg.features import feature_vector_labels
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

N_NODES = 22
FEAT_NAMES = feature_vector_labels(normalize=True)


def apps_for_shas(shas: list[str], by_sha: dict[str, Any]) -> list[Any]:
    return [by_sha[s] for s in shas]


def vectorize_shas(
    tensors: dict[str, dict[str, Any]],
    shas: list[str],
    by_sha: dict[str, Any],
    *,
    mode: str,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    apps = apps_for_shas(shas, by_sha)
    X, y, names, _ = _vectorize(tensors, apps, mode=mode)
    return X, y, names


def malware_full_vectors(
    tensors: dict[str, dict[str, Any]],
    malware_shas: list[str],
    *,
    mode: str = "full",
) -> np.ndarray:
  rows: list[np.ndarray] = []
  for sha in malware_shas:
      t = tensors[sha]
      x = t["x"].detach().cpu().numpy().astype(np.float64).reshape(-1)
      if mode == "node_only":
          rows.append(x)
      elif mode == "full":
          from abrg.androct.run_gae_run3_5 import _adj_matrix

          A = _adj_matrix(t["edge_index"], t["edge_weight"]).reshape(-1)
          rows.append(np.concatenate([x, A]))
      else:
          from abrg.androct.run_gae_run3_5 import _adj_matrix

          A = _adj_matrix(t["edge_index"], t["edge_weight"]).reshape(-1)
          rows.append(A)
  return np.stack(rows, axis=0)


def top_node_feature_deltas(
    tensors: dict[str, dict[str, Any]],
    cluster_shas: list[str],
    global_mean_nodes: np.ndarray,
    k: int = 10,
) -> list[dict[str, Any]]:
    """global_mean_nodes: (22, 10) mean node feature tensor."""
    if not cluster_shas:
        return []
    stack = np.stack(
        [tensors[s]["x"].detach().cpu().numpy().astype(np.float64) for s in cluster_shas],
        axis=0,
    )
    cluster_mean = stack.mean(axis=0).reshape(-1)
    delta = cluster_mean - global_mean_nodes.reshape(-1)
    idx = np.argsort(np.abs(delta))[::-1][:k]
    out: list[dict[str, Any]] = []
    for i in idx:
        node_i = i // len(FEAT_NAMES)
        feat_i = i % len(FEAT_NAMES)
        cat = GRAPH_CATEGORY_UNIVERSE[node_i]
        feat = FEAT_NAMES[feat_i]
        out.append(
            {
                "node": cat,
                "feature": feat,
                "cluster_mean": float(cluster_mean[i]),
                "global_mean": float(global_mean_nodes.reshape(-1)[i]),
                "delta": float(delta[i]),
            }
        )
    return out


def cosine_leakage(
    hold_shas: list[str],
    train_malware_shas: list[str],
    tensors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not hold_shas or not train_malware_shas:
        return {
            "mean_pairwise_cosine": float("nan"),
            "per_holdout_mean_max_cosine": float("nan"),
            "n_hold": len(hold_shas),
            "n_train_malware": len(train_malware_shas),
        }
    X_h = malware_full_vectors(tensors, hold_shas, mode="full")
    X_t = malware_full_vectors(tensors, train_malware_shas, mode="full")
    X_h = np.nan_to_num(X_h, nan=0.0)
    X_t = np.nan_to_num(X_t, nan=0.0)
    # row normalize
    def _norm(M: np.ndarray) -> np.ndarray:
        n = np.linalg.norm(M, axis=1, keepdims=True)
        n = np.where(n == 0, 1.0, n)
        return M / n

    H = _norm(X_h)
    T = _norm(X_t)
    sim = H @ T.T
    per_hold_max = sim.max(axis=1)
    return {
        "mean_pairwise_cosine": float(sim.mean()),
        "per_holdout_mean_max_cosine": float(per_hold_max.mean()),
        "per_holdout_max_cosine": per_hold_max.tolist(),
        "n_hold": len(hold_shas),
        "n_train_malware": len(train_malware_shas),
    }
