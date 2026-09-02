"""Check 4 — S1_norm volume / OOV / shuffled-support."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import split_apps
from abrg.kernels.load import load_t1k
from abrg.ocdev.part_b import graph_adj
from abrg.ocdev_validate.check1 import _df_from_sparse, _s1_norm_from_sparse, _sparse_from_adj
from abrg.ocdev_validate.util import eval_auc_block, leak_rho, write_json
from abrg.validate.residual import apply_residual, ols_fit


SHUFFLE_SEEDS = tuple(range(42, 62))  # 20 seeds
EPS = 1e-12


def _s1_from_sparse(ii: np.ndarray, jj: np.ndarray, ww: np.ndarray, df: np.ndarray) -> float:
    if ww.size == 0:
        return 0.0
    return float(ww[df[ii, jj] == 0].sum())


def _cov_t1k(tensors: dict[str, dict], shas: list[str]) -> dict[str, list[float]]:
    rows = []
    for s in shas:
        t = tensors[s]
        sg = t.get("static_global")
        if hasattr(sg, "norm"):
            static = float(sg.norm().item())
        else:
            static = float(np.linalg.norm(np.asarray(sg, dtype=float))) if sg is not None else 0.0
        n_inv = float(t.get("n_inv_events", t.get("n_mapped", 0)))
        n_tot = float(t.get("n_total_events", t.get("n_events", 0)))
        oov = float(t["oov_rate"]) if "oov_rate" in t else (1.0 - n_inv / n_tot if n_tot else 1.0)
        rows.append(
            {
                "in_vocab_events": n_inv,
                "total_events": n_tot,
                "active_nodes": float(t["n_active"]),
                "edge_count": float(t["n_edges"]),
                "density": float(t["density"]),
                "oov_rate": oov,
                "static_norm": static,
            }
        )
    keys = rows[0].keys()
    return {k: [r[k] for r in rows] for k in keys}


def run_check4(*, out: Path, split_bundle: Any) -> dict[str, Any]:
    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train_shas = [a.sha256 for a in split["train"]]
    test_b = [a.sha256 for a in split["test_benign"]]
    test_m = [a.sha256 for a in split["test_malware"]]
    all_shas = train_shas + test_b + test_m
    t1k = load_t1k(by_sha=split_bundle.by_sha, all_shas=all_shas)
    print("[ocdev_validate/C4] sparsifying T1K adjs …", flush=True)
    train_sp = [_sparse_from_adj(graph_adj(t1k[s], 1000)) for s in train_shas]
    te_sp = [_sparse_from_adj(graph_adj(t1k[s], 1000)) for s in (test_b + test_m)]
    df = _df_from_sparse(train_sp, np.arange(len(train_sp)), 1000)

    print("[ocdev_validate/C4] scoring S1_norm …", flush=True)
    sc_tr = np.asarray([_s1_norm_from_sparse(ii, jj, ww, df) for ii, jj, ww in train_sp])
    sc_te = np.asarray([_s1_norm_from_sparse(ii, jj, ww, df) for ii, jj, ww in te_sp])
    labels = [0] * len(test_b) + [1] * len(test_m)
    te_shas = test_b + test_m
    cov = _cov_t1k(t1k, te_shas)
    rho = leak_rho(sc_te.tolist(), cov)
    raw_auc = eval_auc_block(sc_te.tolist(), labels)

    oov_tr = _cov_t1k(t1k, train_shas)["oov_rate"]
    oov_te = cov["oov_rate"]
    n_nz_tr = int(np.count_nonzero(sc_tr))
    train_s1_identically_zero = bool(n_nz_tr == 0)
    if train_s1_identically_zero:
        # OLS on a constant-0 target is degenerate; residual = raw score.
        resid = sc_te.tolist()
        resid_auc = eval_auc_block(resid, labels)
        meta = {
            "coef_intercept": 0.0,
            "coef_oov": 0.0,
            "r2": None,
            "n_fit": int(len(sc_tr)),
            "degenerate": True,
            "reason": (
                "train-benign S1_norm is identically 0 by construction "
                "(every nonzero train cell has df>0); OLS score~oov is undefined; "
                "residualisation is the identity"
            ),
        }
    else:
        reg, meta = ols_fit(sc_tr.tolist(), oov_tr)
        resid = apply_residual(reg, sc_te.tolist(), oov_te)
        resid_auc = eval_auc_block(resid, labels)
        meta["degenerate"] = False

    def _shuffle_block(score_fn, label: str) -> dict[str, Any]:
        floors = []
        per_seed = []
        sc_seed42 = None
        for seed in SHUFFLE_SEEDS:
            rng = np.random.default_rng(seed)
            flat = df.reshape(-1).copy()
            rng.shuffle(flat)
            df_sh = flat.reshape(df.shape)
            sc = [score_fn(ii, jj, ww, df_sh) for ii, jj, ww in te_sp]
            a = float(roc_auc_score(labels, sc))
            af = max(a, 1.0 - a)
            floors.append(af)
            per_seed.append(
                {
                    "seed": seed,
                    "auc": a,
                    "auc_floor": af,
                    "direction": "malware_higher_score" if a >= 0.5 else "benign_higher_score",
                }
            )
            if seed == 42:
                sc_seed42 = sc
        sh = np.asarray(floors, dtype=np.float64)
        out = {
            "score": label,
            "what_was_permuted": (
                "the 1000×1000 df matrix was flattened and the cell assignments "
                "randomly permuted (document-frequency values reassigned to cells); "
                "mean_w and sd_w were not permuted and are unused by S1/S1_norm"
            ),
            "n_seeds": len(SHUFFLE_SEEDS),
            "seeds": list(SHUFFLE_SEEDS),
            "per_seed": per_seed,
            "auc_floor_mean": float(np.mean(sh)),
            "auc_floor_std": float(np.std(sh, ddof=1)),
            "auc_floor_min": float(np.min(sh)),
            "auc_floor_max": float(np.max(sh)),
            "n_seeds_auc_floor_gt_0.55": int(np.sum(sh > 0.55)),
            "n_seeds_auc_floor_gt_0.50": int(np.sum(sh > 0.50)),
        }
        if sc_seed42 is not None:
            out["seed42_spearman_vs_volume"] = leak_rho(sc_seed42, cov)
        return out

    print("[ocdev_validate/C4] shuffle S1_norm and S1 × 20 …", flush=True)
    sh_norm = _shuffle_block(_s1_norm_from_sparse, "S1_norm")
    sh_raw = _shuffle_block(_s1_from_sparse, "S1")
    sh_raw["original_control_seed42_recorded"] = 0.5688944513975803
    sh_raw["seed42_matches_recorded"] = abs(
        next(r["auc_floor"] for r in sh_raw["per_seed"] if r["seed"] == 42) - 0.5688944513975803
    ) < 1e-6

    payload = {
        "score": "S1_norm",
        "family": "T1K_B_docfreq",
        "raw": raw_auc,
        "spearman_eval": rho,
        "residualisation": {
            "method": "OLS S1_norm ~ oov_rate, fit on 562 train-benign only (R2)",
            "train_benign_S1_norm_identically_zero": train_s1_identically_zero,
            "train_benign_n_nonzero": n_nz_tr,
            "ols": meta,
            "residualised": resid_auc,
            "residual_equals_raw": train_s1_identically_zero,
        },
        "shuffled_support": sh_norm,
        "shuffled_support_S1_raw": sh_raw,
    }
    write_json(out / "check4.json", payload)
    return payload
