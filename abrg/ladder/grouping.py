"""Malware grouping: Route A (VT/AVClass) and Route B (behavioral clustering)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from abrg.ladder import CLUSTER_K_GRID
from abrg.ladder.vectorize import malware_full_vectors, top_node_feature_deltas


def _check_vt_access(malware_shas: list[str]) -> dict[str, Any]:
    env_keys = [
        os.environ.get("VIRUSTOTAL_API_KEY", "").strip(),
        os.environ.get("VT_API_KEY", "").strip(),
    ]
    key_present = any(k for k in env_keys)
    search_roots = [
        Path("datasets/androct_2017"),
        Path.home() / ".virustotal",
        Path("/Volumes/ABRG_MW"),
    ]
    local_files: list[str] = []
    for root in search_roots:
        if not root.is_dir():
            continue
        for pat in ("*virustotal*", "*vt_report*", "*VT_*"):
            for p in root.rglob(pat):
                if p.is_file() and p.stat().st_size > 0:
                    local_files.append(str(p))
                if len(local_files) >= 20:
                    break
    return {
        "route": "A",
        "vt_api_key_in_env": key_present,
        "local_vt_report_files_sample": local_files[:20],
        "n_local_vt_files_found": len(local_files),
        "available": key_present or len(local_files) > 0,
        "note": (
            "No VirusTotal report corpus found locally and no VT API key in env; "
            "cannot run AVClass2 without VT reports."
            if not key_present and not local_files
            else "VT access detected but AVClass2 pipeline not wired in this module."
        ),
    }


def _silhouette_curve(
    X: np.ndarray,
    k_grid: tuple[int, ...],
    *,
    method: str,
) -> dict[str, Any]:
    curve: list[dict[str, Any]] = []
    best_k = k_grid[0]
    best_s = -1.0
    for k in k_grid:
        if k >= len(X):
            continue
        if method == "ward":
            labels = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(X)
        elif method == "kmeans":
            labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(X)
        else:
            raise ValueError(method)
        if len(set(labels)) < 2:
            s = float("nan")
        else:
            s = float(silhouette_score(X, labels))
        curve.append({"k": k, "silhouette": s})
        if np.isfinite(s) and s > best_s:
            best_s = s
            best_k = k
    return {
        "criterion": "max_silhouette_over_k_grid",
        "k_grid": list(k_grid),
        "curve": curve,
        "chosen_k": best_k,
        "chosen_silhouette": best_s,
        "cluster_method": method,
    }


def _cluster_profiles(
    tensors: dict[str, dict[str, Any]],
    shas: list[str],
    labels: np.ndarray,
    by_sha: dict[str, Any],
) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    global_x = np.stack(
        [tensors[s]["x"].detach().cpu().numpy().astype(np.float64) for s in shas], axis=0
    )
    global_mean = global_x.mean(axis=0)
    for cid in sorted(set(labels.tolist())):
        idx = labels == cid
        cluster_shas = [shas[i] for i in range(len(shas)) if idx[i]]
        mapped = [float(tensors[s]["n_mapped"]) for s in cluster_shas]
        profiles[str(cid)] = {
            "n": len(cluster_shas),
            "median_mapped_events": float(np.median(mapped)),
            "top_node_feature_deltas": top_node_feature_deltas(
                tensors, cluster_shas, global_mean
            ),
        }
    return profiles


def route_b_clustering(
    tensors: dict[str, dict[str, Any]],
    malware_shas: list[str],
    by_sha: dict[str, Any],
) -> dict[str, Any]:
    X = malware_full_vectors(tensors, malware_shas, mode="full")
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)

    ward_sil = _silhouette_curve(Xs, CLUSTER_K_GRID, method="ward")
    k_ward = ward_sil["chosen_k"]
    ward_labels = AgglomerativeClustering(n_clusters=k_ward, linkage="ward").fit_predict(Xs)

    km_sil = _silhouette_curve(Xs, CLUSTER_K_GRID, method="kmeans")
    k_km = km_sil["chosen_k"]
    kmeans = KMeans(n_clusters=k_km, random_state=42, n_init=10)
    km_labels = kmeans.fit_predict(Xs)

    def size_dist(labels: np.ndarray) -> dict[str, int]:
        counts: dict[str, int] = {}
        for c in labels:
            key = str(int(c))
            counts[key] = counts.get(key, 0) + 1
        return counts

    return {
        "route": "B",
        "n_malware": len(malware_shas),
        "feature_dim": int(X.shape[1]),
        "standardization": "malware_only_fit",
        "ward": {
            "linkage": "ward",
            "silhouette_selection": ward_sil,
            "cluster_sizes": size_dist(ward_labels),
            "profiles": _cluster_profiles(tensors, malware_shas, ward_labels, by_sha),
            "assignments": {s: int(ward_labels[i]) for i, s in enumerate(malware_shas)},
        },
        "kmeans": {
            "silhouette_selection": km_sil,
            "cluster_sizes": size_dist(km_labels),
            "profiles": _cluster_profiles(tensors, malware_shas, km_labels, by_sha),
            "assignments": {s: int(km_labels[i]) for i, s in enumerate(malware_shas)},
        },
        "primary_for_holdout": "ward",
    }


def run_grouping(
    tensors: dict[str, dict[str, Any]],
    malware_shas: list[str],
    by_sha: dict[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    route_a = _check_vt_access(malware_shas)
    (out_dir / "route_a_vt_check.json").write_text(
        json.dumps(route_a, indent=2) + "\n", encoding="utf-8"
    )

    route_b = route_b_clustering(tensors, malware_shas, by_sha)
    (out_dir / "route_b_behavioral.json").write_text(
        json.dumps(route_b, indent=2) + "\n", encoding="utf-8"
    )

    summary = {
        "route_a": route_a,
        "route_b_primary": "ward",
        "route_b_ward_k": route_b["ward"]["silhouette_selection"]["chosen_k"],
        "route_b_kmeans_k": route_b["kmeans"]["silhouette_selection"]["chosen_k"],
        "route_b_ward_n_clusters": len(route_b["ward"]["cluster_sizes"]),
        "used_for_rung2": "route_b_ward",
    }
    (out_dir / "grouping_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return {"route_a": route_a, "route_b": route_b, "summary": summary}
