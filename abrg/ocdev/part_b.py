"""Part B: support-novelty scoring on transition cells (no learning)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, _dist, split_apps
from abrg.kernels.load import load_t1k
from abrg.ocdev import EPS, OCPOOL_INCUMBENT, SEED, SIZE_FLOOR
from abrg.ocdev.detectors import eval_block
from abrg.transitions.features import adj_matrix
from abrg.transitions import N_NODES


def _gate(auc_floor: float) -> dict[str, bool]:
    return {
        "clears_size_floor": float(auc_floor) >= SIZE_FLOOR,
        "clears_ocpool": float(auc_floor) >= OCPOOL_INCUMBENT,
    }


def _covariates(tensors: dict[str, dict], shas: list[str]) -> dict[str, list[float]]:
    rows = []
    for s in shas:
        t = tensors[s]
        mapped = float(t.get("n_mapped", t.get("n_inv_events", 0)))
        total = float(t.get("n_events", t.get("n_total_events", 0)))
        static = t.get("static_norm", t.get("static_slice_norm", 0.0))
        if hasattr(static, "item"):
            static = float(static)
        rows.append(
            {
                "mapped_event_count": mapped,
                "total_event_count": total,
                "active_nodes": float(t["n_active"]),
                "edge_count": float(t["n_edges"]),
                "graph_density": float(t["density"]),
                "static_feature_norm": float(static),
            }
        )
    keys = rows[0].keys()
    return {k: [r[k] for r in rows] for k in keys}


def graph_adj(t: dict[str, Any], n: int) -> np.ndarray:
    return adj_matrix(t["edge_index"], t["edge_weight"], n=n)


def fit_support_stats(
    tensors: dict[str, dict],
    train_shas: list[str],
    *,
    n: int,
) -> dict[str, np.ndarray]:
    """Fit df / mean_w / sd_w on train-benign only."""
    present = np.zeros((n, n), dtype=np.float64)
    sum_w = np.zeros((n, n), dtype=np.float64)
    sum_w2 = np.zeros((n, n), dtype=np.float64)
    count_w = np.zeros((n, n), dtype=np.float64)
    for s in train_shas:
        A = graph_adj(tensors[s], n)
        nz = A > 0
        present += nz.astype(np.float64)
        sum_w += np.where(nz, A, 0.0)
        sum_w2 += np.where(nz, A * A, 0.0)
        count_w += nz.astype(np.float64)
    n_tr = float(len(train_shas))
    df = present / max(n_tr, 1.0)
    mean_w = np.divide(sum_w, count_w, out=np.zeros_like(sum_w), where=count_w > 0)
    # sample sd over graphs where present; 0 if count < 2
    var = np.divide(sum_w2, count_w, out=np.zeros_like(sum_w2), where=count_w > 0) - mean_w**2
    var = np.maximum(var, 0.0)
    sd_w = np.sqrt(var)
    sd_w = np.where(count_w >= 2, sd_w, 0.0)
    return {"df": df, "mean_w": mean_w, "sd_w": sd_w, "count_w": count_w}


def score_graph(
    A: np.ndarray,
    stats: dict[str, np.ndarray],
    *,
    eps: float = EPS,
) -> dict[str, float]:
    """
    Conventions for df==0 cells:
      S1: include mass (explicit support violation).
      S2: treat as fully rare — use -log(eps) weight (finite; not inf/nan).
      S3/S4: cells with df==0 use mean_w=0, sd_w=0 → z = w/(eps) one-sided if w>0.
    """
    df = stats["df"]
    mean_w = stats["mean_w"]
    sd_w = stats["sd_w"]
    nz = A > 0

    # S1
    s1 = float(A[nz & (df == 0)].sum()) if np.any(nz & (df == 0)) else 0.0

    # S2 — df==0 → -log(eps)
    df_safe = np.where(df > 0, df, eps)
    idf = -np.log(df_safe + eps)
    s2 = float((A * idf)[nz].sum()) if np.any(nz) else 0.0

    # S3 one-sided and two-sided
    z = (A - mean_w) / (sd_w + eps)
    # for never-seen cells with w>0, mean_w=0 sd_w=0 → large positive z
    s3_one = float(np.maximum(0.0, z).sum())
    s3_two = float(np.abs(z).sum())
    s4 = float(np.maximum(0.0, z).max()) if z.size else 0.0
    s4_two = float(np.abs(z).max()) if z.size else 0.0

    nnz = int(nz.sum())
    return {
        "S1": s1,
        "S2": s2,
        "S3_one": s3_one,
        "S3_two": s3_two,
        "S4": s4,
        "S4_two": s4_two,
        "nnz": float(nnz),
        "S1_norm": s1 / max(nnz, 1),
        "S2_norm": s2 / max(nnz, 1),
        "S3_one_norm": s3_one / max(nnz, 1),
        "S3_two_norm": s3_two / max(nnz, 1),
        "S4_norm": s4,  # max already localised
        "S4_two_norm": s4_two,
    }


PRIMARY_SCORES = ("S1", "S2", "S3_one", "S4")
ALL_SCORE_KEYS = (
    "S1",
    "S2",
    "S3_one",
    "S3_two",
    "S4",
    "S4_two",
    "S1_norm",
    "S2_norm",
    "S3_one_norm",
    "S3_two_norm",
)


def _eval_score_list(
    scores: list[float],
    labels: list[int],
    cov: dict[str, list[float]],
    train_scores: list[float],
) -> dict[str, Any]:
    block = eval_block(scores, labels, cov)
    block["score_distributions"]["train_benign"] = _dist(train_scores)
    block["gate"] = _gate(block["auc"]["auc_floor"])
    return block


def run_matrix_family(
    *,
    name: str,
    tensors: dict[str, dict],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    n: int,
    out_dir: Path,
    pred_writer: csv.writer,
    artifacts: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = fit_support_stats(tensors, train_shas, n=n)
    np.save(artifacts / f"df__{name}.npy", stats["df"])
    np.save(artifacts / f"mean_w__{name}.npy", stats["mean_w"])
    np.save(artifacts / f"sd_w__{name}.npy", stats["sd_w"])

    df = stats["df"]
    df_report = {
        "n_cells": int(n * n),
        "n_df_zero": int((df == 0).sum()),
        "df_mean": float(df.mean()),
        "df_median": float(np.median(df)),
        "df_p90": float(np.percentile(df, 90)),
        "df_matrix": df.tolist(),
        "eps": EPS,
        "df0_convention": {
            "S1": "include mass on df==0 cells",
            "S2": "use -log(eps) for df==0 (finite)",
            "S3_S4": "mean_w=0,sd_w=0 → z=w/eps for present never-seen cells",
        },
    }
    (out_dir / f"df_report__{name}.json").write_text(
        json.dumps({k: v for k, v in df_report.items() if k != "df_matrix"}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    (out_dir / f"df_matrix__{name}.json").write_text(
        json.dumps({"df": df.tolist()}, indent=2) + "\n", encoding="utf-8"
    )

    def score_partition(shas: list[str]) -> list[dict[str, float]]:
        return [score_graph(graph_adj(tensors[s], n), stats) for s in shas]

    tr_rows = score_partition(train_shas)
    tb_rows = score_partition(test_b)
    tm_rows = score_partition(test_m)
    labels = [0] * len(test_b) + [1] * len(test_m)
    te_shas = test_b + test_m
    cov = _covariates(tensors, te_shas)

    results: dict[str, Any] = {"family": name, "n": n, "df_report": {k: v for k, v in df_report.items() if k != "df_matrix"}}
    for key in ALL_SCORE_KEYS:
        tr = [r[key] for r in tr_rows]
        te = [r[key] for r in tb_rows] + [r[key] for r in tm_rows]
        block = _eval_score_list(te, labels, cov, tr)
        block["primary"] = key in PRIMARY_SCORES or key.endswith("_norm") and key.replace("_norm", "") in PRIMARY_SCORES
        results[key] = block
        for sha, lab, sc in zip(te_shas, labels, te):
            pred_writer.writerow(
                [sha, lab, sc, "B", name, key, "none", "splitA", "NA", "NA", "support"]
            )

    # Shuffled-support control on S1/S2 (primary)
    rng = np.random.default_rng(SEED)
    flat = df.reshape(-1).copy()
    rng.shuffle(flat)
    stats_shuf = {
        "df": flat.reshape(df.shape),
        "mean_w": stats["mean_w"],
        "sd_w": stats["sd_w"],
    }
    results["shuffled_support"] = {}
    for key in ("S1", "S2", "S1_norm", "S2_norm"):
        te = [
            score_graph(graph_adj(tensors[s], n), stats_shuf)[key]
            for s in te_shas
        ]
        tr = [
            score_graph(graph_adj(tensors[s], n), stats_shuf)[key]
            for s in train_shas
        ]
        results["shuffled_support"][key] = _eval_score_list(te, labels, cov, tr)

    (out_dir / f"scores__{name}.json").write_text(
        json.dumps(results, indent=2) + "\n", encoding="utf-8"
    )
    return results


def run_part_b(
    *,
    split_bundle: Any,
    tensors_t22: dict[str, dict],
    out: Path,
    artifacts: Path,
    pred_writer: csv.writer,
) -> dict[str, Any]:
    out_b = out / "partB_support"
    out_b.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train_shas = [a.sha256 for a in split["train"]]
    test_b = [a.sha256 for a in split["test_benign"]]
    test_m = [a.sha256 for a in split["test_malware"]]
    if any(a.label != "benign" for a in split["train"]):
        raise SystemExit("STOP: Part B train contains non-benign")

    summary: dict[str, Any] = {}

    print("[ocdev/B] T22 proximity transitions …", flush=True)
    summary["T22_proximity"] = run_matrix_family(
        name="T22_proximity",
        tensors=tensors_t22,
        train_shas=train_shas,
        test_b=test_b,
        test_m=test_m,
        n=N_NODES,
        out_dir=out_b,
        pred_writer=pred_writer,
        artifacts=artifacts,
    )

    # T1K API-1000
    print("[ocdev/B] T1K B_docfreq transitions …", flush=True)
    all_shas = train_shas + test_b + test_m
    t1k = load_t1k(by_sha=split_bundle.by_sha, all_shas=all_shas)
    summary["T1K_B_docfreq"] = run_matrix_family(
        name="T1K_B_docfreq",
        tensors=t1k,
        train_shas=train_shas,
        test_b=test_b,
        test_m=test_m,
        n=1000,
        out_dir=out_b,
        pred_writer=pred_writer,
        artifacts=artifacts,
    )
    summary["T1K_B_docfreq"]["sparsity_note"] = (
        "1000x1000 cells; most df=0; S1/S2/S3 handle zeros via stated conventions"
    )

    # Invocation 22-cat — rebuild via transitions.part_a (read-only import)
    print("[ocdev/B] T22 invocation transitions …", flush=True)
    from abrg.invgraph.extract import extract_invocation_pairs
    from abrg.transitions.part_a import build_both_variants

    apps = [split_bundle.by_sha[s] for s in all_shas]
    pairs = extract_invocation_pairs(apps)
    inv_with, inv_no, _ = build_both_variants(
        base_tensors=tensors_t22, pairs=pairs, shas=all_shas
    )
    # Use no_self_loops variant (part A structural pass choice typically)
    summary["T22_invocation_no_self"] = run_matrix_family(
        name="T22_invocation_no_self",
        tensors=inv_no,
        train_shas=train_shas,
        test_b=test_b,
        test_m=test_m,
        n=N_NODES,
        out_dir=out_b,
        pred_writer=pred_writer,
        artifacts=artifacts,
    )

    (out_b / "partB_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
