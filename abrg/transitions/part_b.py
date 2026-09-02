"""Part B — one-class battery on proximity transition features."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.transitions import PCA_COMPONENTS, REF, SEEDS
from abrg.transitions.detectors import (
    eval_scores,
    fit_pca_train_only,
    score_centroid_cosine,
    score_centroid_euclidean,
    score_isolation_forest,
    score_knn,
    score_mahalanobis,
    score_ocsvm,
    transform_pair,
)
from abrg.transitions.features import (
    F4_DEF,
    FEATURE_DIMS,
    FEATURE_KINDS,
    covariates,
    matrix_for_apps,
)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _mean_std(vals: list[float]) -> dict[str, Any]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(arr)) if len(arr) else float("nan"),
        "std": float(np.nanstd(arr, ddof=0)) if len(arr) else float("nan"),
        "values": [float(v) for v in vals],
    }


def _run_detector_battery(
    *,
    tag: str,
    X_tr: np.ndarray,
    X_tb: np.ndarray,
    X_tm: np.ndarray,
    cov_te: dict[str, list[float]],
    out_dir: Path,
) -> dict[str, Any]:
    X_te = np.vstack([X_tb, X_tm])
    labels = [0] * len(X_tb) + [1] * len(X_tm)
    results: dict[str, Any] = {"tag": tag, "n_features": int(X_tr.shape[1])}

    # Stochastic: OCSVM, IF — 5 seeds
    for name, fn in (
        ("ocsvm_rbf", score_ocsvm),
        ("isolation_forest", score_isolation_forest),
    ):
        per_seed = []
        for seed in SEEDS:
            scores = fn(X_tr, X_te, seed=seed)
            row = eval_scores(scores, labels, cov_te)
            row["seed"] = seed
            per_seed.append(row)
            _write_json(out_dir / f"{tag}__{name}__seed{seed}.json", row)
        results[name] = {
            "stochastic": True,
            "seeds": list(SEEDS),
            "auc_floor": _mean_std([r["auc"]["auc_floor"] for r in per_seed]),
            "directions": [r["auc"]["direction"] for r in per_seed],
            "per_seed": per_seed,
        }

    # Deterministic
    for name, scores in (
        ("centroid_euclidean", score_centroid_euclidean(X_tr, X_te)),
        ("centroid_cosine", score_centroid_cosine(X_tr, X_te)),
        ("mahalanobis_ledoit_wolf", score_mahalanobis(X_tr, X_te)),
        ("knn_k1", score_knn(X_tr, X_te, k=1)),
        ("knn_k5", score_knn(X_tr, X_te, k=5)),
        ("knn_k20", score_knn(X_tr, X_te, k=20)),
    ):
        row = eval_scores(scores, labels, cov_te)
        row["stochastic"] = False
        results[name] = row
        _write_json(out_dir / f"{tag}__{name}.json", row)

    return results


def run_part_b(
    *,
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    out_dir: Path,
    tensors: dict[str, dict[str, Any]] | None = None,
    tag_prefix: str = "prox",
) -> dict[str, Any]:
    """
    If tensors is None, load run2 corpus cache (proximity 22-node).
    tag_prefix distinguishes proximity vs invocation matrices.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if tensors is None:
        bundle = load_corpus_cache(androct_run2_output_dir())
        tensors = bundle.tensors

    cov_te = covariates(tensors, test_b + test_m)
    summary: dict[str, Any] = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tag_prefix": tag_prefix,
        "F4_definition": F4_DEF,
        "feature_dims": FEATURE_DIMS,
        "references": REF,
        "pca_integrity": "PCA and scalers fit on train-benign only; test never used in fit",
        "configs": {},
    }

    # Base feature kinds
    for kind in FEATURE_KINDS:
        print(f"[transitions/B] {tag_prefix} {kind} …", flush=True)
        X_tr = matrix_for_apps(tensors, train_shas, kind)
        X_tb = matrix_for_apps(tensors, test_b, kind)
        X_tm = matrix_for_apps(tensors, test_m, kind)
        tag = f"{tag_prefix}__{kind}"
        cfg = _run_detector_battery(
            tag=tag,
            X_tr=X_tr,
            X_tb=X_tb,
            X_tm=X_tm,
            cov_te=cov_te,
            out_dir=out_dir,
        )
        cfg["feature"] = kind
        cfg["dim"] = FEATURE_DIMS[kind]
        cfg["reduction"] = None
        summary["configs"][tag] = cfg

        # PCA on F1 and F3 only
        if kind in ("F1_adj_only", "F3_full"):
            for nc in PCA_COMPONENTS:
                print(f"[transitions/B] {tag_prefix} {kind} PCA={nc} …", flush=True)
                pca, pca_meta = fit_pca_train_only(X_tr, nc)
                # assert test not in fit — already true by construction
                X_tr_p, X_tb_p = transform_pair(X_tr, X_tb, pca)
                _, X_tm_p = transform_pair(X_tr, X_tm, pca)
                tag_p = f"{tag_prefix}__{kind}__pca{nc}"
                cfg_p = _run_detector_battery(
                    tag=tag_p,
                    X_tr=X_tr_p,
                    X_tb=X_tb_p,
                    X_tm=X_tm_p,
                    cov_te=cov_te,
                    out_dir=out_dir,
                )
                cfg_p["feature"] = kind
                cfg_p["dim"] = int(X_tr_p.shape[1])
                cfg_p["reduction"] = f"pca_{nc}"
                cfg_p["pca"] = pca_meta
                summary["configs"][tag_p] = cfg_p
                _write_json(out_dir / f"{tag_p}__pca_meta.json", pca_meta)

    # Gate table: which clear 0.7025 and 0.7765
    gate_rows = []
    for tag, cfg in summary["configs"].items():
        for det in (
            "ocsvm_rbf",
            "isolation_forest",
            "centroid_euclidean",
            "centroid_cosine",
            "mahalanobis_ledoit_wolf",
            "knn_k1",
            "knn_k5",
            "knn_k20",
        ):
            block = cfg[det]
            if det in ("ocsvm_rbf", "isolation_forest"):
                floor = float(block["auc_floor"]["mean"])
                direction = (
                    block["directions"][0] if block.get("directions") else "mixed"
                )
            else:
                floor = float(block["auc"]["auc_floor"])
                direction = block["auc"]["direction"]
            gate_rows.append(
                {
                    "tag": tag,
                    "detector": det,
                    "auc_floor": floor,
                    "direction": direction,
                    "clears_size_floor_0.7025": floor > REF["highest_size_floor_mapped"],
                    "clears_OCPool_mean_0.7765": floor > REF["OCPool_mean"],
                }
            )
    summary["gate_rows"] = gate_rows
    summary["n_clear_size_floor"] = sum(1 for r in gate_rows if r["clears_size_floor_0.7025"])
    summary["n_clear_ocpool"] = sum(1 for r in gate_rows if r["clears_OCPool_mean_0.7765"])
    # best overall
    best = max(gate_rows, key=lambda r: r["auc_floor"])
    summary["best"] = best
    _write_json(out_dir / "partB_summary.json", summary)
    print(
        f"[transitions/B] done best={best['tag']}::{best['detector']} "
        f"floor={best['auc_floor']:.4f} clear_size={summary['n_clear_size_floor']} "
        f"clear_ocpool={summary['n_clear_ocpool']}",
        flush=True,
    )
    return summary
