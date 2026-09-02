"""Rung 1–2 supervised runs and random-group control."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from abrg.androct.run_gae_run3_5 import _stratified_split, SEED, TEST_RATIO
from abrg.apigraph.split import SplitBundle
from abrg.ladder import HARNESS_TOLERANCE, MODES, MODELS, REF_ROWS, SEEDS
from abrg.ladder.floors import labels_for_shas, mapped_event_floor
from abrg.ladder.models import fit_multi_seed_hgb, fit_supervised
from abrg.ladder.vectorize import apps_for_shas, cosine_leakage, vectorize_shas


def _check_harness(result: dict[str, Any]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    targets = {
        "full": REF_ROWS["supervised_HGB_full"],
        "adj_only": REF_ROWS["supervised_HGB_adj_only"],
    }
    stop = False
    for mode, ref in targets.items():
        got = float(
            result["modes"][mode]["models"]["hist_gradient_boosting"]["auc"]["auc_floor"]
        )
        delta = abs(got - ref)
        ok = delta <= HARNESS_TOLERANCE
        checks.append(
            {
                "mode": mode,
                "reference_auc_floor": ref,
                "got_auc_floor": got,
                "delta": delta,
                "within_tolerance": ok,
            }
        )
        if not ok:
            stop = True
    return {"checks": checks, "stop": stop, "tolerance": HARNESS_TOLERANCE}


def run_rung1(
    tensors: dict[str, dict[str, Any]],
    split_b: SplitBundle,
    out_dir: Any,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    eligible = split_b.eligible
    split = _stratified_split(eligible, seed=SEED, test_ratio=TEST_RATIO)
    train_apps = split["train"]
    test_apps = split["test_benign"] + split["test_malware"]
    train_shas = [a.sha256 for a in train_apps]
    test_shas = [a.sha256 for a in test_apps]
    by_sha = split_b.by_sha

    result: dict[str, Any] = {
        "rung": 1,
        "assumption": "supervised_random_split",
        "split": "stratified_both_class seed=42 test_ratio=0.2",
        "n_train": len(train_shas),
        "n_test": len(test_shas),
        "modes": {},
        "harness": None,
    }

    for mode in MODES:
        X_tr, y_tr, names = vectorize_shas(tensors, train_shas, by_sha, mode=mode)
        X_te, y_te, _ = vectorize_shas(tensors, test_shas, by_sha, mode=mode)
        mode_block: dict[str, Any] = {"models": {}}
        for model_name in MODELS:
            if model_name == "hist_gradient_boosting":
                multi = fit_multi_seed_hgb(X_tr, y_tr, X_te, y_te)
                primary = multi["runs"][0]
                mode_block["models"][model_name] = {
                    "primary_seed": SEED,
                    "auc": primary["auc"],
                    "multi_seed": {
                        "mean_auc_floor": multi["mean_auc_floor"],
                        "std_auc_floor": multi["std_auc_floor"],
                        "per_seed_auc_floor": multi["per_seed_auc_floor"],
                    },
                }
            else:
                r = fit_supervised(
                    X_tr,
                    y_tr,
                    X_te,
                    y_te,
                    model_name=model_name,
                    seed=SEED,
                    compute_importance=(mode == "full"),
                    names=names,
                )
                mode_block["models"][model_name] = {
                    "auc": r["auc"],
                    **({"importance": r["importance"]} if r.get("importance") else {}),
                }
        floors = mapped_event_floor(
            tensors, test_shas, labels_for_shas(test_shas, by_sha)
        )
        mode_block["mapped_event_floor"] = floors
        result["modes"][mode] = mode_block

    harness = _check_harness(result)
    result["harness"] = harness
    (out_dir / "rung1.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if harness["stop"]:
        (out_dir / "HARNESS_FAIL.json").write_text(
            json.dumps(harness, indent=2) + "\n", encoding="utf-8"
        )
    return result


def _assignments_to_groups(assignments: dict[str, int]) -> dict[int, list[str]]:
    groups: dict[int, list[str]] = {}
    for sha, gid in assignments.items():
        groups.setdefault(int(gid), []).append(sha)
    return groups


def random_group_assignments(
    malware_shas: list[str],
    cluster_sizes: dict[str, int],
    *,
    seed: int = SEED,
) -> dict[str, int]:
    rng = np.random.default_rng(seed)
    shuffled = list(malware_shas)
    rng.shuffle(shuffled)
    sizes = sorted([int(v) for v in cluster_sizes.values()], reverse=True)
    assignments: dict[str, int] = {}
    idx = 0
    for gid, sz in enumerate(sizes):
        for _ in range(sz):
            if idx >= len(shuffled):
                break
            assignments[shuffled[idx]] = gid
            idx += 1
    # any remainder
    while idx < len(shuffled):
        assignments[shuffled[idx]] = len(sizes)
        idx += 1
    return assignments


def run_group_holdout(
    tensors: dict[str, dict[str, Any]],
    split_b: SplitBundle,
    assignments: dict[str, int],
    *,
    label: str,
    out_dir: Any,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    train_benign = [a.sha256 for a in split_b.train]
    test_benign = [a.sha256 for a in split_b.test_benign]
    all_malware = [a.sha256 for a in split_b.test_malware]
    by_sha = split_b.by_sha
    groups = _assignments_to_groups(assignments)

    fold_results: list[dict[str, Any]] = []
    pooled_scores: list[float] = []
    pooled_labels: list[int] = []

    for gid in sorted(groups.keys()):
        hold_m = groups[gid]
        train_m = [s for s in all_malware if s not in hold_m]
        train_shas = train_benign + train_m
        test_shas = test_benign + hold_m
        y_test = labels_for_shas(test_shas, by_sha)
        floor = mapped_event_floor(tensors, test_shas, y_test)
        leakage = cosine_leakage(hold_m, train_m, tensors)

        fold_block: dict[str, Any] = {
            "group_id": gid,
            "n_malware_holdout": len(hold_m),
            "n_test": len(test_shas),
            "mapped_event_floor": floor,
            "leakage": leakage,
            "modes": {},
        }

        for mode in MODES:
            X_tr, y_tr, _ = vectorize_shas(tensors, train_shas, by_sha, mode=mode)
            X_te, y_te, _ = vectorize_shas(tensors, test_shas, by_sha, mode=mode)
            mode_res: dict[str, Any] = {}
            for model_name in MODELS:
                if model_name == "hist_gradient_boosting":
                    multi = fit_multi_seed_hgb(X_tr, y_tr, X_te, y_te)
                    primary = multi["runs"][0]
                    mode_res[model_name] = {
                        "auc": primary["auc"],
                        "multi_seed": {
                            "mean_auc_floor": multi["mean_auc_floor"],
                            "std_auc_floor": multi["std_auc_floor"],
                        },
                    }
                    scores = primary["scores"]
                else:
                    r = fit_supervised(
                        X_tr, y_tr, X_te, y_te, model_name=model_name, seed=SEED
                    )
                    mode_res[model_name] = {"auc": r["auc"]}
                    scores = r["scores"]
                if model_name == "hist_gradient_boosting" and mode == "full":
                    pooled_scores.extend(scores)
                    pooled_labels.extend(y_te.tolist())

            fold_block["modes"][mode] = mode_res

        fold_results.append(fold_block)

    # aggregate AUC across folds (mean of per-fold auc_floor)
    aggregate: dict[str, Any] = {}
    for mode in MODES:
        aggregate[mode] = {}
        for model_name in MODELS:
            aucs = [
                float(f["modes"][mode][model_name]["auc"]["auc_floor"])
                for f in fold_results
            ]
            weights = [f["n_test"] for f in fold_results]
            wsum = sum(weights)
            wmean = sum(a * w for a, w in zip(aucs, weights)) / wsum if wsum else float("nan")
            aggregate[mode][model_name] = {
                "per_fold_auc_floor": aucs,
                "mean_auc_floor": float(np.mean(aucs)),
                "std_auc_floor": float(np.std(aucs)),
                "weighted_mean_auc_floor": float(wmean),
            }

    from abrg.androct.run_gae_run2 import _auc_with_bootstrap

    pooled = _auc_with_bootstrap(pooled_scores, pooled_labels)

    # leakage vs AUC correlation (HGB full)
    fold_aucs = [
        float(f["modes"]["full"]["hist_gradient_boosting"]["auc"]["auc_floor"])
        for f in fold_results
    ]
    fold_sims = [float(f["leakage"]["mean_pairwise_cosine"]) for f in fold_results]
    if len(fold_aucs) >= 2:
        corr = float(np.corrcoef(fold_sims, fold_aucs)[0, 1])
    else:
        corr = float("nan")

    result = {
        "label": label,
        "n_folds": len(fold_results),
        "folds": fold_results,
        "aggregate": aggregate,
        "pooled_oof_hgb_full": pooled,
        "leakage_auc_correlation_hgb_full": corr,
    }
    (out_dir / f"{label}.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    return result


def run_rung2(
    tensors: dict[str, dict[str, Any]],
    split_b: SplitBundle,
    route_b: dict[str, Any],
    out_dir: Any,
    control_dir: Any,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)
    beh_path = out_dir / "behavioral_group_holdout.json"
    if beh_path.is_file():
        behavioral = json.loads(beh_path.read_text(encoding="utf-8"))
    else:
        ward_assign = route_b["ward"]["assignments"]
        behavioral = run_group_holdout(
            tensors,
            split_b,
            ward_assign,
            label="behavioral_group_holdout",
            out_dir=out_dir,
        )
    random_path = control_dir / "random_group_holdout.json"
    if random_path.is_file():
        random = json.loads(random_path.read_text(encoding="utf-8"))
    else:
        random_assign = random_group_assignments(
            [a.sha256 for a in split_b.test_malware],
            route_b["ward"]["cluster_sizes"],
            seed=SEED,
        )
        (control_dir / "random_assignments.json").write_text(
            json.dumps(random_assign, indent=2) + "\n", encoding="utf-8"
        )
        random = run_group_holdout(
            tensors,
            split_b,
            random_assign,
            label="random_group_holdout",
            out_dir=control_dir,
        )
    return {"behavioral": behavioral, "random": random}
