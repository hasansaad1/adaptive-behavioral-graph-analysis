"""Compare recomputed desc_seed metrics to frozen reproduce_config expected values."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from abrg.desc_seed.metrics import recompute_all_metrics

DEFAULT_ATOL = 1e-3


def _flatten_expected(expected: dict[str, Any], prefix: str = "") -> dict[str, float]:
    flat: dict[str, float] = {}
    for key, val in expected.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            if "auc" in val and len(val) <= 4:
                if val.get("auc") is not None:
                    flat[f"{path}.auc"] = float(val["auc"])
                if "mean_predicted" in val:
                    flat[f"{path}.mean_predicted"] = float(val["mean_predicted"])
                if "fire_count" in val:
                    flat[f"{path}.fire_count"] = float(val["fire_count"])
            else:
                flat.update(_flatten_expected(val, path))
        elif isinstance(val, (int, float)) and val is not None:
            flat[path] = float(val)
        elif isinstance(val, list) and val and isinstance(val[0], (int, float)):
            for i, item in enumerate(val):
                flat[f"{path}[{i}]"] = float(item)
    return flat


def _flatten_actual(actual: dict[str, Any]) -> dict[str, float]:
    expected_shape = {
        "self_cross.cosine_temp00_auc": actual["self_cross"]["cosine_temp00_auc"],
        "self_cross.cosine_temp07_auc": actual["self_cross"]["cosine_temp07_auc"],
        "self_cross.mean_self_cosine_temp00": actual["self_cross"]["mean_self_cosine_temp00"],
        "self_cross.mean_cross_cosine_temp00": actual["self_cross"]["mean_cross_cosine_temp00"],
        "self_cross.population_mean_profile_temp00_auc": actual["self_cross"][
            "population_mean_profile_temp00_auc"
        ],
        "self_cross.mass_active_over_all": actual["self_cross"]["mass_active_over_all"],
        "self_cross.jaccard_threshold_0_5": actual["self_cross"]["jaccard_threshold_0_5"],
        "self_cross.active_minus_inactive_mean": actual["self_cross"][
            "active_minus_inactive_mean"
        ],
        "ceiling.distinct_profiles": float(actual["ceiling"]["distinct_profiles"]),
        "ceiling.n_duplicate_groups": float(actual["ceiling"]["n_duplicate_groups"]),
        "ceiling.apps_in_duplicate_groups": float(
            actual["ceiling"]["apps_in_duplicate_groups"]
        ),
        "ceiling.max_attainable_auc": actual["ceiling"]["max_attainable_auc"],
        "ceiling.observed_fraction_of_ceiling": actual["ceiling"][
            "observed_fraction_of_ceiling"
        ],
        "within_app.model_median": actual["within_app"]["model_median"],
        "within_app.model_mean": actual["within_app"]["model_mean"],
        "within_app.model_iqr": actual["within_app"]["model_iqr"],
        "within_app.model_min": actual["within_app"]["model_min"],
        "within_app.model_max": actual["within_app"]["model_max"],
        "within_app.model_above_0_5": float(actual["within_app"]["model_above_0_5"]),
        "within_app.prior_median": actual["within_app"]["prior_median"],
        "within_app.prior_mean": actual["within_app"]["prior_mean"],
        "within_app.prior_iqr": actual["within_app"]["prior_iqr"],
        "within_app.prior_min": actual["within_app"]["prior_min"],
        "within_app.prior_max": actual["within_app"]["prior_max"],
        "within_app.prior_above_0_5": float(actual["within_app"]["prior_above_0_5"]),
        "within_app.median_delta_model_minus_prior": actual["within_app"][
            "median_delta_model_minus_prior"
        ],
        "within_app.prior_wins": float(actual["within_app"]["prior_wins"]),
        "within_app.model_beats_prior": float(actual["within_app"]["model_beats_prior"]),
        "within_app.spearman_rho_delta_vs_prior_baseline": actual["within_app"][
            "spearman_rho_delta_vs_prior_baseline"
        ],
        "within_app.spearman_p_value": actual["within_app"]["spearman_p_value"],
        "stability_temp00.mean_per_app_per_category_std": actual["stability_temp00"][
            "mean_per_app_per_category_std"
        ],
        "stability_temp00.mean_pairwise_seed_correlation": actual["stability_temp00"][
            "mean_pairwise_seed_correlation"
        ],
        "stability_temp07.mean_per_app_per_category_std": actual["stability_temp07"][
            "mean_per_app_per_category_std"
        ],
        "stability_temp07.mean_pairwise_seed_correlation": actual["stability_temp07"][
            "mean_pairwise_seed_correlation"
        ],
        "stability_temp07.mean_absolute_displacement_from_temp00": actual[
            "stability_temp07"
        ]["mean_absolute_displacement_from_temp00"],
        "stability_temp07.correlation_temp07_mean_vs_temp00": actual["stability_temp07"][
            "correlation_temp07_mean_vs_temp00"
        ],
    }
    for cat, block in actual["per_category"].items():
        expected_shape[f"per_category.{cat}.fire_count"] = float(block["fire_count"])
        expected_shape[f"per_category.{cat}.mean_predicted"] = float(
            block["mean_predicted"]
        )
        if block.get("auc") is not None:
            expected_shape[f"per_category.{cat}.auc"] = float(block["auc"])
    dup_sizes = actual["ceiling"].get("duplicate_group_sizes") or []
    for i, size in enumerate(dup_sizes):
        expected_shape[f"ceiling.duplicate_group_sizes[{i}]"] = float(size)
    return expected_shape


def compare_metrics(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    atol: float = DEFAULT_ATOL,
) -> dict[str, Any]:
    exp_flat = _flatten_expected(expected)
    act_flat = _flatten_actual(actual)
    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for key, exp_val in sorted(exp_flat.items()):
        act_val = act_flat.get(key)
        if act_val is None:
            rows.append(
                {
                    "metric": key,
                    "expected": exp_val,
                    "actual": None,
                    "delta": None,
                    "match": False,
                }
            )
            mismatches.append(key)
            continue
        delta = act_val - exp_val
        match = abs(delta) <= atol
        rows.append(
            {
                "metric": key,
                "expected": exp_val,
                "actual": act_val,
                "delta": delta,
                "match": match,
            }
        )
        if not match:
            mismatches.append(key)
    ok = len(mismatches) == 0 and all(
        math.isfinite(v) for v in act_flat.values() if v is not None
    )
    return {
        "ok": ok,
        "kind": "desc_seed",
        "atol": atol,
        "n_metrics": len(rows),
        "n_mismatch": len(mismatches),
        "mismatches": mismatches,
        "rows": rows,
    }


def validate_run_dir(run_dir: Path, *, atol: float | None = None) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    config = json.loads((run_dir / "reproduce_config.json").read_text(encoding="utf-8"))
    expected = config["expected"]
    tol = float(atol if atol is not None else config.get("atol", DEFAULT_ATOL))
    actual = recompute_all_metrics(run_dir)
    report = compare_metrics(expected, actual, atol=tol)
    report["mode"] = "desc_seed_recompute"
    report["run_dir"] = str(run_dir)
    return report
