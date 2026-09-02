"""Graph kernels via GraKeL — fit on train-benign Gram only; score with eval×train."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from abrg.kernels._grakel_shim import Propagation, ShortestPath, WeisfeilerLehman

LabelTag = Literal["identity_or_argmax", "degree"]


@dataclass
class KernelResult:
    name: str
    K_train: np.ndarray  # (n_train, n_train)
    K_eval_train: np.ndarray  # (n_eval, n_train)
    wall_sec: float
    skipped: bool = False
    skip_reason: str = ""
    failures: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    label_mode: str = ""


def _assert_fit_scope(train_ids: list[str], forbidden: list[str]) -> None:
    if set(train_ids) & set(forbidden):
        raise SystemExit("STOP: forbidden IDs in kernel fit set")


def fit_wl(
    train_graphs: list[Any],
    eval_graphs: list[Any],
    *,
    h: int,
    train_ids: list[str],
    forbidden: list[str],
    label_mode: str,
) -> KernelResult:
    _assert_fit_scope(train_ids, forbidden)
    t0 = time.perf_counter()
    # base kernel is VertexHistogram by default inside WeisfeilerLehman
    kern = WeisfeilerLehman(n_iter=h, normalize=True)
    K_tr = np.asarray(kern.fit_transform(train_graphs), dtype=np.float64)
    K_et = np.asarray(kern.transform(eval_graphs), dtype=np.float64)
    assert K_tr.shape == (len(train_graphs), len(train_graphs))
    assert K_et.shape == (len(eval_graphs), len(train_graphs))
    return KernelResult(
        name=f"WL_h{h}",
        K_train=K_tr,
        K_eval_train=K_et,
        wall_sec=time.perf_counter() - t0,
        notes="GraKeL WeisfeilerLehman; Gram = train×train fit, eval×train score (never eval×eval)",
        label_mode=label_mode,
    )


def fit_propagation(
    train_graphs: list[Any],
    eval_graphs: list[Any],
    *,
    train_ids: list[str],
    forbidden: list[str],
    label_mode: str,
    t_max: int = 5,
) -> KernelResult:
    _assert_fit_scope(train_ids, forbidden)
    t0 = time.perf_counter()
    kern = Propagation(t_max=t_max, normalize=True)
    K_tr = np.asarray(kern.fit_transform(train_graphs), dtype=np.float64)
    K_et = np.asarray(kern.transform(eval_graphs), dtype=np.float64)
    return KernelResult(
        name="Propagation",
        K_train=K_tr,
        K_eval_train=K_et,
        wall_sec=time.perf_counter() - t0,
        notes=f"GraKeL Propagation t_max={t_max}; train×train / eval×train",
        label_mode=label_mode,
    )


def fit_shortest_path(
    train_graphs: list[Any],
    eval_graphs: list[Any],
    *,
    train_ids: list[str],
    forbidden: list[str],
    label_mode: str,
    kind: str,
) -> KernelResult:
    """Skip on T1K (K=1000) — cubic in nodes × graphs is intractable."""
    if kind == "T1K":
        return KernelResult(
            name="ShortestPath",
            K_train=np.zeros((0, 0)),
            K_eval_train=np.zeros((0, 0)),
            wall_sec=0.0,
            skipped=True,
            skip_reason="skipped on T1K (K=1000): shortest-path kernel not tractable",
            label_mode=label_mode,
        )
    _assert_fit_scope(train_ids, forbidden)
    t0 = time.perf_counter()
    try:
        kern = ShortestPath(normalize=True, with_labels=True)
        K_tr = np.asarray(kern.fit_transform(train_graphs), dtype=np.float64)
        K_et = np.asarray(kern.transform(eval_graphs), dtype=np.float64)
    except Exception as e:  # noqa: BLE001
        return KernelResult(
            name="ShortestPath",
            K_train=np.zeros((0, 0)),
            K_eval_train=np.zeros((0, 0)),
            wall_sec=time.perf_counter() - t0,
            skipped=True,
            skip_reason=f"ShortestPath failed on this corpus: {type(e).__name__}: {e}",
            label_mode=label_mode,
        )
    return KernelResult(
        name="ShortestPath",
        K_train=K_tr,
        K_eval_train=K_et,
        wall_sec=time.perf_counter() - t0,
        notes="GraKeL ShortestPath with_labels=True; T22 only",
        label_mode=label_mode,
    )
