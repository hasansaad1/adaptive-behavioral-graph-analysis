"""Check 1 — nested-bootstrap bias for the two headline configurations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import split_apps
from abrg.kernels.load import load_t1k
from abrg.ocdev.detectors import fit_score_centroid_euclidean
from abrg.ocdev.part_a import load_profiles
from abrg.ocdev.part_b import fit_support_stats, graph_adj, score_graph
from abrg.ocdev_validate import HEADLINE_A, HEADLINE_B, NESTED_B, NESTED_SEED
from abrg.ocdev_validate.util import dist_summary, write_json


def _sparse_from_adj(A: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ii, jj = np.nonzero(A)
    return ii.astype(np.int32), jj.astype(np.int32), A[ii, jj].astype(np.float64)


def _s1_norm_from_sparse(
    ii: np.ndarray, jj: np.ndarray, ww: np.ndarray, df: np.ndarray
) -> float:
    if ww.size == 0:
        return 0.0
    s1 = float(ww[df[ii, jj] == 0].sum())
    return s1 / float(ww.size)


def _df_from_sparse(
    triples: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    indices: np.ndarray,
    n: int,
) -> np.ndarray:
    present = np.zeros((n, n), dtype=np.float64)
    for i in indices:
        ii, jj, _ = triples[int(i)]
        if ii.size:
            present[ii, jj] += 1.0
    return present / max(float(len(indices)), 1.0)


def _bias_pack(point: float, floors: np.ndarray) -> dict[str, Any]:
    floors = np.asarray(floors, dtype=np.float64)
    d = dist_summary(floors)
    boot_mean = d["mean"]
    bias = boot_mean - point  # mean(bootstrap) − full-sample
    bias_corrected = 2.0 * point - boot_mean
    q_lo, q_hi = d["p2.5"], d["p97.5"]
    basic_lo = 2.0 * point - q_hi
    basic_hi = 2.0 * point - q_lo
    if basic_lo > basic_hi:
        basic_lo, basic_hi = basic_hi, basic_lo
    nested_width = q_hi - q_lo
    point_in_nested = bool(q_lo <= point <= q_hi)
    # BCa is not defined for this nested scheme (resample train, score fixed eval).
    thesis: dict[str, Any]
    if point_in_nested:
        thesis = {
            "carries": "full_sample_point",
            "value": point,
            "interval": [q_lo, q_hi],
            "interval_kind": "nested_percentile_B200",
            "reason": (
                "full-sample point lies inside the nested percentile interval; "
                f"|bias|={abs(bias):.4f} vs nested width={nested_width:.4f}"
            ),
        }
    else:
        thesis = {
            "carries": "bootstrap_mean",
            "value": boot_mean,
            "interval": [q_lo, q_hi],
            "interval_kind": "nested_percentile_B200",
            "reason": (
                "full-sample point lies outside the nested percentile interval; "
                "bias-corrected estimate moves further from the observed sampling "
                "distribution of the nested procedure, so the nested mean is carried"
            ),
        }
    return {
        "full_sample_point": point,
        "bootstrap": d,
        "bias_mean_minus_point": bias,
        "bias_corrected_2point_minus_mean": bias_corrected,
        "nested_percentile_ci95": [q_lo, q_hi],
        "basic_reverse_percentile_ci95": [basic_lo, basic_hi],
        "bca": {
            "feasible": False,
            "reason": (
                "scipy.stats.bootstrap BCa assumes i.i.d. resampling of the "
                "observations that enter the statistic; nested train-resample / "
                "fixed-eval scoring is a different scheme"
            ),
        },
        "point_inside_nested_percentile_ci": point_in_nested,
        "bias_over_nested_width": float(bias / nested_width) if nested_width else float("nan"),
        "thesis_carries": thesis,
    }


def _histogram(path: Path, floors: np.ndarray, point: float, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.hist(floors, bins=20, color="#4C78A8", edgecolor="white", alpha=0.9)
    ax.axvline(point, color="#E45756", linewidth=2, label=f"full-sample {point:.4f}")
    ax.axvline(float(np.mean(floors)), color="#72B7B2", linewidth=2, linestyle="--", label=f"boot mean {np.mean(floors):.4f}")
    ax.set_xlabel("nested AUC_floor")
    ax.set_ylabel("count")
    ax.set_title(title)
    ax.legend(frameon=False)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


def run_check1(*, out: Path, split_bundle: Any, B: int = NESTED_B) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(NESTED_SEED)
    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)

    # ---- Part A: D1 centroid_euclidean ----
    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    tr = np.asarray([sha_to_i[a.sha256] for a in split["train"]], dtype=np.int64)
    te = np.asarray(
        [sha_to_i[a.sha256] for a in (split["test_benign"] + split["test_malware"])],
        dtype=np.int64,
    )
    y = np.asarray([0] * len(split["test_benign"]) + [1] * len(split["test_malware"]))
    X = arrays["D1"]
    X_te = X[te]
    sc0, _ = fit_score_centroid_euclidean(X[tr], X_te)
    point_a = max(float(roc_auc_score(y, sc0)), 1.0 - float(roc_auc_score(y, sc0)))

    floors_a = np.empty(B, dtype=np.float64)
    for b in range(B):
        boot = rng.choice(tr, size=len(tr), replace=True)
        sc, _ = fit_score_centroid_euclidean(X[boot], X_te)
        a = float(roc_auc_score(y, sc))
        floors_a[b] = max(a, 1.0 - a)
        if (b + 1) % 50 == 0:
            print(f"[ocdev_validate/C1] D1 nested {b+1}/{B}", flush=True)
    pack_a = _bias_pack(point_a, floors_a)
    pack_a["config"] = HEADLINE_A["config"]
    pack_a["headline_recorded_point"] = HEADLINE_A["point_auc_floor"]
    pack_a["recomputed_point_matches_headline"] = abs(point_a - HEADLINE_A["point_auc_floor"]) < 1e-9

    np.save(out / "nested_aucs__D1_centroid.npy", floors_a)
    _histogram(
        out / "hist__D1_centroid.png",
        floors_a,
        point_a,
        "nested bootstrap AUC_floor — trained D1 / centroid_euclidean",
    )

    # ---- Part B: T1K S1_norm ----
    train_shas = [a.sha256 for a in split["train"]]
    test_b = [a.sha256 for a in split["test_benign"]]
    test_m = [a.sha256 for a in split["test_malware"]]
    all_shas = train_shas + test_b + test_m
    t1k = load_t1k(by_sha=split_bundle.by_sha, all_shas=all_shas)
    print("[ocdev_validate/C1] sparsifying T1K adjs …", flush=True)
    train_sp = [_sparse_from_adj(graph_adj(t1k[s], 1000)) for s in train_shas]
    te_sp = [_sparse_from_adj(graph_adj(t1k[s], 1000)) for s in (test_b + test_m)]
    y2 = np.asarray([0] * len(test_b) + [1] * len(test_m))

    stats0 = fit_support_stats(t1k, train_shas, n=1000)
    n_tr = len(train_shas)
    df0 = _df_from_sparse(train_sp, np.arange(n_tr), 1000)
    if not np.allclose(df0, stats0["df"]):
        raise SystemExit("STOP: sparse df != fit_support_stats df")
    sc_te0 = [_s1_norm_from_sparse(ii, jj, ww, df0) for ii, jj, ww in te_sp]
    sc_dense = [score_graph(graph_adj(t1k[s], 1000), stats0)["S1_norm"] for s in test_b[:3]]
    if any(abs(a - b) > 1e-12 for a, b in zip(sc_dense, sc_te0[:3])):
        raise SystemExit("STOP: sparse S1_norm != dense score_graph")
    point_b = max(float(roc_auc_score(y2, sc_te0)), 1.0 - float(roc_auc_score(y2, sc_te0)))

    floors_b = np.empty(B, dtype=np.float64)
    for b in range(B):
        idx = rng.choice(n_tr, size=n_tr, replace=True)
        df = _df_from_sparse(train_sp, idx, 1000)
        sc = [_s1_norm_from_sparse(ii, jj, ww, df) for ii, jj, ww in te_sp]
        a = float(roc_auc_score(y2, sc))
        floors_b[b] = max(a, 1.0 - a)
        if (b + 1) % 50 == 0:
            print(f"[ocdev_validate/C1] T1K S1_norm nested {b+1}/{B}", flush=True)
    pack_b = _bias_pack(point_b, floors_b)
    pack_b["config"] = HEADLINE_B["config"]
    pack_b["headline_recorded_point"] = HEADLINE_B["point_auc_floor"]
    pack_b["recomputed_point_matches_headline"] = abs(point_b - HEADLINE_B["point_auc_floor"]) < 1e-9

    np.save(out / "nested_aucs__T1K_S1_norm.npy", floors_b)
    _histogram(
        out / "hist__T1K_S1_norm.png",
        floors_b,
        point_b,
        "nested bootstrap AUC_floor — T1K_B_docfreq / S1_norm",
    )

    bias_a = pack_a["bias_mean_minus_point"]
    bias_b = pack_b["bias_mean_minus_point"]
    same_sign = (bias_a < 0 and bias_b < 0) or (bias_a > 0 and bias_b > 0)
    comparison = {
        "bias_sign_consistent": bool(same_sign),
        "D1_bias": bias_a,
        "S1_norm_bias": bias_b,
        "D1_bias_over_width": pack_a["bias_over_nested_width"],
        "S1_norm_bias_over_width": pack_b["bias_over_nested_width"],
    }

    payload = {
        "B": B,
        "nested_seed": NESTED_SEED,
        "partA_D1_centroid": pack_a,
        "partB_T1K_S1_norm": pack_b,
        "bias_comparison": comparison,
    }
    write_json(out / "bias_stats.json", payload)
    return payload
