"""Check 1 — ladder rung-2 per-fold raw AUC vs floor, pooled OOF, scale."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT
from abrg.final_validate.util import auc_raw_and_floor, eval_auc_block, score_dist, write_json
from abrg.ladder import MODELS, MODES, SEED
from abrg.ladder.rungs import _assignments_to_groups
from abrg.ladder.vectorize import vectorize_shas

LADDER = ANDROCT_OUTPUT_ROOT / "ladder"
BEH_JSON = LADDER / "rung2" / "behavioral_group_holdout.json"
RAND_JSON = LADDER / "control" / "random_group_holdout.json"
RAND_ASSIGN = LADDER / "control" / "random_assignments.json"
WARD_ASSIGN = LADDER / "grouping" / "route_b_behavioral.json"
EPS = 1e-12


def _from_saved(path: Path) -> dict[str, Any]:
    blob = json.loads(path.read_text(encoding="utf-8"))
    tables: dict[str, Any] = {}
    for mode in MODES:
        tables[mode] = {}
        for model in MODELS:
            rows = []
            for f in blob["folds"]:
                auc = f["modes"][mode][model]["auc"]
                raw = float(auc["auc"])
                floor = float(auc["auc_floor"])
                rows.append(
                    {
                        "fold": int(f["group_id"]),
                        "n_malware": int(f["n_malware_holdout"]),
                        "n_test": int(f["n_test"]),
                        "n_benign": int(f["n_test"]) - int(f["n_malware_holdout"]),
                        "raw_auc": raw,
                        "auc_floor": floor,
                        "direction": auc.get("direction"),
                        "inverted": raw < 0.5,
                    }
                )
            raws = np.asarray([r["raw_auc"] for r in rows], dtype=np.float64)
            floors = np.asarray([r["auc_floor"] for r in rows], dtype=np.float64)
            w = np.asarray([r["n_test"] for r in rows], dtype=np.float64)
            tables[mode][model] = {
                "folds": rows,
                "n_folds_raw_auc_lt_0.5": int(np.sum(raws < 0.5)),
                "mean_raw_auc": float(np.mean(raws)),
                "mean_auc_floor": float(np.mean(floors)),
                "inflation_floor_minus_raw": float(np.mean(floors) - np.mean(raws)),
                "weighted_mean_raw_auc": float(np.average(raws, weights=w)),
                "weighted_mean_auc_floor": float(np.average(floors, weights=w)),
                "std_raw_auc": float(np.std(raws, ddof=1)),
                "std_auc_floor": float(np.std(floors, ddof=1)),
            }
    pooled = blob.get("pooled_oof_hgb_full")
    return {
        "label": blob.get("label"),
        "n_folds": blob.get("n_folds"),
        "saved_aggregate": blob.get("aggregate"),
        "saved_pooled_oof_hgb_full": (
            {k: pooled[k] for k in pooled if k != "roc_points"} if pooled else None
        ),
        "from_saved_json": tables,
    }


def _fit_predict_train_test(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
    model_name: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Same estimators as ladder.models.fit_supervised; scores only, no bootstrap."""
    X_tr = np.nan_to_num(X_tr, nan=0.0, posinf=0.0, neginf=0.0)
    X_te = np.nan_to_num(X_te, nan=0.0, posinf=0.0, neginf=0.0)
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
                        random_state=SEED,
                    ),
                ),
            ]
        )
        pipe.fit(X_tr, y_tr)
        return pipe.predict_proba(X_te)[:, 1], pipe.predict_proba(X_tr)[:, 1]
    if model_name == "hist_gradient_boosting":
        clf = HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.08,
            max_iter=300,
            random_state=SEED,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
        )
        clf.fit(X_tr, y_tr)
        return clf.predict_proba(X_te)[:, 1], clf.predict_proba(X_tr)[:, 1]
    raise ValueError(model_name)


