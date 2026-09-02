"""Nested bootstrap for winning GLocalKD config."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score
import torch

from abrg.glocalkd import BATCH_SIZE, EPOCHS, NESTED_B
from abrg.glocalkd.data import make_loader
from abrg.glocalkd.models import Pooling
from abrg.glocalkd.score import score_graphs
from abrg.glocalkd.train import LossMode, train_glocalkd


def nested_bootstrap(
    *,
    tensors: dict[str, dict[str, Any]],
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    in_dim: int,
    pooling: Pooling,
    loss_mode: LossMode,
    score_variant: str,
    naive_ci: list[float],
    B: int | None = None,
    epochs: int = EPOCHS,
    seed: int = 42,
    device: torch.device | None = None,
) -> dict[str, Any]:
    B = B or NESTED_B
    device = device or torch.device("cpu")
    rng = np.random.default_rng(seed)
    eval_ids = test_b + test_m
    labels = [0] * len(test_b) + [1] * len(test_m)
    eval_loader = make_loader(tensors, eval_ids, batch_size=BATCH_SIZE, shuffle=False)
    floors: list[float] = []
    t0 = __import__("time").perf_counter()

    for b in range(B):
        print(f"  [nested] start boot {b+1}/{B}", flush=True)
        boot_idx = rng.choice(len(train), size=len(train), replace=True)
        boot_train = [train[i] for i in boot_idx]
        try:
            target, predictor, *_ = train_glocalkd(
                tensors=tensors,
                train_shas=boot_train,
                in_dim=in_dim,
                pooling=pooling,
                seed=seed + b,
                loss_mode=loss_mode,
                epochs=epochs,
                trained=True,
                device=device,
            )
            scored = score_graphs(
                target, predictor, eval_loader, device, shas_in_order=eval_ids
            )
            scores = scored[score_variant]
            a = float(roc_auc_score(labels, scores))
            floors.append(max(a, 1.0 - a))
        except Exception as e:  # noqa: BLE001
            print(f"  [nested] boot {b} failed: {e}", flush=True)
            continue
        if (b + 1) % 10 == 0:
            print(f"  [nested] {b+1}/{B}", flush=True)

    elapsed = __import__("time").perf_counter() - t0
    if not floors:
        return {"B_requested": B, "B_ok": 0, "error": "no replicates", "wall_sec": elapsed}
    arr = np.asarray(floors, dtype=float)
    lo, hi = np.percentile(arr, [2.5, 97.5]).tolist()
    return {
        "B_requested": B,
        "B_ok": int(len(floors)),
        "auc_floor_mean": float(arr.mean()),
        "auc_floor_std": float(arr.std()),
        "percentile_ci95": [float(lo), float(hi)],
        "naive_score_resample_ci95": naive_ci,
        "wall_sec": elapsed,
        "pooling": pooling,
        "loss_mode": loss_mode,
        "score_variant": score_variant,
        "epochs": epochs,
    }
