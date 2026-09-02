"""
D-3 factorial (referencing vs localisation) + d_self/d_cross + random-init D1 paired test.
Scoring passes only — no retrain, no new tensors.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy import stats
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_e0_selfref import (
    N_PARTS,
    N_REF,
    N_TEST,
    SEED,
    TEST_RATIO,
    _d_adj,
    _d_node,
    _pct,
    _ref_test_indices,
)
from abrg.androct.run_gae_run3_5 import _stratified_split
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.androct.run_gae_run3_5 import _adj_matrix, _vectorize
from abrg.apigraph.split import load_run3_split
from abrg.devread import EXPECTED_SPLIT_DIGEST_PREFIX
from abrg.devread.run_d1_randominit_controls import (
    PAIRED_BOOT_B,
    PAIRED_BOOT_SEED,
    TABLE_A4_KEYS,
    _legacy_check3_covariates,
    _paired_bootstrap_auc_diff,
    _score_l2,
    _table_a4_covariates,
    delong_test,
)
from abrg.features import feature_vector_labels
from abrg.final_validate.util import auc_raw_and_floor
from abrg.ladder.vectorize import malware_full_vectors
from abrg.ocdev.part_a import load_profiles
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.validate.residual import apply_residual, ols_fit

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results"
FLOOR = 0.7025
ACT_IDX = feature_vector_labels(normalize=True).index("act_v_frac")
N_NODES = 22

NON_PRODUCIBLE = frozenset({"sms", "telephony", "clipboard", "dynamic_code_loading"})

REF = {
    "ipc_raw_share": 0.575,
    "d0_scalar_recon": 0.6379,
    "d0_centred": 0.7617,
    "d1_centroid": 0.800426,
    "d3_supervised": 0.9624,
    "raw_centroid": 0.7769,
    "raw_hgb": 0.9746,
}

ART = {
    "B": REPO / "abrg/output/androct_2017/ocdev/controls/raw_tensor/raw__RAW_full__none__centroid_euclidean__splitA__foldNA.json",
    "C": REPO / "abrg/output/androct_2017/ocdev/partA_profiles/splitA_trained/trained__D0__none__centroid_euclidean__splitA__foldNA.json",
    "D": REPO / "abrg/output/androct_2017/ocdev/partA_profiles/splitA_trained/trained__D1__none__centroid_euclidean__splitA__foldNA.json",
    "D_ri": REPO / "abrg/output/androct_2017/ocdev/controls/random_init_splitA/random_init__D1__none__centroid_euclidean__splitA__foldNA.json",
}


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _load_spine() -> dict[str, Any]:
    bundle = load_run3_split()
    dig = bundle.sha_list_digest
    if not dig.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(f"STOP: digest {dig[:16]} != {EXPECTED_SPLIT_DIGEST_PREFIX}")

    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train = split["train"]
    test_b = split["test_benign"]
    test_m = split["test_malware"]
    if len(train) != 562 or len(test_b) != 141 or len(test_m) != 1700:
        raise SystemExit(
            f"STOP: split {len(train)}/{len(test_b)}/{len(test_m)} != 562/141/1700"
        )

    arrays_tr, shas = load_profiles("trained_t22")
    arrays_ri, shas_ri = load_profiles("random_init_t22")
    if shas != shas_ri:
        raise SystemExit("STOP: profile index mismatch")

    sha_to_app = {a.sha256: a for a in corpus.eligible}
    train_shas = [a.sha256 for a in train]
    test_shas = [a.sha256 for a in test_b] + [a.sha256 for a in test_m]
    labels = np.asarray([0] * len(test_b) + [1] * len(test_m), dtype=np.int32)
    sha_to_i = {s: i for i, s in enumerate(shas)}
    tr_idx = np.asarray([sha_to_i[s] for s in train_shas], dtype=np.int64)
    te_idx = np.asarray([sha_to_i[s] for s in test_shas], dtype=np.int64)

    eligible_shas = [a.sha256 for a in corpus.eligible]
    X_raw, _, _, _ = _vectorize(corpus.tensors, [sha_to_app[s] for s in eligible_shas], mode="full")

    return {
        "digest": dig,
        "train_shas": train_shas,
        "test_shas": test_shas,
        "labels": labels,
        "tr_idx": tr_idx,
        "te_idx": te_idx,
        "sha_to_i": sha_to_i,
        "shas": shas,
        "tensors": corpus.tensors,
        "sha_to_app": sha_to_app,
        "X_raw": X_raw,
        "D0": arrays_tr["D0"],
        "D1": arrays_tr["D1"],
        "D1_ri": arrays_ri["D1"],
        "eligible": corpus.eligible,
    }


def _centroid_scores(X_tr: np.ndarray, X_te: np.ndarray) -> np.ndarray:
    mu = X_tr.mean(axis=0)
    return np.linalg.norm(X_te - mu, axis=1)


def _eval_scores(scores: np.ndarray, labels: np.ndarray) -> dict[str, Any]:
    block = _auc_with_bootstrap(scores.tolist(), labels.tolist())
    return {
        "auc": float(block["auc"]),
        "auc_floor": float(block["auc_floor"]),
        "direction": block["direction"],
        "ci95_floor": block.get("ci95_floor"),
        "clears_floor": float(block["auc_floor"]) >= FLOOR,
    }


def _load_artifact_auc(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    a = obj["auc"]
    return {
        "auc": float(a["auc"]),
        "auc_floor": float(a["auc_floor"]),
        "direction": a["direction"],
        "ci95_floor": a.get("ci95_floor"),
        "artifact": str(path),
    }


def _raw_act_frac_matrix(tensors: dict, shas: list[str]) -> np.ndarray:
    rows = []
    for s in shas:
        x = tensors[s]["x"]
        if hasattr(x, "numpy"):
            x = x.numpy()
        rows.append(x[:, ACT_IDX].astype(np.float64))
    return np.stack(rows, axis=0)


def _per_coord_univariate(
    X_tr: np.ndarray, X_te: np.ndarray, labels: np.ndarray
) -> list[dict[str, Any]]:
    rows = []
    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        if cat in NON_PRODUCIBLE:
            rows.append(
                {
                    "category": cat,
                    "producible": False,
                    "raw_auc": float("nan"),
                    "raw_auc_floor": float("nan"),
                    "raw_direction": "N/A",
                    "dev_auc": float("nan"),
                    "dev_auc_floor": float("nan"),
                    "dev_direction": "N/A",
                    "delta_floor": float("nan"),
                    "direction_flipped": False,
                }
            )
            continue
        mu = float(X_tr[:, j].mean())
        s_tr = np.abs(X_tr[:, j] - mu)
        s_te = np.abs(X_te[:, j] - mu)
        rb = auc_raw_and_floor(s_te.tolist(), labels.tolist())
        rows.append(
            {
                "category": cat,
                "producible": True,
                "raw_auc": float(rb["auc"]),
                "raw_auc_floor": float(rb["auc_floor"]),
                "raw_direction": rb["direction"],
                "dev_auc": float("nan"),
                "dev_auc_floor": float("nan"),
                "dev_direction": "",
                "delta_floor": float("nan"),
                "direction_flipped": False,
            }
        )
    return rows


def _task1(ctx: dict[str, Any]) -> dict[str, Any]:
    tr, te = ctx["tr_idx"], ctx["te_idx"]
    labels = ctx["labels"]

    # Cell A — minimal construction (no exact persisted artifact)
    raw_scalar = np.linalg.norm(ctx["X_raw"], axis=1)
    mu_scalar = float(raw_scalar[tr].mean())
    scores_a = np.abs(raw_scalar[te] - mu_scalar)
    cell_a = {
        "cell": "A",
        "representation": "RAW",
        "readout": "SCALAR",
        "instantiation": (
            "Minimal: s_i = ||X_raw_i||_2 (704-d flattened input); "
            "benign-only score |s_i - mean_train_benign(s)|. No exact persisted artifact."
        ),
        **_eval_scores(scores_a, labels),
    }

    # Cells B, C, D — recompute + verify artifacts
    scores_b = _centroid_scores(ctx["X_raw"][tr], ctx["X_raw"][te])
    cell_b = {
        "cell": "B",
        "representation": "RAW",
        "readout": "PER-NODE",
        "instantiation": "RAW_full 704-d centroid Euclidean (ocdev raw_tensor control)",
        **_eval_scores(scores_b, labels),
        "artifact": str(ART["B"]),
    }
    art_b = _load_artifact_auc(ART["B"])
    if abs(cell_b["auc_floor"] - art_b["auc_floor"]) > 1e-4:
        raise SystemExit(f"STOP: cell B recompute {cell_b['auc_floor']} != artifact {art_b['auc_floor']}")

    scores_c = _centroid_scores(ctx["D0"][tr], ctx["D0"][te])
    cell_c = {
        "cell": "C",
        "representation": "DEV",
        "readout": "SCALAR",
        "instantiation": "D0 profile (1-d GAE recon error); centroid = |D0 - mu_train|",
        **_eval_scores(scores_c, labels),
        "artifact": str(ART["C"]),
    }
    art_c = _load_artifact_auc(ART["C"])
    if abs(cell_c["auc_floor"] - art_c["auc_floor"]) > 1e-4:
        raise SystemExit(f"STOP: cell C mismatch")

    scores_d = _centroid_scores(ctx["D1"][tr], ctx["D1"][te])
    cell_d = {
        "cell": "D",
        "representation": "DEV",
        "readout": "PER-NODE",
        "instantiation": "D1 profile (22-d); centroid L2 vs train-benign mean",
        **_eval_scores(scores_d, labels),
        "artifact": str(ART["D"]),
    }
    art_d = _load_artifact_auc(ART["D"])
    if abs(cell_d["auc_floor"] - art_d["auc_floor"]) > 1e-4:
        raise SystemExit(f"STOP: cell D mismatch")

    cells = {"A": cell_a, "B": cell_b, "C": cell_c, "D": cell_d}
    af = {k: cells[k]["auc_floor"] for k in "ABCD"}

    margins = {
        "referencing_at_scalar": af["C"] - af["A"],
        "referencing_at_per_node": af["D"] - af["B"],
        "readout_on_raw": af["B"] - af["A"],
        "readout_on_dev": af["D"] - af["C"],
        "interaction": (af["D"] - af["B"]) - (af["C"] - af["A"]),
    }

    margin_tests: dict[str, Any] = {}
    score_map = {
        "referencing_at_scalar": (scores_a, scores_c),
        "referencing_at_per_node": (scores_b, scores_d),
        "readout_on_raw": (scores_a, scores_b),
        "readout_on_dev": (scores_c, scores_d),
    }
    for name, delta in margins.items():
        if name == "interaction":
            margin_tests[name] = {"delta": delta, "tested": False, "reason": "interaction (derived margin)"}
            continue
        if abs(delta) <= 0.02:
            margin_tests[name] = {"delta": delta, "tested": False, "reason": "|delta|<=0.02"}
            continue
        s_lo, s_hi = score_map[name]
        margin_tests[name] = {
            "delta": delta,
            "tested": True,
            "delong": delong_test(labels, s_hi, s_lo),
            "paired_bootstrap": _paired_bootstrap_auc_diff(
                labels, s_hi, s_lo, B=PAIRED_BOOT_B, seed=PAIRED_BOOT_SEED
            ),
            "spearman_rho": float(spearmanr(s_lo, s_hi).statistic),
        }

    # Per-coordinate RAW (act_v_frac) vs DEV (D1)
    act = _raw_act_frac_matrix(ctx["tensors"], ctx["shas"])
    coord_rows = []
    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        if cat in NON_PRODUCIBLE:
            coord_rows.append(
                {
                    "category": cat,
                    "producible": False,
                    "raw_auc": "N/A",
                    "raw_auc_floor": "N/A",
                    "raw_direction": "N/A",
                    "dev_auc": "N/A",
                    "dev_auc_floor": "N/A",
                    "dev_direction": "N/A",
                    "delta_floor": "N/A",
                    "direction_flipped": "N/A",
                }
            )
            continue
        mu_r = float(act[tr, j].mean())
        mu_d = float(ctx["D1"][tr, j].mean())
        s_raw = np.abs(act[te, j] - mu_r)
        s_dev = np.abs(ctx["D1"][te, j] - mu_d)
        rb = auc_raw_and_floor(s_raw.tolist(), labels.tolist())
        db = auc_raw_and_floor(s_dev.tolist(), labels.tolist())
        flip = (rb["direction"] != db["direction"]) and rb["direction"] and db["direction"]
        coord_rows.append(
            {
                "category": cat,
                "producible": True,
                "raw_auc": float(rb["auc"]),
                "raw_auc_floor": float(rb["auc_floor"]),
                "raw_direction": rb["direction"],
                "dev_auc": float(db["auc"]),
                "dev_auc_floor": float(db["auc_floor"]),
                "dev_direction": db["direction"],
                "delta_floor": float(db["auc_floor"] - rb["auc_floor"]),
                "direction_flipped": bool(flip),
            }
        )
    coord_rows.sort(key=lambda r: (-999 if r["delta_floor"] == "N/A" else -float(r["delta_floor"])))

    prod = [r for r in coord_rows if r["producible"]]
    n_pos_delta = sum(1 for r in prod if r["delta_floor"] > 0)
    n_flip = sum(1 for r in prod if r["direction_flipped"])

    # Controls: volume covariates on B, C, D
    test_shas = ctx["test_shas"]
    cov_a4 = _table_a4_covariates(ctx["tensors"], test_shas, ctx["sha_to_app"])
    cov_legacy = _legacy_check3_covariates(ctx["tensors"], test_shas)
    cov = {**cov_a4, "static_feature_norm": cov_legacy["static_feature_norm"]}
    cov_keys = list(TABLE_A4_KEYS) + ["static_feature_norm"]

    vol: dict[str, Any] = {}
    for cell_name, sc in zip(("B", "C", "D"), (scores_b, scores_c, scores_d)):
        rhos = {}
        for k in cov_keys:
            rho, _ = spearmanr(sc, cov[k])
            rhos[k] = float(rho)
        vol[cell_name] = {
            "spearman": rhos,
            "max_abs_table_a4": max(abs(rhos[k]) for k in TABLE_A4_KEYS),
            "static_feature_norm_rho": rhos["static_feature_norm"],
        }

    # Shuffled labels on cell D
    rng = np.random.default_rng(SHUFFLE_SEED := 42)
    y_shuf = labels.copy()
    rng.shuffle(y_shuf)
    shuf_d = _eval_scores(scores_d, y_shuf)

    return {
        "cells": cells,
        "margins": margins,
        "margin_tests": margin_tests,
        "coord_rows": coord_rows,
        "coord_summary": {
            "n_producible": len(prod),
            "n_positive_delta": n_pos_delta,
            "n_direction_flip": n_flip,
            "flip_categories": [r["category"] for r in prod if r["direction_flipped"]],
        },
        "volume_covariates": vol,
        "shuffled_D": shuf_d,
    }


def _task2(ctx: dict[str, Any]) -> dict[str, Any]:
    win_pt = REPO / "abrg/output/androct_2017/selfref/windows/armb_n8_windows.pt"
    payload = torch.load(win_pt, map_location="cpu", weights_only=False)
    snap_cache = payload["snap_cache"]
    ws_csv = REPO / "abrg/output/androct_2017/selfref/deviations/window_scores.csv"

    eligible = ctx["eligible"]
    split = split_apps(eligible)
    test_apps = split["test_benign"] + split["test_malware"]
    strat = _stratified_split(eligible, seed=SEED, test_ratio=TEST_RATIO)
    train_apps = strat["train"]
    hgb_test_apps = strat["test_benign"] + strat["test_malware"]
    sha_list = [a.sha256 for a in eligible]

    cross_ref_seed = SEED + 909
    rng = np.random.default_rng(cross_ref_seed)

    def _build_stores(mode: str) -> tuple[dict, dict]:
        d_self: dict[str, dict[str, list[np.ndarray]]] = {"node": {}, "adj": {}}
        d_cross: dict[str, dict[str, list[np.ndarray]]] = {"node": {}, "adj": {}}
        for app in eligible:
            snaps = snap_cache[app.sha256]
            ref_i, test_i = _ref_test_indices(mode, app.sha256)
            Xs = [snaps[k]["x"].numpy().astype(np.float64) for k in ref_i]
            As = [snaps[k]["A"].numpy().astype(np.float64) for k in ref_i]
            R_x = np.mean(np.stack(Xs, axis=0), axis=0)
            R_a = np.mean(np.stack(As, axis=0), axis=0)
            d_self_n, d_self_a, d_cross_n, d_cross_a = [], [], [], []
            for ti in test_i:
                X = snaps[ti]["x"].numpy().astype(np.float64)
                A = snaps[ti]["A"].numpy().astype(np.float64)
                d_self_n.append(_d_node(X, R_x))
                d_self_a.append(_d_adj(A, R_a))
                candidates = [s for s in sha_list if s != app.sha256]
                j_sha = candidates[int(rng.integers(0, len(candidates)))]
                ref_j, _ = _ref_test_indices(mode, j_sha)
                Xs_j = [snap_cache[j_sha][k]["x"].numpy().astype(np.float64) for k in ref_j]
                As_j = [snap_cache[j_sha][k]["A"].numpy().astype(np.float64) for k in ref_j]
                R_xj = np.mean(np.stack(Xs_j, axis=0), axis=0)
                R_aj = np.mean(np.stack(As_j, axis=0), axis=0)
                d_cross_n.append(_d_node(X, R_xj))
                d_cross_a.append(_d_adj(A, R_aj))
            d_self["node"][app.sha256] = d_self_n
            d_self["adj"][app.sha256] = d_self_a
            d_cross["node"][app.sha256] = d_cross_n
            d_cross["adj"][app.sha256] = d_cross_a
        return d_self, d_cross

    def _app_vec(store: dict[str, list[np.ndarray]], a) -> np.ndarray:
        return np.concatenate(store[a.sha256], axis=0)

    def _cross_window_scores(
        d_cross: dict[str, dict[str, list[np.ndarray]]],
        mode: str,
        space: str,
        score_type: str,
        apps: list,
    ) -> dict[str, list[float]]:
        train_vecs: list[np.ndarray] = []
        for a in split["train"]:
            train_vecs.extend(d_cross[space][a.sha256])
        mu = np.mean(np.stack(train_vecs, axis=0), axis=0)
        out: dict[str, list[float]] = {}
        key = "scalar" if score_type == "SCALAR" else "centroid"
        for a in apps:
            sc = []
            for v in d_cross[space][a.sha256]:
                if score_type == "SCALAR":
                    sc.append(float(np.linalg.norm(v)))
                else:
                    sc.append(float(np.linalg.norm(v - mu)))
            out[a.sha256] = sc
        return out

    def _self_window_scores_from_csv(mode: str, space: str, score_type: str, apps: list) -> dict[str, list[float]]:
        col = "scalar_L2" if score_type == "SCALAR" else "centroid_L2"
        want_shas = {a.sha256 for a in apps}
        by_sha: dict[str, list[tuple[int, float]]] = defaultdict(list)
        with ws_csv.open(encoding="utf-8") as f:
            r = csv.DictReader(f)
            for row in r:
                if row["split_mode"] != mode or row["space"] != space:
                    continue
                if row["sha256"] not in want_shas:
                    continue
                by_sha[row["sha256"]].append((int(row["test_snap_idx"]), float(row[col])))
        return {s: [p[1] for p in sorted(by_sha[s])] for s in want_shas if s in by_sha}

    def _app_verdict(win: dict[str, list[float]], verdict: str, tau: float | None) -> dict[str, float]:
        out = {}
        for sha, sc in win.items():
            if verdict == "MEAN":
                out[sha] = float(np.mean(sc))
            elif verdict == "MAX":
                out[sha] = float(np.max(sc))
            elif verdict == "FRACTION":
                assert tau is not None
                out[sha] = float(np.mean([1.0 if s > tau else 0.0 for s in sc]))
            else:
                raise ValueError(verdict)
        return out

    def _train_benign_windows(mode: str, space: str, score_type: str, *, cross: bool, d_cross=None) -> list[float]:
        vals: list[float] = []
        if cross:
            assert d_cross is not None
            ws = _cross_window_scores(d_cross, mode, space, score_type, split["train"])
        else:
            ws = _self_window_scores_from_csv(mode, space, score_type, split["train"])
        for a in split["train"]:
            vals.extend(ws[a.sha256])
        return vals

    results_hgb: dict[str, Any] = {}
    results_oc: dict[str, Any] = {"self": {}, "cross": {}}
    y_te = np.array([1 if a.label == "malware" else 0 for a in hgb_test_apps])
    y_te_split = np.array([1 if a.label == "malware" else 0 for a in test_apps])

    stores_by_mode: dict[str, tuple] = {}
    for mode in ("PREFIX", "SCATTERED"):
        d_self, d_cross = _build_stores(mode)
        stores_by_mode[mode] = (d_self, d_cross)
        y_tr = np.array([1 if a.label == "malware" else 0 for a in train_apps])
        for space in ("node", "adj"):
            for tag, store in (("self", d_self), ("cross", d_cross)):
                X_tr = np.nan_to_num(np.stack([_app_vec(store[space], a) for a in train_apps]))
                X_te = np.nan_to_num(np.stack([_app_vec(store[space], a) for a in hgb_test_apps]))
                clf = HistGradientBoostingClassifier(
                    max_depth=6,
                    learning_rate=0.08,
                    max_iter=300,
                    random_state=SEED,
                    early_stopping=True,
                    validation_fraction=0.1,
                    n_iter_no_change=20,
                )
                clf.fit(X_tr, y_tr)
                sc = clf.predict_proba(X_te)[:, 1]
                results_hgb[f"{mode}_{tag}_{space}"] = _eval_scores(sc, y_te)

            for score_type in ("SCALAR", "CENTROID"):
                tb_self = _train_benign_windows(mode, space, score_type, cross=False)
                tb_cross = _train_benign_windows(mode, space, score_type, cross=True, d_cross=d_cross)
                tau_self = _pct(tb_self, 95.0)
                tau_cross = _pct(tb_cross, 95.0)
                ws_self = _self_window_scores_from_csv(mode, space, score_type, test_apps)
                ws_cross = _cross_window_scores(d_cross, mode, space, score_type, test_apps)
                for verdict in ("MEAN", "MAX", "FRACTION"):
                    for tag, ws, tau in (
                        ("self", ws_self, tau_self),
                        ("cross", ws_cross, tau_cross),
                    ):
                        app_sc = _app_verdict(ws, verdict, tau if verdict == "FRACTION" else None)
                        sc_arr = np.array([app_sc[a.sha256] for a in test_apps])
                        key = f"{mode}_{space}_{score_type}_{verdict}"
                        results_oc[tag][key] = _eval_scores(sc_arr, y_te_split)

    # Primary DeLong: PREFIX node HGB self vs cross
    d_self_p, d_cross_p = stores_by_mode["PREFIX"]
    y_tr = np.array([1 if a.label == "malware" else 0 for a in train_apps])
    X_tr_s = np.nan_to_num(np.stack([_app_vec(d_self_p["node"], a) for a in train_apps]))
    X_te_s = np.nan_to_num(np.stack([_app_vec(d_self_p["node"], a) for a in hgb_test_apps]))
    X_tr_c = np.nan_to_num(np.stack([_app_vec(d_cross_p["node"], a) for a in train_apps]))
    X_te_c = np.nan_to_num(np.stack([_app_vec(d_cross_p["node"], a) for a in hgb_test_apps]))
    clf_s = HistGradientBoostingClassifier(
        max_depth=6, learning_rate=0.08, max_iter=300, random_state=SEED,
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=20,
    )
    clf_s.fit(X_tr_s, y_tr)
    sc_self = clf_s.predict_proba(X_te_s)[:, 1]
    clf_c = HistGradientBoostingClassifier(
        max_depth=6, learning_rate=0.08, max_iter=300, random_state=SEED,
        early_stopping=True, validation_fraction=0.1, n_iter_no_change=20,
    )
    clf_c.fit(X_tr_c, y_tr)
    sc_cross = clf_c.predict_proba(X_te_c)[:, 1]
    delong_hgb_node = delong_test(y_te, sc_self, sc_cross)

    margin = results_hgb["PREFIX_self_node"]["auc_floor"] - results_hgb["PREFIX_cross_node"]["auc_floor"]
    verdict = "SELF_IS_LOAD_BEARING" if margin > 0.02 else "SELF_IS_DECORATIVE"

    e0_matrix = REPO / "abrg/output/androct_2017/selfref/matrix_24.csv"
    e0_self_oc: dict[str, float] = {}
    if e0_matrix.is_file():
        with e0_matrix.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["tag"] != "raw":
                    continue
                k = f"{row['split_mode']}_{row['space']}_{row['score_type']}_{row['verdict']}"
                e0_self_oc[k] = float(row["auc_floor"])

    return {
        "verdict": verdict,
        "cross_ref_seed": cross_ref_seed,
        "artifact_window_scores": str(ws_csv),
        "artifact_snap_cache": str(win_pt),
        "hgb": results_hgb,
        "one_class": results_oc,
        "e0_self_one_class_ref": e0_self_oc,
        "delong_hgb_node": delong_hgb_node,
        "margin_hgb_node_floor": margin,
        "e0_ref_ceiling_prefix_node": [0.9154, 0.9340],
        "thesis_sentence_if_decorative": (
            "A6_selfref.tex Phase 4: diagnostic ceiling 0.9154--0.9340 floor AUC on "
            "self-deviation d=|X-R_i| must be reframed as an app/window-profile ceiling "
            "under supervision, not evidence that self-deviation carries class information."
        ),
    }


def _task3(ctx: dict[str, Any]) -> dict[str, Any]:
    tr, te = ctx["tr_idx"], ctx["te_idx"]
    labels = ctx["labels"]
    sc_tr = _score_l2(ctx["D1"][tr], ctx["D1"][te])
    sc_ri = _score_l2(ctx["D1_ri"][tr], ctx["D1_ri"][te])

    ev_tr = _eval_scores(sc_tr, labels)
    ev_ri = _eval_scores(sc_ri, labels)
    art = _load_artifact_auc(ART["D_ri"])

    dl = delong_test(labels, sc_ri, sc_tr)
    pb = _paired_bootstrap_auc_diff(labels, sc_ri, sc_tr, B=PAIRED_BOOT_B, seed=PAIRED_BOOT_SEED)
    rho = float(spearmanr(sc_tr, sc_ri).statistic)
    distinguishable = not pb["contains_zero"]

    out: dict[str, Any] = {
        "trained_auc_floor": ev_tr["auc_floor"],
        "random_init_auc_floor": ev_ri["auc_floor"],
        "artifact_random_init": art,
        "delong": dl,
        "paired_bootstrap": pb,
        "spearman_rho": rho,
        "distinguishable": distinguishable,
        "prior_reporting": {
            "in_thesis_chapter_a": False,
            "grep_811844": "not found in thesis/chapter_a/*.tex",
            "catalogue_path": str(ART["D_ri"]),
            "catalogue_value": art["auc_floor"],
            "note": (
                "Seven-family table (tab:a6-family-sweep) pairs Run~8 embedding 0.7591, "
                "not random-init D1 centroid. Deviation-profile trained-vs-untrained row absent."
            ),
        },
    }

    if distinguishable:
        # Minimal extra controls on random-init scores
        test_shas = ctx["test_shas"]
        cov_a4 = _table_a4_covariates(ctx["tensors"], test_shas, ctx["sha_to_app"])
        cov_legacy = _legacy_check3_covariates(ctx["tensors"], test_shas)
        rhos = {}
        for k in TABLE_A4_KEYS:
            rhos[k] = float(spearmanr(sc_ri, cov_a4[k]).statistic)
        rhos["static_feature_norm"] = float(spearmanr(sc_ri, cov_legacy["static_feature_norm"]).statistic)
        out["controls_if_distinguishable"] = {"spearman_vs_scores": rhos}
    else:
        out["verdict"] = "NOT_DISTINGUISHABLE"

    return out


def _write_d3_report(t1: dict[str, Any]) -> None:
    cells = t1["cells"]
    m = t1["margins"]
    lines = [
        "# D-3: Referencing versus localisation (2×2 factorial)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Design",
        "",
        "Axis A: **RAW** = input tensor; **DEV** = deviation vs train-benign reference.",
        "Axis B: **SCALAR** = collapsed score; **PER-NODE** = vector centroid L2.",
        "",
        "## 2×2 floor AUC",
        "",
        "| Cell | Repr | Readout | AUC_floor | direction | clears 0.7025? | CI95 floor | instantiation |",
        "|------|------|---------|----------:|-----------|----------------|------------|---------------|",
    ]
    for k in "ABCD":
        c = cells[k]
        ci = c.get("ci95_floor")
        ci_s = f"[{ci[0]:.6f}, {ci[1]:.6f}]" if ci else ""
        lines.append(
            f"| {k} | {c['representation']} | {c['readout']} | {c['auc_floor']:.6f} | "
            f"{c['direction']} | {c['clears_floor']} | {ci_s} | {c['instantiation'][:60]}… |"
        )

    lines.extend(["", "## Margins", ""])
    for name, val in m.items():
        lines.append(f"- **{name}**: {val:+.6f}")

    lines.extend(["", "## Margin paired tests (|Δ|>0.02)", ""])
    for name, t in t1["margin_tests"].items():
        if not t.get("tested"):
            lines.append(f"- {name}: not tested ({t.get('reason')})")
        else:
            d = t["delong"]
            pb = t["paired_bootstrap"]
            lines.append(
                f"- {name}: Δ={t['delta']:+.6f}; DeLong p={d['p_two_sided']:.6f}; "
                f"bootstrap CI [{pb['ci95_diff_floor'][0]:+.6f}, {pb['ci95_diff_floor'][1]:+.6f}]; "
                f"ρ={t['spearman_rho']:.6f}; distinguishable={not pb['contains_zero']}"
            )

    cs = t1["coord_summary"]
    lines.extend(
        [
            "",
            "## Per-coordinate referencing (18 PRODUCIBLE; 4 N/A)",
            "",
            f"- Positive Δ (dev_floor - raw_floor): **{cs['n_positive_delta']}/{cs['n_producible']}**",
            f"- Direction reversals: **{cs['n_direction_flip']}** — {cs['flip_categories']}",
            "",
            "CSV: `results/D3_per_coordinate.csv`",
            "",
            "## Controls",
            "",
            f"- Shuffled labels cell D: AUC_floor **{t1['shuffled_D']['auc_floor']:.6f}**",
            "",
            "### Volume Spearman (cells B–D, test apps)",
            "",
        ]
    )
    for ck, v in t1["volume_covariates"].items():
        lines.append(
            f"- Cell {ck}: max |ρ| Table A.4 = {v['max_abs_table_a4']:.6f}; "
            f"static_feature_norm ρ = {v['static_feature_norm_rho']:.6f}"
        )

    lines.extend(["", "## Interpretation", ""])
    if m["interaction"] > 0.05:
        lines.append(
            "Large **interaction**: referencing gain differs by readout — referencing pays "
            "primarily at per-node readout (or vice versa)."
        )
    elif m["referencing_at_per_node"] > m["referencing_at_scalar"]:
        lines.append(
            "**Referencing** carries more of the climb at per-node readout; readout upgrade "
            "on DEV also contributes."
        )
    else:
        lines.append("Report margins numerically; interaction modest.")

    (RESULTS / "D3_referencing_vs_localisation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_task2_report(t2: dict[str, Any]) -> None:
    v = t2["verdict"]
    lines = [
        f"# VERDICT: **{v}**",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## d_self versus d_cross (AndroCT windows, PREFIX)",
        "",
        f"Cross-reference seed: **{t2['cross_ref_seed']}** (class-blind random other-app reference).",
        f"HGB node margin (self − cross) floor AUC: **{t2['margin_hgb_node_floor']:+.6f}**",
        "",
        "### Supervised HGB (DIAGNOSTIC CEILING — not a detector)",
        "",
        "| arm | space | AUC_floor | direction |",
        "|-----|-------|----------:|-----------|",
    ]
    for k, ev in t2["hgb"].items():
        lines.append(f"| {k} | — | {ev['auc_floor']:.6f} | {ev['direction']} |")

    lines.extend(["", "### One-class readouts (test apps)", ""])
    for tag in ("self", "cross"):
        lines.append(f"**{tag}**")
        for k, ev in t2["one_class"][tag].items():
            lines.append(f"- {k}: {ev['auc_floor']:.6f} ({ev['direction']})")

    d = t2["delong_hgb_node"]
    lines.extend(
        [
            "",
            "### DeLong (HGB node, self vs cross)",
            "",
            f"- Δ floor AUC: {d['auc_diff_floor']:+.6f}; z={d['z']:.6f}; p={d['p_two_sided']:.6f}",
            "",
            "## Cross-reference (different metrics — not directly comparable)",
            "",
            "- v2 E4: d_self/d_cross ratio 72×–411× at session granularity (Chapter B)",
            "- This task: window-level d vectors, PREFIX reference, HGB diagnostic ceiling",
            "",
            f"E0 reference ceiling PREFIX node: {t2['e0_ref_ceiling_prefix_node']}",
        ]
    )
    if v == "SELF_IS_DECORATIVE":
        lines.extend(["", "## Thesis sentence to soften", "", t2["thesis_sentence_if_decorative"]])

    (RESULTS / "d_self_vs_d_cross.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_task3_report(t3: dict[str, Any]) -> None:
    verdict = "DISTINGUISHABLE" if t3.get("distinguishable") else t3.get("verdict", "NOT_DISTINGUISHABLE")
    lines = [
        f"# VERDICT: **{verdict}**",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Random-init vs trained D1 centroid (paired, same test apps)",
        "",
        f"| scorer | AUC_floor |",
        f"|--------|----------:|",
        f"| trained D1 L2 | {t3['trained_auc_floor']:.6f} |",
        f"| random-init D1 L2 | {t3['random_init_auc_floor']:.6f} |",
        f"| Δ (RI − trained) | {t3['random_init_auc_floor'] - t3['trained_auc_floor']:+.6f} |",
        "",
        f"Catalogue artifact: `{t3['artifact_random_init']['artifact']}` → "
        f"{t3['artifact_random_init']['auc_floor']:.6f}",
        "",
        "### DeLong",
        "",
    ]
    d = t3["delong"]
    lines.append(
        f"- raw Δ={d['auc_diff_raw']:+.6f}; z={d['z']:.6f}; p={d['p_two_sided']:.6f}"
    )
    pb = t3["paired_bootstrap"]
    lines.extend(
        [
            "",
            "### Paired bootstrap (B=2000, floor-AUC difference)",
            "",
            f"- mean Δ={pb['mean_diff_floor']:+.6f}; CI [{pb['ci95_diff_floor'][0]:+.6f}, "
            f"{pb['ci95_diff_floor'][1]:+.6f}]; contains zero: {pb['contains_zero']}",
            f"- Spearman ρ={t3['spearman_rho']:.6f}",
            "",
            "## Prior reporting",
            "",
            f"- In Chapter A thesis tex: **{t3['prior_reporting']['in_thesis_chapter_a']}**",
            f"- {t3['prior_reporting']['note']}",
        ]
    )
    (RESULTS / "randominit_D1_paired.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    print("[d3] loading spine …", flush=True)
    ctx = _load_spine()
    print("[d3] task 1 factorial …", flush=True)
    t1 = _task1(ctx)
    print("[d3] task 2 d_self vs d_cross …", flush=True)
    t2 = _task2(ctx)
    print("[d3] task 3 random-init paired …", flush=True)
    t3 = _task3(ctx)

    RESULTS.mkdir(parents=True, exist_ok=True)

    # CSVs
    with (RESULTS / "D3_factorial_2x2.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["cell", "representation", "readout", "auc", "auc_floor", "direction", "clears_floor", "instantiation"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for k in "ABCD":
            w.writerow(t1["cells"][k])

    with (RESULTS / "D3_per_coordinate.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(t1["coord_rows"][0].keys()))
        w.writeheader()
        w.writerows(t1["coord_rows"])

    _write_d3_report(t1)
    _write_task2_report(t2)
    _write_task3_report(t3)

    summary = {"task1": t1, "task2": t2, "task3": t3}
    (RESULTS / "D3_hygiene_summary.json").write_text(
        json.dumps(summary, indent=2, default=_json_default) + "\n", encoding="utf-8"
    )
    print("[d3] done → results/D3_*.md", flush=True)


if __name__ == "__main__":
    main()
