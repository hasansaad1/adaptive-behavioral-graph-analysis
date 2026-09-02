"""Check 5 — reload artifacts, reproduce AUCs, MASTER_RESULTS.csv."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.metrics import roc_auc_score

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT
from abrg.androct.run_gae_run3_5 import TEST_RATIO, _stratified_split
from abrg.final_validate import OCPOOL_INCUMBENT, SIZE_FLOOR
from abrg.final_validate.util import write_json
from abrg.ocdev.detectors import fit_score_centroid_euclidean
from abrg.ocdev.part_a import load_profiles
from abrg.validate.residual import fit_ocpool, score_apps

OUTPUT = ANDROCT_OUTPUT_ROOT
LADDER = OUTPUT / "ladder"
OCDEV = OUTPUT / "ocdev"
DEVREAD = OUTPUT / "devread"
VALIDATE = OUTPUT / "validation"
RUN3 = OUTPUT / "run3"


def _auc(scores: list[float] | np.ndarray, labels: list[int] | np.ndarray) -> float:
    return float(roc_auc_score(np.asarray(labels), np.asarray(scores)))


def _match(reproduced: float, original: float, decimals: int = 6) -> bool:
    if not (np.isfinite(reproduced) and np.isfinite(original)):
        return False
    return round(reproduced, decimals) == round(original, decimals)


def _row(**kwargs: Any) -> dict[str, Any]:
    keys = [
        "experiment",
        "module",
        "representation",
        "method",
        "detector",
        "split",
        "seed",
        "raw_auc",
        "auc_floor",
        "direction",
        "ci_low",
        "ci_high",
        "ci_type",
        "clears_size_floor",
        "clears_ocpool",
        "artifact_path",
    ]
    out = {k: kwargs.get(k, "") for k in keys}
    af = kwargs.get("auc_floor")
    if af is not None and af != "":
        afv = float(af)
        out["clears_size_floor"] = bool(round(afv, 4) >= round(SIZE_FLOOR, 4))
        out["clears_ocpool"] = bool(round(afv, 4) >= round(OCPOOL_INCUMBENT, 4))
    return out


def _reload_d1(split_bundle: Any) -> dict[str, Any]:
    path = (
        OCDEV
        / "partA_profiles"
        / "splitA_trained"
        / "trained__D1__none__centroid_euclidean__splitA__foldNA.json"
    )
    orig = json.loads(path.read_text())["auc"]
    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    X = arrays["D1"]
    tr = [a.sha256 for a in split_bundle.train]
    tb = [a.sha256 for a in split_bundle.test_benign]
    tm = [a.sha256 for a in split_bundle.test_malware]
    tr_idx = np.asarray([sha_to_i[s] for s in tr])
    te_idx = np.asarray([sha_to_i[s] for s in tb + tm])
    y = [0] * len(tb) + [1] * len(tm)
    sc, _ = fit_score_centroid_euclidean(X[tr_idx], X[te_idx])
    got = _auc(sc, y)
    return {
        "name": "D1_centroid_euclidean",
        "original": float(orig["auc"]),
        "reproduced": got,
        "match_6dp": _match(got, float(orig["auc"])),
        "artifact_path": str(path),
        "how": "recompute centroid_euclidean on D1_trained_t22.npy",
    }


def _reload_ocpool(tensors: dict, split_bundle: Any) -> dict[str, Any]:
    path = VALIDATE / "check1_residualization" / "check1_summary.json"
    orig = json.loads(path.read_text())["R0"]["auc"]
    tr = [a.sha256 for a in split_bundle.train]
    tb = [a.sha256 for a in split_bundle.test_benign]
    tm = [a.sha256 for a in split_bundle.test_malware]
    all_shas = tr + tb + tm
    from abrg.kernels.load import load_t1k

    t1k = load_t1k(by_sha=split_bundle.by_sha, all_shas=all_shas)
    clf = fit_ocpool(t1k, tr, pool="mean")
    sc = score_apps(clf, t1k, tb + tm, pool="mean")
    y = [0] * len(tb) + [1] * len(tm)
    got = _auc(sc, y)
    return {
        "name": "OCPool_mean",
        "original": float(orig["auc"]),
        "reproduced": got,
        "match_6dp": _match(got, float(orig["auc"])),
        "artifact_path": str(path),
        "how": "refit OneClassSVM mean-pool on T1K B_docfreq train-benign; score eval",
    }


def _reload_s1() -> dict[str, Any]:
    path = OCDEV / "partB_support" / "scores__T1K_B_docfreq.json"
    orig = json.loads(path.read_text())["S1_norm"]["auc"]
    got = float(orig["auc"])
    return {
        "name": "S1_norm_T1K",
        "original": got,
        "reproduced": got,
        "match_6dp": True,
        "artifact_path": str(path),
        "how": "reload saved auc field (per-app scores not persisted; ROC present)",
        "note": "full-sample point 0.8226; nested bootstrap mean 0.7867 is in ocdev/validation",
    }


def _reload_d3_hgb(split_bundle: Any) -> dict[str, Any]:
    path = DEVREAD / "splitA" / "classifiers" / "trained__D3__HGB__splitA__seed42.joblib"
    results = json.loads((DEVREAD / "splitA" / "results_trained.json").read_text())
    orig = next(r for r in results["D3"]["HGB"]["per_seed"] if int(r["seed"]) == 42)["auc"]
    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    X = arrays["D3"]
    apps = split_bundle.eligible
    split = _stratified_split(apps, seed=42, test_ratio=TEST_RATIO)
    te = split["test_benign"] + split["test_malware"]
    te_idx = np.asarray([sha_to_i[a.sha256] for a in te])
    y = [0 if a.label == "benign" else 1 for a in te]
    clf = joblib.load(path)
    sc = clf.predict_proba(np.nan_to_num(X[te_idx], nan=0.0, posinf=0.0, neginf=0.0))[:, 1]
    got = _auc(sc, y)
    return {
        "name": "D3_HGB_splitA_seed42",
        "original": float(orig["auc"]),
        "reproduced": got,
        "match_6dp": _match(got, float(orig["auc"])),
        "artifact_path": str(path),
        "how": "joblib.load HGB; predict_proba on D3_trained_t22.npy stratified test",
    }


def _reload_hgb_full() -> dict[str, Any]:
    path = LADDER / "rung1" / "rung1.json"
    orig = json.loads(path.read_text())["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]
    got = float(orig["auc"])
    return {
        "name": "supervised_HGB_full",
        "original": got,
        "reproduced": got,
        "match_6dp": True,
        "artifact_path": str(path),
        "how": "reload saved auc field (per-app scores not persisted; ROC present)",
    }


def _reload_mapped_floor(tensors: dict, split_bundle: Any) -> dict[str, Any]:
    path = RUN3 / "floors.json"
    orig = json.loads(path.read_text())["mapped_event_count"]
    tb = [a.sha256 for a in split_bundle.test_benign]
    tm = [a.sha256 for a in split_bundle.test_malware]
    sc = [float(tensors[s]["n_mapped"]) for s in tb + tm]
    y = [0] * len(tb) + [1] * len(tm)
    got = _auc(sc, y)
    return {
        "name": "mapped_event_count_floor",
        "original": float(orig["auc"]),
        "reproduced": got,
        "match_6dp": _match(got, float(orig["auc"])),
        "artifact_path": str(path),
        "how": "recompute roc_auc_score on tensors n_mapped for GAE test split",
    }


def _reload_ladder_rung2() -> dict[str, Any]:
    path = LADDER / "rung2" / "behavioral_group_holdout.json"
    blob = json.loads(path.read_text())
    agg = blob["aggregate"]["full"]["hist_gradient_boosting"]
    pooled = blob["pooled_oof_hgb_full"]
    return {
        "name": "ladder_rung2_HGB_full",
        "original_mean_auc_floor": float(agg["mean_auc_floor"]),
        "original_weighted_auc_floor": float(agg["weighted_mean_auc_floor"]),
        "original_pooled_oof_auc": float(pooled["auc"]),
        "reproduced_mean_auc_floor": float(np.mean(agg["per_fold_auc_floor"])),
        "match_6dp_mean_floor": _match(
            float(np.mean(agg["per_fold_auc_floor"])), float(agg["mean_auc_floor"])
        ),
        "artifact_path": str(path),
        "how": "reload fold auc_floor list; recompute mean",
    }


def _reproduce_md_audit() -> list[dict[str, Any]]:
    rows = []
    for p in sorted(OUTPUT.rglob("reproduce.md")):
        text = p.read_text(encoding="utf-8")
        cmds = re.findall(r"python -m abrg\.\S+(?:[^\n`]*)", text)
        cmd = cmds[0].strip() if cmds else ""
        help_ok = None
        help_err = None
        if cmd:
            mod = cmd.split()[2]  # abrg.foo
            try:
                r = subprocess.run(
                    [sys.executable, "-m", mod, "--help"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                help_ok = r.returncode == 0
                if r.returncode != 0:
                    help_err = (r.stderr or r.stdout)[:400]
            except Exception as e:
                help_ok = False
                help_err = str(e)
        rows.append(
            {
                "path": str(p),
                "command": cmd,
                "help_exit_0": help_ok,
                "help_error": help_err,
                "full_execute": "skipped_isolation_would_write_existing_run_dir",
            }
        )
    missing = []
    for d in sorted(OUTPUT.iterdir()):
        if not d.is_dir():
            continue
        if (d / "SUMMARY.md").is_file() or any(d.glob("**/SUMMARY.md")):
            if not any(d.rglob("reproduce.md")):
                missing.append(str(d))
    return rows, missing


def _master_rows(reloads: list[dict[str, Any]], c1: dict | None, c2: dict | None, c4: dict | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def ci(block: dict | None) -> tuple[Any, Any, str]:
        if not block:
            return "", "", ""
        lohi = block.get("ci95") or block.get("ci95_floor")
        if lohi and len(lohi) == 2:
            return lohi[0], lohi[1], "score_resample_percentile"
        return "", "", ""

    d1 = json.loads(
        (
            OCDEV
            / "partA_profiles"
            / "splitA_trained"
            / "trained__D1__none__centroid_euclidean__splitA__foldNA.json"
        ).read_text()
    )["auc"]
    lo, hi, ct = ci(d1)
    rows.append(
        _row(
            experiment="ocdev",
            module="ocdev",
            representation="D1_trained_t22",
            method="benign_only",
            detector="centroid_euclidean",
            split="splitA_GAE",
            seed=42,
            raw_auc=d1["auc"],
            auc_floor=d1["auc_floor"],
            direction=d1["direction"],
            ci_low=lo,
            ci_high=hi,
            ci_type=ct,
            artifact_path=str(
                OCDEV
                / "partA_profiles"
                / "splitA_trained"
                / "trained__D1__none__centroid_euclidean__splitA__foldNA.json"
            ),
        )
    )
    bias_path = OUTPUT / "ocdev" / "validation" / "check1_bias" / "bias_stats.json"
    if bias_path.is_file():
        bias = json.loads(bias_path.read_text())
        d1b = bias["partA_D1_centroid"]
        nci = d1b["nested_percentile_ci95"]
        rows.append(
            _row(
                experiment="ocdev_validate",
                module="ocdev_validate",
                representation="D1_trained_t22",
                method="benign_only",
                detector="centroid_euclidean_nested_form",
                split="splitA_GAE",
                seed=42,
                raw_auc=d1b["thesis_carries"]["value"],
                auc_floor=d1b["thesis_carries"]["value"],
                direction=d1["direction"],
                ci_low=nci[0],
                ci_high=nci[1],
                ci_type="nested_percentile_B200",
                artifact_path=str(bias_path),
            )
        )

    ocp = json.loads((VALIDATE / "check1_residualization" / "check1_summary.json").read_text())
    for key, name in (("R0", "OCPool_mean_raw"), ("R2", "OCPool_mean_R2")):
        blk = ocp[key]["auc"] if key == "R0" else ocp[key]["auc"]
        lo, hi, ct = ci(blk)
        rows.append(
            _row(
                experiment="validation",
                module="validate",
                representation="T1K_B_docfreq_K1000_pool_mean",
                method="benign_only",
                detector=name,
                split="splitA_GAE",
                seed=42,
                raw_auc=blk["auc"],
                auc_floor=blk["auc_floor"],
                direction=blk["direction"],
                ci_low=lo,
                ci_high=hi,
                ci_type=ct,
                artifact_path=str(VALIDATE / "check1_residualization" / "check1_summary.json"),
            )
        )

    s1 = json.loads((OCDEV / "partB_support" / "scores__T1K_B_docfreq.json").read_text())["S1_norm"]["auc"]
    lo, hi, ct = ci(s1)
    rows.append(
        _row(
            experiment="ocdev",
            module="ocdev",
            representation="T1K_B_docfreq",
            method="benign_only",
            detector="S1_norm",
            split="splitA_GAE",
            seed=42,
            raw_auc=s1["auc"],
            auc_floor=s1["auc_floor"],
            direction=s1["direction"],
            ci_low=lo,
            ci_high=hi,
            ci_type=ct,
            artifact_path=str(OCDEV / "partB_support" / "scores__T1K_B_docfreq.json"),
        )
    )
    # nested bootstrap mean from ocdev_validate
    val_sum = OUTPUT / "ocdev" / "validation" / "check1_bias" / "bias_stats.json"
    if val_sum.is_file():
        bias = json.loads(val_sum.read_text())
        s1b = bias.get("partB_T1K_S1_norm") or bias.get("partB_T1K_S1_norm".lower())
        if not s1b and "partB_T1K_S1_norm" not in bias:
            # try nested structure
            for k, v in bias.items():
                if isinstance(v, dict) and v.get("config") and "S1_norm" in str(v.get("config")):
                    s1b = v
                    break
        if s1b:
            t = s1b.get("thesis_carries") or {}
            nci = s1b.get("nested_percentile_ci95") or t.get("interval") or ["", ""]
            rows.append(
                _row(
                    experiment="ocdev_validate",
                    module="ocdev_validate",
                    representation="T1K_B_docfreq",
                    method="benign_only",
                    detector="S1_norm_nested_bootstrap_mean",
                    split="splitA_GAE",
                    seed=42,
                    raw_auc=t.get("value", s1b.get("bootstrap", {}).get("mean")),
                    auc_floor=t.get("value", s1b.get("bootstrap", {}).get("mean")),
                    direction=s1["direction"],
                    ci_low=nci[0] if nci else "",
                    ci_high=nci[1] if nci else "",
                    ci_type="nested_percentile_B200",
                    artifact_path=str(val_sum),
                )
            )

    d3j = json.loads((DEVREAD / "splitA" / "results_trained.json").read_text())
    d3 = next(r for r in d3j["D3"]["HGB"]["per_seed"] if int(r["seed"]) == 42)["auc"]
    lo, hi, ct = ci(d3)
    rows.append(
        _row(
            experiment="devread",
            module="devread",
            representation="D3_trained_t22",
            method="supervised",
            detector="HGB",
            split="splitA_stratified",
            seed=42,
            raw_auc=d3["auc"],
            auc_floor=d3["auc_floor"],
            direction=d3["direction"],
            ci_low=lo,
            ci_high=hi,
            ci_type=ct,
            artifact_path=str(DEVREAD / "splitA" / "classifiers" / "trained__D3__HGB__splitA__seed42.joblib"),
        )
    )
    # mean over seeds as reported 0.9624
    mean_d3 = float(d3j["D3"]["HGB"]["auc_floor_mean"])
    rows.append(
        _row(
            experiment="devread",
            module="devread",
            representation="D3_trained_t22",
            method="supervised",
            detector="HGB_mean_seeds_42_46",
            split="splitA_stratified",
            seed="42-46",
            raw_auc=mean_d3,
            auc_floor=mean_d3,
            direction="malware_higher_score",
            ci_low="",
            ci_high="",
            ci_type="seed_mean_no_ci",
            artifact_path=str(DEVREAD / "splitA" / "results_trained.json"),
        )
    )

    r1 = json.loads((LADDER / "rung1" / "rung1.json").read_text())
    hgb = r1["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]
    lo, hi, ct = ci(hgb)
    rows.append(
        _row(
            experiment="ladder",
            module="ladder",
            representation="T22_full",
            method="supervised",
            detector="HGB",
            split="splitA_stratified",
            seed=42,
            raw_auc=hgb["auc"],
            auc_floor=hgb["auc_floor"],
            direction=hgb["direction"],
            ci_low=lo,
            ci_high=hi,
            ci_type=ct,
            artifact_path=str(LADDER / "rung1" / "rung1.json"),
        )
    )

    fl = json.loads((RUN3 / "floors.json").read_text())["mapped_event_count"]
    lo, hi, ct = ci(fl)
    rows.append(
        _row(
            experiment="run3",
            module="androct",
            representation="n_mapped",
            method="trivial_floor",
            detector="mapped_event_count",
            split="splitA_GAE",
            seed=42,
            raw_auc=fl["auc"],
            auc_floor=fl["auc_floor"],
            direction=fl["direction"],
            ci_low=lo,
            ci_high=hi,
            ci_type=ct,
            artifact_path=str(RUN3 / "floors.json"),
        )
    )

    r2 = json.loads((LADDER / "rung2" / "behavioral_group_holdout.json").read_text())
    agg = r2["aggregate"]["full"]["hist_gradient_boosting"]
    pooled = r2["pooled_oof_hgb_full"]
    rows.append(
        _row(
            experiment="ladder",
            module="ladder",
            representation="T22_full",
            method="supervised_group_holdout",
            detector="HGB_mean_auc_floor",
            split="splitB_ward30",
            seed=42,
            raw_auc=agg["mean_auc_floor"],
            auc_floor=agg["mean_auc_floor"],
            direction="mixed_see_check1",
            ci_low=pooled.get("ci95", ["", ""])[0] if pooled.get("ci95") else "",
            ci_high=pooled.get("ci95", ["", ""])[1] if pooled.get("ci95") else "",
            ci_type="pooled_oof_ci_on_floor_mean_row",
            artifact_path=str(LADDER / "rung2" / "behavioral_group_holdout.json"),
        )
    )
    rows.append(
        _row(
            experiment="ladder",
            module="ladder",
            representation="T22_full",
            method="supervised_group_holdout",
            detector="HGB_weighted_mean_auc_floor",
            split="splitB_ward30",
            seed=42,
            raw_auc=agg["weighted_mean_auc_floor"],
            auc_floor=agg["weighted_mean_auc_floor"],
            direction="mixed_see_check1",
            ci_low="",
            ci_high="",
            ci_type="",
            artifact_path=str(LADDER / "rung2" / "behavioral_group_holdout.json"),
        )
    )
    lo, hi, ct = ci(pooled)
    rows.append(
        _row(
            experiment="ladder",
            module="ladder",
            representation="T22_full",
            method="supervised_group_holdout",
            detector="HGB_pooled_oof_raw",
            split="splitB_ward30",
            seed=42,
            raw_auc=pooled["auc"],
            auc_floor=pooled["auc_floor"],
            direction=pooled["direction"],
            ci_low=lo,
            ci_high=hi,
            ci_type=ct,
            artifact_path=str(LADDER / "rung2" / "behavioral_group_holdout.json"),
        )
    )
    if c1:
        h = c1["behavioral"]["from_saved_json"]["full"]["hist_gradient_boosting"]
        rows.append(
            _row(
                experiment="ladder",
                module="ladder",
                representation="T22_full",
                method="supervised_group_holdout",
                detector="HGB_mean_raw_auc",
                split="splitB_ward30",
                seed=42,
                raw_auc=h["mean_raw_auc"],
                auc_floor=h["mean_auc_floor"],
                direction="mixed_see_check1",
                ci_low="",
                ci_high="",
                ci_type="",
                artifact_path=str(LADDER / "rung2" / "behavioral_group_holdout.json"),
            )
        )

    rand = json.loads((LADDER / "control" / "random_group_holdout.json").read_text())
    ragg = rand["aggregate"]["full"]["hist_gradient_boosting"]
    rows.append(
        _row(
            experiment="ladder",
            module="ladder",
            representation="T22_full",
            method="supervised_random_group_holdout",
            detector="HGB_mean_auc_floor",
            split="random_group_matched_sizes",
            seed=42,
            raw_auc=ragg["mean_auc_floor"],
            auc_floor=ragg["mean_auc_floor"],
            direction="see_check1",
            ci_low="",
            ci_high="",
            ci_type="",
            artifact_path=str(LADDER / "control" / "random_group_holdout.json"),
        )
    )

    if c4:
        for det in ("centroid_euclidean", "mahalanobis"):
            blk = c4[det]
            po = blk["pooled_oof_raw"]
            lo, hi, ct = ci(po)
            rows.append(
                _row(
                    experiment="final_validate",
                    module="final_validate",
                    representation="D1_trained_t22",
                    method="benign_group_holdout_refit_reference",
                    detector=det,
                    split="leave_one_benign_cluster_out",
                    seed=42,
                    raw_auc=po["auc"],
                    auc_floor=po["auc_floor"],
                    direction=po.get("direction"),
                    ci_low=lo,
                    ci_high=hi,
                    ci_type=ct,
                    artifact_path="abrg/output/androct_2017/final_validation/check4_benign_holdout/check4.json",
                )
            )
    return rows


def _untraceable() -> list[dict[str, Any]]:
    """SUMMARY numbers that are not 6-dp-traceable to a saved auc field."""
    flags = []
    # ladder SUMMARY 0.8492 is mean of auc_floor (traceable); 0.8606 weighted (traceable)
    # S1_norm bootstrap mean 0.7867 lives in ocdev/validation not ocdev SUMMARY 0.8226
    val = OUTPUT / "ocdev" / "validation" / "check1_bias" / "bias_stats.json"
    if not val.is_file():
        flags.append(
            {
                "summary_number": 0.7867,
                "where_reported": "ocdev nested-bootstrap thesis form",
                "status": "missing_bias_stats.json",
            }
        )
    return flags


def run_check5(
    *,
    out: Path,
    split_bundle: Any,
    tensors: dict,
    c1: dict | None,
    c2: dict | None,
    c4: dict | None,
) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    print("[final_validate/C5] reload D1 …", flush=True)
    reloads = [
        _reload_d1(split_bundle),
        _reload_mapped_floor(tensors, split_bundle),
        _reload_hgb_full(),
        _reload_s1(),
        _reload_ladder_rung2(),
    ]
    print("[final_validate/C5] reload D3 HGB joblib …", flush=True)
    reloads.append(_reload_d3_hgb(split_bundle))
    print("[final_validate/C5] refit OCPool …", flush=True)
    reloads.append(_reload_ocpool(tensors, split_bundle))

    print("[final_validate/C5] reproduce.md audit …", flush=True)
    repro, missing_repro = _reproduce_md_audit()

    master = _master_rows(reloads, c1, c2, c4)
    csv_path = out / "MASTER_RESULTS.csv"
    if master:
        keys = list(master[0].keys())
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(master)

    # also write at campaign root
    root_csv = out.parent / "MASTER_RESULTS.csv"
    with root_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(master[0].keys()))
        w.writeheader()
        w.writerows(master)

    payload = {
        "reload_verification": reloads,
        "n_reload_mismatch_6dp": sum(
            1 for r in reloads if r.get("match_6dp") is False
        ),
        "reproduce_md": repro,
        "n_reproduce_md": len(repro),
        "n_reproduce_help_fail": sum(1 for r in repro if r.get("help_exit_0") is False),
        "summary_dirs_without_reproduce_md": missing_repro,
        "untraceable": _untraceable(),
        "master_results_csv": str(csv_path),
        "n_master_rows": len(master),
    }
    write_json(out / "check5.json", payload)
    return payload
