#!/usr/bin/env python3
"""Stage 2b — temperature 0.7 sampling stability arm + Stage 3 re-score."""
from __future__ import annotations

import json
import statistics
from pathlib import Path

from abrg.registry import GRAPH_CATEGORY_UNIVERSE

from score_self_cross import ROOT, score_configuration
from run_predictions import PROMPT_PATH, SEEDS, _load_apps, _pearson, run_seed

PRED_DIR = ROOT / "predictions"
TEMP07 = 0.7
CATS = list(GRAPH_CATEGORY_UNIVERSE)


def _load_temp00_predictions(seed: int = 42) -> dict[str, dict[str, float]]:
    path = PRED_DIR / f"seed_{seed}.json"
    return json.loads(path.read_text(encoding="utf-8"))["predictions"]


def _mean_across_seeds(
    by_seed: list[dict[str, dict[str, float]]], apps: list[str]
) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for app in apps:
        out[app] = {
            cat: float(statistics.mean(s[app][cat] for s in by_seed)) for cat in CATS
        }
    return out


def _stability_report(
    seeds_payload: list[dict], apps: list[dict], temp00_mean: dict[str, dict[str, float]]
) -> dict:
    app_ids = [a["app_id"] for a in apps]
    by_seed = [p["predictions"] for p in seeds_payload]
    temp07_mean = _mean_across_seeds(by_seed, app_ids)

    cell_stds: list[float] = []
    per_cat_std: dict[str, list[float]] = {c: [] for c in CATS}
    mad_from_t00: list[float] = []
    for app in app_ids:
        for cat in CATS:
            vals = [by_seed[s][app][cat] for s in range(len(by_seed))]
            sd = statistics.pstdev(vals) if len(vals) > 1 else 0.0
            cell_stds.append(sd)
            per_cat_std[cat].append(sd)
            mad_from_t00.append(
                abs(temp07_mean[app][cat] - temp00_mean[app][cat])
            )
    cat_mean_std = {c: float(statistics.mean(per_cat_std[c])) for c in CATS}
    sorted_cats = sorted(cat_mean_std.items(), key=lambda kv: -kv[1])

    flat = []
    for s in range(len(by_seed)):
        flat.append([by_seed[s][app][cat] for app in app_ids for cat in CATS])
    t00_flat = [temp00_mean[app][cat] for app in app_ids for cat in CATS]
    t07_flat = [temp07_mean[app][cat] for app in app_ids for cat in CATS]
    corrs: list[float] = []
    for i in range(len(by_seed)):
        for j in range(i + 1, len(by_seed)):
            corrs.append(_pearson(flat[i], flat[j]))

    return {
        "temperature": TEMP07,
        "seeds": SEEDS,
        "parse_success_rate_per_seed": {
            str(p["seed"]): p["parse_success_rate"] for p in seeds_payload
        },
        "cross_seed_agreement": {
            "mean_per_app_per_category_std": float(statistics.mean(cell_stds)),
            "mean_pairwise_seed_correlation": float(statistics.mean(corrs)) if corrs else float("nan"),
            "pairwise_seed_correlations": corrs,
        },
        "displacement_from_temp00": {
            "mean_absolute_difference": float(statistics.mean(mad_from_t00)),
            "correlation_temp07_mean_vs_temp00": float(_pearson(t07_flat, t00_flat)),
        },
        "per_category_cross_seed_std": cat_mean_std,
        "ipc_intents_cross_seed_std": cat_mean_std["ipc_intents"],
        "highest_cross_seed_std_categories": [
            {"category": c, "mean_per_app_std": v} for c, v in sorted_cats[:5]
        ],
        "lowest_cross_seed_std_categories": [
            {"category": c, "mean_per_app_std": v} for c, v in sorted_cats[-5:]
        ],
    }


def main() -> None:
    if not PROMPT_PATH.is_file():
        raise SystemExit(f"missing prompt template: {PROMPT_PATH}")
    template = PROMPT_PATH.read_text(encoding="utf-8")
    apps = _load_apps()
    if len(apps) != 53:
        raise SystemExit(f"expected 53 apps, got {len(apps)}")

    temp00_by_seed = []
    for seed in SEEDS:
        temp00_by_seed.append(_load_temp00_predictions(seed))
    temp00_mean = _mean_across_seeds(temp00_by_seed, [a["app_id"] for a in apps])

    seeds_payload = []
    for seed in SEEDS:
        print(f"[stage2b] temp={TEMP07} seed={seed} …", flush=True)
        payload = run_seed(seed, template, apps, temperature=TEMP07)
        out = PRED_DIR / f"temp07_seed_{seed}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        seeds_payload.append(payload)

    stability = _stability_report(seeds_payload, apps, temp00_mean)
    (ROOT / "prediction_summary_temp07.json").write_text(
        json.dumps(stability, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    scores_dir = ROOT / "scores"
    scores_dir.mkdir(parents=True, exist_ok=True)

    temp00_score = score_configuration(
        temperature=0.0,
        prediction_files=["seed_{seed}.json"],
        average_seeds=True,
    )
    temp07_score = score_configuration(
        temperature=TEMP07,
        prediction_files=["temp07_seed_{seed}.json"],
        average_seeds=True,
    )
    (scores_dir / "self_cross_temp07.json").write_text(
        json.dumps(temp07_score, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    report = {
        "stability": stability,
        "stage3_auc": {
            "temperature_0.0": temp00_score["self_cross"]["auc"],
            "temperature_0.7": temp07_score["self_cross"]["auc"],
            "population_baseline_0.0": temp00_score["population_baseline"]["auc"],
            "population_baseline_0.7": temp07_score["population_baseline"]["auc"],
        },
        "stage3_detail": {
            "temp00": temp00_score,
            "temp07": temp07_score,
        },
    }
    (ROOT / "stage2b_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
