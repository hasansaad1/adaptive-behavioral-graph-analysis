"""Run 6 Part 2 — benign/malware graph heterogeneity geometry."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_distances, euclidean_distances

from abrg.androct.paths import androct_run2_output_dir, androct_run6_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import SEED, _auc_with_bootstrap, _dist, split_apps
from abrg.androct.run_gae_run3_5 import _adj_matrix, _vectorize

SUBSAMPLE_N = 500


def _pairwise_stats(X: np.ndarray, *, seed: int = SEED) -> dict[str, Any]:
    n = X.shape[0]
    subsampled = False
    idx = np.arange(n)
    if n > SUBSAMPLE_N:
        rng = np.random.default_rng(seed)
        idx = rng.choice(n, size=SUBSAMPLE_N, replace=False)
        X = X[idx]
        subsampled = True
        n = SUBSAMPLE_N
    # cosine distance; diagonal is 0 — take upper triangle
    D = cosine_distances(X)
    iu = np.triu_indices(n, k=1)
    vals = D[iu]
    return {
        "n_graphs_used": n,
        "subsampled": subsampled,
        "subsample_cap": SUBSAMPLE_N,
        "mean_pairwise_cosine_distance": float(vals.mean()) if len(vals) else float("nan"),
        "median_pairwise_cosine_distance": float(np.median(vals)) if len(vals) else float("nan"),
        "n_pairs": int(len(vals)),
    }


def _l2_normalize_rows(X: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return X / norms


def _pca_curve(X: np.ndarray) -> dict[str, Any]:
    if X.shape[0] < 2:
        return {"n_components_90pct": float("nan"), "explained_variance_ratio": []}
    n_comp = min(X.shape[0], X.shape[1], 64)
    pca = PCA(n_components=n_comp, random_state=SEED)
    pca.fit(X)
    evr = pca.explained_variance_ratio_
    cum = np.cumsum(evr)
    n90 = int(np.searchsorted(cum, 0.90) + 1) if len(cum) else float("nan")
    if isinstance(n90, int) and n90 > len(cum):
        n90 = len(cum)
    return {
        "n_components_fit": int(n_comp),
        "n_components_90pct_variance": int(n90) if n90 == n90 else float("nan"),
        "explained_variance_ratio": [float(x) for x in evr.tolist()],
        "cumulative_explained_variance": [float(x) for x in cum.tolist()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 6 Part 2 — graph geometry")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    out = args.output_dir or (androct_run6_output_dir() / "part2_geometry")
    out.mkdir(parents=True, exist_ok=True)
    bundle = load_corpus_cache(androct_run2_output_dir())
    # GAE split (benign-only train) — matches Run 3 inversion context
    split = split_apps(bundle.eligible)
    tensors = bundle.tensors

    print("[run6/p2] flatten full = node(220) + adj(484) = 704", flush=True)
    parts = {
        "train_benign": split["train"],
        "test_benign": split["test_benign"],
        "test_malware": split["test_malware"],
    }
    X_raw: dict[str, np.ndarray] = {}
    for name, apps in parts.items():
        X, _, _, _ = _vectorize(tensors, apps, mode="full")
        X_raw[name] = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
        print(f"  {name}: n={X_raw[name].shape[0]} dim={X_raw[name].shape[1]}", flush=True)

    results: dict[str, Any] = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "part": 2,
        "flattening": {
            "node_block": "22 nodes × 10 features = 220 (row-major, GRAPH_CATEGORY_UNIVERSE order)",
            "edge_block": "22×22 weighted adjacency (w_cum transition probs; 0 if no edge) = 484",
            "total_dim": 704,
            "concat": "np.concatenate([x.reshape(-1), A.reshape(-1)])",
        },
        "split": {k: len(v) for k, v in parts.items()},
        "pairwise_cosine_raw": {},
        "pairwise_cosine_l2_normalized": {},
        "centroid_distance": {},
        "pca": {},
    }

    for name, X in X_raw.items():
        results["pairwise_cosine_raw"][name] = _pairwise_stats(X, seed=SEED)
        results["pairwise_cosine_l2_normalized"][name] = _pairwise_stats(
            _l2_normalize_rows(X), seed=SEED
        )
        results["pca"][name] = _pca_curve(X)

    def ratio(block: dict[str, Any], key: str) -> float:
        a = block["test_benign"][key]
        b = block["test_malware"][key]
        return float(a / b) if b and b == b and b != 0 else float("nan")

    results["ratio_test_benign_over_test_malware"] = {
        "raw_mean": ratio(results["pairwise_cosine_raw"], "mean_pairwise_cosine_distance"),
        "raw_median": ratio(results["pairwise_cosine_raw"], "median_pairwise_cosine_distance"),
        "l2norm_mean": ratio(
            results["pairwise_cosine_l2_normalized"], "mean_pairwise_cosine_distance"
        ),
        "l2norm_median": ratio(
            results["pairwise_cosine_l2_normalized"], "median_pairwise_cosine_distance"
        ),
    }

    # Centroid of train_benign
    centroid = X_raw["train_benign"].mean(axis=0, keepdims=True)
    centroid_l2 = _l2_normalize_rows(centroid)

    def centroid_dists(X: np.ndarray, *, normalize: bool) -> np.ndarray:
        if normalize:
            Xn = _l2_normalize_rows(X)
            # cosine distance to centroid = 1 - cos sim; use euclidean on L2 rows ≈ related
            return cosine_distances(Xn, centroid_l2).reshape(-1)
        return euclidean_distances(X, centroid).reshape(-1)

    for norm_flag, tag in ((False, "euclidean_to_raw_centroid"), (True, "cosine_to_l2_centroid")):
        d_ben = centroid_dists(X_raw["test_benign"], normalize=norm_flag)
        d_mal = centroid_dists(X_raw["test_malware"], normalize=norm_flag)
        scores = d_ben.tolist() + d_mal.tolist()
        labels = [0] * len(d_ben) + [1] * len(d_mal)
        auc = _auc_with_bootstrap(scores, labels)
        higher = (
            "test_malware"
            if np.median(d_mal) > np.median(d_ben)
            else ("test_benign" if np.median(d_ben) > np.median(d_mal) else "tied")
        )
        results["centroid_distance"][tag] = {
            "test_benign": _dist(d_ben.tolist()),
            "test_malware": _dist(d_mal.tolist()),
            "higher_median_distance_class": higher,
            "inverted_vs_malware_should_be_farther": higher == "test_benign",
            "auc_distance_as_score": auc,
        }

    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")

    lines = [
        "# Run 6 Part 2 — graph geometry / heterogeneity",
        f"- UTC: {results['utc']}",
        f"- flattening: {results['flattening']['total_dim']}-dim "
        f"({results['flattening']['node_block']}; {results['flattening']['edge_block']})",
        f"- pairwise subsample: up to {SUBSAMPLE_N}/partition seed={SEED}",
        "",
        "## 1. Pairwise cosine distance (raw vectors)",
    ]
    for name in parts:
        r = results["pairwise_cosine_raw"][name]
        lines.append(
            f"- {name}: mean={r['mean_pairwise_cosine_distance']:.6f} "
            f"median={r['median_pairwise_cosine_distance']:.6f} "
            f"n_graphs={r['n_graphs_used']} subsampled={r['subsampled']}"
        )
    rr = results["ratio_test_benign_over_test_malware"]
    lines.append(f"- ratio test_benign/test_malware mean={rr['raw_mean']:.6f} median={rr['raw_median']:.6f}")
    lines.extend(["", "## 2. Pairwise cosine distance (L2-normalized rows)"])
    for name in parts:
        r = results["pairwise_cosine_l2_normalized"][name]
        lines.append(
            f"- {name}: mean={r['mean_pairwise_cosine_distance']:.6f} "
            f"median={r['median_pairwise_cosine_distance']:.6f}"
        )
    lines.append(
        f"- ratio test_benign/test_malware mean={rr['l2norm_mean']:.6f} "
        f"median={rr['l2norm_median']:.6f}"
    )
    lines.extend(["", "## 3. Distance to train_benign centroid"])
    for tag, block in results["centroid_distance"].items():
        ab = block["auc_distance_as_score"]
        lines.append(f"### {tag}")
        lines.append(
            f"- test_benign med={block['test_benign']['median']:.6f} "
            f"IQR={block['test_benign']['iqr']:.6f}"
        )
        lines.append(
            f"- test_malware med={block['test_malware']['median']:.6f} "
            f"IQR={block['test_malware']['iqr']:.6f}"
        )
        lines.append(
            f"- higher_median_distance_class={block['higher_median_distance_class']} "
            f"inverted={block['inverted_vs_malware_should_be_farther']}"
        )
        lines.append(
            f"- AUC_floor(distance as score)={ab['auc_floor']:.6f} "
            f"CI_floor=[{ab['ci95_floor'][0]:.6f}, {ab['ci95_floor'][1]:.6f}] "
            f"direction={ab['direction']}"
        )
    lines.extend(["", "## 4. PCA — components to 90% variance"])
    for name in parts:
        p = results["pca"][name]
        lines.append(
            f"- {name}: n_comp_90%={p['n_components_90pct_variance']} "
            f"(fit {p['n_components_fit']} comps)"
        )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"[run6/p2] done → {out}", flush=True)


if __name__ == "__main__":
    main()
