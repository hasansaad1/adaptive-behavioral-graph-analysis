"""Recompute desc_seed scoring from frozen predictions + observed matrix."""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score

from abrg.registry import GRAPH_CATEGORY_UNIVERSE

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUN_DIR = REPO_ROOT / "abrg" / "output" / "desc_seed"

EXCLUDED = {
    "ai.susi",
    "at.mikenet.serbianlatintocyrillic",
    "br.odb.knights",
    "buet.rafi.dictionary",
    "cat.jordihernandez.cinecat",
    "app.fedilab.nitterizeme",
}
SEEDS = [42, 43, 44, 45, 46]
CATS = list(GRAPH_CATEGORY_UNIVERSE)


def run_dir_paths(run_dir: Path) -> dict[str, Path]:
    run_dir = run_dir.resolve()
    return {
        "run_dir": run_dir,
        "observed": run_dir / "observed" / "observed_59x22.csv",
        "predictions": run_dir / "predictions",
        "prompt_template": run_dir / "prompt_template.txt",
        "metadata_fdroid": run_dir / "metadata" / "fdroid_59.json",
        "metadata_packages": run_dir / "metadata" / "packages_59.json",
        "summary_temp07": run_dir / "prediction_summary_temp07.json",
        "summary_temp00": run_dir / "prediction_summary.json",
    }


def load_observed(obs_path: Path) -> tuple[list[str], np.ndarray]:
    rows = []
    with obs_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["app_id"] in EXCLUDED:
                continue
            rows.append(row)
    rows.sort(key=lambda r: r["app_id"])
    app_ids = [r["app_id"] for r in rows]
    obs = np.asarray([[float(r[c]) for c in CATS] for r in rows], dtype=np.float64)
    return app_ids, obs


def load_predictions_from_seeds(
    pred_dir: Path,
    pattern: str,
    *,
    average_seeds: bool,
) -> dict[str, dict[str, float]]:
    by_seed: list[dict[str, dict[str, float]]] = []
    for seed in SEEDS:
        path = pred_dir / pattern.format(seed=seed)
        payload = json.loads(path.read_text(encoding="utf-8"))
        by_seed.append(payload["predictions"])
    apps = sorted(set(by_seed[0]) & set.intersection(*[set(s) for s in by_seed[1:]]))
    if not average_seeds:
        return {a: by_seed[0][a] for a in apps}
    out: dict[str, dict[str, float]] = {}
    for app in apps:
        out[app] = {
            cat: float(statistics.mean(by_seed[s][app][cat] for s in range(len(by_seed))))
            for cat in CATS
        }
    return out


def predictions_to_matrix(
    app_ids: list[str], predictions: dict[str, dict[str, float]]
) -> np.ndarray:
    return np.asarray(
        [[float(predictions[app][c]) for c in CATS] for app in app_ids],
        dtype=np.float64,
    )


