"""Shared helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score, roc_curve

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.apigraph.split import load_run3_split
from abrg.final_validate import EXPECTED_SPLIT_DIGEST_PREFIX, WILD_MALWARE_BASE_RATE


def assert_digest() -> Any:
    bundle = load_run3_split()
    dig = bundle.sha_list_digest
    if not dig.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {dig[:16]}… != {EXPECTED_SPLIT_DIGEST_PREFIX}…"
        )
    print(f"[final_validate] split OK {dig[:12]}…", flush=True)
    return bundle


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def auc_raw_and_floor(scores: list[float] | np.ndarray, labels: list[int] | np.ndarray) -> dict[str, Any]:
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return {
            "auc": float("nan"),
            "auc_floor": float("nan"),
            "direction": "undefined",
        }
    a = float(roc_auc_score(y, s))
    return {
        "auc": a,
        "auc_floor": max(a, 1.0 - a),
        "direction": "malware_higher_score" if a >= 0.5 else "benign_higher_score",
    }


def tpr_at_fpr_from_scores(
    scores: np.ndarray,
    labels: np.ndarray,
    fpr_targets: tuple[float, ...],
    *,
    n_neg: int,
    n_pos: int,
    wild_pi: float = WILD_MALWARE_BASE_RATE,
) -> list[dict[str, Any]]:
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    fpr, tpr, thr = roc_curve(y, s)
    rows = []
    for target in fpr_targets:
        # largest TPR among points with fpr <= target (standard TPR@FPR<=α)
        ok = np.where(fpr <= target + 1e-15)[0]
        if ok.size:
            i = int(ok[np.argmax(tpr[ok])])
        else:
            i = 0
        fp_rate = float(fpr[i])
        tp_rate = float(tpr[i])
        threshold = float(thr[i]) if np.isfinite(thr[i]) else float("inf")
        fp = fp_rate * n_neg
        tp = tp_rate * n_pos
        prec_test = float(tp / (tp + fp)) if (tp + fp) > 0 else float("nan")
        prec_wild = float(
            (tp_rate * wild_pi) / (tp_rate * wild_pi + fp_rate * (1.0 - wild_pi))
        ) if (tp_rate * wild_pi + fp_rate * (1.0 - wild_pi)) > 0 else float("nan")
        rows.append(
            {
                "fpr_target": target,
                "fpr_achieved": fp_rate,
                "tpr": tp_rate,
                "threshold": threshold,
                "precision_test_balance_141_1700": prec_test,
                "precision_wild_base_rate": prec_wild,
                "wild_base_rate": wild_pi,
            }
        )
    return rows


def tpr_at_fpr_from_roc_points(
    roc_points: list[dict[str, Any]],
    fpr_targets: tuple[float, ...],
    *,
    n_neg: int,
    n_pos: int,
    wild_pi: float = WILD_MALWARE_BASE_RATE,
) -> list[dict[str, Any]]:
    fpr = np.asarray([p["fpr"] for p in roc_points], dtype=np.float64)
    tpr = np.asarray([p["tpr"] for p in roc_points], dtype=np.float64)
    thr = np.asarray(
        [p.get("threshold", float("nan")) for p in roc_points], dtype=np.float64
    )
    rows = []
    for target in fpr_targets:
        ok = np.where(fpr <= target + 1e-15)[0]
        if ok.size:
            i = int(ok[np.argmax(tpr[ok])])
        else:
            i = 0
        fp_rate = float(fpr[i])
        tp_rate = float(tpr[i])
        threshold = float(thr[i]) if np.isfinite(thr[i]) else float("inf")
        fp = fp_rate * n_neg
        tp = tp_rate * n_pos
        prec_test = float(tp / (tp + fp)) if (tp + fp) > 0 else float("nan")
        den = tp_rate * wild_pi + fp_rate * (1.0 - wild_pi)
        prec_wild = float((tp_rate * wild_pi) / den) if den > 0 else float("nan")
        rows.append(
            {
                "fpr_target": target,
                "fpr_achieved": fp_rate,
                "tpr": tp_rate,
                "threshold": threshold,
                "precision_test_balance_141_1700": prec_test,
                "precision_wild_base_rate": prec_wild,
                "wild_base_rate": wild_pi,
            }
        )
    return rows


def score_dist(x: np.ndarray) -> dict[str, float]:
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return {"n": 0, "median": float("nan"), "iqr": float("nan"), "min": float("nan"), "max": float("nan")}
    q25, q50, q75 = np.percentile(x, [25, 50, 75])
    return {
        "n": int(x.size),
        "median": float(q50),
        "iqr": float(q75 - q25),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "mean": float(np.mean(x)),
        "std": float(np.std(x, ddof=1) if x.size > 1 else 0.0),
    }


def eval_auc_block(scores: list[float], labels: list[int]) -> dict[str, Any]:
    return _auc_with_bootstrap(scores, labels)
