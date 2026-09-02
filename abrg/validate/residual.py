"""OCPool scoring + oov residualization variants R0–R3."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.svm import OneClassSVM

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist

PoolName = Literal["mean", "max", "add"]


def pool_x(t: dict[str, Any], pool: PoolName) -> np.ndarray:
    x = t["x"].detach().cpu().numpy()
    if pool == "add":
        v = x.sum(axis=0)
    elif pool == "mean":
        v = x.mean(axis=0)
    else:
        v = x.max(axis=0)
    return np.concatenate([v, t["static_global"].detach().cpu().numpy()])


def fit_ocpool(
    tensors: dict[str, dict[str, Any]],
    train_shas: list[str],
    *,
    pool: PoolName = "mean",
) -> OneClassSVM:
    X_tr = np.stack([pool_x(tensors[s], pool) for s in train_shas])
    return OneClassSVM(kernel="rbf", nu=0.1, gamma="scale").fit(X_tr)


def score_apps(
    clf: OneClassSVM,
    tensors: dict[str, dict[str, Any]],
    shas: list[str],
    *,
    pool: PoolName = "mean",
) -> list[float]:
    X = np.stack([pool_x(tensors[s], pool) for s in shas])
    return (-clf.decision_function(X)).tolist()


def ols_fit(scores: list[float], oov: list[float]) -> tuple[LinearRegression, dict[str, float]]:
    y = np.asarray(scores, dtype=np.float64)
    x = np.asarray(oov, dtype=np.float64).reshape(-1, 1)
    mask = np.isfinite(y) & np.isfinite(x.ravel())
    reg = LinearRegression().fit(x[mask], y[mask])
    meta = {
        "coef_intercept": float(reg.intercept_),
        "coef_oov": float(reg.coef_[0]),
        "r2": float(reg.score(x[mask], y[mask])),
        "n_fit": int(mask.sum()),
    }
    return reg, meta


def apply_residual(reg: LinearRegression, scores: list[float], oov: list[float]) -> list[float]:
    y = np.asarray(scores, dtype=np.float64)
    x = np.asarray(oov, dtype=np.float64).reshape(-1, 1)
    return (y - reg.predict(x)).tolist()


def residual_block(
    scores: list[float],
    labels: list[int],
    *,
    name: str,
    ols_meta: dict[str, float] | None = None,
) -> dict[str, Any]:
    auc = _auc_with_bootstrap(scores, labels)
    out: dict[str, Any] = {
        "name": name,
        "auc": auc,
        "score_dist": _dist(scores),
    }
    if ols_meta is not None:
        out.update(ols_meta)
    return out


def check1_residualization(
    tensors: dict[str, dict[str, Any]],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    *,
    pool: PoolName = "mean",
) -> dict[str, Any]:
    """
    R0: raw OCPool scores on eval
    R1: OLS score~oov fit on EVAL, residual on eval (leaky; reproduces 0.8141)
    R2: OLS fit on TRAIN-BENIGN scores~oov, apply to eval (honest)
    R3: same as R2 + residual distribution compare train vs eval
    """
    clf = fit_ocpool(tensors, train_shas, pool=pool)
    sc_tr = score_apps(clf, tensors, train_shas, pool=pool)
    sc_tb = score_apps(clf, tensors, test_b, pool=pool)
    sc_tm = score_apps(clf, tensors, test_m, pool=pool)
    sc_te = sc_tb + sc_tm
    labels = [0] * len(test_b) + [1] * len(test_m)

    oov_tr = [float(tensors[s]["oov_rate"]) for s in train_shas]
    oov_te = [float(tensors[s]["oov_rate"]) for s in test_b + test_m]

    # R0
    r0 = residual_block(sc_te, labels, name="R0_raw")

    # R1 — leaky eval-fit
    reg1, meta1 = ols_fit(sc_te, oov_te)
    resid1 = apply_residual(reg1, sc_te, oov_te)
    r1 = residual_block(resid1, labels, name="R1_ols_fit_eval", ols_meta=meta1)

    # R2 — train-fit
    reg2, meta2 = ols_fit(sc_tr, oov_tr)
    resid2 = apply_residual(reg2, sc_te, oov_te)
    r2 = residual_block(resid2, labels, name="R2_ols_fit_train", ols_meta=meta2)

    # R3 — distributions
    resid_tr = apply_residual(reg2, sc_tr, oov_tr)
    r3 = {
        **r2,
        "name": "R3_train_fit_with_residual_dists",
        "train_residual_dist": _dist(resid_tr),
        "eval_residual_dist": _dist(resid2),
        "eval_residual_benign_dist": _dist(resid2[: len(test_b)]),
        "eval_residual_malware_dist": _dist(resid2[len(test_b) :]),
        # QQ: sorted percentiles
        "qq_percentiles": [1, 5, 10, 25, 50, 75, 90, 95, 99],
        "qq_train": [float(np.percentile(resid_tr, p)) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)],
        "qq_eval": [float(np.percentile(resid2, p)) for p in (1, 5, 10, 25, 50, 75, 90, 95, 99)],
        "coef_intercept": meta2["coef_intercept"],
        "coef_oov": meta2["coef_oov"],
        "r2": meta2["r2"],
    }

    oov_tr_arr = np.asarray(oov_tr, dtype=float)
    oov_te_arr = np.asarray(oov_te, dtype=float)
    tr_lo, tr_hi = float(oov_tr_arr.min()), float(oov_tr_arr.max())
    te_lo, te_hi = float(oov_te_arr.min()), float(oov_te_arr.max())
    extrapolation = {
        "train_benign_oov_range": [tr_lo, tr_hi],
        "eval_oov_range": [te_lo, te_hi],
        "eval_requires_extrapolation_below": bool(te_lo < tr_lo - 1e-12),
        "eval_requires_extrapolation_above": bool(te_hi > tr_hi + 1e-12),
        "frac_eval_below_train_min": float(np.mean(oov_te_arr < tr_lo)),
        "frac_eval_above_train_max": float(np.mean(oov_te_arr > tr_hi)),
    }

    delta = float(r2["auc"]["auc_floor"] - r1["auc"]["auc_floor"])
    # Thesis number: R2 (honest). State plainly.
    thesis_carries = {
        "variant": "R2_ols_fit_train",
        "auc_floor": r2["auc"]["auc_floor"],
        "direction": r2["auc"]["direction"],
        "ci95_floor": r2["auc"]["ci95_floor"],
        "reason": "OLS fit on train-benign only; eval never used in residualization fit",
    }

    return {
        "pool": pool,
        "R0": r0,
        "R1": r1,
        "R2": r2,
        "R3": r3,
        "delta_R2_minus_R1": delta,
        "oov_extrapolation": extrapolation,
        "thesis_carries": thesis_carries,
        "expected_R0": 0.7765,
        "expected_R1": 0.8141,
    }
