"""SUMMARY.md + reproduce artefacts for Chapter C."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from abrg.chapter_c.config import (
    LAMBDA_REC_PIN,
    OUTPUT_ROOT,
    RECENCY_ADDS_CRITERION,
    REFERENCE_COMBINE,
    REFERENCE_COMBINE_JUSTIFICATION,
)


def _fmt(x: Any) -> str:
    if isinstance(x, float):
        if x != x:
            return "nan"
        return f"{x:.6g}"
    return str(x)


def _miqr(d: dict[str, Any] | None) -> str:
    if not d:
        return "n/a"
    return (
        f"median={_fmt(d.get('median'))} "
        f"IQR=[{_fmt(d.get('q1'))}, {_fmt(d.get('q3'))}] "
        f"n={d.get('n')}"
    )


def write_summary(artefacts: dict[str, Any], path: Path | None = None) -> Path:
    path = path or (OUTPUT_ROOT / "SUMMARY.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    s0 = artefacts["stage0"]
    s1 = artefacts["stage1"]
    s2 = artefacts["stage2"]
    s3 = artefacts["stage3"]
    s4 = artefacts["stage4"]
    excl = artefacts.get("exclusions", [])

    lines: list[str] = []
    lines.append("# Chapter C — SUMMARY (numbers only)")
    lines.append("")
    lines.append("No malware. No AUC.")
    lines.append("")
    lines.append("## Graph builder note")
    lines.append("")
    bn = s1["builder_note"]
    lines.append(f"- AndroCT tensor builder: `{bn['androct_tensor_builder']}`")
    lines.append(f"  - properties: `{json.dumps(bn['androct_properties'])}`")
    lines.append(f"- Chapter C builder: `{bn['chapter_c_builder']}`")
    lines.append(f"  - properties: `{json.dumps(bn['chapter_c_properties'])}`")
    lines.append(f"- Choice: {bn['choice']}")
    lines.append("")
    lines.append("## Stage 0 — ingest")
    lines.append("")
    lines.append(f"| field | value |")
    lines.append(f"|-------|------:|")
    lines.append(f"| verify_export exit | {s0['verify_exit_code']} |")
    lines.append(f"| sessions in index | {s0['n_sessions_index']} |")
    lines.append(f"| usable pass (timestamps OK) | {s0['n_pass']} |")
    lines.append(f"| reference-tier failures | {s0['n_fail_reference']} |")
    lines.append(f"| batch pass | {s0['batch_pass']} |")
    lines.append(f"| batch fail | {s0['batch_fail']} |")
    lines.append(f"| apps with usable sessions | {s0['n_apps_pass']} |")
    lines.append(f"| apps with ≥5 usable | {s0['n_apps_ge5_usable']} |")
    lines.append(f"| gate (≥30 apps with ≥5) | {s0['gate_apps_ge5']} |")
    lines.append(f"| session_index contiguous | {s0['session_index_contiguous']} |")
    lines.append(f"| timestamp exclusions | {len(s0['timestamp_exclusions'])} |")
    lines.append(f"| n_nodes universe | {s0['n_nodes_universe']} |")
    lines.append("")
    lines.append("### Per-app usable session counts")
    lines.append("")
    lines.append("| app_id | n |")
    lines.append("|--------|--:|")
    for a, n in s0["per_app_pass_counts"].items():
        lines.append(f"| {a} | {n} |")
    lines.append("")

    lines.append("## Stage 1 — graph construction")
    lines.append("")
    pins = s1["pins"]
    lines.append(f"| pin | value |")
    lines.append(f"|-----|------:|")
    lines.append(f"| k_burst | {pins['k_burst']} |")
    lines.append(f"| delta_sec | {pins['delta_sec']} |")
    lines.append(f"| lambda_rec | {pins['lambda_rec']} (source: abrg.config.LAMBDA_REC) |")
    lines.append(f"| window_sec | {pins.get('window_sec', 60.0)} (multi-window cumulative) |")
    lines.append(f"| normalize | {pins['normalize']} |")
    lines.append(f"| static_mode | {pins['static_mode']} |")
    lines.append(f"| apps static resolved | {pins['n_apps_static_resolved']} |")
    lines.append(f"| apps static fallback | {pins['n_apps_static_fallback']} |")
    lines.append("")
    lines.append("### Corpus graph statistics")
    lines.append("")
    cs = pins["corpus_stats"]
    for key in ("mapped_events", "n_active_nodes", "n_edges", "density"):
        lines.append(f"- {key}: {_miqr(cs[key])}")
    lines.append("")
    lines.append("### Per-session graph stats")
    lines.append("")
    lines.append(
        "| app_id | export_dir_name | idx | mapped | active | edges | density | static |"
    )
    lines.append(
        "|--------|-----------------|----:|-------:|-------:|------:|--------:|--------|"
    )
    for row in s1["session_stats"]:
        lines.append(
            f"| {row['app_id']} | {row['export_dir_name']} | "
            f"{row['session_index_within_app']} | {row['mapped_events']} | "
            f"{row['n_active_nodes']} | {row['n_edges']} | "
            f"{row['density']:.6g} | {row['static_resolved']} |"
        )
    lines.append("")
    dr = s1["delta_retention"]
    lines.append("### δ retention")
    lines.append("")
    lines.append(f"- k_burst={dr['k_burst']} delta_sec={dr['delta_sec']}")
    lines.append(f"- n_k_candidates={dr['n_k_candidates']}")
    lines.append(f"- n_delta_retained={dr['n_delta_retained']}")
    lines.append(f"- retention_overall={_fmt(dr['retention_overall'])}")
    lines.append("")
    lines.append("| quartile | n_events_lo | n_events_hi | n_sessions | retention |")
    lines.append("|---------:|------------:|------------:|-----------:|----------:|")
    for q in dr["by_event_count_quartile"]:
        lines.append(
            f"| {q['quartile']} | {_fmt(q['n_events_lo'])} | {_fmt(q['n_events_hi'])} | "
            f"{q['n_sessions']} | {_fmt(q['retention'])} |"
        )
    lines.append("")
    fit = dr["fitted_curve"]
    lines.append(f"- fitted_model={fit.get('model')} fit_ok={fit.get('fit_ok')}")
    lines.append(f"- params={fit.get('params')}")
    lines.append(
        f"- retention_at_5k={_fmt(fit.get('at_5k'))} "
        f"at_10k={_fmt(fit.get('at_10k'))} at_50k={_fmt(fit.get('at_50k'))}"
    )
    lines.append("")

    lines.append("## Stage 2 — reference convergence")
    lines.append("")
    lines.append(f"- reference_combine: `{REFERENCE_COMBINE}`")
    lines.append(f"- justification: {REFERENCE_COMBINE_JUSTIFICATION}")
    conv = s2["convergence"]
    lines.append(f"- channel (primary): {conv['channel']}")
    lines.append(f"- primary_metric: {conv['primary_metric']}")
    lines.append(f"- n_apps: {conv['n_apps']}")
    lines.append(f"- n_never_stabilise: {conv['n_never_stabilise']}")
    lines.append(f"- never_stabilise_apps: {conv['never_stabilise_apps']}")
    lines.append(f"- stabilisation_k: {_miqr(conv['stabilisation_k_distribution'])}")
    lines.append(f"- pooled Spearman e vs k: {conv['pooled_spearman_heldout_vs_k']}")
    lines.append(f"- Wilcoxon first>last held-out: {conv['wilcoxon_heldout_first_vs_last']}")
    lines.append("")
    lines.append("### Pooled drift band")
    lines.append("")
    lines.append("| k | median | q1 | q3 |")
    lines.append("|--:|-------:|---:|---:|")
    pb = conv["pooled_drift_band"]
    for i in range(len(pb["k"])):
        lines.append(
            f"| {pb['k'][i]} | {_fmt(pb['median'][i])} | {_fmt(pb['q1'][i])} | {_fmt(pb['q3'][i])} |"
        )
    lines.append("")
    lines.append("### Pooled held-out band")
    lines.append("")
    lines.append("| k | median | q1 | q3 |")
    lines.append("|--:|-------:|---:|---:|")
    pb = conv["pooled_heldout_band"]
    for i in range(len(pb["k"])):
        lines.append(
            f"| {pb['k'][i]} | {_fmt(pb['median'][i])} | {_fmt(pb['q1'][i])} | {_fmt(pb['q3'][i])} |"
        )
    lines.append("")
    lines.append("### Per-app stabilisation k and Spearman")
    lines.append("")
    lines.append("| app_id | stab_k | spearman_rho | spearman_p | n_sessions |")
    lines.append("|--------|-------:|-------------:|-----------:|-----------:|")
    for app, row in conv["per_app"].items():
        sp = row.get("spearman_heldout_vs_k") or {}
        lines.append(
            f"| {app} | {row.get('stabilisation_k')} | "
            f"{_fmt(sp.get('rho'))} | {_fmt(sp.get('p'))} | {row['n_sessions']} |"
        )
    lines.append("")
    lines.append("### Shuffled-session-order control (5 seeds)")
    lines.append("")
    for seed_row in s2["shuffle"]["per_seed"]:
        lines.append(
            f"- seed={seed_row['seed']} "
            f"n_never_stabilise={seed_row['n_never_stabilise']} "
            f"stab_k={_miqr(seed_row['stabilisation_k_distribution'])} "
            f"wilcoxon={seed_row['wilcoxon_heldout_first_vs_last']}"
        )
        hb = seed_row["pooled_heldout_band"]
        lines.append(
            f"  heldout_medians_by_k={list(zip(hb['k'], [_fmt(x) for x in hb['median']]))}"
        )
    lines.append("")
    lines.append("### Cross-app control")
    lines.append("")
    ca = s2["cross_app"]
    lines.append(f"- within_app: {_miqr(ca['within_app'])}")
    lines.append(f"- cross_app: {_miqr(ca['cross_app'])}")
    lines.append(f"- Mann-Whitney U: {ca['mannwhitney_u']}")
    lines.append("")

    lines.append("## Stage 3 — recency vs memory")
    lines.append("")
    lines.append(f"- criterion (declared): {RECENCY_ADDS_CRITERION}")
    lines.append(f"- lambda_rec pin: {LAMBDA_REC_PIN}")
    lines.append("")
    for ch, block in s3["variants"].items():
        c = block["convergence"]
        x = block["cross_app"]
        lines.append(f"### Variant `{ch}`")
        lines.append(f"- stab_k: {_miqr(c['stabilisation_k_distribution'])}")
        lines.append(f"- n_never_stabilise: {c['n_never_stabilise']}")
        lines.append(f"- within: {_miqr(x['within_app'])}")
        lines.append(f"- cross: {_miqr(x['cross_app'])}")
        lines.append(f"- Mann-Whitney: {x['mannwhitney_u']}")
        sep = None
        if x["within_app"].get("median") == x["within_app"].get("median"):
            sep = x["cross_app"]["median"] - x["within_app"]["median"]
        lines.append(f"- separation (cross_med − within_med): {_fmt(sep)}")
        lines.append("")
    lines.append("### Pairwise per-app deltas")
    lines.append("")
    for pair in s3["pairwise_deltas"]:
        lines.append(f"- {pair['pair']}: median_delta={_miqr(pair['median_delta'])}")
        lines.append(
            f"  wins_a={pair['wins_a']} wins_b={pair['wins_b']} ties={pair['ties']} "
            f"win_rate_a_lower={_fmt(pair['win_rate_a_lower_error'])} "
            f"wilcoxon={pair['wilcoxon_per_app_median_deltas']}"
        )
        lines.append("  per_app_median_delta:")
        for app, dlt in sorted(pair["per_app_median_delta"].items()):
            lines.append(f"  - {app}: {_fmt(dlt)}")
    lines.append("")
    lines.append("### λ_rec sweep (channel=both)")
    lines.append("")
    lines.append("| lambda_rec | stab_k_med | n_never | within_med | cross_med | sep |")
    lines.append("|-----------:|-----------:|--------:|-----------:|----------:|----:|")
    for row in s3["lambda_sweep"]:
        x = row["cross_app"]
        sep = x["cross_app"]["median"] - x["within_app"]["median"]
        lines.append(
            f"| {row['lambda_rec']} | "
            f"{_fmt(row['stabilisation_k_distribution'].get('median'))} | "
            f"{row['n_never_stabilise']} | "
            f"{_fmt(x['within_app']['median'])} | "
            f"{_fmt(x['cross_app']['median'])} | {_fmt(sep)} |"
        )
    lines.append("")

    lines.append("## Stage 4 — cold start")
    lines.append("")
    lines.append(f"- e(R_1,S_2): {_miqr(s4['e_R1_S2_distribution'])}")
    lines.append(
        f"- k to within 10% of final e: {_miqr(s4['k_to_within_10pct_distribution'])}"
    )
    lines.append(f"- n_never_reach_10pct: {s4['n_never_reach_10pct']}")
    lines.append(
        f"- Spearman median_active_nodes vs stab_k: "
        f"{s4['spearman_median_active_nodes_vs_stabilisation_k']}"
    )
    lines.append(
        f"- Spearman median_edges vs stab_k: "
        f"{s4['spearman_median_edges_vs_stabilisation_k']}"
    )
    lines.append("")
    lines.append("| app_id | e(R1,S2) | k_to_10pct |")
    lines.append("|--------|---------:|-----------:|")
    for app, e in sorted(s4["e_R1_S2_values"].items()):
        lines.append(
            f"| {app} | {_fmt(e)} | {s4['k_to_within_10pct_of_final_e'].get(app)} |"
        )
    lines.append("")

    lines.append("## Exclusions")
    lines.append("")
    if not excl:
        lines.append("(none)")
    else:
        for e in excl:
            lines.append(f"- {e}")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
