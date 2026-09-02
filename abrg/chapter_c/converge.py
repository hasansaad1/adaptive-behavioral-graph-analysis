"""Stage 2–4: reference convergence, controls, recency variants, cold start."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy import stats as scipy_stats

from abrg.chapter_c.config import (
    COLD_START_FRAC,
    EDGE_WEIGHT_VARIANTS,
    LAMBDA_REC_PIN,
    LAMBDA_REC_SWEEP,
    RECENCY_ADDS_CRITERION,
    REFERENCE_COMBINE,
    REFERENCE_COMBINE_JUSTIFICATION,
    SHUFFLE_SEEDS,
    STABILISATION_FRAC,
)
from abrg.chapter_c.graphs import GraphBuildBundle, graph_key
from abrg.chapter_c.ingest import Stage0Report, convergence_apps, sessions_for_app
from abrg.chapter_c.tensorize import (
    Channel,
    distances,
    mean_reference,
    median_iqr,
    pooled_curve_band,
    session_vector,
)


def _vectors_for_app(
    report: Stage0Report,
    bundle: GraphBuildBundle,
    app_id: str,
    channel: Channel,
    order: list[int] | None = None,
) -> list[np.ndarray]:
    sess = sessions_for_app(report, app_id)
    if order is not None:
        sess = [sess[i] for i in order]
    vecs: list[np.ndarray] = []
    for s in sess:
        g = bundle.graphs[graph_key(app_id, s.export_dir_name)]
        vecs.append(session_vector(g, channel=channel))
    return vecs


def app_curves(
    vectors: list[np.ndarray],
    *,
    channel: Channel,
    primary_metric: str = "frobenius_combined",
) -> dict[str, Any]:
    n = len(vectors)
    drift: list[dict[str, float]] = []
    heldout: list[dict[str, float]] = []
    refs: list[np.ndarray] = []
    for k in range(1, n):
        R_k = mean_reference(vectors[:k])
        refs.append(R_k)
        R_kp1 = mean_reference(vectors[: k + 1])
        drift.append(distances(R_k, R_kp1, channel=channel))
        heldout.append(distances(R_k, vectors[k], channel=channel))
    # stabilisation on primary drift metric
    stab_k = None
    if len(drift) >= 1:
        base = drift[0][primary_metric]
        thr = STABILISATION_FRAC * base if base > 0 else 0.0
        for i, d in enumerate(drift):
            if d[primary_metric] < thr:
                stab_k = i + 1  # k sessions in R_k
                break
    e_vals = [h[primary_metric] for h in heldout]
    spearman = None
    if len(e_vals) >= 3 and float(np.std(e_vals)) > 0.0:
        ks = list(range(1, len(e_vals) + 1))
        rho, p = scipy_stats.spearmanr(ks, e_vals)
        spearman = {"rho": float(rho), "p": float(p)}
    elif len(e_vals) >= 3:
        spearman = {"rho": float("nan"), "p": float("nan"), "note": "constant_series"}
    return {
        "n_sessions": n,
        "drift": drift,
        "heldout": heldout,
        "stabilisation_k": stab_k,
        "primary_metric": primary_metric,
        "heldout_primary": e_vals,
        "drift_primary": [d[primary_metric] for d in drift],
        "spearman_heldout_vs_k": spearman,
        "refs": refs,
    }


def wilcoxon_first_last(per_app_series: dict[str, list[float]]) -> dict[str, Any]:
    first: list[float] = []
    last: list[float] = []
    for series in per_app_series.values():
        if len(series) >= 1:
            first.append(series[0])
            last.append(series[-1])
    if len(first) < 5:
        return {"n": len(first), "statistic": None, "p": None}
    # alternative: first > last (error decreases)
    try:
        res = scipy_stats.wilcoxon(first, last, alternative="greater")
        return {
            "n": len(first),
            "statistic": float(res.statistic),
            "p": float(res.pvalue),
            "alternative": "first_gt_last",
        }
    except Exception as exc:  # noqa: BLE001
        return {"n": len(first), "error": str(exc)}


def run_convergence(
    report: Stage0Report,
    bundle: GraphBuildBundle,
    *,
    channel: Channel = "both",
    primary_metric: str = "frobenius_combined",
    apps: list[str] | None = None,
) -> dict[str, Any]:
    apps = apps or convergence_apps(report)
    per_app: dict[str, Any] = {}
    drift_curves: dict[str, list[float]] = {}
    err_curves: dict[str, list[float]] = {}
    stab_points: dict[str, int | None] = {}
    for app in apps:
        vecs = _vectors_for_app(report, bundle, app, channel)
        if len(vecs) < 2:
            continue
        cur = app_curves(vecs, channel=channel, primary_metric=primary_metric)
        # drop heavy refs from JSON later
        per_app[app] = {k: v for k, v in cur.items() if k != "refs"}
        drift_curves[app] = cur["drift_primary"]
        err_curves[app] = cur["heldout_primary"]
        stab_points[app] = cur["stabilisation_k"]

    never = sorted(a for a, k in stab_points.items() if k is None)
    # pooled spearman: concatenate all (k, e) pairs
    all_k: list[int] = []
    all_e: list[float] = []
    for app, series in err_curves.items():
        for i, e in enumerate(series):
            all_k.append(i + 1)
            all_e.append(e)
    pooled_sp = None
    if len(all_e) >= 3:
        rho, p = scipy_stats.spearmanr(all_k, all_e)
        pooled_sp = {"rho": float(rho), "p": float(p), "n_pairs": len(all_e)}

    return {
        "channel": channel,
        "primary_metric": primary_metric,
        "reference_combine": REFERENCE_COMBINE,
        "reference_combine_justification": REFERENCE_COMBINE_JUSTIFICATION,
        "n_apps": len(per_app),
        "per_app": per_app,
        "stabilisation_k_per_app": stab_points,
        "n_never_stabilise": len(never),
        "never_stabilise_apps": never,
        "stabilisation_k_distribution": median_iqr(
            [float(k) for k in stab_points.values() if k is not None]
        ),
        "pooled_drift_band": pooled_curve_band(drift_curves),
        "pooled_heldout_band": pooled_curve_band(err_curves),
        "wilcoxon_heldout_first_vs_last": wilcoxon_first_last(err_curves),
        "pooled_spearman_heldout_vs_k": pooled_sp,
        "_drift_curves": drift_curves,
        "_err_curves": err_curves,
        "_vectors": {
            app: _vectors_for_app(report, bundle, app, channel) for app in per_app
        },
    }


def run_shuffle_control(
    report: Stage0Report,
    bundle: GraphBuildBundle,
    *,
    channel: Channel = "both",
    primary_metric: str = "frobenius_combined",
    seeds: tuple[int, ...] = SHUFFLE_SEEDS,
) -> dict[str, Any]:
    apps = convergence_apps(report)
    seed_results: list[dict[str, Any]] = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        drift_curves: dict[str, list[float]] = {}
        err_curves: dict[str, list[float]] = {}
        stab: dict[str, int | None] = {}
        for app in apps:
            n = len(sessions_for_app(report, app))
            order = list(rng.permutation(n))
            vecs = _vectors_for_app(report, bundle, app, channel, order=order)
            if len(vecs) < 2:
                continue
            cur = app_curves(vecs, channel=channel, primary_metric=primary_metric)
            drift_curves[app] = cur["drift_primary"]
            err_curves[app] = cur["heldout_primary"]
            stab[app] = cur["stabilisation_k"]
        seed_results.append(
            {
                "seed": seed,
                "pooled_drift_band": pooled_curve_band(drift_curves),
                "pooled_heldout_band": pooled_curve_band(err_curves),
                "n_never_stabilise": sum(1 for v in stab.values() if v is None),
                "stabilisation_k_distribution": median_iqr(
                    [float(k) for k in stab.values() if k is not None]
                ),
                "wilcoxon_heldout_first_vs_last": wilcoxon_first_last(err_curves),
            }
        )
    return {"channel": channel, "seeds": list(seeds), "per_seed": seed_results}


def run_cross_app_control(
    conv: dict[str, Any],
    *,
    primary_metric: str = "frobenius_combined",
) -> dict[str, Any]:
    """
    Within-app: all e(R_k, S_{k+1}) from temporal curves.
    Cross-app: for every A≠B, distance(R_B_full, S) for every session S of A,
    where R_B_full = mean of all B session vectors.
    """
    vectors: dict[str, list[np.ndarray]] = conv["_vectors"]
    channel: Channel = conv["channel"]
    within = [e for series in conv["_err_curves"].values() for e in series]

    full_refs = {app: mean_reference(vs) for app, vs in vectors.items() if vs}
    cross: list[float] = []
    for a, vs in vectors.items():
        for b, Rb in full_refs.items():
            if a == b:
                continue
            for S in vs:
                d = distances(Rb, S, channel=channel)
                cross.append(d[primary_metric])

    mw = None
    if within and cross:
        # H1: within < cross
        u, p = scipy_stats.mannwhitneyu(within, cross, alternative="less")
        mw = {"U": float(u), "p": float(p), "alternative": "within_lt_cross"}

    return {
        "primary_metric": primary_metric,
        "within_app": median_iqr(within),
        "cross_app": median_iqr(cross),
        "within_values_n": len(within),
        "cross_values_n": len(cross),
        "mannwhitney_u": mw,
        "_within": within,
        "_cross": cross,
    }


def pairwise_variant_deltas(
    per_variant_err: dict[str, dict[str, list[float]]],
    *,
    a: str,
    b: str,
) -> dict[str, Any]:
    """Per-app median(e_a - e_b) over shared k indices; plus pooled Wilcoxon on paired app medians."""
    apps = sorted(set(per_variant_err[a]) & set(per_variant_err[b]))
    per_app_delta_med: dict[str, float] = {}
    wins_a = 0
    wins_b = 0
    ties = 0
    for app in apps:
        ea = per_variant_err[a][app]
        eb = per_variant_err[b][app]
        m = min(len(ea), len(eb))
        if m == 0:
            continue
        deltas = [ea[i] - eb[i] for i in range(m)]
        med = float(np.median(deltas))
        per_app_delta_med[app] = med
        if med < 0:
            wins_a += 1
        elif med > 0:
            wins_b += 1
        else:
            ties += 1
    vals = list(per_app_delta_med.values())
    wcx = None
    if len(vals) >= 5:
        try:
            res = scipy_stats.wilcoxon(vals, alternative="two-sided")
            wcx = {"statistic": float(res.statistic), "p": float(res.pvalue)}
        except Exception as exc:  # noqa: BLE001
            wcx = {"error": str(exc)}
    return {
        "pair": f"{a}_minus_{b}",
        "n_apps": len(per_app_delta_med),
        "per_app_median_delta": per_app_delta_med,
        "median_delta": median_iqr(vals),
        "win_rate_a_lower_error": wins_a / len(apps) if apps else float("nan"),
        "wins_a": wins_a,
        "wins_b": wins_b,
        "ties": ties,
        "wilcoxon_per_app_median_deltas": wcx,
    }


def run_stage3_variants(
    report: Stage0Report,
    bundles_by_lambda: dict[float, GraphBuildBundle],
    *,
    primary_metric: str = "frobenius_combined",
) -> dict[str, Any]:
    """
    bundles_by_lambda[LAMBDA_REC_PIN] used for channel variants;
    full lambda sweep uses channel='both' (or w_rec — declared).
    """
    base = bundles_by_lambda[LAMBDA_REC_PIN]
    variants: dict[str, Any] = {}
    per_variant_err: dict[str, dict[str, list[float]]] = {}
    for ch in EDGE_WEIGHT_VARIANTS:
        conv = run_convergence(report, base, channel=ch, primary_metric=primary_metric)
        cross = run_cross_app_control(conv, primary_metric=primary_metric)
        shuffle = run_shuffle_control(report, base, channel=ch, primary_metric=primary_metric)
        variants[ch] = {
            "convergence": {k: v for k, v in conv.items() if not k.startswith("_")},
            "cross_app": {k: v for k, v in cross.items() if not k.startswith("_")},
            "shuffle": shuffle,
            "_err_curves": conv["_err_curves"],
            "_within": cross["_within"],
            "_cross": cross["_cross"],
            "_drift_curves": conv["_drift_curves"],
        }
        per_variant_err[ch] = conv["_err_curves"]

    pairs = [
        pairwise_variant_deltas(per_variant_err, a="w_rec", b="w_cum"),
        pairwise_variant_deltas(per_variant_err, a="both", b="w_cum"),
        pairwise_variant_deltas(per_variant_err, a="both", b="w_rec"),
    ]

    # decay sweep: rebuild convergence for each lambda on channel both
    sweep: list[dict[str, Any]] = []
    for lam in LAMBDA_REC_SWEEP:
        b = bundles_by_lambda[lam]
        conv = run_convergence(report, b, channel="both", primary_metric=primary_metric)
        cross = run_cross_app_control(conv, primary_metric=primary_metric)
        sweep.append(
            {
                "lambda_rec": lam,
                "pooled_heldout_band": conv["pooled_heldout_band"],
                "pooled_drift_band": conv["pooled_drift_band"],
                "stabilisation_k_distribution": conv["stabilisation_k_distribution"],
                "n_never_stabilise": conv["n_never_stabilise"],
                "cross_app": {k: v for k, v in cross.items() if not k.startswith("_")},
            }
        )

    return {
        "recency_adds_criterion": RECENCY_ADDS_CRITERION,
        "variants": variants,
        "pairwise_deltas": pairs,
        "lambda_sweep": sweep,
        "lambda_rec_pin": LAMBDA_REC_PIN,
    }


def run_cold_start(
    conv_both: dict[str, Any],
    report: Stage0Report,
    bundle: GraphBuildBundle,
    *,
    primary_metric: str = "frobenius_combined",
) -> dict[str, Any]:
    err_curves: dict[str, list[float]] = conv_both["_err_curves"]
    e12 = [series[0] for series in err_curves.values() if series]
    # sessions to within 10% of final e
    reach: dict[str, int | None] = {}
    for app, series in err_curves.items():
        if not series:
            reach[app] = None
            continue
        target = series[-1]
        # within 10% of final: |e_k - e_final| <= 0.1 * |e_final|  OR e_k <= 1.1*e_final if positive
        thr = abs(target) * COLD_START_FRAC
        hit = None
        for i, e in enumerate(series):
            if abs(e - target) <= thr:
                hit = i + 1
                break
        reach[app] = hit

    # sparsity vs stabilisation
    stab = conv_both["stabilisation_k_per_app"]
    med_active: list[float] = []
    med_edges: list[float] = []
    stab_vals: list[float] = []
    apps_for_rho: list[str] = []
    for app, sk in stab.items():
        rows = [s for s in bundle.stats if s.app_id == app]
        if not rows or sk is None:
            continue
        med_active.append(float(np.median([r.n_active_nodes for r in rows])))
        med_edges.append(float(np.median([r.n_edges for r in rows])))
        stab_vals.append(float(sk))
        apps_for_rho.append(app)

    rho_active = rho_edges = None
    if len(stab_vals) >= 5:
        ra, pa = scipy_stats.spearmanr(med_active, stab_vals)
        re, pe = scipy_stats.spearmanr(med_edges, stab_vals)
        rho_active = {"rho": float(ra), "p": float(pa), "n": len(stab_vals)}
        rho_edges = {"rho": float(re), "p": float(pe), "n": len(stab_vals)}

    return {
        "e_R1_S2_distribution": median_iqr(e12),
        "e_R1_S2_values": {app: series[0] for app, series in err_curves.items() if series},
        "k_to_within_10pct_of_final_e": reach,
        "k_to_within_10pct_distribution": median_iqr(
            [float(v) for v in reach.values() if v is not None]
        ),
        "n_never_reach_10pct": sum(1 for v in reach.values() if v is None),
        "spearman_median_active_nodes_vs_stabilisation_k": rho_active,
        "spearman_median_edges_vs_stabilisation_k": rho_edges,
        "stabilisation_never": conv_both["never_stabilise_apps"],
    }


def strip_private(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if not k.startswith("_")}
