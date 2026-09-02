"""Nested bootstrap for the winning configuration (resample train-benign, refit)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

from abrg.kernels import NESTED_BOOTSTRAP_B, NESTED_BOOTSTRAP_B_FALLBACK
from abrg.kernels._nx import LabelMode, prepare_graphs
from abrg.kernels.detectors import (
    det_centroid_cosine,
    det_centroid_euclidean,
    det_isolation_forest,
    det_knn,
    det_knn_kernel,
    det_lof,
    det_ocsvm_precomputed,
    det_ocsvm_rbf,
)
from abrg.kernels.embeddings import (
    embed_fgsd,
    embed_gl2vec,
    embed_graph2vec,
    embed_netlsd,
)
from abrg.kernels.graph_kernels import fit_propagation, fit_shortest_path, fit_wl


def _detector_scores_emb(
    name: str, X_tr: np.ndarray, X_te: np.ndarray, seed: int
) -> list[float]:
    if name == "ocsvm_rbf":
        return det_ocsvm_rbf(X_tr, X_te, seed=seed)
    if name == "isolation_forest":
        return det_isolation_forest(X_tr, X_te, seed=seed)
    if name == "lof_novelty":
        return det_lof(X_tr, X_te, seed=seed)
    if name == "centroid_euclidean":
        return det_centroid_euclidean(X_tr, X_te)
    if name == "centroid_cosine":
        return det_centroid_cosine(X_tr, X_te)
    if name.startswith("knn_k"):
        k = int(name.split("k")[1])
        return det_knn(X_tr, X_te, k=k)
    raise SystemExit(f"unknown embedding detector {name}")


def _detector_scores_kern(
    name: str, K_tr: np.ndarray, K_et: np.ndarray
) -> list[float]:
    if name == "ocsvm_precomputed":
        return det_ocsvm_precomputed(K_tr, K_et)
    if name.startswith("knn_kernel_k"):
        k = int(name.rsplit("k", 1)[1])
        return det_knn_kernel(K_tr, K_et, k=k)
    raise SystemExit(f"unknown kernel detector {name}")


def nested_bootstrap_winner(
    *,
    tensors: dict[str, dict[str, Any]],
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    kind: str,
    family: str,
    method: str,
    detector: str,
    label_mode: LabelMode,
    naive_ci: list[float],
    B: int | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """
    Resample the 562 train-benign apps with replacement, refit embedding/kernel +
    detector, score fixed eval. Percentile CI on auc_floor.
    """
    B = B or NESTED_BOOTSTRAP_B
    rng = np.random.default_rng(seed)
    eval_ids = test_b + test_m
    labels = [0] * len(test_b) + [1] * len(test_m)
    floors: list[float] = []
    t0 = __import__("time").perf_counter()
    forbidden = test_b + test_m

    # Precompute fixed embeddings when the representation has no fitted params
    pre_X_train: np.ndarray | None = None
    pre_X_eval: np.ndarray | None = None
    if family == "embedding" and method in ("FGSD", "NetLSD"):
        print(f"  [nested] precompute {method} once (no fit params)", flush=True)
        nx_tr, _, _, _ = prepare_graphs(tensors, train, kind=kind, label_mode=label_mode)
        nx_ev, _, _, _ = prepare_graphs(tensors, eval_ids, kind=kind, label_mode=label_mode)
        if method == "FGSD":
            emb0 = embed_fgsd(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            )
        else:
            emb0 = embed_netlsd(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            )
        pre_X_train = emb0.X_train
        pre_X_eval = emb0.X_eval

    # Precompute NX / GraKeL graphs once for methods that refit
    nx_train_all = lab_train_all = gk_train_all = None
    nx_eval_all = lab_eval_all = gk_eval_all = None
    if family == "embedding" and method in ("Graph2Vec", "GL2Vec"):
        print("  [nested] precompute NX graphs once", flush=True)
        nx_train_all, _, lab_train_all, _ = prepare_graphs(
            tensors, train, kind=kind, label_mode=label_mode
        )
        nx_eval_all, _, lab_eval_all, _ = prepare_graphs(
            tensors, eval_ids, kind=kind, label_mode=label_mode
        )
    elif family == "kernel":
        print("  [nested] precompute GraKeL graphs once", flush=True)
        _, gk_train_all, _, _ = prepare_graphs(
            tensors, train, kind=kind, label_mode=label_mode
        )
        _, gk_eval_all, _, _ = prepare_graphs(
            tensors, eval_ids, kind=kind, label_mode=label_mode
        )

    for b in range(B):
        boot_idx = rng.choice(len(train), size=len(train), replace=True)
        boot_train = [train[i] for i in boot_idx]
        try:
            if pre_X_train is not None and pre_X_eval is not None:
                X_tr = pre_X_train[list(boot_idx)]
                scores = _detector_scores_emb(detector, X_tr, pre_X_eval, seed)
            elif family == "embedding":
                assert nx_train_all is not None and nx_eval_all is not None
                nx_tr = [nx_train_all[i] for i in boot_idx]
                lab_tr = [lab_train_all[i] for i in boot_idx]  # type: ignore[index]
                if method == "Graph2Vec":
                    emb = embed_graph2vec(
                        nx_tr,
                        nx_eval_all,
                        lab_tr,
                        lab_eval_all,  # type: ignore[arg-type]
                        train_ids=boot_train,
                        eval_ids=eval_ids,
                        forbidden_ids=forbidden,
                        seed=seed,
                    )
                elif method == "GL2Vec":
                    emb = embed_gl2vec(
                        nx_tr,
                        nx_eval_all,
                        train_ids=boot_train,
                        eval_ids=eval_ids,
                        forbidden_ids=forbidden,
                        seed=seed,
                    )
                else:
                    raise SystemExit(method)
                scores = _detector_scores_emb(detector, emb.X_train, emb.X_eval, seed)
            else:
                assert gk_train_all is not None and gk_eval_all is not None
                gk_tr = [gk_train_all[i] for i in boot_idx]
                if method.startswith("WL_h"):
                    h = int(method.split("h")[1])
                    kr = fit_wl(
                        gk_tr,
                        gk_eval_all,
                        h=h,
                        train_ids=boot_train,
                        forbidden=forbidden,
                        label_mode=label_mode,
                    )
                elif method == "Propagation":
                    kr = fit_propagation(
                        gk_tr,
                        gk_eval_all,
                        train_ids=boot_train,
                        forbidden=forbidden,
                        label_mode=label_mode,
                    )
                elif method == "ShortestPath":
                    kr = fit_shortest_path(
                        gk_tr,
                        gk_eval_all,
                        train_ids=boot_train,
                        forbidden=forbidden,
                        label_mode=label_mode,
                        kind=kind,
                    )
                    if kr.skipped:
                        continue
                else:
                    raise SystemExit(method)
                scores = _detector_scores_kern(detector, kr.K_train, kr.K_eval_train)

            a = float(roc_auc_score(labels, scores))
            floors.append(max(a, 1.0 - a))
        except Exception as e:  # noqa: BLE001
            print(f"  [nested] boot {b} failed: {e}", flush=True)
            continue
        if (b + 1) % 10 == 0:
            print(f"  [nested] {b+1}/{B}", flush=True)

    elapsed = __import__("time").perf_counter() - t0
    used_B = B

    if not floors:
        return {
            "B_requested": B,
            "B_ok": 0,
            "error": "no successful bootstrap replicates",
            "wall_sec": elapsed,
            "fallback_note": f"consider B={NESTED_BOOTSTRAP_B_FALLBACK}",
        }
    arr = np.asarray(floors, dtype=float)
    lo, hi = np.percentile(arr, [2.5, 97.5]).tolist()
    return {
        "B_requested": used_B,
        "B_ok": int(len(floors)),
        "auc_floor_mean": float(arr.mean()),
        "auc_floor_std": float(arr.std()),
        "percentile_ci95": [float(lo), float(hi)],
        "naive_score_resample_ci95": naive_ci,
        "wall_sec": elapsed,
        "family": family,
        "method": method,
        "detector": detector,
        "kind": kind,
        "label_mode": label_mode,
        "fallback_note": (
            f"B={used_B}; fallback B={NESTED_BOOTSTRAP_B_FALLBACK} if infeasible"
        ),
    }
