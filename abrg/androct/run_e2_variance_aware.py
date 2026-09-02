"""
E2 — Variance-aware readouts on E0 self-reference deviation vectors.

No window rebuild, no reference recomputation for the main path.
Loads persisted d from abrg/output/androct_2017/selfref/.
Phase 4 conformal derives reference-window d from E0's cached
armb_n8_windows.pt (same builder; not a rebuild).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
from scipy.stats import spearmanr
from sklearn.covariance import LedoitWolf
from sklearn.decomposition import PCA

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_e0_selfref import (
    EXPECTED_DIGEST_PREFIX,
    FLOOR_MAPPED,
    N_NODES,
    N_PARTS,
    N_REF,
    N_TEST,
    SEED,
    _d_adj,
    _d_node,
    _pct,
    _ref_test_indices,
    _rho,
    _size_matched_apps,
    _stable_app_seed,
)
from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.apigraph.split import _sha_digest
from abrg.features import feature_vector_labels
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

E0_SELFREF = Path("abrg/output/androct_2017/selfref")
E0_BEST_RAW = 0.6997  # PREFIX SCALAR MAX node
E0_BEST_SM = 0.6235  # SCATTERED CENTROID MAX adj (size-matched)
EPS = 1e-8
ACT_V_FRAC_IDX = feature_vector_labels(normalize=True).index("act_v_frac")
assert len(GRAPH_CATEGORY_UNIVERSE) == N_NODES


def _load_d_store(dev_dir: Path) -> dict[str, dict[str, dict[str, np.ndarray]]]:
    """mode -> space -> sha -> [2, 22]"""
    out: dict[str, dict[str, dict[str, np.ndarray]]] = {}
    for mode in ("PREFIX", "SCATTERED"):
        out[mode] = {}
        for space in ("node", "adj"):
            sp = dev_dir / mode / space
            if not sp.is_dir():
                raise SystemExit(f"STOP: missing d dir {sp}")
            store: dict[str, np.ndarray] = {}
            for p in sp.glob("*.npy"):
                arr = np.load(p)
                if arr.shape != (N_TEST, N_NODES):
                    raise SystemExit(f"STOP: {p} shape {arr.shape} ≠ ({N_TEST},{N_NODES})")
                store[p.stem] = arr
            out[mode][space] = store
    return out


def _stack_train_benign(
    d_store: dict[str, np.ndarray],
    train_shas: list[str],
) -> np.ndarray:
    mats = [d_store[sha] for sha in train_shas]
    return np.concatenate(mats, axis=0)  # [n_train*2, 22]


def _phase1_diagnostic(
    X_tr: np.ndarray,
    X_tb: np.ndarray,
    X_tm: np.ndarray,
    node_var: np.ndarray,
    node_mapped_share: np.ndarray,
) -> dict[str, Any]:
    pca = PCA(n_components=N_NODES)
    pca.fit(X_tr)
    ev = pca.explained_variance_
    evr = pca.explained_variance_ratio_
    cum = np.cumsum(evr)

    def n_for(thresh: float) -> int:
        return int(np.searchsorted(cum, thresh) + 1)

    n50, n90, n99 = n_for(0.50), n_for(0.90), n_for(0.99)
    mars = bool(n90 <= math.floor(N_NODES / 3))  # under a third

    # Project onto each PC (sorted descending variance — PCA default)
    axes = []
    ratios = []
    for i in range(N_NODES):
        u = pca.components_[i]
        msq_b = float(np.mean((X_tb @ u) ** 2))
        msq_m = float(np.mean((X_tm @ u) ** 2))
        ratio = msq_m / msq_b if msq_b > 0 else float("nan")
        axes.append(
            {
                "pc": i,
                "eigenvalue": float(ev[i]),
                "var_ratio": float(evr[i]),
                "cum_var": float(cum[i]),
                "msq_benign": msq_b,
                "msq_malware": msq_m,
                "malware_benign_ratio": ratio,
            }
        )
        ratios.append(ratio)

    ratios_a = np.array(ratios, dtype=np.float64)
    third = N_NODES // 3
    high = ratios_a[:third]
    low = ratios_a[-third:]
    # Separation strength: |log(ratio)| — away from 1
    sep_high = float(np.nanmean(np.abs(np.log(np.clip(high, 1e-12, None)))))
    sep_low = float(np.nanmean(np.abs(np.log(np.clip(low, 1e-12, None)))))
    # Also mean ratio deviation from 1
    mean_abs_log_all = float(np.nanmean(np.abs(np.log(np.clip(ratios_a, 1e-12, None)))))

    if mean_abs_log_all < 0.05:  # ratios ~ within ~5% of 1 on average
        verdict = "NO_SEPARATION"
        where = "nowhere — malware:benign projection ratios ≈ 1 on every axis"
    elif sep_low > sep_high * 1.15:
        verdict = "LOW_VARIANCE_SEPARATION"
        where = (
            "low-variance axes — MaRS regime "
            f"(mean |log ratio| low-third={sep_low:.4f} > high-third={sep_high:.4f})"
        )
    elif sep_high > sep_low * 1.15:
        verdict = "HIGH_VARIANCE_SEPARATION"
        where = (
            "high-variance axes — opposite of MaRS "
            f"(mean |log ratio| high-third={sep_high:.4f} > low-third={sep_low:.4f})"
        )
    else:
        # borderline — pick the larger
        if sep_low >= sep_high:
            verdict = "LOW_VARIANCE_SEPARATION"
            where = f"weakly low-variance (sep_low={sep_low:.4f}, sep_high={sep_high:.4f})"
        else:
            verdict = "HIGH_VARIANCE_SEPARATION"
            where = f"weakly high-variance (sep_high={sep_high:.4f}, sep_low={sep_low:.4f})"

    rho_var_share = _rho(node_var.tolist(), node_mapped_share.tolist())

    return {
        "eigenvalues": ev.tolist(),
        "explained_variance_ratio": evr.tolist(),
        "cumulative_variance": cum.tolist(),
        "n_components_50": n50,
        "n_components_90": n90,
        "n_components_99": n99,
        "mars_condition_90pct_under_third": mars,
        "n_under_third": math.floor(N_NODES / 3),
        "axes": axes,
        "sep_high_third": sep_high,
        "sep_low_third": sep_low,
        "mean_abs_log_ratio_all": mean_abs_log_all,
        "separation_where": where,
        "verdict": verdict,
        "node_variance": {
            GRAPH_CATEGORY_UNIVERSE[j]: float(node_var[j]) for j in range(N_NODES)
        },
        "node_mapped_share": {
            GRAPH_CATEGORY_UNIVERSE[j]: float(node_mapped_share[j]) for j in range(N_NODES)
        },
        "spearman_rho_node_var_vs_mapped_share": rho_var_share,
        "pca_components": pca.components_.tolist(),  # for optional later use
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="E2 variance-aware selfref readouts")
    parser.add_argument(
        "--e0-dir",
        type=Path,
        default=E0_SELFREF,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("abrg/output/androct_2017/selfref_e2"),
    )
    parser.add_argument(
        "--results-md",
        type=Path,
        default=Path("results/E2_variance_aware.md"),
    )
    args = parser.parse_args()
    e0 = args.e0_dir
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    dev_dir = e0 / "deviations"

    # ── Input assertions ─────────────────────────────────────
    bundle = load_corpus_cache(androct_run2_output_dir())
    digest = _sha_digest(bundle.split)
    if not digest.startswith(EXPECTED_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: digest {digest[:12]} ≠ prefix {EXPECTED_DIGEST_PREFIX}"
        )
    split = bundle.split
    n_tr, n_tb, n_tm = (
        len(split["train"]),
        len(split["test_benign"]),
        len(split["test_malware"]),
    )
    if (n_tr, n_tb, n_tm) != (562, 141, 1700):
        raise SystemExit(f"STOP: split {n_tr}/{n_tb}/{n_tm} ≠ 562/141/1700")
    print(f"[E2] digest={digest[:12]}… split={n_tr}/{n_tb}/{n_tm}", flush=True)

    d_all = _load_d_store(dev_dir)
    eligible = list(bundle.eligible)
    train_shas = [a.sha256 for a in split["train"]]
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            store = d_all[mode][space]
            if len(store) != 2403:
                raise SystemExit(
                    f"STOP: {mode}/{space} has {len(store)} apps ≠ 2403"
                )
            missing = [s for s in train_shas if s not in store]
            if missing:
                raise SystemExit(f"STOP: missing train d for {missing[0]}")
    print("[E2] d vectors asserted OK", flush=True)

    # Load window cache only for Phase 1d mapped share + Phase 4 conformal refs
    win_pt = e0 / "windows" / "armb_n8_windows.pt"
    if not win_pt.is_file():
        raise SystemExit(f"STOP: missing window cache {win_pt} (needed for 1d + conformal)")
    win_payload = torch.load(win_pt, map_location="cpu", weights_only=False)
    snap_cache: dict[str, list[dict[str, Any]]] = win_payload["snap_cache"]

    # Node mapped-event share on train-benign (mean act_v_frac over all 8 windows)
    share_acc = np.zeros(N_NODES, dtype=np.float64)
    n_share = 0
    for a in split["train"]:
        for s in snap_cache[a.sha256]:
            x = s["x"].numpy().astype(np.float64)
            share_acc += x[:, ACT_V_FRAC_IDX]
            n_share += 1
    node_mapped_share = share_acc / max(n_share, 1)

    # ── Phase 1: anisotropy (primary on PREFIX/node; also emit adj) ──
    phase1_by: dict[tuple[str, str], dict[str, Any]] = {}
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            store = d_all[mode][space]
            X_tr = _stack_train_benign(store, train_shas)
            X_tb = np.concatenate(
                [store[a.sha256] for a in split["test_benign"]], axis=0
            )
            X_tm = np.concatenate(
                [store[a.sha256] for a in split["test_malware"]], axis=0
            )
            node_var = X_tr.var(axis=0)
            diag = _phase1_diagnostic(X_tr, X_tb, X_tm, node_var, node_mapped_share)
            # drop bulky components from per-mode save except primary
            phase1_by[(mode, space)] = diag
            print(
                f"[E2] Phase1 {mode}/{space}: verdict={diag['verdict']} "
                f"n90={diag['n_components_90']} mars={diag['mars_condition_90pct_under_third']}",
                flush=True,
            )

    # Primary diagnostic for gating: PREFIX node (matches E0 best space)
    phase1 = phase1_by[("PREFIX", "node")]
    gate_verdict = phase1["verdict"]

    # Persist phase1 (strip pca_components from secondary to keep JSON lean)
    phase1_out = {}
    for (mode, space), d in phase1_by.items():
        slim = {k: v for k, v in d.items() if k != "pca_components"}
        phase1_out[f"{mode}_{space}"] = slim
    (out / "phase1_anisotropy.json").write_text(
        json.dumps(phase1_out, indent=2) + "\n"
    )
    np.save(out / "node_variance_PREFIX_node.npy", np.array(
        [phase1["node_variance"][c] for c in GRAPH_CATEGORY_UNIVERSE]
    ))

    # ── Fit scorers Phase 2–3 ─────────────────────────────────
    scorers: dict[tuple[str, str, str], dict[str, Any]] = {}
    # key: (mode, space, score_type) -> {fn, meta}

    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            store = d_all[mode][space]
            X_tr = _stack_train_benign(store, train_shas)
            mu = X_tr.mean(axis=0)
            # Phase 2 Mahalanobis
            lw = LedoitWolf().fit(X_tr)
            S = lw.covariance_
            # condition number
            eig = np.linalg.eigvalsh(S)
            cond = float(eig.max() / max(eig.min(), 1e-18))
            try:
                S_inv = np.linalg.inv(S)
            except np.linalg.LinAlgError:
                S_inv = np.linalg.pinv(S)
            shrinkage = float(getattr(lw, "shrinkage_", float("nan")))

            def make_maha(mu_=mu, S_inv_=S_inv):
                def score(d: np.ndarray) -> float:
                    v = d - mu_
                    return float(v @ S_inv_ @ v)

                return score

            scorers[(mode, space, "MAHALANOBIS")] = {
                "fn": make_maha(),
                "mu": mu,
                "cond": cond,
                "shrinkage": shrinkage,
                "eig_min": float(eig.min()),
                "eig_max": float(eig.max()),
            }
            np.save(out / f"cov_{mode}_{space}.npy", S)

            # Phase 3 per-node std
            sigma = X_tr.std(axis=0) + EPS

            def make_z(sigma_=sigma):
                def score(d: np.ndarray) -> float:
                    z = d / sigma_
                    return float(np.linalg.norm(z))

                return score

            scorers[(mode, space, "NODE_STD")] = {
                "fn": make_z(),
                "sigma": sigma,
            }
            np.save(out / f"sigma_{mode}_{space}.npy", sigma)

    print("[E2] Phase2–3 scorers fitted (train-benign only)", flush=True)

    # Precompute all window scores
    # rows: sha, mode, space, score_type, test_snap_pos (0/1), score, label, partition, n_mapped
    app_by_sha = {a.sha256: a for a in eligible}
    train_sha_set = set(train_shas)

    window_rows: list[dict[str, Any]] = []
    # Also store scores keyed for fast lookup
    # scores[(mode, space, score_type)][sha] = [s0, s1]
    score_tables: dict[tuple[str, str, str], dict[str, list[float]]] = {}

    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            for stype in ("MAHALANOBIS", "NODE_STD"):
                fn = scorers[(mode, space, stype)]["fn"]
                table: dict[str, list[float]] = {}
                store = d_all[mode][space]
                for sha, arr in store.items():
                    sc = [fn(arr[i]) for i in range(N_TEST)]
                    table[sha] = sc
                    a = app_by_sha[sha]
                    part = (
                        "train"
                        if sha in train_sha_set
                        else ("test_benign" if a.label == "benign" else "test_malware")
                    )
                    for i, s in enumerate(sc):
                        window_rows.append(
                            {
                                "sha256": sha,
                                "label": a.label,
                                "partition": part,
                                "split_mode": mode,
                                "space": space,
                                "score_type": stype,
                                "test_pos": i,
                                "score": s,
                                "n_mapped_app": int(a.n_mapped),
                            }
                        )
                score_tables[(mode, space, stype)] = table

    with (out / "window_scores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(window_rows[0].keys()))
        w.writeheader()
        w.writerows(window_rows)

    def train_benign_window_scores(mode, space, stype) -> list[float]:
        t = score_tables[(mode, space, stype)]
        vals = []
        for sha in train_shas:
            vals.extend(t[sha])
        return vals

    def app_verdict(
        win_scores: dict[str, list[float]],
        verdict: str,
        tau: float | None,
    ) -> dict[str, float]:
        out_m = {}
        for sha, sc in win_scores.items():
            if verdict == "MEAN":
                out_m[sha] = float(np.mean(sc))
            elif verdict == "MAX":
                out_m[sha] = float(np.max(sc))
            elif verdict == "FRACTION":
                assert tau is not None
                out_m[sha] = float(np.mean([1.0 if s > tau else 0.0 for s in sc]))
            else:
                raise ValueError(verdict)
        return out_m

    def eval_auc(
        scores_by_sha: dict[str, float],
        test_benign: list,
        test_malware: list,
    ) -> dict[str, Any]:
        scores = [scores_by_sha[a.sha256] for a in test_benign] + [
            scores_by_sha[a.sha256] for a in test_malware
        ]
        labels = [0] * len(test_benign) + [1] * len(test_malware)
        return _auc_with_bootstrap(scores, labels)

    def run_matrix(
        test_benign: list,
        test_malware: list,
        *,
        tag: str,
    ) -> list[dict[str, Any]]:
        rows = []
        apps = test_benign + test_malware
        for mode in ("PREFIX", "SCATTERED"):
            for space in ("node", "adj"):
                for stype in ("MAHALANOBIS", "NODE_STD"):
                    tb_win = train_benign_window_scores(mode, space, stype)
                    tau95 = _pct(tb_win, 95)
                    win_all = {
                        a.sha256: score_tables[(mode, space, stype)][a.sha256]
                        for a in apps
                    }
                    for verdict in ("MEAN", "MAX", "FRACTION"):
                        tau = tau95 if verdict == "FRACTION" else None
                        app_sc = app_verdict(win_all, verdict, tau)
                        auc = eval_auc(app_sc, test_benign, test_malware)
                        rho_b = _rho(
                            [app_sc[a.sha256] for a in test_benign],
                            [float(a.n_mapped) for a in test_benign],
                        )
                        rho_m = _rho(
                            [app_sc[a.sha256] for a in test_malware],
                            [float(a.n_mapped) for a in test_malware],
                        )
                        meta = scorers[(mode, space, stype)]
                        rows.append(
                            {
                                "tag": tag,
                                "split_mode": mode,
                                "score_type": stype,
                                "verdict": verdict,
                                "space": space,
                                "auc": auc["auc"],
                                "auc_floor": auc["auc_floor"],
                                "direction": auc["direction"],
                                "ci95_floor_lo": auc["ci95_floor"][0],
                                "ci95_floor_hi": auc["ci95_floor"][1],
                                "clears_floor": bool(auc["auc_floor"] >= FLOOR_MAPPED),
                                "tau95": tau95 if verdict == "FRACTION" else "",
                                "rho_benign": rho_b,
                                "rho_malware": rho_m,
                                "n_test_benign": len(test_benign),
                                "n_test_malware": len(test_malware),
                                "cond_S": meta.get("cond", ""),
                                "shrinkage": meta.get("shrinkage", ""),
                            }
                        )
        return rows

    print("[E2] Phase2–3 raw matrix …", flush=True)
    matrix_raw = run_matrix(split["test_benign"], split["test_malware"], tag="raw")

    n_mapped_map = {a.sha256: int(a.n_mapped) for a in eligible}
    scored = split["test_benign"] + split["test_malware"]
    matched, size_meta = _size_matched_apps(scored, n_mapped_map)
    matched_b = [a for a in matched if a.label == "benign"]
    matched_m = [a for a in matched if a.label == "malware"]
    print(
        f"[E2] size-matched n_benign={len(matched_b)} n_malware={len(matched_m)} "
        f"overlap=[{size_meta['overlap_lo']:.1f},{size_meta['overlap_hi']:.1f}]",
        flush=True,
    )
    matrix_matched = run_matrix(matched_b, matched_m, tag="size_matched")

    matrix_csv = out / "matrix.csv"
    with matrix_csv.open("w", newline="", encoding="utf-8") as f:
        fields = list(matrix_raw[0].keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(matrix_raw)
        w.writerows(matrix_matched)

    # Tau sweep
    tau_rows = []
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            for stype in ("MAHALANOBIS", "NODE_STD"):
                tb_win = train_benign_window_scores(mode, space, stype)
                win_all = {
                    a.sha256: score_tables[(mode, space, stype)][a.sha256]
                    for a in scored
                }
                for p in range(50, 100):
                    tau = _pct(tb_win, float(p))
                    app_sc = app_verdict(win_all, "FRACTION", tau)
                    auc = eval_auc(app_sc, split["test_benign"], split["test_malware"])
                    tau_rows.append(
                        {
                            "split_mode": mode,
                            "space": space,
                            "score_type": stype,
                            "tau_percentile": p,
                            "tau": tau,
                            "auc_floor": auc["auc_floor"],
                            "direction": auc["direction"],
                        }
                    )
    with (out / "tau_sweep.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(tau_rows[0].keys()))
        w.writeheader()
        w.writerows(tau_rows)

    # Best Phase 2–3 for conformal / ablation
    best_raw = max(matrix_raw, key=lambda r: float(r["auc_floor"]))
    best_sm = max(matrix_matched, key=lambda r: float(r["auc_floor"]))
    e2_best_floor = float(best_raw["auc_floor"])
    if e2_best_floor > E0_BEST_RAW:
        wrap = {
            "source": "E2",
            "split_mode": best_raw["split_mode"],
            "space": best_raw["space"],
            "score_type": best_raw["score_type"],
            "verdict_ref": best_raw["verdict"],
            "auc_floor": e2_best_floor,
        }
    else:
        wrap = {
            "source": "E0",
            "split_mode": "PREFIX",
            "space": "node",
            "score_type": "SCALAR",
            "verdict_ref": "MAX",
            "auc_floor": E0_BEST_RAW,
            "note": "E2 did not improve on E0 best raw; conformal wraps E0 SCALAR",
        }
    # Ablation always on best E2 Phase 2–3 readout (not E0)
    abl_target = {
        "split_mode": best_raw["split_mode"],
        "space": best_raw["space"],
        "score_type": best_raw["score_type"],
        "verdict": best_raw["verdict"],
        "auc_floor": e2_best_floor,
    }
    print(f"[E2] wrap={wrap['source']} {wrap}; abl_target={abl_target}", flush=True)

    # ── Phase 4: conformal ───────────────────────────────────
    print("[E2] Phase4 conformal …", flush=True)

    def score_d_vector(d: np.ndarray, mode: str, space: str, stype: str) -> float:
        if stype in ("MAHALANOBIS", "NODE_STD"):
            return scorers[(mode, space, stype)]["fn"](d)
        if stype == "SCALAR":
            return float(np.linalg.norm(d))
        raise ValueError(stype)

    def compute_all_window_d(
        mode: str, space: str, sha: str
    ) -> tuple[list[np.ndarray], list[int], list[int]]:
        """Return d for all 8 windows vs R_i = mean of ref tensors; plus ref/test idx."""
        snaps = snap_cache[sha]
        ref_i, test_i = _ref_test_indices(mode, sha)
        if space == "node":
            mats = [snaps[i]["x"].numpy().astype(np.float64) for i in ref_i]
            R = np.mean(np.stack(mats, axis=0), axis=0)
            ds = []
            for i in range(N_PARTS):
                X = snaps[i]["x"].numpy().astype(np.float64)
                ds.append(_d_node(X, R))
        else:
            mats = [snaps[i]["A"].numpy().astype(np.float64) for i in ref_i]
            R = np.mean(np.stack(mats, axis=0), axis=0)
            ds = []
            for i in range(N_PARTS):
                A = snaps[i]["A"].numpy().astype(np.float64)
                ds.append(_d_adj(A, R))
        return ds, ref_i, test_i

    w_mode = wrap["split_mode"]
    w_space = wrap["space"]
    w_stype = wrap["score_type"]

    conformal_rows = []
    # For AUC: use min_p as score (lower = more anomalous)
    conf_min_p: dict[str, float] = {}
    conf_frac: dict[float, dict[str, float]] = {0.05: {}, 0.1: {}, 0.2: {}}
    raw_wrap_scores: dict[str, float] = {}  # MEAN of test scores for rho comparison

    for a in eligible:
        ds, ref_i, test_i = compute_all_window_d(w_mode, w_space, a.sha256)
        calib = [score_d_vector(ds[i], w_mode, w_space, w_stype) for i in ref_i]
        test_sc = [score_d_vector(ds[i], w_mode, w_space, w_stype) for i in test_i]
        pvals = []
        for ts in test_sc:
            n_ge = sum(1 for c in calib if c >= ts)
            p = (1 + n_ge) / (len(calib) + 1)
            pvals.append(p)
        min_p = float(min(pvals))
        conf_min_p[a.sha256] = min_p
        for alpha in conf_frac:
            conf_frac[alpha][a.sha256] = float(
                np.mean([1.0 if p < alpha else 0.0 for p in pvals])
            )
        raw_wrap_scores[a.sha256] = float(np.mean(test_sc))
        conformal_rows.append(
            {
                "sha256": a.sha256,
                "label": a.label,
                "min_p": min_p,
                "p0": pvals[0],
                "p1": pvals[1],
                "frac_p_lt_0.05": conf_frac[0.05][a.sha256],
                "frac_p_lt_0.1": conf_frac[0.1][a.sha256],
                "frac_p_lt_0.2": conf_frac[0.2][a.sha256],
                "raw_mean_score": raw_wrap_scores[a.sha256],
                "n_mapped": int(a.n_mapped),
            }
        )

    with (out / "conformal_per_app.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(conformal_rows[0].keys()))
        w.writeheader()
        w.writerows(conformal_rows)

    conformal_auc_rows = []
    # min_p: lower more anomalous → use as score; AUC floor handles direction
    for name, scores_map in [
        ("min_p", conf_min_p),
        ("frac_p_lt_0.05", conf_frac[0.05]),
        ("frac_p_lt_0.1", conf_frac[0.1]),
        ("frac_p_lt_0.2", conf_frac[0.2]),
    ]:
        for tag, tb, tm in [
            ("raw", split["test_benign"], split["test_malware"]),
            ("size_matched", matched_b, matched_m),
        ]:
            auc = eval_auc(scores_map, tb, tm)
            rho_b = _rho(
                [scores_map[a.sha256] for a in tb],
                [float(a.n_mapped) for a in tb],
            )
            rho_m = _rho(
                [scores_map[a.sha256] for a in tm],
                [float(a.n_mapped) for a in tm],
            )
            conformal_auc_rows.append(
                {
                    "tag": tag,
                    "verdict": name,
                    "auc_floor": auc["auc_floor"],
                    "direction": auc["direction"],
                    "ci95_floor_lo": auc["ci95_floor"][0],
                    "ci95_floor_hi": auc["ci95_floor"][1],
                    "clears_floor": bool(auc["auc_floor"] >= FLOOR_MAPPED),
                    "rho_benign": rho_b,
                    "rho_malware": rho_m,
                    "n_test_benign": len(tb),
                    "n_test_malware": len(tm),
                    "wrap_source": wrap["source"],
                    "wrap_score": w_stype,
                    "wrap_mode": w_mode,
                    "wrap_space": w_space,
                }
            )

    # Volume coupling reduction: |rho| of raw wrap vs |rho| of min_p
    rho_raw_b = _rho(
        [raw_wrap_scores[a.sha256] for a in split["test_benign"]],
        [float(a.n_mapped) for a in split["test_benign"]],
    )
    rho_raw_m = _rho(
        [raw_wrap_scores[a.sha256] for a in split["test_malware"]],
        [float(a.n_mapped) for a in split["test_malware"]],
    )
    rho_conf_b = next(
        r["rho_benign"]
        for r in conformal_auc_rows
        if r["tag"] == "raw" and r["verdict"] == "min_p"
    )
    rho_conf_m = next(
        r["rho_malware"]
        for r in conformal_auc_rows
        if r["tag"] == "raw" and r["verdict"] == "min_p"
    )
    conformal_volume = {
        "rho_raw_benign": rho_raw_b,
        "rho_raw_malware": rho_raw_m,
        "rho_min_p_benign": rho_conf_b,
        "rho_min_p_malware": rho_conf_m,
        "abs_rho_reduced_benign": abs(rho_raw_b) - abs(rho_conf_b)
        if not (math.isnan(rho_raw_b) or math.isnan(rho_conf_b))
        else float("nan"),
        "abs_rho_reduced_malware": abs(rho_raw_m) - abs(rho_conf_m)
        if not (math.isnan(rho_raw_m) or math.isnan(rho_conf_m))
        else float("nan"),
    }

    with (out / "conformal_auc.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(conformal_auc_rows[0].keys()))
        w.writeheader()
        w.writerows(conformal_auc_rows)

    # ── Phase 5: shuffled labels ──────────────────────────────
    print("[E2] Phase5 shuffled + delta + E0 compare + ablation …", flush=True)
    rng_shuf = np.random.default_rng(SEED)
    shuffle_rows = []
    for r in matrix_raw:
        mode, space, stype, verdict = (
            r["split_mode"],
            r["space"],
            r["score_type"],
            r["verdict"],
        )
        tb_win = train_benign_window_scores(mode, space, stype)
        tau95 = _pct(tb_win, 95)
        win_all = {
            a.sha256: score_tables[(mode, space, stype)][a.sha256]
            for a in scored
        }
        app_sc = app_verdict(
            win_all, verdict, tau95 if verdict == "FRACTION" else None
        )
        scores = [app_sc[a.sha256] for a in split["test_benign"]] + [
            app_sc[a.sha256] for a in split["test_malware"]
        ]
        labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
        labels_s = list(labels)
        rng_shuf.shuffle(labels_s)
        auc = _auc_with_bootstrap(scores, labels_s)
        shuffle_rows.append(
            {
                "split_mode": mode,
                "score_type": stype,
                "verdict": verdict,
                "space": space,
                "auc_floor": auc["auc_floor"],
                "direction": auc["direction"],
            }
        )
    with (out / "shuffled_labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(shuffle_rows[0].keys()))
        w.writeheader()
        w.writerows(shuffle_rows)
    shuf_mean = float(np.mean([r["auc_floor"] for r in shuffle_rows]))

    # PREFIX - SCATTERED delta
    raw_by = {
        (r["score_type"], r["verdict"], r["space"], r["split_mode"]): r
        for r in matrix_raw
    }
    delta_rows = []
    for stype in ("MAHALANOBIS", "NODE_STD"):
        for verdict in ("MEAN", "MAX", "FRACTION"):
            for space in ("node", "adj"):
                p = raw_by[(stype, verdict, space, "PREFIX")]
                s = raw_by[(stype, verdict, space, "SCATTERED")]
                delta_rows.append(
                    {
                        "score_type": stype,
                        "verdict": verdict,
                        "space": space,
                        "auc_floor_prefix": p["auc_floor"],
                        "auc_floor_scattered": s["auc_floor"],
                        "delta_prefix_minus_scattered": p["auc_floor"] - s["auc_floor"],
                    }
                )
    with (out / "prefix_scattered_delta.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(delta_rows[0].keys()))
        w.writeheader()
        w.writerows(delta_rows)
    mean_abs_delta = float(
        np.mean([abs(r["delta_prefix_minus_scattered"]) for r in delta_rows])
    )

    # E0 comparison — load E0 matrix
    e0_matrix = list(
        csv.DictReader((e0 / "matrix_24.csv").open(encoding="utf-8"))
    )
    # Map E2 cells to E0 counterparts: same verdict, space, split; E0 SCALAR↔MAH/NODE via geometry
    # Spec: "every E2 readout beside its E0 counterpart (SCALAR 0.6997 raw / 0.6235 size-matched)"
    # Pair MAHALANOBIS with CENTROID (both use mu_benign), NODE_STD with SCALAR (both L2-like)
    e0_pair = {"MAHALANOBIS": "CENTROID", "NODE_STD": "SCALAR"}
    e0_compare_rows = []
    for r in matrix_raw + matrix_matched:
        e0_stype = e0_pair[r["score_type"]]
        e0_r = next(
            (
                x
                for x in e0_matrix
                if x["tag"] == r["tag"]
                and x["split_mode"] == r["split_mode"]
                and x["verdict"] == r["verdict"]
                and x["space"] == r["space"]
                and x["score_type"] == e0_stype
            ),
            None,
        )
        e0_floor = float(e0_r["auc_floor"]) if e0_r else float("nan")
        e2_floor = float(r["auc_floor"])
        e0_compare_rows.append(
            {
                "tag": r["tag"],
                "split_mode": r["split_mode"],
                "verdict": r["verdict"],
                "space": r["space"],
                "e2_score": r["score_type"],
                "e0_score": e0_stype,
                "e2_auc_floor": e2_floor,
                "e0_auc_floor": e0_floor,
                "delta_e2_minus_e0": e2_floor - e0_floor
                if e0_r
                else float("nan"),
                "e2_direction": r["direction"],
                "e0_direction": e0_r["direction"] if e0_r else "",
            }
        )
    with (out / "e0_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(e0_compare_rows[0].keys()))
        w.writeheader()
        w.writerows(e0_compare_rows)

    # Headline: any E2 improvement?
    raw_deltas = [
        r["delta_e2_minus_e0"]
        for r in e0_compare_rows
        if r["tag"] == "raw" and not math.isnan(r["delta_e2_minus_e0"])
    ]
    sm_deltas = [
        r["delta_e2_minus_e0"]
        for r in e0_compare_rows
        if r["tag"] == "size_matched" and not math.isnan(r["delta_e2_minus_e0"])
    ]
    headline = {
        "e2_best_raw": e2_best_floor,
        "e0_best_raw": E0_BEST_RAW,
        "e2_best_size_matched": float(best_sm["auc_floor"]),
        "e0_best_size_matched": E0_BEST_SM,
        "max_delta_raw": float(max(raw_deltas)) if raw_deltas else float("nan"),
        "max_delta_size_matched": float(max(sm_deltas)) if sm_deltas else float("nan"),
        "any_clears_floor_raw": any(r["clears_floor"] for r in matrix_raw),
        "any_clears_floor_size_matched": any(
            r["clears_floor"] for r in matrix_matched
        ),
        "variance_aware_recovered_signal": bool(
            float(best_sm["auc_floor"]) >= FLOOR_MAPPED
            or (max(sm_deltas) if sm_deltas else -1) > 0.02
        ),
    }

    # ── Control 7: per-node ablation on best E2 readout ───────
    abl_mode = abl_target["split_mode"]
    abl_space = abl_target["space"]
    abl_stype = abl_target["score_type"]
    abl_verdict = abl_target["verdict"]
    fn = scorers[(abl_mode, abl_space, abl_stype)]["fn"]
    store = d_all[abl_mode][abl_space]
    tb_win_full = []
    for sha in train_shas:
        for d in store[sha]:
            tb_win_full.append(fn(d))
    tau95_abl = _pct(tb_win_full, 95)

    def scores_ablated(zero_j: int | None) -> dict[str, float]:
        out_s = {}
        for a in scored:
            sc = []
            for d in store[a.sha256]:
                dd = d.copy()
                if zero_j is not None:
                    dd[zero_j] = 0.0
                sc.append(fn(dd))
            if abl_verdict == "MEAN":
                out_s[a.sha256] = float(np.mean(sc))
            elif abl_verdict == "MAX":
                out_s[a.sha256] = float(np.max(sc))
            else:
                out_s[a.sha256] = float(
                    np.mean([1.0 if s > tau95_abl else 0.0 for s in sc])
                )
        return out_s

    base_sc = scores_ablated(None)
    base_auc = eval_auc(base_sc, split["test_benign"], split["test_malware"])
    abl_rows = []
    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        sc = scores_ablated(j)
        auc = eval_auc(sc, split["test_benign"], split["test_malware"])
        drop = base_auc["auc_floor"] - auc["auc_floor"]
        abl_rows.append(
            {
                "node": cat,
                "node_idx": j,
                "auc_floor": auc["auc_floor"],
                "direction": auc["direction"],
                "drop_vs_baseline": drop,
                "node_variance": phase1["node_variance"][cat],
                "node_mapped_share": phase1["node_mapped_share"][cat],
            }
        )
    abl_rows.sort(key=lambda r: -r["drop_vs_baseline"])
    with (out / "ablation.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(abl_rows[0].keys()))
        w.writeheader()
        w.writerows(abl_rows)

    ipc_row = next(r for r in abl_rows if r["node"] == "ipc_intents")
    top_drop = abl_rows[0]
    ipc_dominates = (
        ipc_row["node"] == top_drop["node"]
        and ipc_row["drop_vs_baseline"] > 0.05
        and (
            len(abl_rows) < 2
            or ipc_row["drop_vs_baseline"] > 2.0 * abl_rows[1]["drop_vs_baseline"]
        )
    )
    # Cross drops with variance
    drops = [r["drop_vs_baseline"] for r in abl_rows]
    vars_ = [r["node_variance"] for r in abl_rows]
    rho_drop_var = _rho(drops, vars_)

    # Per-node mean |d| difference malware - benign on test (explainability)
    mean_d_b = np.mean(
        np.concatenate([store[a.sha256] for a in split["test_benign"]], axis=0),
        axis=0,
    )
    mean_d_m = np.mean(
        np.concatenate([store[a.sha256] for a in split["test_malware"]], axis=0),
        axis=0,
    )
    profile_rows = []
    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        abl = next(r for r in abl_rows if r["node_idx"] == j)
        profile_rows.append(
            {
                "node": cat,
                "mean_d_benign": float(mean_d_b[j]),
                "mean_d_malware": float(mean_d_m[j]),
                "delta_mal_minus_ben": float(mean_d_m[j] - mean_d_b[j]),
                "node_variance": phase1["node_variance"][cat],
                "ablation_drop": abl["drop_vs_baseline"],
                "variance_tertile": (
                    "high"
                    if phase1["node_variance"][cat]
                    >= np.percentile(list(phase1["node_variance"].values()), 66)
                    else (
                        "low"
                        if phase1["node_variance"][cat]
                        <= np.percentile(list(phase1["node_variance"].values()), 33)
                        else "mid"
                    )
                ),
            }
        )
    profile_rows.sort(key=lambda r: -abs(r["delta_mal_minus_ben"]))
    with (out / "deviation_difference_profile.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        w = csv.DictWriter(f, fieldnames=list(profile_rows[0].keys()))
        w.writeheader()
        w.writerows(profile_rows)

    # ── Stop / summary ───────────────────────────────────────
    sm_clear = headline["any_clears_floor_size_matched"]
    if gate_verdict == "NO_SEPARATION":
        stop_note = (
            "Phase 1 NO_SEPARATION — Phases 2–3 are completeness runs; "
            "do not iterate covariance / shrinkage / eps / alpha."
        )
    elif not sm_clear:
        stop_note = (
            "Nothing clears 0.7025 after size-matching. E0's null was not a "
            "geometry artifact — variance-aware readouts do not recover signal."
        )
    else:
        stop_note = "Size-matched cell(s) clear floor — variance-aware geometry recovered signal."

    summary = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "digest": digest,
        "phase1_verdict": gate_verdict,
        "phase1_where": phase1["separation_where"],
        "phase1_mars_condition": phase1["mars_condition_90pct_under_third"],
        "phase1_n90": phase1["n_components_90"],
        "wrap": wrap,
        "ablation_target": abl_target,
        "headline": headline,
        "conformal_volume": conformal_volume,
        "size_matched_meta": size_meta,
        "shuffle_mean_auc_floor": shuf_mean,
        "mean_abs_prefix_scattered_delta": mean_abs_delta,
        "ipc_intents_dominates": ipc_dominates,
        "ipc_drop": ipc_row["drop_vs_baseline"],
        "top_ablation": top_drop,
        "rho_ablation_drop_vs_node_variance": rho_drop_var,
        "stop_note": stop_note,
        "recency_prediction": (
            "E0 |PREFIX−SCATTERED|=0.0055 ⇒ exchangeable windows; "
            "recency-weighted R_i predicted no-op — not run."
        ),
        "whitening_distinction": (
            "Chapter A Run5+LedoitWolf whitened X before the encoder (−0.078 floor). "
            "E2 Mahalanobis is residual-space scoring on d — different object."
        ),
        "artifacts": {
            "phase1": str(out / "phase1_anisotropy.json"),
            "matrix": str(matrix_csv),
            "conformal_auc": str(out / "conformal_auc.csv"),
            "e0_comparison": str(out / "e0_comparison.csv"),
            "ablation": str(out / "ablation.csv"),
            "profile": str(out / "deviation_difference_profile.csv"),
        },
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    # ── Markdown report ──────────────────────────────────────
    def fmt(x, nd=4):
        if isinstance(x, float):
            if math.isnan(x):
                return "nan"
            return f"{x:.{nd}f}"
        return str(x)

    lines: list[str] = []
    L = lines.append
    L("# E2 — Variance-aware readouts on self-reference d vectors")
    L("")
    L("Runs entirely on E0 persisted d vectors. No window rebuild. "
      "Phase 4 conformal uses E0 `armb_n8_windows.pt` only to score reference "
      "windows under the same R_i / scoring function.")
    L("")
    L("## Input assertions")
    L("")
    L(f"- Digest `{digest[:12]}…` (prefix `{EXPECTED_DIGEST_PREFIX}`)")
    L(f"- Split {n_tr}/{n_tb}/{n_tm}; 2403 apps × 2 test-window d ∈ ℝ²²")
    L("- PREFIX + SCATTERED; node + adj — all present")
    L(f"- Artifacts: `{dev_dir}`")
    L("")
    L("## Phase 1 — Anisotropy diagnostic (PREFIX / node primary)")
    L("")
    L(f"- Eigenvalue: n for 50%/90%/99% variance = "
      f"**{phase1['n_components_50']} / {phase1['n_components_90']} / {phase1['n_components_99']}** "
      f"(of {N_NODES})")
    L(f"- MaRS condition (>90% variance in <⅓ of components, i.e. ≤{phase1['n_under_third']}): "
      f"**{phase1['mars_condition_90pct_under_third']}**")
    L(f"- Separation lives: {phase1['separation_where']}")
    L(f"- Spearman ρ(node variance, mapped-event share) = "
      f"**{fmt(phase1['spearman_rho_node_var_vs_mapped_share'], 3)}**")
    L("")
    L(f"**VERDICT: `{gate_verdict}`**")
    L("")
    L("| PC | var_ratio | cum | E[proj²] ben | E[proj²] mal | mal:ben |")
    L("|---:|---:|---:|---:|---:|---:|")
    for ax in phase1["axes"]:
        L(
            f"| {ax['pc']} | {fmt(ax['var_ratio'])} | {fmt(ax['cum_var'])} | "
            f"{fmt(ax['msq_benign'], 6)} | {fmt(ax['msq_malware'], 6)} | "
            f"{fmt(ax['malware_benign_ratio'], 3)} |"
        )
    L("")
    L(f"Full Phase 1 (all mode×space): `{out / 'phase1_anisotropy.json'}`")
    L("")
    L("## Phase 2 — Mahalanobis (Ledoit-Wolf)")
    L("")
    L("Covariance fit on train-benign d only. Distinct from Chapter A input-space "
      "whitening (Run 5 −0.078): this is residual-space scoring.")
    for mode in ("PREFIX", "SCATTERED"):
        for space in ("node", "adj"):
            m = scorers[(mode, space, "MAHALANOBIS")]
            L(
                f"- {mode}/{space}: cond(S)={fmt(m['cond'], 2)}, "
                f"shrinkage={fmt(m['shrinkage'], 4)}"
            )
    L("")
    L("### Raw matrix")
    L("")
    L("| split | score | verdict | space | auc_floor | dir | CI95 | clears | ρ_b | ρ_m |")
    L("|---|---|---|---|---:|---|---|---|---:|---:|")
    for r in matrix_raw:
        L(
            f"| {r['split_mode']} | {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor'])} | {r['direction']} | "
            f"[{fmt(r['ci95_floor_lo'])}, {fmt(r['ci95_floor_hi'])}] | "
            f"{r['clears_floor']} | {fmt(r['rho_benign'], 3)} | {fmt(r['rho_malware'], 3)} |"
        )
    L("")
    L("### Size-matched matrix (PRIMARY)")
    L("")
    L(
        f"Surviving n: **benign={len(matched_b)}, malware={len(matched_m)}** "
        f"(overlap n_mapped ∈ [{fmt(size_meta['overlap_lo'], 1)}, "
        f"{fmt(size_meta['overlap_hi'], 1)}]). Underpowered vs full test — equal prominence."
    )
    L("")
    L("| split | score | verdict | space | auc_floor | dir | CI95 | clears | ρ_b | ρ_m | n_b | n_m |")
    L("|---|---|---|---|---:|---|---|---|---:|---:|---:|---:|")
    for r in matrix_matched:
        L(
            f"| {r['split_mode']} | {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor'])} | {r['direction']} | "
            f"[{fmt(r['ci95_floor_lo'])}, {fmt(r['ci95_floor_hi'])}] | "
            f"{r['clears_floor']} | {fmt(r['rho_benign'], 3)} | {fmt(r['rho_malware'], 3)} | "
            f"{r['n_test_benign']} | {r['n_test_malware']} |"
        )
    L("")
    L(f"Artifact: `{matrix_csv}`")
    L("")
    L("## Phase 4 — Conformal p-values")
    L("")
    L(
        f"Wrapped **{wrap['source']}** `{w_stype}` on {w_mode}/{w_space} "
        f"(ref verdict {wrap.get('verdict_ref')}, auc_floor={fmt(wrap['auc_floor'])}). "
        "Calibration = app's own 6 reference-window scores. "
        "Licensed by E0 exchangeability (|PREFIX−SCATTERED|=0.0055)."
    )
    L("")
    L("| tag | verdict | auc_floor | dir | clears | ρ_b | ρ_m | n_b | n_m |")
    L("|---|---|---:|---|---|---:|---:|---:|---:|")
    for r in conformal_auc_rows:
        L(
            f"| {r['tag']} | {r['verdict']} | {fmt(r['auc_floor'])} | {r['direction']} | "
            f"{r['clears_floor']} | {fmt(r['rho_benign'], 3)} | {fmt(r['rho_malware'], 3)} | "
            f"{r['n_test_benign']} | {r['n_test_malware']} |"
        )
    L("")
    L("Volume coupling (does conformal reduce |ρ| vs raw wrap score?):")
    L(
        f"- raw ρ_b={fmt(conformal_volume['rho_raw_benign'], 3)}, "
        f"ρ_m={fmt(conformal_volume['rho_raw_malware'], 3)}"
    )
    L(
        f"- min_p ρ_b={fmt(conformal_volume['rho_min_p_benign'], 3)}, "
        f"ρ_m={fmt(conformal_volume['rho_min_p_malware'], 3)}"
    )
    L(
        f"- |ρ| reduction benign={fmt(conformal_volume['abs_rho_reduced_benign'], 3)}, "
        f"malware={fmt(conformal_volume['abs_rho_reduced_malware'], 3)}"
    )
    L("")
    L("## Phase 5 — Controls")
    L("")
    L("### 1–3. Size-matched, floor, volume — see matrices above.")
    L("")
    L("### 4. Shuffled labels")
    L("")
    L(f"Mean shuffled auc_floor = **{fmt(shuf_mean)}** "
      f"(E0 was 0.517; treat <~0.53 as noise). Artifact: `{out / 'shuffled_labels.csv'}`")
    L("")
    L("### 5. PREFIX − SCATTERED delta")
    L("")
    L(f"Mean |Δ| = **{fmt(mean_abs_delta)}**. Artifact: `{out / 'prefix_scattered_delta.csv'}`")
    L("")
    L("| score | verdict | space | PREFIX | SCATTERED | Δ |")
    L("|---|---|---|---:|---:|---:|")
    for r in delta_rows:
        L(
            f"| {r['score_type']} | {r['verdict']} | {r['space']} | "
            f"{fmt(r['auc_floor_prefix'])} | {fmt(r['auc_floor_scattered'])} | "
            f"{fmt(r['delta_prefix_minus_scattered'])} |"
        )
    L("")
    L("### 6. E0 comparison (HEADLINE)")
    L("")
    L(
        f"E2 best raw={fmt(headline['e2_best_raw'])} vs E0 {E0_BEST_RAW}; "
        f"E2 best size-matched={fmt(headline['e2_best_size_matched'])} vs E0 {E0_BEST_SM}. "
        f"Max Δ(E2−E0) raw={fmt(headline['max_delta_raw'])}, "
        f"size-matched={fmt(headline['max_delta_size_matched'])}. "
        f"**Variance-aware recovered signal?** "
        f"**{headline['variance_aware_recovered_signal']}** "
        f"(size-matched clears floor: {headline['any_clears_floor_size_matched']})."
    )
    L("")
    L("Pairing: MAHALANOBIS↔E0 CENTROID, NODE_STD↔E0 SCALAR.")
    L("")
    L("| tag | split | verdict | space | E2 | E0 | E2 floor | E0 floor | Δ |")
    L("|---|---|---|---|---|---|---:|---:|---:|")
    for r in e0_compare_rows:
        L(
            f"| {r['tag']} | {r['split_mode']} | {r['verdict']} | {r['space']} | "
            f"{r['e2_score']} | {r['e0_score']} | {fmt(r['e2_auc_floor'])} | "
            f"{fmt(r['e0_auc_floor'])} | {fmt(r['delta_e2_minus_e0'])} |"
        )
    L("")
    L(f"Artifact: `{out / 'e0_comparison.csv'}`")
    L("")
    L("### 7. Per-node ablation + deviation-difference profile")
    L("")
    L(
        f"Ablation target: {abl_stype} / {abl_mode} / {abl_space} / {abl_verdict} "
        f"(baseline auc_floor={fmt(base_auc['auc_floor'])})."
    )
    L(
        f"**ipc_intents dominates?** **{ipc_dominates}** "
        f"(ipc drop={fmt(ipc_row['drop_vs_baseline'])}; "
        f"top={top_drop['node']} drop={fmt(top_drop['drop_vs_baseline'])})."
    )
    if ipc_dominates:
        L("Standing caveat applies: 2017 malware repackaging inflates Intent traffic structurally.")
    else:
        L("ipc_intents does **not** dominate — self-deviation is not the Chapter A univariate Intent detector.")
    L(f"Spearman ρ(ablation drop, node variance) = {fmt(rho_drop_var, 3)}")
    L("")
    L("| rank | node | auc_floor | drop | node_var | mapped_share |")
    L("|---:|---|---:|---:|---:|---:|")
    for i, r in enumerate(abl_rows, 1):
        L(
            f"| {i} | {r['node']} | {fmt(r['auc_floor'])} | {fmt(r['drop_vs_baseline'])} | "
            f"{fmt(r['node_variance'], 6)} | {fmt(r['node_mapped_share'], 4)} |"
        )
    L("")
    L("Deviation-difference profile (mean d malware − benign), sorted by |Δ|:")
    L("")
    L("| node | mean_d_ben | mean_d_mal | Δ | var tertile | abl drop |")
    L("|---|---:|---:|---:|---|---:|")
    for r in profile_rows:
        L(
            f"| {r['node']} | {fmt(r['mean_d_benign'], 4)} | {fmt(r['mean_d_malware'], 4)} | "
            f"{fmt(r['delta_mal_minus_ben'], 4)} | {r['variance_tertile']} | "
            f"{fmt(r['ablation_drop'])} |"
        )
    L("")
    L(f"Artifacts: `{out / 'ablation.csv'}`, `{out / 'deviation_difference_profile.csv'}`")
    L("")
    L("## Predictions recorded (not run)")
    L("")
    L(f"- {summary['recency_prediction']}")
    L(f"- {summary['whitening_distinction']}")
    L("")
    L("## Stop rule")
    L("")
    L(f"**{stop_note}**")
    L("")
    L("---")
    L("")
    L(f"Generated {summary['utc']}. Summary: `{out / 'summary.json'}`.")

    args.results_md.parent.mkdir(parents=True, exist_ok=True)
    args.results_md.write_text("\n".join(lines) + "\n")
    print(f"[E2] wrote {args.results_md}", flush=True)
    print(f"[E2] Phase1={gate_verdict} best_raw={e2_best_floor:.4f} "
          f"best_sm={float(best_sm['auc_floor']):.4f} sm_clear={sm_clear}", flush=True)
    print(stop_note, flush=True)


if __name__ == "__main__":
    main()
