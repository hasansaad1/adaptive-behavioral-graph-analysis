"""Experiment S2: ABRG deviation profile + supervised readout."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import torch
import torch.nn.functional as F
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from sklearn.metrics import roc_auc_score

from abrg.androct.paths import androct_run5_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import EPOCHS, LR, SEED, TEST_RATIO, WD, _auc_with_bootstrap, split_apps
from abrg.androct.run_gae_run3_5 import _adj_matrix, _stratified_split, _vectorize
from abrg.apigraph.split import load_run3_split
from abrg.autoencoder import FeatureDecoder, build_gae, graph_reconstruction_error_dual, seed_rng, train_gae_multi_dual
from abrg.devread import (
    CLASSIFIERS,
    DEVREAD_OUTPUT_ROOT,
    EXPECTED_SPLIT_DIGEST_PREFIX,
    FEATURE_SETS,
    RAW_SETS,
    RUN5_ALPHA,
    RUN5_HIDDEN,
    RUN5_REF_AUC_FLOOR,
    RUN5_REF_TOL,
    SEEDS,
)
from abrg.features import node_feature_dim
from abrg.ladder.floors import mapped_event_floor


def _seeds_for_classifier(clf_name: str) -> tuple[int, ...]:
    if clf_name == "HGB":
        return SEEDS
    return (SEED,)


def _population_floor(
    tensors: dict[str, dict[str, Any]],
    test_shas: list[str],
    labels: list[int],
) -> dict[str, Any]:
    return mapped_event_floor(tensors, test_shas, labels)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _assert_ladder_folds(groups: dict[int, list[str]], ladder_holdout_path: Path) -> None:
    ladder = json.loads(ladder_holdout_path.read_text(encoding="utf-8"))
    ladder_meta = {int(f["group_id"]): int(f["n_malware_holdout"]) for f in ladder["folds"]}
    if sorted(groups) != sorted(ladder_meta):
        raise SystemExit("STOP: split-B fold ids do not match ladder behavioral holdout.")
    for gid, n_m in ladder_meta.items():
        if len(groups[gid]) != n_m:
            raise SystemExit(
                f"STOP: fold {gid} malware count {len(groups[gid])} != ladder {n_m}"
            )


def _auc_fast(scores: list[float], labels: list[int]) -> dict[str, Any]:
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return {
            "auc": float("nan"),
            "auc_floor": float("nan"),
            "direction": "undefined",
            "ci95": [float("nan"), float("nan")],
            "ci95_floor": [float("nan"), float("nan")],
            "n": int(len(y)),
        }
    auc = float(roc_auc_score(y, s))
    inv = float(roc_auc_score(y, -s))
    if inv > auc:
        return {
            "auc": inv,
            "auc_floor": inv,
            "direction": "benign_higher_score",
            "ci95": [float("nan"), float("nan")],
            "ci95_floor": [float("nan"), float("nan")],
            "n": int(len(y)),
        }
    return {
        "auc": auc,
        "auc_floor": auc,
        "direction": "malware_higher_score",
        "ci95": [float("nan"), float("nan")],
        "ci95_floor": [float("nan"), float("nan")],
        "n": int(len(y)),
    }


def _assert_split_digest(digest: str) -> None:
    if not digest.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {digest[:16]} != {EXPECTED_SPLIT_DIGEST_PREFIX}..."
        )


def _load_or_train_run5_model(
    *,
    tensors: dict[str, dict[str, Any]],
    split: dict[str, list[Any]],
    artifacts_dir: Path,
) -> tuple[Any, Any, dict[str, Any]]:
    ckpt = androct_run5_output_dir() / "gae_androct_run5_h8.pt"
    in_ch = node_feature_dim()
    if ckpt.is_file():
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        model = build_gae(in_ch, int(payload.get("hidden", RUN5_HIDDEN)))
        model.encoder = EdgeWeightProbeEncoder(model.encoder)
        feature_decoder = FeatureDecoder(int(payload.get("hidden", RUN5_HIDDEN)), in_ch)
        model.load_state_dict(payload["model_state"])
        feature_decoder.load_state_dict(payload["feature_decoder_state"])
        source = "loaded_run5_checkpoint"
        ckpt_used = ckpt
        retrained = False
    else:
        # Train only on benign train partition.
        train_graphs = [
            (tensors[a.sha256]["x"], tensors[a.sha256]["edge_index"], tensors[a.sha256]["edge_weight"])
            for a in split["train"]
            if tensors[a.sha256]["edge_index"].numel() > 0
        ]
        if any(a.label != "benign" for a in split["train"]):
            raise SystemExit("STOP: training partition contains non-benign apps.")
        seed_rng(SEED)
        model = build_gae(in_ch, RUN5_HIDDEN)
        model.encoder = EdgeWeightProbeEncoder(model.encoder)
        feature_decoder = FeatureDecoder(RUN5_HIDDEN, in_ch)
        train_gae_multi_dual(
            model=model,
            feature_decoder=feature_decoder,
            graphs=train_graphs,
            epochs=EPOCHS,
            lr=LR,
            alpha=RUN5_ALPHA,
            weight_decay=WD,
        )
        ckpt_used = artifacts_dir / "gae_androct_run5_h8_retrained.pt"
        torch.save(
            {
                "model_state": model.state_dict(),
                "feature_decoder_state": feature_decoder.state_dict(),
                "hidden": RUN5_HIDDEN,
                "alpha": RUN5_ALPHA,
                "in_channels": in_ch,
            },
            ckpt_used,
        )
        source = "retrained_run5_pins"
        retrained = True
    model.eval()
    feature_decoder.eval()
    meta = {"source": source, "checkpoint_path": str(ckpt_used), "retrained": retrained}
    return model, feature_decoder, meta


def _scalar_auc_floor(
    model: Any,
    feature_decoder: Any,
    split: dict[str, list[Any]],
    tensors: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    scores_b = [
        graph_reconstruction_error_dual(
            model,
            feature_decoder,
            tensors[a.sha256]["x"],
            tensors[a.sha256]["edge_index"],
            tensors[a.sha256]["edge_weight"],
            alpha=RUN5_ALPHA,
        )
        for a in split["test_benign"]
    ]
    scores_m = [
        graph_reconstruction_error_dual(
            model,
            feature_decoder,
            tensors[a.sha256]["x"],
            tensors[a.sha256]["edge_index"],
            tensors[a.sha256]["edge_weight"],
            alpha=RUN5_ALPHA,
        )
        for a in split["test_malware"]
    ]
    labels = [0] * len(scores_b) + [1] * len(scores_m)
    scores = scores_b + scores_m
    return _auc_with_bootstrap(scores, labels)


def _per_app_deviation(
    model: Any,
    feature_decoder: Any,
    t: dict[str, Any],
) -> dict[str, np.ndarray | float]:
    x = t["x"]
    edge_index = t["edge_index"]
    edge_weight = t["edge_weight"]
    with torch.no_grad():
        z = model.encode(x, edge_index, edge_weight)
        x_hat = feature_decoder(z)
        # D1: per-node feature reconstruction error (mean over feature dims)
        d1 = ((x_hat - x) ** 2).mean(dim=1).detach().cpu().numpy().astype(np.float64)

        # D2: per-cell adjacency weighted BCE error over full n x n.
        logits = z @ z.t()
        n = logits.size(0)
        target = torch.zeros((n, n), dtype=logits.dtype, device=logits.device)
        if edge_index.numel() > 0:
            target[edge_index[0], edge_index[1]] = 1.0
        n_pos = float(target.sum().item())
        n_tot = float(target.numel())
        n_neg = n_tot - n_pos
        if n_pos > 0.0:
            pos_weight = torch.tensor(n_neg / n_pos, dtype=logits.dtype, device=logits.device)
            d2_cell = F.binary_cross_entropy_with_logits(
                logits, target, pos_weight=pos_weight, reduction="none"
            )
        else:
            d2_cell = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
        d2m = d2_cell.detach().cpu().numpy().astype(np.float64)
        d2 = d2m.reshape(-1)

        # D3: per-node aggregate over incident cells (row + col).
        d3 = []
        for i in range(n):
            inc = np.concatenate([d2m[i, :], d2m[:, i]])
            d3.extend([float(np.mean(inc)), float(np.max(inc))])
        d3_arr = np.asarray(d3, dtype=np.float64)
        d4 = np.concatenate([d1, d3_arr])
        d5 = np.concatenate([d1, d2])
        d0 = float(graph_reconstruction_error_dual(model, feature_decoder, x, edge_index, edge_weight, alpha=RUN5_ALPHA))
    return {"D0": d0, "D1": d1, "D2": d2, "D3": d3_arr, "D4": d4, "D5": d5}


def _build_profiles(
    *,
    model: Any,
    feature_decoder: Any,
    shas: list[str],
    tensors: dict[str, dict[str, Any]],
    out_dir: Path,
    tag: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, list[Any]] = {k: [] for k in FEATURE_SETS}
    for sha in shas:
        d = _per_app_deviation(model, feature_decoder, tensors[sha])
        for k in FEATURE_SETS:
            data[k].append(d[k])
    # Persist profile arrays with index file.
    index_path = out_dir / f"app_index_{tag}.csv"
    with index_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["row", "sha256"])
        for i, s in enumerate(shas):
            w.writerow([i, s])

    arrays: dict[str, np.ndarray] = {}
    for k in FEATURE_SETS:
        if k == "D0":
            arr = np.asarray(data[k], dtype=np.float64).reshape(-1, 1)
        else:
            arr = np.stack(data[k], axis=0).astype(np.float64)
        arrays[k] = arr
        np.save(out_dir / f"{k}_{tag}.npy", arr)
    dims = {k: int(v.shape[1]) for k, v in arrays.items()}
    return {"arrays": arrays, "dims": dims, "index_csv": str(index_path)}


def _profile_norm_stats(
    arrays: dict[str, np.ndarray],
    labels: np.ndarray,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, X in arrays.items():
        norms = np.linalg.norm(X, axis=1)
        block = {}
        for cls, name in ((0, "benign"), (1, "malware")):
            vals = norms[labels == cls]
            if len(vals) == 0:
                block[name] = {"mean": float("nan"), "iqr": float("nan"), "median": float("nan")}
            else:
                q1, q3 = np.percentile(vals, [25, 75])
                block[name] = {
                    "mean": float(np.mean(vals)),
                    "median": float(np.median(vals)),
                    "iqr": float(q3 - q1),
                }
        out[k] = block
    return out


def _raw_feature_sets(tensors: dict[str, dict[str, Any]], apps: list[Any]) -> dict[str, np.ndarray]:
    X_full, _, _, _ = _vectorize(tensors, apps, mode="full")
    X_node, _, _, _ = _vectorize(tensors, apps, mode="node_only")
    X_adj, _, _, _ = _vectorize(tensors, apps, mode="adj_only")
    return {
        "RAW_full": np.nan_to_num(X_full, nan=0.0, posinf=0.0, neginf=0.0),
        "RAW_node_only": np.nan_to_num(X_node, nan=0.0, posinf=0.0, neginf=0.0),
        "RAW_adj_only": np.nan_to_num(X_adj, nan=0.0, posinf=0.0, neginf=0.0),
    }


def _fit_predict(
    clf_name: str,
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    X_te: np.ndarray,
    *,
    seed: int,
) -> tuple[Any, np.ndarray]:
    if clf_name == "LR_L2":
        clf = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        penalty="l2",
                        solver="lbfgs",
                        max_iter=4000,
                        class_weight="balanced",
                        random_state=seed,
                    ),
                ),
            ]
        )
    elif clf_name == "LR_L1":
        clf = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        penalty="l1",
                        solver="liblinear",
                        max_iter=4000,
                        class_weight="balanced",
                        random_state=seed,
                    ),
                ),
            ]
        )
    elif clf_name == "HGB":
        clf = HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.08,
            max_iter=300,
            early_stopping=True,
            n_iter_no_change=20,
            validation_fraction=0.1,
            random_state=seed,
        )
    else:
        raise ValueError(clf_name)
    clf.fit(X_tr, y_tr)
    if hasattr(clf, "predict_proba"):
        s = clf.predict_proba(X_te)[:, 1]
    else:
        s = clf.decision_function(X_te)
    return clf, np.asarray(s, dtype=np.float64)


def _run_split_a(
    *,
    X_sets: dict[str, np.ndarray],
    y: np.ndarray,
    apps: list[Any],
    tensors: dict[str, dict[str, Any]],
    out_dir: Path,
    pred_writer: csv.writer,
    model_tag: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    split = _stratified_split(apps, seed=SEED, test_ratio=TEST_RATIO)
    sha_to_idx = {a.sha256: i for i, a in enumerate(apps)}
    tr_idx = np.asarray([sha_to_idx[a.sha256] for a in split["train"]], dtype=np.int64)
    te_apps = split["test_benign"] + split["test_malware"]
    te_idx = np.asarray([sha_to_idx[a.sha256] for a in te_apps], dtype=np.int64)
    y_te = y[te_idx]
    test_floor = _population_floor(
        tensors,
        [a.sha256 for a in te_apps],
        y_te.tolist(),
    )

    results: dict[str, Any] = {}
    for fset, X in X_sets.items():
        results[fset] = {}
        for clf_name in CLASSIFIERS:
            per_seed = []
            for seed in _seeds_for_classifier(clf_name):
                clf, scores = _fit_predict(clf_name, X[tr_idx], y[tr_idx], X[te_idx], seed=seed)
                auc = _auc_with_bootstrap(scores.tolist(), y_te.tolist())
                model_path = out_dir / "classifiers" / f"{model_tag}__{fset}__{clf_name}__splitA__seed{seed}.joblib"
                model_path.parent.mkdir(parents=True, exist_ok=True)
                joblib.dump(clf, model_path)
                per_seed.append({"seed": seed, "auc": auc, "model_path": str(model_path), "scores": scores.tolist()})
                for local_i, app in enumerate(te_apps):
                    pred_writer.writerow(
                        [app.sha256, int(y_te[local_i]), float(scores[local_i]), fset, clf_name, "splitA", "NA", seed, model_tag]
                    )
            floors = [float(r["auc"]["auc_floor"]) for r in per_seed]
            results[fset][clf_name] = {
                "per_seed": [{k: v for k, v in r.items() if k != "scores"} for r in per_seed],
                "auc_floor_mean": float(np.mean(floors)),
                "auc_floor_std": float(np.std(floors)),
                "population_floor": test_floor,
            }
    (out_dir / f"results_{model_tag}.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _run_split_b(
    *,
    X_sets: dict[str, np.ndarray],
    y: np.ndarray,
    split_b: Any,
    tensors: dict[str, dict[str, Any]],
    assignments: dict[str, int],
    out_dir: Path,
    pred_writer: csv.writer,
    model_tag: str,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ladder_assign_path = Path("abrg/output/androct_2017/ladder/grouping/route_b_behavioral.json")
    ladder_holdout_path = Path("abrg/output/androct_2017/ladder/rung2/behavioral_group_holdout.json")
    ladder_assign = json.loads(ladder_assign_path.read_text(encoding="utf-8"))["ward"]["assignments"]
    if assignments != ladder_assign:
        raise SystemExit("STOP: provided split-B assignments do not match ladder artifact.")

    by_sha_idx = {a.sha256: i for i, a in enumerate(split_b.eligible)}
    train_b_shas = [a.sha256 for a in split_b.train]
    test_ben_shas = [a.sha256 for a in split_b.test_benign]
    all_m_shas = [a.sha256 for a in split_b.test_malware]
    groups: dict[int, list[str]] = {}
    for sha, gid in assignments.items():
        groups.setdefault(int(gid), []).append(sha)
    _assert_ladder_folds(groups, ladder_holdout_path)

    results: dict[str, Any] = {}
    for fset, X in X_sets.items():
        results[fset] = {}
        for clf_name in CLASSIFIERS:
            fold_rows = []
            pooled_scores: list[float] = []
            pooled_labels: list[int] = []
            for gid in sorted(groups):
                hold_m = groups[gid]
                train_m = [s for s in all_m_shas if s not in hold_m]
                tr_shas = train_b_shas + train_m
                te_shas = test_ben_shas + hold_m
                tr_idx = np.asarray([by_sha_idx[s] for s in tr_shas], dtype=np.int64)
                te_idx = np.asarray([by_sha_idx[s] for s in te_shas], dtype=np.int64)
                y_te = y[te_idx]
                fold_floor = _population_floor(tensors, te_shas, y_te.tolist())

                per_seed = []
                primary_scores: np.ndarray | None = None
                for seed in _seeds_for_classifier(clf_name):
                    clf, scores = _fit_predict(clf_name, X[tr_idx], y[tr_idx], X[te_idx], seed=seed)
                    # Fast fold AUCs; bootstrap reserved for pooled OOF / splitA summaries.
                    auc = _auc_fast(scores.tolist(), y_te.tolist())
                    model_path = None
                    # Persist only primary-seed models for compact feature sets.
                    if seed == SEED and fset in ("D0", "D4", "D5", "RAW_full"):
                        model_path = out_dir / "classifiers" / f"{model_tag}__{fset}__{clf_name}__splitB_fold{gid}__seed{seed}.joblib"
                        model_path.parent.mkdir(parents=True, exist_ok=True)
                        joblib.dump(clf, model_path)
                    per_seed.append(
                        {
                            "seed": seed,
                            "auc": auc,
                            "model_path": str(model_path) if model_path else None,
                        }
                    )
                    if seed == SEED:
                        primary_scores = scores
                    for local_i, sha in enumerate(te_shas):
                        pred_writer.writerow(
                            [sha, int(y_te[local_i]), float(scores[local_i]), fset, clf_name, "splitB", gid, seed, model_tag]
                        )
                assert primary_scores is not None
                pooled_scores.extend(primary_scores.tolist())
                pooled_labels.extend(y_te.tolist())
                fold_rows.append(
                    {
                        "fold": gid,
                        "n_test": int(len(te_idx)),
                        "n_malware": int(len(hold_m)),
                        "population_floor": fold_floor,
                        "per_seed": per_seed,
                        "primary_auc": per_seed[0]["auc"],
                    }
                )
            fold_aucs = [float(f["primary_auc"]["auc_floor"]) for f in fold_rows]
            w = [f["n_test"] for f in fold_rows]
            pooled_auc = _auc_with_bootstrap(pooled_scores, pooled_labels)
            fold_floors = [float(f["population_floor"]["auc_floor"]) for f in fold_rows]
            results[fset][clf_name] = {
                "folds": fold_rows,
                "mean_auc_floor": float(np.mean(fold_aucs)),
                "std_auc_floor": float(np.std(fold_aucs)),
                "weighted_mean_auc_floor": float(np.average(fold_aucs, weights=w)),
                "pooled_oof_auc": pooled_auc,
                "mean_population_floor": float(np.mean(fold_floors)),
            }
    (out_dir / f"results_{model_tag}.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _best_config(split_a: dict[str, Any], split_b: dict[str, Any]) -> tuple[str, str, str]:
    best = None
    for fset in FEATURE_SETS:
        if fset not in split_b:
            continue
        for clf, blk in split_b[fset].items():
            score = float(blk["weighted_mean_auc_floor"])
            if best is None or score > best[0]:
                best = (score, fset, clf)
    if best is None:
        # fallback to splitA if splitB unavailable
        for fset in FEATURE_SETS:
            for clf, blk in split_a[fset].items():
                score = float(blk["auc_floor_mean"])
                if best is None or score > best[0]:
                    best = (score, fset, clf)
    assert best is not None
    return best[1], best[2], "splitB"


def _run_shuffled_label_control(
    *,
    best_feature_set: str,
    best_clf: str,
    X_sets: dict[str, np.ndarray],
    apps: list[Any],
    y: np.ndarray,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    split = _stratified_split(apps, seed=SEED, test_ratio=TEST_RATIO)
    sha_to_idx = {a.sha256: i for i, a in enumerate(apps)}
    tr_idx = np.asarray([sha_to_idx[a.sha256] for a in split["train"]], dtype=np.int64)
    te_idx = np.asarray([sha_to_idx[a.sha256] for a in (split["test_benign"] + split["test_malware"])], dtype=np.int64)
    y_tr = y[tr_idx].copy()
    rng = np.random.default_rng(SEED)
    rng.shuffle(y_tr)
    clf, scores = _fit_predict(best_clf, X_sets[best_feature_set][tr_idx], y_tr, X_sets[best_feature_set][te_idx], seed=SEED)
    auc = _auc_with_bootstrap(scores.tolist(), y[te_idx].tolist())
    out = {
        "feature_set": best_feature_set,
        "classifier": best_clf,
        "split": "splitA",
        "auc": auc,
    }
    (out_dir / "shuffled_label_control.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def _extract_22_category_importance_lr_l1(
    model_path: str,
    feature_set: str,
    out_dir: Path,
) -> dict[str, Any]:
    from abrg.registry import GRAPH_CATEGORY_UNIVERSE

    out_dir.mkdir(parents=True, exist_ok=True)
    clf = joblib.load(model_path)
    if not hasattr(clf, "named_steps"):
        return {"available": False, "reason": "not_pipeline"}
    c = clf.named_steps["clf"]
    if not hasattr(c, "coef_"):
        return {"available": False, "reason": "no_coef"}
    coef = c.coef_.reshape(-1)
    scale = clf.named_steps["scaler"].scale_
    coef_orig = coef / scale

    n_cat = len(GRAPH_CATEGORY_UNIVERSE)
    cat_mass = {cat: 0.0 for cat in GRAPH_CATEGORY_UNIVERSE}
    if feature_set == "D1":
        for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
            cat_mass[cat] += abs(float(coef_orig[i]))
    elif feature_set == "D3":
        for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
            cat_mass[cat] += abs(float(coef_orig[2 * i])) + abs(float(coef_orig[2 * i + 1]))
    elif feature_set == "D4":
        for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
            cat_mass[cat] += abs(float(coef_orig[i]))
            base = n_cat + 2 * i
            cat_mass[cat] += abs(float(coef_orig[base])) + abs(float(coef_orig[base + 1]))
    elif feature_set == "D5":
        # D1 + D2 where D2 is 22x22 flattened.
        offset = n_cat
        for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
            cat_mass[cat] += abs(float(coef_orig[i]))
            row = coef_orig[offset + i * n_cat : offset + (i + 1) * n_cat]
            col = coef_orig[offset + i : offset + n_cat * n_cat : n_cat]
            cat_mass[cat] += float(np.sum(np.abs(row))) + float(np.sum(np.abs(col)))
    else:
        return {"available": False, "reason": f"feature_set_{feature_set}_not_mappable"}
    ranked = sorted(cat_mass.items(), key=lambda kv: -kv[1])
    out = {"available": True, "feature_set": feature_set, "category_abs_importance": ranked}
    (out_dir / "category_importance_t22.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def _save_predictions_header(path: Path) -> tuple[Any, csv.writer]:
    path.parent.mkdir(parents=True, exist_ok=True)
    f = path.open("w", newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow(
        [
            "app_id",
            "true_label",
            "score",
            "feature_set",
            "classifier",
            "split",
            "fold",
            "seed",
            "encoder",
        ]
    )
    return f, w


def _load_profiles_from_disk(profiles_dir: Path, tag: str) -> dict[str, Any]:
    arrays: dict[str, np.ndarray] = {}
    dims: dict[str, int] = {}
    for k in FEATURE_SETS:
        p = profiles_dir / f"{k}_{tag}.npy"
        if not p.is_file():
            raise SystemExit(f"STOP: missing profile file {p}")
        arr = np.load(p)
        arrays[k] = arr
        dims[k] = int(arr.shape[1]) if arr.ndim == 2 else 1
    return {"arrays": arrays, "dims": dims}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Experiment S2: devread")
    ap.add_argument("--out", type=Path, default=DEVREAD_OUTPUT_ROOT)
    ap.add_argument("--skip-random-init", action="store_true")
    ap.add_argument("--skip-split-a", action="store_true")
    ap.add_argument("--skip-split-b", action="store_true")
    ap.add_argument("--skip-profiles", action="store_true")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    split_bundle = load_run3_split()
    _assert_split_digest(split_bundle.sha_list_digest)

    corpus = load_corpus_cache(Path("abrg/output/androct_2017/run2"))
    split = split_apps(corpus.eligible)
    tensors = corpus.tensors
    if any(a.label != "benign" for a in split["train"]):
        raise SystemExit("STOP: GAE training split contains non-benign apps.")
    print(
        f"[devread] split train={len(split['train'])} test_b={len(split['test_benign'])} test_m={len(split['test_malware'])}",
        flush=True,
    )

    # Stage 1: load/retrain run5 and assert scalar.
    model, feature_decoder, ck_meta = _load_or_train_run5_model(
        tensors=tensors, split=split, artifacts_dir=artifacts
    )
    scalar_auc = _scalar_auc_floor(model, feature_decoder, split, tensors)
    if abs(float(scalar_auc["auc_floor"]) - RUN5_REF_AUC_FLOOR) > RUN5_REF_TOL:
        raise SystemExit(
            f"STOP: scalar AUC_floor {scalar_auc['auc_floor']:.6f} differs from 0.638 by > {RUN5_REF_TOL}"
        )
    print(f"[devread] scalar D0 auc_floor={scalar_auc['auc_floor']:.6f}", flush=True)

    # Stage 2 profiles for all eligible apps (T22)
    apps = list(split_bundle.eligible)
    shas = [a.sha256 for a in apps]
    y = np.asarray([1 if a.label == "malware" else 0 for a in apps], dtype=np.int32)
    prof_dir = artifacts / "profiles"
    if args.skip_profiles and (prof_dir / "D1_trained_t22.npy").is_file():
        prof_tr = _load_profiles_from_disk(prof_dir, "trained_t22")
    else:
        prof_tr = _build_profiles(
            model=model,
            feature_decoder=feature_decoder,
            shas=shas,
            tensors=tensors,
            out_dir=prof_dir,
            tag="trained_t22",
        )
    norm_stats = _profile_norm_stats(prof_tr["arrays"], y)

    # T1K dimensionality / tractability report only.
    from abrg.kernels.load import load_t1k

    all_shas = [a.sha256 for a in split_bundle.train + split_bundle.test_benign + split_bundle.test_malware]
    t1k = load_t1k(by_sha=split_bundle.by_sha, all_shas=all_shas)
    train_b_shas = [a.sha256 for a in split_bundle.train]
    # Cells non-zero in at least one train benign graph.
    nz_mask = np.zeros((1000, 1000), dtype=bool)
    for s in train_b_shas:
        ei = t1k[s]["edge_index"].detach().cpu().numpy()
        if ei.size:
            nz_mask[ei[0], ei[1]] = True
    t1k_dim_report = {
        "D1_dim": 1000,
        "D2_full_dim": 1000 * 1000,
        "D2_nonzero_train_benign_dim": int(nz_mask.sum()),
        "D3_dim": 2000,
        "D4_dim": 3000,
        "D5_full_dim": 1001000,
        "D5_nonzero_train_benign_dim": int(1000 + nz_mask.sum()),
    }

    # Feature sets for readout on T22.
    X_sets = {k: np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0) for k, v in prof_tr["arrays"].items()}
    raw_sets = _raw_feature_sets(tensors, apps)
    X_with_raw = dict(X_sets)
    X_with_raw.update(raw_sets)

    pred_path = artifacts / "predictions.csv"
    if args.skip_split_a and (out / "splitA" / "results_trained.json").is_file():
        splitA_trained = json.loads((out / "splitA" / "results_trained.json").read_text(encoding="utf-8"))
        pred_f = pred_path.open("a", newline="", encoding="utf-8")
        pred_w = csv.writer(pred_f)
    else:
        pred_f, pred_w = _save_predictions_header(pred_path)
    try:
        if not args.skip_split_a:
            splitA_trained = _run_split_a(
                X_sets=X_with_raw,
                y=y,
                apps=apps,
                tensors=tensors,
                out_dir=out / "splitA",
                pred_writer=pred_w,
                model_tag="trained",
            )

        ladder_assign_path = Path("abrg/output/androct_2017/ladder/grouping/route_b_behavioral.json")
        assignments = json.loads(ladder_assign_path.read_text(encoding="utf-8"))["ward"]["assignments"]
        splitB_trained = {}
        if not args.skip_split_b:
            splitb_dir = out / "splitB"
            if splitb_dir.exists():
                import shutil

                shutil.rmtree(splitb_dir / "classifiers", ignore_errors=True)
            splitB_trained = _run_split_b(
                X_sets=X_with_raw,
                y=y,
                split_b=split_bundle,
                tensors=tensors,
                assignments=assignments,
                out_dir=splitb_dir,
                pred_writer=pred_w,
                model_tag="trained",
            )
        elif (out / "splitB" / "results_trained.json").is_file():
            splitB_trained = json.loads((out / "splitB" / "results_trained.json").read_text(encoding="utf-8"))

        # Random-init GAE control.
        splitA_rand = {}
        splitB_rand = {}
        if not args.skip_random_init:
            seed_rng(SEED)
            rnd_model = build_gae(node_feature_dim(), RUN5_HIDDEN)
            rnd_model.encoder = EdgeWeightProbeEncoder(rnd_model.encoder)
            rnd_dec = FeatureDecoder(RUN5_HIDDEN, node_feature_dim())
            rnd_model.eval()
            rnd_dec.eval()
            prof_rnd = _build_profiles(
                model=rnd_model,
                feature_decoder=rnd_dec,
                shas=shas,
                tensors=tensors,
                out_dir=artifacts / "profiles",
                tag="random_init_t22",
            )
            X_rand = {k: np.nan_to_num(v, nan=0.0, posinf=0.0, neginf=0.0) for k, v in prof_rnd["arrays"].items()}
            splitA_rand = _run_split_a(
                X_sets=X_rand,
                y=y,
                apps=apps,
                tensors=tensors,
                out_dir=out / "controls" / "random_init_splitA",
                pred_writer=pred_w,
                model_tag="random_init",
            )
            splitB_rand = _run_split_b(
                X_sets=X_rand,
                y=y,
                split_b=split_bundle,
                tensors=tensors,
                assignments=assignments,
                out_dir=out / "controls" / "random_init_splitB",
                pred_writer=pred_w,
                model_tag="random_init",
            )
    finally:
        pred_f.close()

    # Shuffled-label control on best trained splitB config.
    best_fset, best_clf, _ = _best_config(splitA_trained, splitB_trained)
    shuffled = _run_shuffled_label_control(
        best_feature_set=best_fset,
        best_clf=best_clf,
        X_sets=X_sets,
        apps=apps,
        y=y,
        out_dir=out / "controls",
    )

    # Repro verification: reload one classifier and reproduce exact AUC.
    one_path = splitA_trained[best_fset][best_clf]["per_seed"][0]["model_path"]
    split_a = _stratified_split(apps, seed=SEED, test_ratio=TEST_RATIO)
    sha_to_idx = {a.sha256: i for i, a in enumerate(apps)}
    tr_idx = np.asarray([sha_to_idx[a.sha256] for a in split_a["train"]], dtype=np.int64)
    te_apps = split_a["test_benign"] + split_a["test_malware"]
    te_idx = np.asarray([sha_to_idx[a.sha256] for a in te_apps], dtype=np.int64)
    reloaded = joblib.load(one_path)
    reload_scores = reloaded.predict_proba(X_sets[best_fset][te_idx])[:, 1]
    reload_auc = _auc_with_bootstrap(reload_scores.tolist(), y[te_idx].tolist())

    # Interpretability for best T22 config with mappable features; prefer LR_L1.
    interp_path = None
    for fset in ("D4", "D5", "D3", "D1"):
        if fset in splitA_trained and "LR_L1" in splitA_trained[fset]:
            interp_path = splitA_trained[fset]["LR_L1"]["per_seed"][0]["model_path"]
            interp_feature = fset
            break
    if interp_path is None:
        interp = {"available": False}
    else:
        interp = _extract_22_category_importance_lr_l1(interp_path, interp_feature, out / "interpret")

    # Persist metadata and reproducibility.
    ckpt_path = Path(ck_meta["checkpoint_path"])
    ck_hash = _sha256_file(ckpt_path)
    reproduce = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "torch": torch.__version__,
        "seeds": list(SEEDS),
        "split_digest": split_bundle.sha_list_digest,
        "run5_pins": {
            "hidden": RUN5_HIDDEN,
            "alpha": RUN5_ALPHA,
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WD,
            "seed": SEED,
        },
        "checkpoint_used": str(ckpt_path),
        "checkpoint_sha256": ck_hash,
        "cluster_assignment_artifact": "abrg/output/androct_2017/ladder/grouping/route_b_behavioral.json",
        "scalar_auc": scalar_auc,
        "reload_verification": {
            "model_path": one_path,
            "best_feature_set": best_fset,
            "best_classifier": best_clf,
            "reloaded_auc_floor": reload_auc["auc_floor"],
            "original_auc_floor": splitA_trained[best_fset][best_clf]["per_seed"][0]["auc"]["auc_floor"],
        },
    }
    (artifacts / "reproduce_config.json").write_text(json.dumps(reproduce, indent=2) + "\n", encoding="utf-8")
    (artifacts / "reproduce.md").write_text(
        "python -m abrg.devread\n",
        encoding="utf-8",
    )
    (out / "profiles" / "norm_stats_trained_t22.json").parent.mkdir(parents=True, exist_ok=True)
    (out / "profiles" / "norm_stats_trained_t22.json").write_text(json.dumps(norm_stats, indent=2) + "\n", encoding="utf-8")
    (out / "profiles" / "t1k_dimensionality.json").write_text(json.dumps(t1k_dim_report, indent=2) + "\n", encoding="utf-8")

    # SUMMARY table.
    lines = [
        "# Experiment S2 — devread SUMMARY",
        "",
        "## Gate outcomes",
        "",
    ]
    d0_a = splitA_trained["D0"]["HGB"]["auc_floor_mean"]
    best_splitA = max(
        (
            (f, c, splitA_trained[f][c]["auc_floor_mean"])
            for f in X_sets
            for c in CLASSIFIERS
        ),
        key=lambda z: z[2],
    )
    best_splitB = max(
        (
            (f, c, splitB_trained[f][c]["weighted_mean_auc_floor"])
            for f in X_sets
            for c in CLASSIFIERS
        ),
        key=lambda z: z[2],
    )
    lines.append(f"- scalar D0 reference auc_floor: {scalar_auc['auc_floor']:.4f}")
    lines.append(f"- best deviation profile splitA: {best_splitA[0]} / {best_splitA[1]} / {best_splitA[2]:.4f}")
    lines.append(f"- best deviation profile splitB weighted: {best_splitB[0]} / {best_splitB[1]} / {best_splitB[2]:.4f}")
    lines.append(f"- raw-input control splitA HGB full: {splitA_trained['RAW_full']['HGB']['auc_floor_mean']:.4f}")
    lines.append(f"- raw-input control splitB HGB full weighted: {splitB_trained['RAW_full']['HGB']['weighted_mean_auc_floor']:.4f}")
    lines.append("")
    lines.append("## Main table")
    lines.append("")
    lines.append("| feature_set | classifier | split | trained_gae auc_mean±std | random_init_gae auc_mean±std |")
    lines.append("|---|---|---|---:|---:|")
    for fset in FEATURE_SETS + RAW_SETS:
        for clf in CLASSIFIERS:
            a = splitA_trained[fset][clf]["auc_floor_mean"]
            asd = splitA_trained[fset][clf]["auc_floor_std"]
            if splitA_rand and fset in splitA_rand:
                r = splitA_rand[fset][clf]["auc_floor_mean"]
                rsd = splitA_rand[fset][clf]["auc_floor_std"]
                rtxt = f"{r:.4f} ± {rsd:.4f}"
            else:
                rtxt = "NA"
            lines.append(f"| {fset} | {clf} | splitA | {a:.4f} ± {asd:.4f} | {rtxt} |")
            b = splitB_trained[fset][clf]["weighted_mean_auc_floor"]
            bsd = splitB_trained[fset][clf]["std_auc_floor"]
            if splitB_rand and fset in splitB_rand:
                br = splitB_rand[fset][clf]["weighted_mean_auc_floor"]
                brsd = splitB_rand[fset][clf]["std_auc_floor"]
                brtxt = f"{br:.4f} ± {brsd:.4f}"
            else:
                brtxt = "NA"
            lines.append(f"| {fset} | {clf} | splitB | {b:.4f} ± {bsd:.4f} | {brtxt} |")
    lines.extend(
        [
            "",
            "## Fixed reference rows",
            "",
            f"- D0 scalar: {RUN5_REF_AUC_FLOOR:.4f}",
            "- HGB raw full random split: 0.9762",
            "- HGB raw behavioral holdout: 0.8492 (weighted 0.8606)",
            "- OCPool_mean: 0.7765 / 0.7544",
            "- size floor: 0.7025",
            "",
            "## Shuffled-label control",
            "",
            f"- feature_set={shuffled['feature_set']} classifier={shuffled['classifier']} "
            f"auc_floor={shuffled['auc']['auc_floor']:.4f} direction={shuffled['auc']['direction']}",
            "",
            "## Repro reload check",
            "",
            f"- reloaded_auc_floor={reload_auc['auc_floor']:.6f}",
            f"- original_auc_floor={splitA_trained[best_fset][best_clf]['per_seed'][0]['auc']['auc_floor']:.6f}",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Global outputs for convenience.
    (out / "artifacts" / "summary_payload.json").write_text(
        json.dumps(
            {
                "scalar_auc": scalar_auc,
                "splitA_trained": splitA_trained,
                "splitB_trained": splitB_trained,
                "splitA_random_init": splitA_rand,
                "splitB_random_init": splitB_rand,
                "shuffled_control": shuffled,
                "interpretability": interp,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[devread] done -> {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
