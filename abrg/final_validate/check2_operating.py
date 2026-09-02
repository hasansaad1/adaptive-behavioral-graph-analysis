"""Check 2 — TPR at fixed FPR operating points from saved ROC / scores."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT
from abrg.final_validate import (
    FPR_POINTS,
    TEST_N_BENIGN,
    TEST_N_MALWARE,
    WILD_BASE_RATE_NOTE,
    WILD_MALWARE_BASE_RATE,
)
from abrg.final_validate.util import tpr_at_fpr_from_roc_points, write_json

OCDEV = ANDROCT_OUTPUT_ROOT / "ocdev"
LADDER = ANDROCT_OUTPUT_ROOT / "ladder"
DEVREAD = ANDROCT_OUTPUT_ROOT / "devread"
VALIDATE = ANDROCT_OUTPUT_ROOT / "validation"
RUN3 = ANDROCT_OUTPUT_ROOT / "run3"

D1_JSON = (
    OCDEV
    / "partA_profiles"
    / "splitA_trained"
    / "trained__D1__none__centroid_euclidean__splitA__foldNA.json"
)
S1_JSON = OCDEV / "partB_support" / "scores__T1K_B_docfreq.json"
OCPOOL_JSON = VALIDATE / "check1_residualization" / "check1_summary.json"
RUNG1_JSON = LADDER / "rung1" / "rung1.json"
D3_JSON = DEVREAD / "splitA" / "results_trained.json"
PRED_CSV = DEVREAD / "artifacts" / "predictions.csv"
FLOOR_JSON = RUN3 / "floors.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ops_from_auc_block(
    auc: dict[str, Any],
    *,
    name: str,
    reported_auc: float,
    n_neg: int,
    n_pos: int,
    split: str,
) -> dict[str, Any]:
    rows = tpr_at_fpr_from_roc_points(
        auc["roc_points"],
        FPR_POINTS,
        n_neg=n_neg,
        n_pos=n_pos,
    )
    tpr_at_001 = next(r["tpr"] for r in rows if r["fpr_target"] == 0.01)
    return {
        "name": name,
        "reported_auc": reported_auc,
        "artifact_auc": float(auc["auc"]),
        "artifact_auc_floor": float(auc["auc_floor"]),
        "direction": auc.get("direction"),
        "n_neg": n_neg,
        "n_pos": n_pos,
        "split": split,
        "source": "saved_roc_points",
        "operating_points": rows,
        "tpr_at_fpr_0.01": tpr_at_001,
        "test_balance_note": (
            "test is malware-heavy (inverted vs wild); "
            f"n_neg={n_neg} n_pos={n_pos}; {WILD_BASE_RATE_NOTE}"
        ),
    }


def _d3_hgb_seed42() -> dict[str, Any]:
    blob = _load_json(D3_JSON)
    per = blob["D3"]["HGB"]["per_seed"]
    seed42 = next(r for r in per if int(r["seed"]) == 42)
    auc = seed42["auc"]
    # stratified split: 141 benign / 340 malware
    n_neg = int(auc["n_neg"])
    n_pos = int(auc["n_pos"])
    return _ops_from_auc_block(
        auc,
        name="D3_profile_HGB_supervised_readout",
        reported_auc=0.9624,
        n_neg=n_neg,
        n_pos=n_pos,
        split="stratified_both_class_seed42 (not 141/1700 GAE split)",
    )


def run_check2(*, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    configs: list[dict[str, Any]] = []

    d1 = _load_json(D1_JSON)
    configs.append(
        _ops_from_auc_block(
            d1["auc"],
            name="D1_centroid_euclidean_benign_only",
            reported_auc=0.8004,
            n_neg=TEST_N_BENIGN,
            n_pos=TEST_N_MALWARE,
            split="GAE_benign_train / test_benign+test_malware",
        )
    )

    ocp = _load_json(OCPOOL_JSON)["R0"]["auc"]
    configs.append(
        _ops_from_auc_block(
            ocp,
            name="OCPool_mean",
            reported_auc=0.7765,
            n_neg=TEST_N_BENIGN,
            n_pos=TEST_N_MALWARE,
            split="GAE_benign_train / test_benign+test_malware",
        )
    )

    s1 = _load_json(S1_JSON)["S1_norm"]["auc"]
    configs.append(
        _ops_from_auc_block(
            s1,
            name="S1_norm_T1K_B_docfreq",
            reported_auc=0.7867,
            n_neg=TEST_N_BENIGN,
            n_pos=TEST_N_MALWARE,
            split="GAE_benign_train / test_benign+test_malware",
        )
    )
    configs[-1]["full_sample_point_auc"] = float(s1["auc_floor"])
    configs[-1]["thesis_form"] = "bootstrap_mean_0.7867; operating points from full-sample ROC (point 0.8226)"

    configs.append(_d3_hgb_seed42())

    rung1 = _load_json(RUNG1_JSON)
    hgb = rung1["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]
    configs.append(
        _ops_from_auc_block(
            hgb,
            name="supervised_HGB_full",
            reported_auc=0.9762,
            n_neg=int(hgb["n_neg"]),
            n_pos=int(hgb["n_pos"]),
            split="stratified_both_class_seed42 (not 141/1700 GAE split)",
        )
    )

    floor = _load_json(FLOOR_JSON)["mapped_event_count"]
    configs.append(
        _ops_from_auc_block(
            floor,
            name="mapped_event_count_floor",
            reported_auc=0.7025,
            n_neg=TEST_N_BENIGN,
            n_pos=TEST_N_MALWARE,
            split="GAE_benign_train / test_benign+test_malware",
        )
    )

    csv_path = out / "tpr_at_fpr.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "name",
                "reported_auc",
                "artifact_auc",
                "n_neg",
                "n_pos",
                "fpr_target",
                "fpr_achieved",
                "tpr",
                "threshold",
                "precision_test_balance",
                "precision_wild_pi_0.01",
            ]
        )
        for c in configs:
            for r in c["operating_points"]:
                w.writerow(
                    [
                        c["name"],
                        c["reported_auc"],
                        c["artifact_auc"],
                        c["n_neg"],
                        c["n_pos"],
                        r["fpr_target"],
                        r["fpr_achieved"],
                        r["tpr"],
                        r["threshold"],
                        r["precision_test_balance_141_1700"],
                        r["precision_wild_base_rate"],
                    ]
                )

    payload = {
        "wild_malware_base_rate": WILD_MALWARE_BASE_RATE,
        "wild_base_rate_note": WILD_BASE_RATE_NOTE,
        "test_class_balance_note": (
            "GAE-split headlines use 141 benign / 1700 malware (malware-heavy). "
            "Wild precision uses Bayes with pi=0.01 (benign-heavy). "
            "Supervised D3+HGB and HGB-full use stratified split (141 benign / 340 malware)."
        ),
        "fpr_targets": list(FPR_POINTS),
        "configurations": configs,
        "tpr_at_fpr_0.01": {c["name"]: c["tpr_at_fpr_0.01"] for c in configs},
    }
    write_json(out / "check2.json", payload)
    return payload
