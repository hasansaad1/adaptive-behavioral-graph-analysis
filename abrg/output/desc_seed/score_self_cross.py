#!/usr/bin/env python3
"""Stage 3 — self-versus-cross AUC for description-predicted behavioural profiles."""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from abrg.registry import GRAPH_CATEGORY_UNIVERSE

ROOT = Path(__file__).resolve().parent
OBS_PATH = ROOT / "observed" / "observed_59x22.csv"
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


def _load_observed() -> tuple[list[str], np.ndarray]:
    rows = []
    with OBS_PATH.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["app_id"] in EXCLUDED:
                continue
            rows.append(row)
    rows.sort(key=lambda r: r["app_id"])
    app_ids = [r["app_id"] for r in rows]
    obs = np.asarray([[float(r[c]) for c in CATS] for r in rows], dtype=np.float64)
    return app_ids, obs


def _cosine_rows(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Row-wise cosine similarity between (n, d) and (m, d) -> (n, m)."""
    a_norm = np.linalg.norm(a, axis=1, keepdims=True)
    b_norm = np.linalg.norm(b, axis=1, keepdims=True)
    a_n = np.divide(a, a_norm, out=np.zeros_like(a), where=a_norm > 0)
    b_n = np.divide(b, b_norm, out=np.zeros_like(b), where=b_norm > 0)
    return a_n @ b_n.T


def _self_cross_auc(pred: np.ndarray, obs: np.ndarray) -> dict:
    """Self pairs on diagonal; cross pairs off-diagonal. Score = cosine similarity."""
    sim = _cosine_rows(pred, obs)
    n = sim.shape[0]
    labels: list[int] = []
    scores: list[float] = []
    self_sims: list[float] = []
    cross_sims: list[float] = []
    for i in range(n):
        labels.append(1)
        scores.append(float(sim[i, i]))
        self_sims.append(float(sim[i, i]))
        for j in range(n):
            if i == j:
                continue
            labels.append(0)
            scores.append(float(sim[i, j]))
            cross_sims.append(float(sim[i, j]))
    auc = float(roc_auc_score(labels, scores))
    return {
        "auc": auc,
        "n_apps": n,
        "n_self_pairs": n,
        "n_cross_pairs": n * (n - 1),
        "mean_self_cosine": float(statistics.mean(self_sims)),
        "mean_cross_cosine": float(statistics.mean(cross_sims)),
        "median_self_cosine": float(statistics.median(self_sims)),
        "median_cross_cosine": float(statistics.median(cross_sims)),
        "self_minus_cross_mean": float(statistics.mean(self_sims) - statistics.mean(cross_sims)),
    }


def _population_baseline_auc(pred: np.ndarray, obs: np.ndarray) -> dict:
    """Population mean predicted profile vs each observed (same score for all apps)."""
    pop = np.mean(pred, axis=0, keepdims=True)
    sim = _cosine_rows(pop, obs).ravel()
    n = obs.shape[0]
    labels = [1] * n + [0] * (n * (n - 1))
    self_scores = [float(sim[i]) for i in range(n)]
    cross_scores = [float(sim[j]) for i in range(n) for j in range(n) if i != j]
    scores = self_scores + cross_scores
    auc = float(roc_auc_score(labels, scores))
    return {
        "auc": auc,
        "population_mean_profile": {c: float(pop[0, k]) for k, c in enumerate(CATS)},
        "mean_self_cosine": float(statistics.mean(self_scores)),
        "mean_cross_cosine": float(statistics.mean(cross_scores)),
    }


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
        if len(by_seed) != 1:
            raise ValueError("average_seeds=False requires a single seed file")
        return {a: by_seed[0][a] for a in apps}
    out: dict[str, dict[str, float]] = {}
    for app in apps:
        out[app] = {}
        for cat in CATS:
            out[app][cat] = float(
                statistics.mean(by_seed[s][app][cat] for s in range(len(by_seed)))
            )
    return out


def predictions_to_matrix(
    app_ids: list[str], predictions: dict[str, dict[str, float]]
) -> np.ndarray:
    return np.asarray(
        [[float(predictions[app][c]) for c in CATS] for app in app_ids],
        dtype=np.float64,
    )


def score_configuration(
    *,
    temperature: float,
    prediction_files: list[str],
    average_seeds: bool,
    pred_dir: Path | None = None,
) -> dict:
    pred_dir = pred_dir or (ROOT / "predictions")
    app_ids, obs = _load_observed()
    if average_seeds:
        preds = load_predictions_from_seeds(
            pred_dir, prediction_files[0], average_seeds=True
        )
        pred_label = f"mean_of_seeds_{SEEDS[0]}_{SEEDS[-1]}"
    else:
        path = pred_dir / prediction_files[0]
        payload = json.loads(path.read_text(encoding="utf-8"))
        preds = payload["predictions"]
        pred_label = prediction_files[0]
    missing = [a for a in app_ids if a not in preds]
    if missing:
        raise ValueError(f"missing predictions for {missing[:5]}… ({len(missing)} total)")
    pred = predictions_to_matrix(app_ids, preds)
    self_cross = _self_cross_auc(pred, obs)
    pop = _population_baseline_auc(pred, obs)
    return {
        "temperature": temperature,
        "prediction_source": pred_label,
        "n_apps": len(app_ids),
        "app_ids": app_ids,
        "scorer": "cosine_similarity",
        "self_cross": self_cross,
        "population_baseline": pop,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temperature", type=float, required=True)
    parser.add_argument(
        "--pattern",
        default="seed_{seed}.json",
        help="Filename pattern under predictions/ with {seed}",
    )
    parser.add_argument(
        "--average-seeds",
        action="store_true",
        help="Average predictions across seeds 42-46 before scoring",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = score_configuration(
        temperature=args.temperature,
        prediction_files=[args.pattern],
        average_seeds=args.average_seeds,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