def _retrain_holdout(
    *,
    tensors: dict,
    split_bundle: Any,
    assignments: dict[str, int],
    label: str,
) -> dict[str, Any]:
    train_benign = [a.sha256 for a in split_bundle.train]
    test_benign = [a.sha256 for a in split_bundle.test_benign]
    all_malware = [a.sha256 for a in split_bundle.test_malware]
    by_sha = split_bundle.by_sha
    groups = _assignments_to_groups(assignments)

    print(f"[final_validate/C1] precomputing vectors ({label}) …", flush=True)
    all_shas = train_benign + test_benign + all_malware
    sha_i = {s: i for i, s in enumerate(all_shas)}
    y_all = np.asarray(
        [1 if by_sha[s].label == "malware" else 0 for s in all_shas], dtype=np.int32
    )
    X_mode: dict[str, np.ndarray] = {}
    for mode in MODES:
        X, _, _ = vectorize_shas(tensors, all_shas, by_sha, mode=mode)
        X_mode[mode] = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    out_modes: dict[str, Any] = {m: {mod: {"folds": []} for mod in MODELS} for m in MODES}

    for gid in sorted(groups):
        hold_m = groups[gid]
        train_m = [s for s in all_malware if s not in set(hold_m)]
        tr_shas = train_benign + train_m
        te_shas = test_benign + hold_m
        tr_idx = np.asarray([sha_i[s] for s in tr_shas], dtype=np.int64)
        te_idx = np.asarray([sha_i[s] for s in te_shas], dtype=np.int64)
        print(f"[final_validate/C1] {label} fold {gid} n_mal={len(hold_m)} …", flush=True)
        for mode in MODES:
            X_tr, y_tr = X_mode[mode][tr_idx], y_all[tr_idx]
            X_te, y_te = X_mode[mode][te_idx], y_all[te_idx]
            for model_name in MODELS:
                sc_te, sc_tr = _fit_predict_train_test(X_tr, y_tr, X_te, model_name)
                raw = auc_raw_and_floor(sc_te, y_te)
                n0 = int((y_te == 0).sum())
                tb, tm = sc_te[:n0], sc_te[n0:]
                mu = float(sc_tr.mean())
                sd = float(sc_tr.std(ddof=1) if sc_tr.size > 1 else 0.0)
                z_te = (sc_te - mu) / (sd + EPS)
                out_modes[mode][model_name]["folds"].append(
                    {
                        "fold": gid,
                        "n_malware": len(hold_m),
                        "n_test": len(te_shas),
                        "raw_auc": raw["auc"],
                        "auc_floor": raw["auc_floor"],
                        "direction": raw["direction"],
                        "inverted": raw["auc"] < 0.5,
                        "score_test_benign": score_dist(tb),
                        "score_test_malware": score_dist(tm),
                        "score_train": score_dist(sc_tr),
                        "zscore_train_mean": mu,
                        "zscore_train_sd": sd,
                        "scores_te": sc_te.tolist(),
                        "labels_te": y_te.tolist(),
                        "z_te": z_te.tolist(),
                    }
                )

    result: dict[str, Any] = {"label": label, "gae_retrained_per_fold": False, "modes": {}}
    for mode in MODES:
        result["modes"][mode] = {}
        for model_name in MODELS:
            folds = out_modes[mode][model_name]["folds"]
            raws = np.asarray([f["raw_auc"] for f in folds])
            floors = np.asarray([f["auc_floor"] for f in folds])
            w = np.asarray([f["n_test"] for f in folds], dtype=float)
            pooled_s, pooled_y, pooled_z = [], [], []
            for f in folds:
                pooled_s.extend(f["scores_te"])
                pooled_y.extend(f["labels_te"])
                pooled_z.extend(f["z_te"])
            pooled = eval_auc_block(pooled_s, pooled_y)
            pooled_z_b = eval_auc_block(pooled_z, pooled_y)
            med_b = np.asarray([f["score_test_benign"]["median"] for f in folds])
            med_m = np.asarray([f["score_test_malware"]["median"] for f in folds])
            slim = [
                {k: v for k, v in f.items() if k not in ("scores_te", "labels_te", "z_te")}
                for f in folds
            ]
            result["modes"][mode][model_name] = {
                "n_folds_raw_auc_lt_0.5": int(np.sum(raws < 0.5)),
                "mean_raw_auc": float(np.mean(raws)),
                "mean_auc_floor": float(np.mean(floors)),
                "inflation_floor_minus_raw": float(np.mean(floors) - np.mean(raws)),
                "weighted_mean_raw_auc": float(np.average(raws, weights=w)),
                "weighted_mean_auc_floor": float(np.average(floors, weights=w)),
                "pooled_oof_raw": pooled,
                "pooled_oof_zscored_train_scores": pooled_z_b,
                "between_fold_var_median_benign": float(np.var(med_b, ddof=1)),
                "between_fold_var_median_malware": float(np.var(med_m, ddof=1)),
                "fold_median_benign_range": [float(med_b.min()), float(med_b.max())],
                "fold_median_malware_range": [float(med_m.min()), float(med_m.max())],
                "n_benign_rows_in_pooled": int(sum(f["n_test"] - f["n_malware"] for f in folds)),
                "folds": slim,
            }
    return result


def _write_fold_csv(path: Path, tables: dict[str, Any], source: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "source",
                "mode",
                "model",
                "fold",
                "n_malware",
                "n_test",
                "raw_auc",
                "auc_floor",
                "direction",
                "inverted",
            ]
        )
        for mode in MODES:
            for model in MODELS:
                for row in tables[mode][model]["folds"]:
                    w.writerow(
                        [
                            source,
                            mode,
                            model,
                            row["fold"],
                            row["n_malware"],
                            row["n_test"],
                            f"{row['raw_auc']:.10f}",
                            f"{row['auc_floor']:.10f}",
                            row.get("direction"),
                            int(row["inverted"]),
                        ]
                    )


