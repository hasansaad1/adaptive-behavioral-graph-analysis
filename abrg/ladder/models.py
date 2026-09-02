"""Supervised tabular models (Run 3.5 compatible)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, SEED
from abrg.ladder import SEEDS


def fit_supervised(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    *,
    model_name: str,
    seed: int = SEED,
    compute_importance: bool = False,
    names: list[str] | None = None,
) -> dict[str, Any]:
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)

    if model_name == "logistic_regression":
        pipe = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=4000,
                        class_weight="balanced",
                        solver="lbfgs",
                        random_state=seed,
                    ),
                ),
            ]
        )
        pipe.fit(X_train, y_train)
        scores = pipe.predict_proba(X_test)[:, 1].tolist()
        importance = None
        if compute_importance and names:
            from abrg.androct.run_gae_run3_5 import _group_importance, _top_abs

            coef = pipe.named_steps["clf"].coef_.reshape(-1)
            scale = pipe.named_steps["scaler"].scale_
            coef_orig = coef / scale
            importance = {
                "type": "logistic_coefficient",
                "top_abs_coefficients": _top_abs(names, coef_orig, k=40),
                "grouped": _group_importance(names, coef_orig),
            }
    elif model_name == "hist_gradient_boosting":
        clf = HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.08,
            max_iter=300,
            random_state=seed,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
        )
        clf.fit(X_train, y_train)
        scores = clf.predict_proba(X_test)[:, 1].tolist()
        importance = None
        if compute_importance and names:
            from sklearn.inspection import permutation_importance

            from abrg.androct.run_gae_run3_5 import _group_importance, _top_abs

            rng_idx = np.random.default_rng(seed).choice(
                len(X_test), size=min(800, len(X_test)), replace=False
            )
            imp = permutation_importance(
                clf,
                X_test[rng_idx],
                y_test[rng_idx],
                n_repeats=5,
                random_state=seed,
                scoring="roc_auc",
                n_jobs=-1,
            )
            importance = {
                "type": "permutation_importance_auc",
                "top_abs_importances": _top_abs(names, imp.importances_mean, k=40),
                "grouped": _group_importance(names, imp.importances_mean),
            }
    else:
        raise ValueError(model_name)

    auc_block = _auc_with_bootstrap(scores, y_test.tolist())
    out: dict[str, Any] = {
        "model": model_name,
        "seed": seed,
        "auc": auc_block,
        "scores": scores,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "n_train_pos": int(y_train.sum()),
        "n_train_neg": int((1 - y_train).sum()),
    }
    if importance is not None:
        out["importance"] = importance
    return out


def fit_multi_seed_hgb(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
) -> dict[str, Any]:
    aucs: list[float] = []
    runs: list[dict[str, Any]] = []
    for seed in SEEDS:
        r = fit_supervised(
            X_train, y_train, X_test, y_test, model_name="hist_gradient_boosting", seed=seed
        )
        runs.append(r)
        aucs.append(float(r["auc"]["auc_floor"]))
    return {
        "seeds": list(SEEDS),
        "per_seed_auc_floor": aucs,
        "mean_auc_floor": float(np.mean(aucs)),
        "std_auc_floor": float(np.std(aucs)),
        "runs": runs,
    }
