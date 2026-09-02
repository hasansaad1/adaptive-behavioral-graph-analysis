"""
Run 6 follow-on: (1) per-node centroid Euclidean AUC ablation;
(2) one-class baselines on same tensors / GAE split.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.covariance import LedoitWolf
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from abrg.androct.paths import androct_run2_output_dir, androct_run6_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run6_part1 import _ablate_all
from abrg.androct.run_gae_run2 import SEED, _auc_with_bootstrap, split_apps
from abrg.androct.run_gae_run3_5 import _vectorize
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

# Reference numbers from prior runs (for table comparison).
REF_CENTROID_EUCLIDEAN_AUC_FLOOR = 0.776892
REF_GAE_RUN5_ALPHA02_H8_AUC_FLOOR = 0.637893  # Run5 h=8 ≈ best dual; user cited 0.638


def _X_for(tensors: dict, apps: list) -> np.ndarray:
    X, _, _, _ = _vectorize(tensors, apps, mode="full")
    return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)


def _centroid_euclidean_auc(
    X_train: np.ndarray, X_test_ben: np.ndarray, X_test_mal: np.ndarray
) -> dict[str, Any]:
    centroid = X_train.mean(axis=0, keepdims=True)
    d_ben = np.linalg.norm(X_test_ben - centroid, axis=1)
    d_mal = np.linalg.norm(X_test_mal - centroid, axis=1)
    scores = d_ben.tolist() + d_mal.tolist()
    labels = [0] * len(d_ben) + [1] * len(d_mal)
    return _auc_with_bootstrap(scores, labels)


def part1_centroid_ablation(bundle, split, out_dir) -> dict[str, Any]:
    tensors = bundle.tensors
    X_tr0 = _X_for(tensors, split["train"])
    X_tb0 = _X_for(tensors, split["test_benign"])
    X_tm0 = _X_for(tensors, split["test_malware"])
    baseline = _centroid_euclidean_auc(X_tr0, X_tb0, X_tm0)
    print(
        f"[centroid-ablation] baseline AUC_floor={baseline['auc_floor']:.6f} "
        f"(ref {REF_CENTROID_EUCLIDEAN_AUC_FLOOR})",
        flush=True,
    )

    rows: list[dict[str, Any]] = []
    for cat in GRAPH_CATEGORY_UNIVERSE:
        print(f"  zero {cat} …", flush=True)
        ablated = _ablate_all(tensors, (cat,), zero_edges=True)
        X_tr = _X_for(ablated, split["train"])
        X_tb = _X_for(ablated, split["test_benign"])
        X_tm = _X_for(ablated, split["test_malware"])
        # Centroid recomputed on ablated train-benign (fair: same representation)
        auc = _centroid_euclidean_auc(X_tr, X_tb, X_tm)
        drop = baseline["auc_floor"] - auc["auc_floor"]
        rows.append(
            {
                "node": cat,
                "auc": auc["auc"],
                "auc_floor": auc["auc_floor"],
                "ci95_floor": auc["ci95_floor"],
                "direction": auc["direction"],
                "delta_auc_floor_vs_baseline": drop,
            }
        )
        print(f"    floor={auc['auc_floor']:.4f} drop={drop:+.4f}", flush=True)

    rows_sorted = sorted(rows, key=lambda r: -r["delta_auc_floor_vs_baseline"])
    result = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "task": "centroid_euclidean_per_node_ablation",
        "zeroing": "node features zeroed + incident edges removed; centroid recomputed on ablated train",
        "flattening": "704-dim full = 220 node + 484 adj (same as Run6 part2)",
        "split": "GAE benign-only train / test_benign+test_malware seed=42",
        "baseline": {
            "auc": baseline["auc"],
            "auc_floor": baseline["auc_floor"],
            "ci95_floor": baseline["ci95_floor"],
            "direction": baseline["direction"],
            "reference_prior_run": REF_CENTROID_EUCLIDEAN_AUC_FLOOR,
        },
        "per_node": rows_sorted,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# Centroid Euclidean AUC — per-node ablation",
        f"- UTC: {result['utc']}",
        f"- baseline AUC_floor={baseline['auc_floor']:.6f} "
        f"CI=[{baseline['ci95_floor'][0]:.6f}, {baseline['ci95_floor'][1]:.6f}]",
        f"- prior Part2 reference={REF_CENTROID_EUCLIDEAN_AUC_FLOOR}",
        "",
        "| rank | node | AUC_floor | CI_floor | Δ vs baseline (drop) |",
        "|---:|---|---:|---|---:|",
    ]
    for i, r in enumerate(rows_sorted, 1):
        lines.append(
            f"| {i} | {r['node']} | {r['auc_floor']:.4f} | "
            f"[{r['ci95_floor'][0]:.4f}, {r['ci95_floor'][1]:.4f}] | "
            f"{r['delta_auc_floor_vs_baseline']:+.4f} |"
        )
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    return result


def part2_oneclass(bundle, split, out_dir) -> dict[str, Any]:
    X_tr = _X_for(bundle.tensors, split["train"])
    X_tb = _X_for(bundle.tensors, split["test_benign"])
    X_tm = _X_for(bundle.tensors, split["test_malware"])
    X_te = np.vstack([X_tb, X_tm])
    y_te = np.array([0] * len(X_tb) + [1] * len(X_tm), dtype=np.int32)

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s = scaler.transform(X_te)

    methods: dict[str, Any] = {}

    # --- Mahalanobis (Ledoit-Wolf on standardized train) ---
    print("[oneclass] Mahalanobis (LedoitWolf) …", flush=True)
    lw = LedoitWolf().fit(X_tr_s)
    # precision_ available; higher distance = more anomalous
    # sklearn 1.x: mahalanobis via np
    diff = X_te_s - lw.location_
    # d^2 = (x-μ) Σ^{-1} (x-μ)^T
    scores_mah = np.einsum("ij,jk,ik->i", diff, lw.precision_, diff)
    methods["mahalanobis_ledoit_wolf"] = _auc_with_bootstrap(
        scores_mah.tolist(), y_te.tolist()
    )

    # --- One-class SVM ---
    print("[oneclass] OneClassSVM RBF …", flush=True)
    ocsvm = OneClassSVM(kernel="rbf", gamma="scale", nu=0.1)
    ocsvm.fit(X_tr_s)
    # decision_function: larger = more inlier → negate for anomaly score
    scores_oc = (-ocsvm.decision_function(X_te_s)).tolist()
    methods["one_class_svm_rbf"] = _auc_with_bootstrap(scores_oc, y_te.tolist())

    # --- Isolation Forest ---
    print("[oneclass] IsolationForest …", flush=True)
    iso = IsolationForest(n_estimators=200, contamination="auto", random_state=SEED, n_jobs=-1)
    iso.fit(X_tr_s)
    # score_samples: higher = more normal → negate
    scores_iso = (-iso.score_samples(X_te_s)).tolist()
    methods["isolation_forest"] = _auc_with_bootstrap(scores_iso, y_te.tolist())

    # --- k-NN distance to train-benign ---
    for k in (1, 5, 20):
        print(f"[oneclass] kNN k={k} …", flush=True)
        nn = NearestNeighbors(n_neighbors=k, metric="euclidean", n_jobs=-1)
        nn.fit(X_tr_s)
        dists, _ = nn.kneighbors(X_te_s)
        # mean distance to k neighbors
        scores_knn = dists.mean(axis=1).tolist()
        methods[f"knn_mean_dist_k{k}"] = _auc_with_bootstrap(scores_knn, y_te.tolist())

    # Centroid (reproduce)
    print("[oneclass] centroid Euclidean (reproduce) …", flush=True)
    cent = _centroid_euclidean_auc(X_tr, X_tb, X_tm)
    methods["centroid_euclidean"] = cent

    result = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "task": "one_class_baselines",
        "flattening": "704-dim full; StandardScaler fit on train-benign for all except raw centroid",
        "split": {
            "train_benign": len(split["train"]),
            "test_benign": len(split["test_benign"]),
            "test_malware": len(split["test_malware"]),
        },
        "references": {
            "centroid_part2_auc_floor": REF_CENTROID_EUCLIDEAN_AUC_FLOOR,
            "gae_run5_h8_alpha0.2_auc_floor": REF_GAE_RUN5_ALPHA02_H8_AUC_FLOOR,
        },
        "methods": {
            name: {
                "auc": b["auc"],
                "auc_floor": b["auc_floor"],
                "ci95_floor": b["ci95_floor"],
                "direction": b["direction"],
                "n": b["n"],
            }
            for name, b in methods.items()
        },
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")

    lines = [
        "# One-class baselines (benign-only train, same 704-dim tensors)",
        f"- UTC: {result['utc']}",
        f"- refs: centroid Part2={REF_CENTROID_EUCLIDEAN_AUC_FLOOR:.3f}; "
        f"GAE Run5 h8 α0.2={REF_GAE_RUN5_ALPHA02_H8_AUC_FLOOR:.3f}",
        "",
        "| method | AUC_floor | CI_floor | direction |",
        "|---|---:|---|---|",
    ]
    order = [
        "centroid_euclidean",
        "mahalanobis_ledoit_wolf",
        "one_class_svm_rbf",
        "isolation_forest",
        "knn_mean_dist_k1",
        "knn_mean_dist_k5",
        "knn_mean_dist_k20",
    ]
    for name in order:
        b = result["methods"][name]
        lines.append(
            f"| {name} | {b['auc_floor']:.4f} | "
            f"[{b['ci95_floor'][0]:.4f}, {b['ci95_floor'][1]:.4f}] | {b['direction']} |"
        )
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 6 addendum — centroid ablation + one-class")
    parser.add_argument(
        "--task",
        choices=("ablation", "oneclass", "both"),
        default="both",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Subdir for single task")
    args = parser.parse_args()
    root = androct_run6_output_dir()
    bundle = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(bundle.eligible)
    print(
        f"[followon] split train={len(split['train'])} "
        f"test_ben={len(split['test_benign'])} test_mal={len(split['test_malware'])}",
        flush=True,
    )
    if args.task in ("ablation", "both"):
        abl_out = (
            args.output_dir
            if args.task == "ablation" and args.output_dir
            else root / "centroid_node_ablation"
        )
        abl = part1_centroid_ablation(bundle, split, abl_out)
    else:
        abl = None

    if args.task in ("oneclass", "both"):
        oc_out = (
            args.output_dir
            if args.task == "oneclass" and args.output_dir
            else root / "oneclass_baselines"
        )
        oc = part2_oneclass(bundle, split, oc_out)
    else:
        oc = None

    if args.task != "both":
        print(f"[followon] done task={args.task}", flush=True)
        return

    # Top-level addendum
    lines = [
        "# Run 6 addendum — centroid node ablation + one-class baselines",
        "",
        "## Centroid Euclidean — AUC drop when node zeroed (top 10)",
    ]
    for r in abl["per_node"][:10]:
        lines.append(
            f"- {r['node']}: drop={r['delta_auc_floor_vs_baseline']:+.4f} "
            f"(floor={r['auc_floor']:.4f})"
        )
    lines.extend(["", "## One-class AUC_floor vs refs (centroid 0.777 / GAE 0.638)"])
    for name, b in oc["methods"].items():
        lines.append(f"- {name}: {b['auc_floor']:.4f}")
    (root / "ADDENDUM_CENTROID_ONECLASS.md").write_text("\n".join(lines) + "\n")
    print(f"[followon] done → {root}", flush=True)


if __name__ == "__main__":
    main()
