"""Part A: one-class detectors on saved deviation profiles."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT, androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist, split_apps
from abrg.androct.run_gae_run3_5 import _vectorize
from abrg.ocdev import (
    DEVREAD_PROFILES,
    EXPECTED_DIMS,
    FEATURE_SETS,
    LADDER_ASSIGNMENTS_PATH,
    LADDER_HOLDOUT_PATH,
    OCPOOL_INCUMBENT,
    PCA_COMPONENTS,
    PCA_SETS,
    SEEDS,
    SIZE_FLOOR,
)
from abrg.ocdev.detectors import (
    eval_block,
    fit_pca,
    fit_score_centroid_cosine,
    fit_score_centroid_euclidean,
    fit_score_iforest,
    fit_score_knn,
    fit_score_lof,
    fit_score_mahalanobis,
    fit_score_ocsvm,
    score_with_fitted,
)


def _gate(auc_floor: float) -> dict[str, bool]:
    return {
        "clears_size_floor": float(auc_floor) >= SIZE_FLOOR,
        "clears_ocpool": float(auc_floor) >= OCPOOL_INCUMBENT,
    }


def load_profiles(tag: str = "trained_t22") -> tuple[dict[str, np.ndarray], list[str]]:
    idx_path = DEVREAD_PROFILES / f"app_index_{tag}.csv"
    if not idx_path.is_file():
        raise SystemExit(f"STOP: missing profile index {idx_path}")
    shas: list[str] = []
    with idx_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            shas.append(row["sha256"])
    arrays: dict[str, np.ndarray] = {}
    for k, dim in EXPECTED_DIMS.items():
        p = DEVREAD_PROFILES / f"{k}_{tag}.npy"
        if not p.is_file():
            raise SystemExit(f"STOP: missing profile {p}")
        arr = np.load(p)
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
        if arr.shape[0] != len(shas):
            raise SystemExit(f"STOP: {k} n={arr.shape[0]} != index {len(shas)}")
        if arr.shape[1] != dim:
            raise SystemExit(f"STOP: {k} dim={arr.shape[1]} != expected {dim}")
        arrays[k] = np.nan_to_num(arr.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        print(f"[ocdev/A] loaded {k}_{tag} shape={arrays[k].shape}", flush=True)
    return arrays, shas


def _assert_train_benign_only(apps: list) -> None:
    if any(getattr(a, "label", None) != "benign" for a in apps):
        raise SystemExit("STOP: non-benign app in fit() train set")


def _covariates(tensors: dict[str, dict], shas: list[str]) -> dict[str, list[float]]:
    rows = []
    for s in shas:
        t = tensors[s]
        mapped = float(t.get("n_mapped", t.get("n_inv_events", 0)))
        total = float(t.get("n_events", t.get("n_total_events", 0)))
        static = t.get("static_norm", t.get("static_slice_norm", 0.0))
        if hasattr(static, "item"):
            static = float(static)
        rows.append(
            {
                "mapped_event_count": mapped,
                "total_event_count": total,
                "active_nodes": float(t["n_active"]),
                "edge_count": float(t["n_edges"]),
                "graph_density": float(t["density"]),
                "static_feature_norm": float(static),
            }
        )
    keys = rows[0].keys()
    return {k: [r[k] for r in rows] for k in keys}


def _detector_grid(
    X_tr: np.ndarray,
    X_te: np.ndarray,
    *,
    seed: int | None,
) -> list[tuple[str, list[float], Any, bool]]:
    out: list[tuple[str, list[float], Any, bool]] = []
    for name, fn in (
        ("centroid_euclidean", fit_score_centroid_euclidean),
        ("centroid_cosine", fit_score_centroid_cosine),
        ("mahalanobis", fit_score_mahalanobis),
    ):
        sc, fit = fn(X_tr, X_te)
        out.append((name, sc, fit, False))
    for k in (1, 5, 20):
        sc, fit = fit_score_knn(X_tr, X_te, k=k)
        out.append((f"knn_k{k}", sc, fit, False))
    sc, fit = fit_score_lof(X_tr, X_te, k=20)
    out.append(("lof", sc, fit, False))
    if seed is not None:
        sc, fit = fit_score_ocsvm(X_tr, X_te, seed=seed)
        out.append(("ocsvm_rbf", sc, fit, True))
        sc, fit = fit_score_iforest(X_tr, X_te, seed=seed)
        out.append(("isolation_forest", sc, fit, True))
    return out


def _train_scores(fitted: Any, name: str, X_tr: np.ndarray) -> list[float]:
    if name == "centroid_euclidean":
        return score_with_fitted(fitted, X_tr, "centroid_euclidean")
    if name == "centroid_cosine":
        return score_with_fitted(fitted, X_tr, "centroid_cosine")
    if name == "mahalanobis":
        return score_with_fitted(fitted, X_tr, "mahalanobis")
    if name.startswith("knn"):
        return score_with_fitted(fitted, X_tr, "knn")
    return score_with_fitted(fitted, X_tr, name)


def _run_feature_on_split(
    *,
    X: np.ndarray,
    tr_idx: np.ndarray,
    te_idx: np.ndarray,
    y_te: np.ndarray,
    cov: dict[str, list[float]],
    feature_set: str,
    reduction: str | None,
    pca_meta: dict | None,
    out_dir: Path,
    artifacts: Path,
    pred_writer: csv.writer,
    te_shas: list[str],
    split_name: str,
    fold: str,
    model_tag: str,
    resume: bool,
) -> dict[str, Any]:
    X_tr = X[tr_idx]
    X_te = X[te_idx]
    results: dict[str, Any] = {"feature_set": feature_set, "reduction": reduction, "pca": pca_meta}

    for name, scores, fitted, _ in _detector_grid(X_tr, X_te, seed=None):
        path = (
            out_dir
            / f"{model_tag}__{feature_set}__{reduction or 'none'}__{name}__{split_name}__fold{fold}.json"
        )
        if resume and path.is_file():
            results[name] = json.loads(path.read_text(encoding="utf-8"))
            continue
        block = eval_block(scores, y_te.tolist(), cov)
        block["stochastic"] = False
        block["gate"] = _gate(block["auc"]["auc_floor"])
        tr_sc = _train_scores(fitted, name, X_tr)
        block["score_distributions"]["train_benign"] = _dist(tr_sc)
        jp = (
            artifacts
            / "detectors"
            / f"{model_tag}__{feature_set}__{reduction or 'none'}__{name}__{split_name}__fold{fold}.joblib"
        )
        jp.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"fitted": fitted, "name": name}, jp)
        block["detector_path"] = str(jp)
        for sha, lab, sc in zip(te_shas, y_te.tolist(), scores):
            pred_writer.writerow(
                [
                    sha,
                    int(lab),
                    float(sc),
                    "A",
                    feature_set,
                    name,
                    reduction or "none",
                    split_name,
                    fold,
                    "NA",
                    model_tag,
                ]
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
        results[name] = block

    for name in ("ocsvm_rbf", "isolation_forest"):
        per_seed = []
        for seed in SEEDS:
            path = (
                out_dir
                / f"{model_tag}__{feature_set}__{reduction or 'none'}__{name}__{split_name}__fold{fold}__seed{seed}.json"
            )
            if resume and path.is_file():
                per_seed.append(json.loads(path.read_text(encoding="utf-8")))
                continue
            grid = _detector_grid(X_tr, X_te, seed=seed)
            sc, fitted = next((s, f) for n, s, f, _ in grid if n == name)
            block = eval_block(sc, y_te.tolist(), cov)
            block["seed"] = seed
            block["stochastic"] = True
            block["gate"] = _gate(block["auc"]["auc_floor"])
            jp = (
                artifacts
                / "detectors"
                / f"{model_tag}__{feature_set}__{reduction or 'none'}__{name}__{split_name}__fold{fold}__seed{seed}.joblib"
            )
            jp.parent.mkdir(parents=True, exist_ok=True)
            joblib.dump({"fitted": fitted, "name": name}, jp)
            block["detector_path"] = str(jp)
            for sha, lab, s in zip(te_shas, y_te.tolist(), sc):
                pred_writer.writerow(
                    [
                        sha,
                        int(lab),
                        float(s),
                        "A",
                        feature_set,
                        name,
                        reduction or "none",
                        split_name,
                        fold,
                        seed,
                        model_tag,
                    ]
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(block, indent=2) + "\n", encoding="utf-8")
            per_seed.append(block)
        floors = [float(p["auc"]["auc_floor"]) for p in per_seed]
        results[name] = {
            "stochastic": True,
            "per_seed": per_seed,
            "auc_floor_mean": float(np.mean(floors)),
            "auc_floor_std": float(np.std(floors)),
            "gate": _gate(float(np.mean(floors))),
        }
    return results


def run_part_a(
    *,
    split_bundle: Any,
    tensors: dict[str, dict],
    out: Path,
    artifacts: Path,
    pred_writer: csv.writer,
    resume: bool,
) -> dict[str, Any]:
    out_a = out / "partA_profiles"
    out_a.mkdir(parents=True, exist_ok=True)
    controls = out / "controls"
    controls.mkdir(parents=True, exist_ok=True)

    t1k_report_path = ANDROCT_OUTPUT_ROOT / "devread" / "profiles" / "t1k_dimensionality.json"
    t1k_note: dict[str, Any] = {
        "T1K_profiles_saved": False,
        "reason": "no D*_trained_t1k.npy under devread/artifacts/profiles — T22 only",
        "dimensionality_report": None,
    }
    if t1k_report_path.is_file():
        t1k_note["dimensionality_report"] = json.loads(t1k_report_path.read_text(encoding="utf-8"))
    print(f"[ocdev/A] {t1k_note['reason']}", flush=True)

    prof_tr, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    by_sha = split_bundle.by_sha

    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train_apps = split["train"]
    test_apps = split["test_benign"] + split["test_malware"]
    _assert_train_benign_only(train_apps)
    tr_idx = np.asarray([sha_to_i[a.sha256] for a in train_apps], dtype=np.int64)
    te_idx = np.asarray([sha_to_i[a.sha256] for a in test_apps], dtype=np.int64)
    y_te = np.asarray(
        [0] * len(split["test_benign"]) + [1] * len(split["test_malware"]), dtype=np.int32
    )
    te_shas = [a.sha256 for a in test_apps]
    cov = _covariates(tensors, te_shas)

    apps_ordered = [by_sha[s] for s in shas]
    X_raw, _, _, _ = _vectorize(tensors, apps_ordered, mode="full")
    X_raw = np.nan_to_num(X_raw, nan=0.0, posinf=0.0, neginf=0.0)

    summary: dict[str, Any] = {"t1k_note": t1k_note, "splitA": {}, "splitB": {}, "controls": {}}

    def run_all_features(
        arrays: dict[str, np.ndarray], model_tag: str, dest: Path
    ) -> dict[str, Any]:
        dest.mkdir(parents=True, exist_ok=True)
        block: dict[str, Any] = {}
        for fset, X in arrays.items():
            print(f"[ocdev/A] {model_tag} {fset} splitA …", flush=True)
            block[fset] = {
                "none": _run_feature_on_split(
                    X=X,
                    tr_idx=tr_idx,
                    te_idx=te_idx,
                    y_te=y_te,
                    cov=cov,
                    feature_set=fset,
                    reduction=None,
                    pca_meta=None,
                    out_dir=dest,
                    artifacts=artifacts,
                    pred_writer=pred_writer,
                    te_shas=te_shas,
                    split_name="splitA",
                    fold="NA",
                    model_tag=model_tag,
                    resume=resume,
                )
            }
            if fset in PCA_SETS:
                for nc in PCA_COMPONENTS:
                    pca, meta = fit_pca(X[tr_idx], nc)
                    Xp = np.zeros((X.shape[0], meta["fitted"]), dtype=np.float64)
                    Xp[tr_idx] = pca.transform(X[tr_idx])
                    Xp[te_idx] = pca.transform(X[te_idx])
                    red = f"pca{nc}"
                    print(
                        f"[ocdev/A] {model_tag} {fset}/{red} expl={meta['explained_variance_sum']:.4f}",
                        flush=True,
                    )
                    block[fset][red] = _run_feature_on_split(
                        X=Xp,
                        tr_idx=tr_idx,
                        te_idx=te_idx,
                        y_te=y_te,
                        cov=cov,
                        feature_set=fset,
                        reduction=red,
                        pca_meta=meta,
                        out_dir=dest,
                        artifacts=artifacts,
                        pred_writer=pred_writer,
                        te_shas=te_shas,
                        split_name="splitA",
                        fold="NA",
                        model_tag=model_tag,
                        resume=resume,
                    )
        return block

    summary["splitA"]["trained"] = run_all_features(prof_tr, "trained", out_a / "splitA_trained")

    rand_tag = "random_init_t22"
    if (DEVREAD_PROFILES / f"D1_{rand_tag}.npy").is_file():
        prof_rnd, shas_r = load_profiles(rand_tag)
        if shas_r != shas:
            raise SystemExit("STOP: random-init profile index != trained index")
        summary["controls"]["random_init_splitA"] = run_all_features(
            prof_rnd, "random_init", controls / "random_init_splitA"
        )
    else:
        summary["controls"]["random_init_splitA"] = {"available": False}

    print("[ocdev/A] RAW_full splitA …", flush=True)
    summary["controls"]["raw_tensor_splitA"] = {
        "RAW_full": {
            "none": _run_feature_on_split(
                X=X_raw,
                tr_idx=tr_idx,
                te_idx=te_idx,
                y_te=y_te,
                cov=cov,
                feature_set="RAW_full",
                reduction=None,
                pca_meta=None,
                out_dir=controls / "raw_tensor",
                artifacts=artifacts,
                pred_writer=pred_writer,
                te_shas=te_shas,
                split_name="splitA",
                fold="NA",
                model_tag="raw",
                resume=resume,
            )
        }
    }

    assignments = {
        str(k): int(v)
        for k, v in json.loads(LADDER_ASSIGNMENTS_PATH.read_text())["ward"]["assignments"].items()
    }
    ladder = json.loads(LADDER_HOLDOUT_PATH.read_text())
    groups: dict[int, list[str]] = {}
    for sha, gid in assignments.items():
        groups.setdefault(int(gid), []).append(sha)
    meta = {int(f["group_id"]): int(f["n_malware_holdout"]) for f in ladder["folds"]}
    if sorted(groups) != sorted(meta):
        raise SystemExit("STOP: split-B fold ids != ladder")
    for gid, n in meta.items():
        if len(groups[gid]) != n:
            raise SystemExit(f"STOP: fold {gid} count mismatch")

    train_b = [a.sha256 for a in split_bundle.train]
    test_ben = [a.sha256 for a in split_bundle.test_benign]
    all_m = [a.sha256 for a in split_bundle.test_malware]

    def run_split_b(
        arrays: dict[str, np.ndarray], model_tag: str, dest: Path, fsets: tuple[str, ...]
    ) -> dict[str, Any]:
        dest.mkdir(parents=True, exist_ok=True)
        out_b: dict[str, Any] = {}
        for fset in fsets:
            X = arrays[fset]
            fold_rows = []
            pooled_s: list[float] = []
            pooled_y: list[int] = []
            for gid in sorted(groups):
                hold = groups[gid]
                tr_fit = train_b  # benign-only fit
                te_shas_f = test_ben + hold
                tr_idx_f = np.asarray([sha_to_i[s] for s in tr_fit], dtype=np.int64)
                te_idx_f = np.asarray([sha_to_i[s] for s in te_shas_f], dtype=np.int64)
                y_te_f = np.asarray([0] * len(test_ben) + [1] * len(hold), dtype=np.int32)
                cov_f = _covariates(tensors, te_shas_f)
                _assert_train_benign_only([by_sha[s] for s in tr_fit])
                if any(by_sha[shas[i]].label != "benign" for i in tr_idx_f):
                    raise SystemExit("STOP: malware in fit indices")
                print(f"[ocdev/A] {model_tag} {fset} splitB fold{gid} …", flush=True)
                blk = _run_feature_on_split(
                    X=X,
                    tr_idx=tr_idx_f,
                    te_idx=te_idx_f,
                    y_te=y_te_f,
                    cov=cov_f,
                    feature_set=fset,
                    reduction=None,
                    pca_meta=None,
                    out_dir=dest,
                    artifacts=artifacts,
                    pred_writer=pred_writer,
                    te_shas=te_shas_f,
                    split_name="splitB",
                    fold=str(gid),
                    model_tag=model_tag,
                    resume=resume,
                )
                prim = blk["mahalanobis"]["auc"]
                sc, _ = fit_score_mahalanobis(X[tr_idx_f], X[te_idx_f])
                pooled_s.extend(sc)
                pooled_y.extend(y_te_f.tolist())
                fold_rows.append(
                    {
                        "fold": gid,
                        "n_test": len(te_shas_f),
                        "n_malware": len(hold),
                        "primary_auc": prim,
                    }
                )
            fold_aucs = [float(f["primary_auc"]["auc_floor"]) for f in fold_rows]
            w = [f["n_test"] for f in fold_rows]
            pooled = _auc_with_bootstrap(pooled_s, pooled_y)
            out_b[fset] = {
                "folds": fold_rows,
                "mean_auc_floor": float(np.mean(fold_aucs)),
                "std_auc_floor": float(np.std(fold_aucs)),
                "weighted_mean_auc_floor": float(np.average(fold_aucs, weights=w)),
                "pooled_oof_auc": pooled,
                "primary_detector": "mahalanobis",
                "gate": _gate(float(np.average(fold_aucs, weights=w))),
            }
        return out_b

    print("[ocdev/A] Split-B trained …", flush=True)
    summary["splitB"]["trained"] = run_split_b(
        prof_tr, "trained", out_a / "splitB_trained", FEATURE_SETS
    )

    (out_a / "partA_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