def cosine_rows(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_norm = np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = np.linalg.norm(b, axis=1, keepdims=True)
    a_n = np.divide(a, a_norm, out=np.zeros_like(a), where=a_norm > 0)
    b_n = np.divide(b, b_norm, out=np.zeros_like(b), where=b_norm > 0)
    return a_n @ b_n.T


def self_cross_auc_from_matrix(score_mat: np.ndarray) -> float:
    n = score_mat.shape[0]
    labels: list[int] = []
    scores: list[float] = []
    for i in range(n):
        labels.append(1)
        scores.append(float(score_mat[i, i]))
        for j in range(n):
            if i == j:
                continue
            labels.append(0)
            scores.append(float(score_mat[i, j]))
    return float(roc_auc_score(labels, scores))


def self_cross_cosine(pred: np.ndarray, obs: np.ndarray) -> dict[str, float]:
    sim = cosine_rows(pred, obs)
    n = sim.shape[0]
    self_sims = [float(sim[i, i]) for i in range(n)]
    cross_sims = [float(sim[i, j]) for i in range(n) for j in range(n) if i != j]
    return {
        "auc": self_cross_auc_from_matrix(sim),
        "mean_self_cosine": float(statistics.mean(self_sims)),
        "mean_cross_cosine": float(statistics.mean(cross_sims)),
    }


def population_mean_profile_auc(pred: np.ndarray, obs: np.ndarray) -> float:
    pop = np.mean(pred, axis=0, keepdims=True)
    sim = cosine_rows(pop, obs)
    n = obs.shape[0]
    labels = [1] * n + [0] * (n * (n - 1))
    scores = [float(sim[0, i]) for i in range(n)] + [
        float(sim[0, j]) for i in range(n) for j in range(n) if i != j
    ]
    return float(roc_auc_score(labels, scores))


def alternative_scorers_temp00(pred: np.ndarray, obs: np.ndarray) -> dict[str, float]:
    n = pred.shape[0]
    pred_sum = pred.sum(axis=1, keepdims=True)
    mass = (pred @ obs.T) / np.where(pred_sum > 0, pred_sum, np.nan)
    pred_bin = (pred >= 0.5).astype(np.float64)
    inter = pred_bin @ obs.T
    union = pred_bin.sum(axis=1, keepdims=True) + obs.sum(axis=1, keepdims=True).T - inter
    jacc = np.divide(inter, union, out=np.zeros_like(inter), where=union > 0)
    score_c = np.full((n, n), np.nan)
    for j in range(n):
        active = obs[j] > 0
        inactive = ~active
        score_c[:, j] = pred[:, active].mean(axis=1) - pred[:, inactive].mean(axis=1)
    return {
        "mass_active_over_all": self_cross_auc_from_matrix(mass),
        "jaccard_threshold_0_5": self_cross_auc_from_matrix(jacc),
        "active_minus_inactive_mean": self_cross_auc_from_matrix(score_c),
    }


def profile_ceiling(obs: np.ndarray) -> dict[str, Any]:
    profiles = [tuple(int(x) for x in obs[i]) for i in range(obs.shape[0])]
    counts = Counter(profiles)
    dup_sizes = sorted((c for c in counts.values() if c > 1), reverse=True)
    labels: list[int] = []
    scores: list[float] = []
    n = len(profiles)
    for i in range(n):
        labels.append(1)
        scores.append(1.0)
        for j in range(n):
            if i == j:
                continue
            labels.append(0)
            scores.append(1.0 if profiles[i] == profiles[j] else 0.0)
    max_auc = float(roc_auc_score(labels, scores))
    return {
        "distinct_profiles": len(counts),
        "n_duplicate_groups": len(dup_sizes),
        "duplicate_group_sizes": dup_sizes,
        "apps_in_duplicate_groups": int(sum(dup_sizes)),
        "max_attainable_auc": max_auc,
    }


def within_app_metrics(pred: np.ndarray, obs: np.ndarray) -> dict[str, Any]:
    pop_rate = obs.mean(axis=0)
    model_aucs: list[float] = []
    prior_aucs: list[float] = []
    for i in range(obs.shape[0]):
        y = obs[i]
        model_aucs.append(float(roc_auc_score(y, pred[i])))
        prior_aucs.append(float(roc_auc_score(y, pop_rate)))
    deltas = [m - p for m, p in zip(model_aucs, prior_aucs)]
    rho, pval = spearmanr(prior_aucs, deltas)
    arr_m = np.array(model_aucs)
    arr_p = np.array(prior_aucs)
    return {
        "model_median": float(np.median(arr_m)),
        "model_mean": float(arr_m.mean()),
        "model_iqr": float(np.percentile(arr_m, 75) - np.percentile(arr_m, 25)),
        "model_min": float(arr_m.min()),
        "model_max": float(arr_m.max()),
        "model_above_0_5": int((arr_m > 0.5).sum()),
        "prior_median": float(np.median(arr_p)),
        "prior_mean": float(arr_p.mean()),
        "prior_iqr": float(np.percentile(arr_p, 75) - np.percentile(arr_p, 25)),
        "prior_min": float(arr_p.min()),
        "prior_max": float(arr_p.max()),
        "prior_above_0_5": int((arr_p > 0.5).sum()),
        "median_delta_model_minus_prior": float(np.median(deltas)),
        "prior_wins": int(sum(1 for d in deltas if d < 0)),
        "model_beats_prior": int(sum(1 for d in deltas if d > 0)),
        "spearman_rho_delta_vs_prior_baseline": float(rho),
        "spearman_p_value": float(pval),
    }


def per_category_metrics(pred: np.ndarray, obs: np.ndarray) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for k, cat in enumerate(CATS):
        y = obs[:, k]
        p = pred[:, k]
        fc = int(y.sum())
        entry: dict[str, Any] = {
            "fire_count": fc,
            "mean_predicted": float(p.mean()),
        }
        if fc == 0:
            entry["auc"] = None
            entry["status"] = "undefined"
        elif fc < 5:
            entry["auc"] = float(roc_auc_score(y, p))
            entry["status"] = "unstable"
        else:
            entry["auc"] = float(roc_auc_score(y, p))
            entry["status"] = "stable"
        out[cat] = entry
    return out


def stability_from_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    cross = payload.get("cross_seed_agreement") or {}
    disp = payload.get("displacement_from_temp00") or {}
    return {
        "mean_per_app_per_category_std": cross.get("mean_per_app_per_category_std"),
        "mean_pairwise_seed_correlation": cross.get("mean_pairwise_seed_correlation"),
        "mean_absolute_displacement_from_temp00": disp.get("mean_absolute_difference"),
        "correlation_temp07_mean_vs_temp00": disp.get("correlation_temp07_mean_vs_temp00"),
        "parse_success_rate_per_seed": payload.get("parse_success_rate_per_seed"),
    }


def recompute_all_metrics(run_dir: Path | None = None) -> dict[str, Any]:
    paths = run_dir_paths(run_dir or DEFAULT_RUN_DIR)
    run_dir = paths["run_dir"]
    app_ids, obs = load_observed(paths["observed"])
    pred_dir = paths["predictions"]
    pred00 = predictions_to_matrix(
        app_ids,
        load_predictions_from_seeds(pred_dir, "seed_{seed}.json", average_seeds=True),
    )
    pred07 = predictions_to_matrix(
        app_ids,
        load_predictions_from_seeds(pred_dir, "temp07_seed_{seed}.json", average_seeds=True),
    )

    sc00 = self_cross_cosine(pred00, obs)
    sc07 = self_cross_cosine(pred07, obs)
    alt = alternative_scorers_temp00(pred00, obs)
    ceiling = profile_ceiling(obs)
    ceiling["observed_fraction_of_ceiling"] = sc00["auc"] / ceiling["max_attainable_auc"]
    within = within_app_metrics(pred00, obs)
    per_cat = per_category_metrics(pred00, obs)

    prompt_hash = hashlib.sha256(paths["prompt_template"].read_bytes()).hexdigest()
    temp00_summary = json.loads(paths["summary_temp00"].read_text(encoding="utf-8"))
    stability_temp07 = stability_from_summary(paths["summary_temp07"])

    return {
        "run_dir": str(run_dir),
        "n_apps": len(app_ids),
        "app_ids": app_ids,
        "prompt_template_sha256": prompt_hash,
        "self_cross": {
            "cosine_temp00_auc": sc00["auc"],
            "cosine_temp07_auc": sc07["auc"],
            "mean_self_cosine_temp00": sc00["mean_self_cosine"],
            "mean_cross_cosine_temp00": sc00["mean_cross_cosine"],
            "population_mean_profile_temp00_auc": population_mean_profile_auc(pred00, obs),
            **alt,
        },
        "ceiling": ceiling,
        "within_app": within,
        "per_category": per_cat,
        "stability_temp00": {
            "mean_per_app_per_category_std": temp00_summary.get(
                "mean_per_app_per_category_std"
            ),
            "mean_pairwise_seed_correlation": temp00_summary.get(
                "mean_pairwise_seed_correlation"
            ),
        },
        "stability_temp07": stability_temp07,
    }
