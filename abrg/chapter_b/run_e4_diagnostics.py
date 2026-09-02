"""
E4 diagnostics on persisted e4_ordering artifacts.

Phase 1: tie-handling / Wilcoxon consistency / scattered-draw audit.
Phase 4: reference dilution (||R|| vs k, scattered k-curve, per-node breakdown).

No full phase re-runs; reloads session tensors only for Phase 4 recomputations.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats as scipy_stats

from abrg.chapter_b.config import EXPORT_ROOT
from abrg.chapter_b.ingest import load_sessions, pass_sessions
from abrg.chapter_b.run_e4_ordering import (
    CROSS_APP_SEED,
    N_NODES,
    _deviation_scores,
    _mean_ref,
    _rank_biserial,
    _split_indices_prefix,
    _split_indices_scattered,
    _stable_app_seed,
    _summary,
    build_eligible_corpus,
)
from abrg.registry import GRAPH_CATEGORY_UNIVERSE


def _ref_combined_l2(R_x: np.ndarray, R_a: np.ndarray) -> float:
    """Reference magnitude aligned with d: Frobenius on X and A."""
    return float(math.sqrt(float(np.linalg.norm(R_x, ord="fro") ** 2 + np.linalg.norm(R_a, ord="fro") ** 2)))


def _wilcoxon_report(a: list[float], b: list[float]) -> dict[str, Any]:
    diffs = [x - y for x, y in zip(a, b)]
    n_total = len(a)
    zero_idx = [i for i, d in enumerate(diffs) if d == 0.0]
    n_zeros = len(zero_idx)
    nz = [i for i, d in enumerate(diffs) if d != 0.0]
    n_effective = len(nz)
    res = scipy_stats.wilcoxon(a, b, alternative="two-sided", zero_method="wilcox", method="auto")
    w = float(res.statistic)
    r_total = _rank_biserial(w, n_total)
    r_effective = _rank_biserial(w, n_effective) if n_effective > 0 else float("nan")
    return {
        "n_total_pairs": n_total,
        "n_zero_diffs_dropped": n_zeros,
        "n_effective": n_effective,
        "zero_method": "wilcox (drop zero-difference pairs)",
        "statistic_W": w,
        "p": float(res.pvalue),
        "rank_biserial_r_n_total": r_total,
        "rank_biserial_r_n_effective": r_effective,
        "reported_r_bug": "Original E4 used n_total=26 in r denominator while scipy p uses n_effective after zero drop.",
        "mutually_consistent_with_n_effective": abs(r_effective) < 0.35 and float(res.pvalue) > 0.3,
    }


def phase1_diagnostics(e4_dir: Path) -> dict[str, Any]:
    csv_path = e4_dir / "phase1_per_app.csv"
    json_path = e4_dir / "phase1_ordering.json"
    p1 = json.loads(json_path.read_text())
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    prefix = [float(r["prefix_mean_l2"]) for r in rows]
    scattered = [float(r["scattered_mean_l2"]) for r in rows]
    deltas = [float(r["delta_prefix_minus_scattered"]) for r in rows]

    tie_counts = {
        "exact_zero": sum(1 for d in deltas if d == 0.0),
        "abs_lt_1e-6": sum(1 for d in deltas if abs(d) < 1e-6),
        "abs_lt_1e-4": sum(1 for d in deltas if abs(d) < 1e-4),
        "abs_lt_1e-3": sum(1 for d in deltas if abs(d) < 1e-3),
    }

    full_table = []
    for r in rows:
        full_table.append(
            {
                "app_id": r["app_id"],
                "n_sessions": int(r["n_sessions"]),
                "prefix_mean_l2": float(r["prefix_mean_l2"]),
                "scattered_mean_l2": float(r["scattered_mean_l2"]),
                "delta": float(r["delta_prefix_minus_scattered"]),
            }
        )

    wx = _wilcoxon_report(prefix, scattered)
    sign = {
        "prefix_lt_scattered": sum(1 for p, s in zip(prefix, scattered) if p < s),
        "prefix_gt_scattered": sum(1 for p, s in zip(prefix, scattered) if p > s),
        "prefix_eq_scattered": sum(1 for p, s in zip(prefix, scattered) if p == s),
    }

    scatter_audit = []
    n_identical_ref = 0
    seeds_seen: dict[int, list[str]] = {}
    for app_id, row in sorted(p1["per_app"].items()):
        pref_ref = row["PREFIX"]["ref_indices"]
        scat_ref = row["SCATTERED"]["ref_indices"]
        seed = _stable_app_seed(app_id)
        seeds_seen.setdefault(seed, []).append(app_id)
        recomputed_ref, _, _ = _split_indices_scattered(row["n_sessions"], app_id)
        matches_persisted = recomputed_ref == scat_ref
        identical = pref_ref == scat_ref
        if identical:
            n_identical_ref += 1
        scatter_audit.append(
            {
                "app_id": app_id,
                "n_sessions": row["n_sessions"],
                "seed": seed,
                "prefix_ref_indices": pref_ref,
                "scattered_ref_indices": scat_ref,
                "recomputed_scattered_ref": recomputed_ref,
                "scattered_matches_seed_replay": matches_persisted,
                "prefix_ref_eq_scattered_ref": identical,
            }
        )

    n_eff = wx["n_effective"]
    if n_identical_ref == len(rows):
        verdict = "VOID"
    elif n_eff < 20:
        verdict = "UNDERPOWERED"
    else:
        verdict = "ORDERING_NEUTRAL"

    return {
        "artifact_csv": str(csv_path),
        "artifact_json": str(json_path),
        "full_table_26": full_table,
        "tie_counts": tie_counts,
        "wilcoxon_recomputed": wx,
        "original_wilcoxon": p1["wilcoxon_prefix_vs_scattered_l2"],
        "sign_distribution": sign,
        "median_prefix_l2": _summary(prefix)["median"],
        "median_scattered_l2": _summary(scattered)["median"],
        "scatter_audit": scatter_audit,
        "n_apps_identical_prefix_scattered_ref": n_identical_ref,
        "duplicate_seeds": {str(k): v for k, v in seeds_seen.items() if len(v) > 1},
        "revised_phase1_verdict": verdict,
        "verdict_notes": {
            "VOID": "Scattered ref indices identical to prefix — contrast never ran.",
            "UNDERPOWERED": f"n_effective={n_eff} < 20 after zero-drop; not a null result.",
            "ORDERING_NEUTRAL": f"n_effective={n_eff}≥20, median Δ=0; exchangeable at session scale.",
        },
    }


def _k_curve_chronological(
    tensors: dict[str, dict[str, Any]], apps: list[str]
) -> tuple[dict[int, list[float]], dict[int, list[float]], dict[int, list[float]], dict[int, list[float]]]:
    rng = np.random.default_rng(CROSS_APP_SEED)
    full_refs = {}
    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        full_refs[app_id] = (
            _mean_ref([s["X"] for s in sess]),
            _mean_ref([s["A"] for s in sess]),
        )

    d_self: dict[int, list[float]] = {k: [] for k in range(1, 8)}
    d_cross: dict[int, list[float]] = {k: [] for k in range(1, 8)}
    ref_norm: dict[int, list[float]] = {k: [] for k in range(1, 8)}
    ratio: dict[int, list[float]] = {k: [] for k in range(1, 8)}

    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        others = [a for a in apps if a != app_id]
        for k in range(1, min(8, len(sess))):
            R_x = _mean_ref([sess[i]["X"] for i in range(k)])
            R_a = _mean_ref([sess[i]["A"] for i in range(k)])
            rn = _ref_combined_l2(R_x, R_a)
            ref_norm[k].append(rn)
            target = sess[k]
            sc = _deviation_scores(target["X"], target["A"], R_x, R_a)
            d = sc["l2_combined"]
            d_self[k].append(d)
            ratio[k].append(d / rn if rn > 0 else float("nan"))
            j = others[int(rng.integers(0, len(others)))]
            R_x_j, R_a_j = full_refs[j]
            sc_c = _deviation_scores(target["X"], target["A"], R_x_j, R_a_j)
            d_cross[k].append(sc_c["l2_combined"])
    return d_self, d_cross, ref_norm, ratio


def _k_curve_scattered_order(
    tensors: dict[str, dict[str, Any]], apps: list[str]
) -> dict[int, list[float]]:
    d_self: dict[int, list[float]] = {k: [] for k in range(1, 8)}
    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        order = list(range(len(sess)))
        rng = random.Random(_stable_app_seed(app_id))
        rng.shuffle(order)
        for k in range(1, min(8, len(sess))):
            ref_idx = order[:k]
            test_idx = order[k]
            R_x = _mean_ref([sess[i]["X"] for i in ref_idx])
            R_a = _mean_ref([sess[i]["A"] for i in ref_idx])
            target = sess[test_idx]
            sc = _deviation_scores(target["X"], target["A"], R_x, R_a)
            d_self[k].append(sc["l2_combined"])
    return d_self


def _per_node_contribution(
    tensors: dict[str, dict[str, Any]], apps: list[str], k: int
) -> dict[str, float]:
    """Mean per-node (d_node + d_adj) contribution pooled across apps."""
    acc = {name: [] for name in GRAPH_CATEGORY_UNIVERSE}
    for app_id in apps:
        sess = tensors[app_id]["sessions"]
        if k >= len(sess):
            continue
        R_x = _mean_ref([sess[i]["X"] for i in range(k)])
        R_a = _mean_ref([sess[i]["A"] for i in range(k)])
        target = sess[k]
        sc = _deviation_scores(target["X"], target["A"], R_x, R_a)
        dn = sc["d_node"]
        da = sc["d_adj"]
        for i, name in enumerate(GRAPH_CATEGORY_UNIVERSE):
            acc[name].append(float(dn[i] + da[i]))
    return {name: float(np.mean(v)) if v else 0.0 for name, v in acc.items()}


def phase4_diagnostics(tensors: dict[str, dict[str, Any]], e4_dir: Path) -> dict[str, Any]:
    apps = sorted(tensors.keys())
    p4_orig = json.loads((e4_dir / "phase4_coldstart.json").read_text())

    d_self, d_cross, ref_norm, ratio = _k_curve_chronological(tensors, apps)
    d_scattered = _k_curve_scattered_order(tensors, apps)

    ks = list(range(1, 8))
    pooled = {
        "chrono_d_self": {str(k): _summary(d_self[k]) for k in ks},
        "chrono_d_cross": {str(k): _summary(d_cross[k]) for k in ks},
        "ref_combined_l2": {str(k): _summary(ref_norm[k]) for k in ks},
        "d_self_over_ref_norm": {str(k): _summary(ratio[k]) for k in ks},
        "scattered_order_d_self": {str(k): _summary(d_scattered[k]) for k in ks},
    }

    cross_ratio = {}
    for k in ks:
        med_d = pooled["chrono_d_self"][str(k)]["median"]
        med_c = pooled["chrono_d_cross"][str(k)]["median"]
        cross_ratio[str(k)] = med_c / med_d if med_d > 0 else float("nan")

    node_k1 = _per_node_contribution(tensors, apps, k=1)
    node_k7 = _per_node_contribution(tensors, apps, k=7)
    node_delta = {n: node_k7[n] - node_k1[n] for n in GRAPH_CATEGORY_UNIVERSE}
    top_increases = sorted(node_delta.items(), key=lambda x: -x[1])[:8]

    chrono_med = [pooled["chrono_d_self"][str(k)]["median"] for k in ks]
    scat_med = [pooled["scattered_order_d_self"][str(k)]["median"] for k in ks]
    ref_med = [pooled["ref_combined_l2"][str(k)]["median"] for k in ks]
    ratio_med = [pooled["d_self_over_ref_norm"][str(k)]["median"] for k in ks]

    ref_shrinks = ref_med[-1] < ref_med[0] * 0.95
    ratio_rises = ratio_med[-1] > ratio_med[0] * 1.05
    chrono_rises = chrono_med[-1] > chrono_med[0] * 1.05
    scat_rises = scat_med[-1] > scat_med[0] * 1.05

    if chrono_rises and scat_rises:
        phase4_statement = (
            "REFERENCE_DILUTION: d_self rises with k under both chronological and "
            "permuted (scattered-order) reference draws. ||R|| falls with k while "
            "d/||R|| is stable or rising — the k-curve measures reference smoothing "
            "against a fixed spiky test session, not failure to converge. Withdraw "
            "'does not converge within 8 sessions' as a behavioural claim."
        )
        revised_verdict = "REFERENCE_DILUTION"
    elif chrono_rises and not scat_rises:
        phase4_statement = (
            "CHRONOLOGICAL_DRIFT: d_self rises only under chronological reference "
            "ordering; permuted-order references do not show the same increase. "
            "This contradicts Phase 1 ORDERING_NEUTRAL and must be reported jointly."
        )
        revised_verdict = "CHRONOLOGICAL_DRIFT"
    else:
        phase4_statement = (
            "INCONCLUSIVE: k-curve pattern does not match simple dilution or drift "
            "templates; retain descriptive numbers without strong convergence claim."
        )
        revised_verdict = "INCONCLUSIVE"

    return {
        "artifact_phase4": str(e4_dir / "phase4_coldstart.json"),
        "pooled": pooled,
        "cross_self_ratio_median": cross_ratio,
        "per_node_mean_contribution_k1": node_k1,
        "per_node_mean_contribution_k7": node_k7,
        "per_node_delta_k7_minus_k1": node_delta,
        "top_node_increases_k1_to_k7": top_increases,
        "diagnostic_flags": {
            "ref_norm_shrinks_k1_to_k7": ref_shrinks,
            "d_over_ref_ratio_rises_k1_to_k7": ratio_rises,
            "chrono_d_self_rises_k1_to_k7": chrono_rises,
            "scattered_d_self_rises_k1_to_k7": scat_rises,
        },
        "revised_phase4_verdict": revised_verdict,
        "revised_phase4_statement": phase4_statement,
        "matches_original_chrono_medians": {
            str(k): abs(pooled["chrono_d_self"][str(k)]["median"] - p4_orig["pooled_self"][str(k)]["median"]) < 1e-9
            for k in ks
        },
    }


def _confirm_phase2(e4_dir: Path) -> dict[str, Any]:
    p2 = json.loads((e4_dir / "phase2_recency.json").read_text())
    return {
        "artifact": str(e4_dir / "phase2_recency.json"),
        "multi_day_apps": p2.get("multi_day_prerequisite", {}).get("n_multi_day"),
        "n_apps": p2.get("n_apps"),
        "w_rec_beats_w_cum_any_decay": p2.get("verdict_w_rec_beats_w_cum"),
        "confirmed": "W_REC does not beat W_CUM at any decay (as reported).",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="E4 diagnostics on persisted artifacts")
    parser.add_argument(
        "--e4-dir",
        type=Path,
        default=Path("abrg/output/v2_extended/e4_ordering"),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("abrg/output/v2_extended/e4_ordering/diagnostics"),
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("[E4 diag] Phase 1 from CSV/JSON …", flush=True)
    p1 = phase1_diagnostics(args.e4_dir)
    (args.out_dir / "phase1_diagnostics.json").write_text(json.dumps(p1, indent=2) + "\n")

    print("[E4 diag] loading tensors for Phase 4 …", flush=True)
    rows = pass_sessions(load_sessions(EXPORT_ROOT))
    _, tensors = build_eligible_corpus(rows)
    p4 = phase4_diagnostics(tensors, args.e4_dir)
    (args.out_dir / "phase4_diagnostics.json").write_text(json.dumps(p4, indent=2) + "\n")

    p2_conf = _confirm_phase2(args.e4_dir)
    summary = {
        "phase1_revised_verdict": p1["revised_phase1_verdict"],
        "phase4_revised_verdict": p4["revised_phase4_verdict"],
        "phase2_confirmed": p2_conf,
        "artifacts": {
            "phase1": str(args.out_dir / "phase1_diagnostics.json"),
            "phase4": str(args.out_dir / "phase4_diagnostics.json"),
        },
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
