"""Node-feature tensors for OCPool (no edges — OCPool ignores topology)."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch

from abrg.apigraph.extract import category_for_callee
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

NODE_FEAT_DIM = 1 + 1 + 1 + len(GRAPH_CATEGORY_UNIVERSE)  # 25
CAT_INDEX = {c: i for i, c in enumerate(GRAPH_CATEGORY_UNIVERSE)}


def _static_global(app: Any) -> np.ndarray:
    n_perm = float(getattr(app, "n_perm", 0) or 0)
    n_comp = float(getattr(app, "n_components", 0) or 0)
    static_norm = float(getattr(app, "static_norm", 0.0) or 0.0)
    n_cats = float(getattr(app, "n_cats_nonzero_static", 0) or 0)
    return np.asarray([n_perm, n_comp, static_norm, n_cats], dtype=np.float32)


def build_ocpool_tensors(
    sequence: list[str],
    vocab: list[str],
    *,
    app: Any,
    onehot: np.ndarray | None = None,
) -> dict[str, Any]:
    """
    Same node features as apigraph construct; no edges.
    Enough for OCPool_mean/max and oov_rate / size floors that don't need edges.
    """
    K = len(vocab)
    index = {c: i for i, c in enumerate(vocab)}
    stream = [index[c] for c in sequence if c in index]
    n_total = len(sequence)
    n_inv = len(stream)
    oov_rate = 1.0 - (n_inv / n_total) if n_total else 1.0

    act_count = np.zeros(K, dtype=np.float64)
    first_pos = np.full(K, -1.0, dtype=np.float64)
    for t, ni in enumerate(stream):
        act_count[ni] += 1.0
        if first_pos[ni] < 0:
            first_pos[ni] = float(t)

    total_act = act_count.sum()
    act_share = act_count / total_act if total_act > 0 else act_count
    active = (act_count > 0).astype(np.float64)
    denom = max(n_inv - 1, 1)
    first_norm = np.zeros(K, dtype=np.float64)
    for i in range(K):
        if first_pos[i] >= 0:
            first_norm[i] = first_pos[i] / denom

    if onehot is None:
        onehot = np.zeros((K, len(GRAPH_CATEGORY_UNIVERSE)), dtype=np.float64)
        for i, callee in enumerate(vocab):
            cat = category_for_callee(callee)
            if cat in CAT_INDEX:
                onehot[i, CAT_INDEX[cat]] = 1.0

    x = np.concatenate(
        [act_share[:, None], active[:, None], first_norm[:, None], onehot],
        axis=1,
    ).astype(np.float32)

    return {
        "x": torch.from_numpy(x),
        "static_global": torch.from_numpy(_static_global(app)),
        "n_active": int(active.sum()),
        "n_inv_events": n_inv,
        "n_total_events": n_total,
        "oov_rate": float(oov_rate),
        "n_edges": 0,
        "density": 0.0,
        "node_feat_dim": NODE_FEAT_DIM,
        "K": K,
    }


def _vocab_onehot(vocab: list[str]) -> np.ndarray:
    K = len(vocab)
    onehot = np.zeros((K, len(GRAPH_CATEGORY_UNIVERSE)), dtype=np.float64)
    for i, callee in enumerate(vocab):
        cat = category_for_callee(callee)
        if cat in CAT_INDEX:
            onehot[i, CAT_INDEX[cat]] = 1.0
    return onehot


def build_many(
    sequences: dict[str, list[str]],
    vocab: list[str],
    by_sha: dict[str, Any],
    shas: list[str],
) -> dict[str, dict[str, Any]]:
    onehot = _vocab_onehot(vocab)
    return {
        sha: build_ocpool_tensors(sequences[sha], vocab, app=by_sha[sha], onehot=onehot)
        for sha in shas
    }