def _thesis(beh_saved: dict) -> dict[str, Any]:
    hgb = beh_saved["from_saved_json"]["full"]["hist_gradient_boosting"]
    pooled_saved = beh_saved.get("saved_pooled_oof_hgb_full") or {}
    n_flip = hgb["n_folds_raw_auc_lt_0.5"]
    pooled_raw = float(pooled_saved.get("auc", float("nan")))
    mean_floor = hgb["mean_auc_floor"]
    mean_raw = hgb["mean_raw_auc"]
    w_floor = hgb["weighted_mean_auc_floor"]
    close_pooled_to_weighted = (
        abs(pooled_raw - w_floor) < 0.02 if np.isfinite(pooled_raw) else False
    )
    all_raw_ge_half = n_flip == 0
    if all_raw_ge_half and close_pooled_to_weighted:
        carries, value = "rung2_mean_auc_floor_HGB_full", mean_floor
        reason = (
            "all per-fold raw AUC >= 0.5 and pooled OOF close to weighted mean; "
            "0.8492 stands"
        )
    else:
        carries, value = "rung2_pooled_oof_raw_HGB_full", pooled_raw
        reason = (
            f"{n_flip}/30 folds have raw AUC < 0.5; "
            f"mean_floor={mean_floor:.6f} vs mean_raw={mean_raw:.6f} "
            f"(inflation={hgb['inflation_floor_minus_raw']:.6f}); "
            f"pooled OOF raw={pooled_raw:.6f}; weighted floor={w_floor:.6f}"
        )
    return {
        "carries": carries,
        "value": value,
        "mean_raw_auc": mean_raw,
        "mean_auc_floor": mean_floor,
        "weighted_mean_auc_floor": w_floor,
        "pooled_oof_raw": pooled_raw,
        "n_folds_raw_auc_lt_0.5": n_flip,
        "reason": reason,
    }


def run_check1(*, out: Path, split_bundle: Any, tensors: dict, skip_retrain: bool = False) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    print("[final_validate/C1] parsing saved ladder JSON …", flush=True)
    beh_saved = _from_saved(BEH_JSON)
    rand_saved = _from_saved(RAND_JSON)
    _write_fold_csv(out / "behavioral_per_fold_raw_from_json.csv", beh_saved["from_saved_json"], "behavioral_json")
    _write_fold_csv(out / "random_per_fold_raw_from_json.csv", rand_saved["from_saved_json"], "random_json")

    thesis = _thesis(beh_saved)
    payload = {
        "behavioral": beh_saved,
        "random_group": rand_saved,
        "retrained_available": False,
        "model_retrains_per_fold": True,
        "gae_retrained_per_fold": False,
        "thesis_carries": thesis,
    }
    write_json(out / "check1.json", payload)
    write_json(
        out / "aggregate_raw_vs_floor.json",
        {
            "behavioral": {
                m: {mod: {k: v for k, v in blk.items() if k != "folds"} for mod, blk in modes.items()}
                for m, modes in beh_saved["from_saved_json"].items()
            },
            "random_group": {
                m: {mod: {k: v for k, v in blk.items() if k != "folds"} for mod, blk in modes.items()}
                for m, modes in rand_saved["from_saved_json"].items()
            },
            "thesis_carries": thesis,
        },
    )

    beh_re = rand_re = None
    if not skip_retrain:
        ward = json.loads(WARD_ASSIGN.read_text())["ward"]["assignments"]
        ward = {str(k): int(v) for k, v in ward.items()}
        rand_a = {str(k): int(v) for k, v in json.loads(RAND_ASSIGN.read_text()).items()}
        beh_re = _retrain_holdout(
            tensors=tensors, split_bundle=split_bundle, assignments=ward, label="behavioral"
        )
        rand_re = _retrain_holdout(
            tensors=tensors, split_bundle=split_bundle, assignments=rand_a, label="random_group"
        )
        write_json(out / "retrained_behavioral.json", beh_re)
        write_json(out / "retrained_random.json", rand_re)

    payload["retrained_available"] = beh_re is not None
    if beh_re:
        payload["retrained_behavioral_HGB_full"] = beh_re["modes"]["full"]["hist_gradient_boosting"]
        payload["retrained_random_HGB_full"] = rand_re["modes"]["full"]["hist_gradient_boosting"]
        payload["retrained_behavioral"] = {
            m: {mod: {k: v for k, v in blk.items() if k != "folds"} for mod, blk in modes.items()}
            for m, modes in beh_re["modes"].items()
        }
        payload["retrained_random"] = {
            m: {mod: {k: v for k, v in blk.items() if k != "folds"} for mod, blk in modes.items()}
            for m, modes in rand_re["modes"].items()
        }
    write_json(out / "check1.json", payload)
    return payload
