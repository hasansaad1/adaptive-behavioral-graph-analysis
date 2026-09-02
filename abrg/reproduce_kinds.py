"""Kind-specific reproduce config, metric extraction, and validation."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

DEFAULT_ATOL_MEDIAN = 0.02
DEFAULT_ATOL_RATIO = 0.05
DEFAULT_ATOL_AUC_FLOOR = 0.02


def get_nested(data: dict[str, Any], path: str) -> Any:
    cur: Any = data
    for key in path.split("."):
        cur = cur[key]
    return cur


def primary_arm_metrics(comparison: dict[str, Any]) -> dict[str, float]:
    arm = comparison.get("normalized_v021") or comparison.get("summary") or comparison
    train = arm.get("train_error") or {}
    test = arm.get("test_error") or {}
    train_med = float(train["median"])
    test_med = float(test["median"])
    ratio = arm.get("train_vs_test_median_ratio")
    if ratio is None:
        ratio = test_med / train_med if train_med else float("nan")
    return {"train_med": train_med, "test_med": test_med, "ratio": float(ratio)}


def primary_negative_control_metrics(results: dict[str, Any]) -> dict[str, float]:
    arm = results["models"]["normalized_v021"]["cells"]["impossible_edge"]
    return {
        "impossible_edge_auc": float(arm["auc"]),
        "impossible_edge_median_delta": float(arm["median_delta"]),
    }


def _best_run5_metrics(comparison: dict[str, Any]) -> dict[str, Any]:
    by_hidden = comparison.get("by_hidden") or {}
    best_h = None
    best_floor = -1.0
    best_dir = ""
    for h, block in by_hidden.items():
        auc = block["auc"]
        floor = float(auc["auc_floor"])
        if floor > best_floor:
            best_floor = floor
            best_h = h
            best_dir = str(auc["direction"])
    return {
        "auc_floor": best_floor,
        "direction": best_dir,
        "inverted": best_dir == "benign_higher_score",
        "best_hidden": best_h,
    }


def _best_oneclass_metrics(comparison: dict[str, Any]) -> dict[str, Any]:
    methods = comparison.get("methods") or {}
    best_name = None
    best_floor = -1.0
    best_dir = ""
    for name, block in methods.items():
        floor = float(block["auc_floor"])
        if floor > best_floor:
            best_floor = floor
            best_name = name
            best_dir = str(block["direction"])
    return {
        "auc_floor": best_floor,
        "direction": best_dir,
        "inverted": best_dir == "benign_higher_score",
        "best_method": best_name,
    }


def primary_androct_metrics(comparison: dict[str, Any], profile: str) -> dict[str, Any]:
    if profile == "arm_mean":
        auc = comparison["auc_by_aggregation"]["mean"]["auc"]
        return {
            "auc_floor": float(auc["auc_floor"]),
            "direction": str(auc["direction"]),
            "inverted": auc["direction"] == "benign_higher_score",
        }
    if profile == "run4_best":
        return {
            "auc_floor": float(comparison["best_auc_floor"]),
            "direction": "benign_higher_score",
            "inverted": True,
            "best_alpha": comparison.get("best_alpha_by_auc_floor"),
        }
    if profile == "run5_best":
        return _best_run5_metrics(comparison)
    if profile == "run3_5_hgb_full":
        m = comparison["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]
        return {
            "auc_floor": float(m["auc_floor"]),
            "direction": str(m["direction"]),
            "inverted": m["direction"] == "benign_higher_score",
        }
    if profile == "run6_part1_hgb":
        m = (
            comparison["conditions"]["a_baseline"]["modes"]["full"]["models"][
                "hist_gradient_boosting"
            ]
        )
        return {
            "auc_floor": float(m["auc_floor"]),
            "direction": str(m["direction"]),
            "inverted": m["direction"] == "benign_higher_score",
        }
    if profile == "run6_part2_centroid_raw":
        block = comparison["centroid_distance"]["euclidean_to_raw_centroid"][
            "auc_distance_as_score"
        ]
        return {
            "auc_floor": float(block["auc_floor"]),
            "direction": str(block["direction"]),
            "inverted": block["direction"] == "benign_higher_score",
        }
    if profile == "run6_part3_armB_mean":
        m = comparison["primary"]["aggregation"]["mean"]["auc"]
        return {
            "auc_floor": float(m["auc_floor"]),
            "direction": str(m["direction"]),
            "inverted": m["direction"] == "benign_higher_score",
        }
    if profile == "run6_centroid_baseline":
        b = comparison["baseline"]
        return {
            "auc_floor": float(b["auc_floor"]),
            "direction": str(b["direction"]),
            "inverted": b["direction"] == "benign_higher_score",
        }
    if profile == "run6_oneclass_best":
        return _best_oneclass_metrics(comparison)
    if profile == "run6_ipc_act_v":
        m = comparison["ipc_act_v_frac_auc"]
        return {
            "auc_floor": float(m["auc_floor"]),
            "direction": str(m["direction"]),
            "inverted": m["direction"] == "benign_higher_score",
        }
    if profile == "run8_best":
        b = comparison["best_scorer"]
        return {
            "auc_floor": float(b["auc_floor"]),
            "direction": str(b["direction"]),
            "inverted": bool(b.get("inverted", b["direction"] == "benign_higher_score")),
        }
    if profile == "gae_default":
        auc = comparison["auc"]
        return {
            "auc_floor": float(auc["auc_floor"]),
            "direction": str(auc["direction"]),
            "inverted": auc["direction"] == "benign_higher_score",
        }
    raise ValueError(f"unknown androct profile: {profile}")


def extract_metrics_from_result(
    data: dict[str, Any], *, kind: str, profile: str = ""
) -> dict[str, Any]:
    if kind == "ratio":
        return primary_arm_metrics(data)
    if kind == "negative_control":
        return primary_negative_control_metrics(data)
    if kind == "androct_auc":
        return primary_androct_metrics(data, profile)
    if kind == "desc_seed":
        return data
    raise ValueError(f"unknown kind: {kind}")


def compare_kind_metrics(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    kind: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    if kind == "ratio":
        diffs = {
            "Δtrain_med": actual["train_med"] - expected["train_med"],
            "Δtest_med": actual["test_med"] - expected["test_med"],
            "Δratio": actual["ratio"] - expected["ratio"],
        }
        ok = (
            abs(diffs["Δtrain_med"]) <= float(config.get("atol_median", DEFAULT_ATOL_MEDIAN))
            and abs(diffs["Δtest_med"]) <= float(config.get("atol_median", DEFAULT_ATOL_MEDIAN))
            and abs(diffs["Δratio"]) <= float(config.get("atol_ratio", DEFAULT_ATOL_RATIO))
            and all(math.isfinite(v) for v in actual.values())
        )
        return {
            "ok": ok,
            "expected": expected,
            "actual": actual,
            "diffs": diffs,
            "kind": kind,
        }

    if kind == "negative_control":
        atol = float(config.get("atol_auc", 0.02))
        diffs = {
            "Δimpossible_edge_auc": actual["impossible_edge_auc"] - expected["impossible_edge_auc"],
            "Δimpossible_edge_median_delta": actual["impossible_edge_median_delta"]
            - expected["impossible_edge_median_delta"],
        }
        ok = (
            abs(diffs["Δimpossible_edge_auc"]) <= atol
            and abs(diffs["Δimpossible_edge_median_delta"]) <= 0.05
        )
        return {"ok": ok, "expected": expected, "actual": actual, "diffs": diffs, "kind": kind}

    if kind == "androct_auc":
        atol = float(config.get("atol_auc_floor", DEFAULT_ATOL_AUC_FLOOR))
        diffs = {"Δauc_floor": actual["auc_floor"] - expected["auc_floor"]}
        dir_ok = actual.get("direction") == expected.get("direction")
        ok = abs(diffs["Δauc_floor"]) <= atol and dir_ok
        return {
            "ok": ok,
            "expected": expected,
            "actual": actual,
            "diffs": diffs,
            "direction_match": dir_ok,
            "kind": kind,
        }

    if kind == "desc_seed":
        from abrg.desc_seed.validate import compare_metrics

        return compare_metrics(
            expected,
            actual,
            atol=float(config.get("atol", 0.001)),
        )

    raise ValueError(f"unknown kind: {kind}")


def result_json_name(kind: str) -> str:
    if kind == "negative_control":
        return "negative_control_results.json"
    if kind == "desc_seed":
        return "scoring_results.json"
    return "comparison.json"


def cli_argv_from_config(config: dict[str, Any], output_dir: Path) -> list[str]:
    kind = config.get("kind", "ratio")
    argv: list[str] = ["-m", config["cli_module"]]
    extra = config.get("cli_extra") or []
    argv.extend(extra)

    if kind == "ratio":
        pins = config["pins"]
        argv.extend(
            [
                "--epochs",
                str(int(pins["epochs"])),
                "--hidden",
                str(int(pins.get("hidden", 16))),
                "--lr",
                str(float(pins.get("lr", 0.01))),
                "--weight-decay",
                str(float(pins.get("weight_decay", 0.0))),
                "--k-burst",
                str(int(pins.get("k_burst", 5))),
                "--delta-sec",
                str(float(pins.get("delta_sec", 5.0))),
                "--lambda-rec",
                str(float(pins.get("lambda_rec", 0.01))),
                "--edge-weight-channel",
                str(pins.get("edge_weight_channel", "w_cum")),
                "--window-sec",
                str(float(pins["window_sec"])),
                "--seed",
                str(int(pins["seed"])),
                "--test-ratio",
                str(float(pins["test_ratio"])),
                "--output-dir",
                str(output_dir),
            ]
        )
        if pins.get("snapshots", True):
            argv.append("--snapshots")
        else:
            argv.append("--no-snapshots")
        if pins.get("drop_never_active_nodes", False):
            argv.append("--drop-never-active-nodes")
        else:
            argv.append("--no-drop-never-active-nodes")
        if pins.get("edge_weight_in_encoder", True):
            argv.append("--use-edge-weight")
        else:
            argv.append("--no-use-edge-weight")
        return argv

    if kind == "negative_control":
        pins = config.get("pins") or {}
        argv.extend(
            [
                "--seed",
                str(int(pins.get("seed", 42))),
                "--test-ratio",
                str(float(pins.get("test_ratio", 0.2))),
                "--window-sec",
                str(float(pins.get("window_sec", 60.0))),
                "--output-dir",
                str(output_dir),
            ]
        )
        if pins.get("edge_weight_in_encoder", config.get("edge_weight", False)):
            argv.append("--use-edge-weight")
        else:
            argv.append("--no-use-edge-weight")
        return argv

    if kind == "androct_auc":
        argv.extend(["--output-dir", str(output_dir)])
        return argv

    if kind == "desc_seed":
        run_dir = output_dir.parent
        argv.extend(
            [
                "--run-dir",
                str(run_dir),
                "--output",
                str(output_dir / "scoring_results.json"),
            ]
        )
        return argv

    raise ValueError(f"unknown kind for cli argv: {kind}")


def config_from_comparison_ratio(
    comparison: dict[str, Any],
    *,
    run_id: str,
    axis: str,
    cli_module: str = "abrg.compare_normalization_ab",
    edge_weight: bool | None = None,
) -> dict[str, Any]:
    pinned = comparison.get("pinned") or {}
    if edge_weight is None:
        edge_weight = bool(
            pinned.get(
                "gae_uses_edge_weight",
                comparison.get("normalized_v021", {}).get("edge_weight_in_encoder", True),
            )
        )
    return {
        "kind": "ratio",
        "run_id": run_id,
        "axis": axis,
        "cli_module": cli_module,
        "scorer": "stochastic",
        "dataset": comparison.get("dataset"),
        "sessions_dir": comparison.get("sessions_dir"),
        "pins": {
            "window_sec": pinned.get("window_sec", 60.0),
            "epochs": pinned.get("epochs", 300),
            "hidden": pinned.get("hidden", 16),
            "lr": pinned.get("lr", 0.01),
            "weight_decay": pinned.get("weight_decay", 0.0),
            "k_burst": pinned.get("k_burst", 5),
            "delta_sec": pinned.get("delta_sec", 5.0),
            "lambda_rec": pinned.get("lambda_rec", 0.01),
            "edge_weight_channel": pinned.get("edge_weight_channel", "w_cum"),
            "snapshots": pinned.get("snapshots", True),
            "drop_never_active_nodes": pinned.get("drop_never_active_nodes", False),
            "seed": pinned.get("seed", 42),
            "test_ratio": pinned.get("test_ratio", 0.2),
            "edge_weight_in_encoder": edge_weight,
        },
        "primary_arm": "normalized_v021",
        "expected": primary_arm_metrics(comparison),
        "atol_median": DEFAULT_ATOL_MEDIAN,
        "atol_ratio": DEFAULT_ATOL_RATIO,
    }


def config_for_androct(
    run_dir: Path,
    *,
    run_id: str,
    axis: str,
    cli_module: str,
    profile: str,
    cli_extra: list[str] | None = None,
) -> dict[str, Any]:
    comparison = json.loads((run_dir / "comparison.json").read_text(encoding="utf-8"))
    return {
        "kind": "androct_auc",
        "run_id": run_id,
        "axis": axis,
        "cli_module": cli_module,
        "profile": profile,
        "cli_extra": cli_extra or [],
        "expected": primary_androct_metrics(comparison, profile),
        "atol_auc_floor": DEFAULT_ATOL_AUC_FLOOR,
    }


def config_for_negative_control(run_dir: Path, *, run_id: str, axis: str) -> dict[str, Any]:
    results = json.loads((run_dir / "negative_control_results.json").read_text(encoding="utf-8"))
    weighted = "weighted" in run_id
    return {
        "kind": "negative_control",
        "run_id": run_id,
        "axis": axis,
        "cli_module": "abrg.negative_control",
        "dataset": results.get("dataset", "v2"),
        "edge_weight": weighted,
        "pins": {
            "seed": int(results.get("seed", 42)),
            "test_ratio": 0.2,
            "window_sec": 60.0,
            "edge_weight_in_encoder": weighted,
        },
        "expected": primary_negative_control_metrics(results),
        "atol_auc": 0.02,
    }
