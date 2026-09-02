"""SUMMARY.md, reproduce artefacts. Numbers and tables only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from abrg.chapter_b.config import (
    ANDROCT_PROTOCOL_WALL_SEC,
    ARTIFACTS_DIR,
    MATERIAL_CLIFF_SMALL,
    MATERIAL_P,
    OUTPUT_ROOT,
    POOLED_JUSTIFICATION,
    POOLED_METHOD,
)
from abrg.chapter_b.stats import json_ready


def _fmt(x: Any, nd: int = 6) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if x != x:
            return "nan"
        if abs(x) >= 1000:
            return f"{x:.4g}"
        return f"{x:.{nd}g}"
    return str(x)


def _dist_cell(d: dict[str, Any] | None) -> str:
    if not d:
        return "n/a"
    return (
        f"med={_fmt(d.get('p50'))} IQR=[{_fmt(d.get('p25'))}, {_fmt(d.get('p75'))}] "
        f"p10={_fmt(d.get('p10'))} p90={_fmt(d.get('p90'))} n={d.get('n')}"
    )


def _mwu_cell(t: dict[str, Any] | None) -> str:
    if not t:
        return "n/a"
    if t.get("note"):
        return str(t["note"])
    if t.get("error"):
        return str(t["error"])
    return (
        f"U={_fmt(t.get('U'))} p={_fmt(t.get('p_value'))} "
        f"δ={_fmt(t.get('cliffs_delta'))} | {t.get('material_statement')}"
    )


def write_summary(
    *,
    verify_exit: int,
    verify_text: str,
    run1: dict[str, Any],
    run2: dict[str, Any],
    figure_paths: list[str],
    path: Path | None = None,
) -> Path:
    path = path or (OUTPUT_ROOT / "SUMMARY.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    inv = run1["inventory"]
    ovn = run1["old_vs_new"]
    fail = run1["failures"]
    ex = run1["exit_codes"]

    lines: list[str] = []
    lines.append("# Chapter B — SUMMARY")
    lines.append("")
    lines.append("Descriptive only. Benign v2. No detector, no AUC, no supervised probe.")
    lines.append("")
    lines.append("## verify_export.py")
    lines.append("")
    lines.append(f"| exit_code | {verify_exit} |")
    lines.append("")
    lines.append("```")
    lines.append(verify_text.strip()[:2000])
    lines.append("```")
    lines.append("")

    lines.append("## Unit alignment (Run 2)")
    lines.append("")
    ua = run2["unit_alignment"]
    lines.append(f"- method: `{ua['method']}`")
    lines.append(f"- builder: `{ua['builder']}` k_burst={ua['k_burst']}")
    lines.append(f"- per-session n={ua['per_session_n']}; per-app pooled n={ua['per_app_pooled_n']}")
    lines.append(f"- AndroCT unit: {ua['androct_unit']}")
    lines.append("")
    lines.append(POOLED_JUSTIFICATION)
    lines.append("")

    lines.append("## Representation comparison")
    lines.append("")
    lines.append(
        "| metric | v2 per-session | v2 per-app pooled | AndroCT benign | AndroCT malware |"
    )
    lines.append("|---|---|---|---|---|")
    for key, label in (
        ("mapped", "mapped events"),
        ("total", "total events"),
        ("mapped_rate", "mapped-event rate"),
        ("n_active", "active nodes"),
        ("n_edges", "edges"),
        ("density", "density"),
    ):
        lines.append(
            f"| {label} | {_dist_cell(run2['v2_per_session'][key])} | "
            f"{_dist_cell(run2['v2_per_app_pooled'][key])} | "
            f"{_dist_cell(run2['androct_benign'][key])} | "
            f"{_dist_cell(run2['androct_malware'][key])} |"
        )
    lines.append(
        f"| wall / protocol length | {_dist_cell(run2['v2_per_session']['wall_duration_s'])} | "
        f"{_dist_cell(run2['v2_per_app_pooled']['wall_duration_s'])} | "
        f"protocol {ANDROCT_PROTOCOL_WALL_SEC}s (no per-trace wall clock) | "
        f"protocol {ANDROCT_PROTOCOL_WALL_SEC}s |"
    )
    lines.append(
        f"| frac graphs ≤2 edges | {run2['v2_per_session']['frac_le2_edges']} "
        f"(n={run2['v2_per_session']['n_le2_edges']}) | "
        f"{run2['v2_per_app_pooled']['frac_le2_edges']} "
        f"(n={run2['v2_per_app_pooled']['n_le2_edges']}) | "
        f"{run2['androct_benign']['frac_le2_edges']} "
        f"(n={run2['androct_benign']['n_le2_edges']}) | "
        f"{run2['androct_malware']['frac_le2_edges']} "
        f"(n={run2['androct_malware']['n_le2_edges']}) |"
    )
    lines.append("")
    lines.append("### Active-node full distribution (value counts)")
    lines.append("")
    lines.append("| unit | value counts |")
    lines.append("|------|--------------|")
    lines.append(f"| v2 per-session | `{run2['v2_per_session']['n_active_value_counts']}` |")
    lines.append(f"| v2 per-app pooled | `{run2['v2_per_app_pooled']['n_active_value_counts']}` |")
    lines.append(f"| AndroCT benign | `{run2['androct_benign']['n_active_value_counts']}` |")
    lines.append(f"| AndroCT malware | `{run2['androct_malware']['n_active_value_counts']}` |")
    lines.append("")
    lines.append("### Mann–Whitney U — v2 per-app pooled vs AndroCT benign")
    lines.append("")
    lines.append(f"Declared material rule: p < {MATERIAL_P} and |Cliff δ| ≥ {MATERIAL_CLIFF_SMALL}.")
    lines.append("")
    lines.append("| metric | test |")
    lines.append("|--------|------|")
    for k, t in run2["mwu_v2_pooled_vs_androct_benign"].items():
        lines.append(f"| {k} | {_mwu_cell(t)} |")
    lines.append("")
    lines.append(f"Metrics meeting the material rule: {run2['mwu_material_metrics'] or '(none)'}")
    lines.append("")

    lines.append("## Category fire rate (per-app, 22 categories)")
    lines.append("")
    lines.append("Fraction of apps with ≥1 mapped event. Ranked by |v2 − AndroCT benign|.")
    lines.append("")
    lines.append("| category | v2 n | v2 frac | AndroCT benign n | AndroCT benign frac | diff |")
    lines.append("|----------|-----:|--------:|-----------------:|--------------------:|-----:|")
    for r in run2["category_fire"]:
        lines.append(
            f"| {r['category']} | {r['v2_n_apps_fire']} | {_fmt(r['v2_frac'])} | "
            f"{r['androct_benign_n_apps_fire']} | {_fmt(r['androct_benign_frac'])} | "
            f"{_fmt(r['diff_v2_minus_androct'])} |"
        )
    lines.append("")
    lines.append("### Dead categories")
    lines.append("")
    lines.append(f"- v2 per-app pooled: {run2['dead_v2_per_app'] or '(none)'}")
    lines.append(f"- AndroCT benign: {run2['dead_androct_benign'] or '(none)'}")
    lines.append(f"- AndroCT malware: {run2['dead_androct_malware'] or '(none)'}")
    lines.append("")
    lines.append("| category | v2 n apps | v2 dead | AndroCT benign n | benign dead | AndroCT malware n | malware dead |")
    lines.append("|----------|----------:|:-------:|-----------------:|:-----------:|------------------:|:------------:|")
    for c, s in run2["special_categories"].items():
        lines.append(
            f"| {c} | {s['v2_n_apps']} | {s['v2_dead']} | {s['androct_benign_n']} | "
            f"{s['androct_benign_dead']} | {s['androct_malware_n']} | {s['androct_malware_dead']} |"
        )
    lines.append("")

    lines.append("## Static slice")
    lines.append("")
    sv = run2["static_v2"]
    sa = run2["static_androct"]
    lines.append(
        f"v2: n_apps={sv['n_apps']} resolved={sv['n_static_resolved']} "
        f"fallback={sv['n_static_fallback']} all-zero={sv['n_all_zero_static_vector']} "
        f"L2 {_dist_cell(sv['l2_norm'])}"
    )
    lines.append("")
    if sa.get("available"):
        b = sa["classes"]["benign"]
        lines.append(
            f"AndroCT benign (Run-2 cache tensors): n={b['n']} all-zero={b['n_all_zero']} "
            f"L2 {_dist_cell(b['l2_norm'])}"
        )
        lines.append("")
        lines.append("| coordinate | v2 all-nodes | v2 per-app mean | AndroCT benign all-nodes | AndroCT benign per-app mean |")
        lines.append("|------------|--------------|-----------------|--------------------------|------------------------------|")
        for a, c in zip(sv["per_coordinate"], b["per_coordinate"]):
            lines.append(
                f"| {a['coordinate']} | {_dist_cell(a['all_nodes_all_apps'])} | "
                f"{_dist_cell(a['per_app_mean_over_22_nodes'])} | "
                f"{_dist_cell(c['all_nodes_all_apps'])} | "
                f"{_dist_cell(c['per_app_mean_over_22_nodes'])} |"
            )
    else:
        lines.append(f"AndroCT static cache: {sa}")
    lines.append("")

    lines.append("## Event yield")
    lines.append("")
    ey = run2["event_yield"]
    lines.append("| | v2 per-session | AndroCT benign | AndroCT malware |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| events / s | {_dist_cell(ey['v2_events_per_sec'])} | "
        f"{_dist_cell(ey['androct_benign_events_per_sec'])} | "
        f"{_dist_cell(ey['androct_malware_events_per_sec'])} |"
    )
    lines.append(
        f"| mapped / s | {_dist_cell(ey['v2_mapped_per_sec'])} | "
        f"{_dist_cell(ey['androct_benign_mapped_per_sec'])} | "
        f"{_dist_cell(ey['androct_malware_mapped_per_sec'])} |"
    )
    lines.append(
        f"| wall | {_dist_cell(ey['v2_session_wall_s'])} | "
        f"protocol {ey['androct_protocol_wall_s']}s | protocol {ey['androct_protocol_wall_s']}s |"
    )
    lines.append("")
    lines.append("Spearman (v2 sessions):")
    lines.append(f"- mapped vs wall: {ey['spearman_mapped_vs_wall']}")
    lines.append(f"- total vs wall: {ey['spearman_total_vs_wall']}")
    lines.append(f"- mapped/s vs wall: {ey['spearman_mapped_per_sec_vs_wall']}")
    lines.append("")
    hk = run2["hooks"]
    lines.append(
        f"Hooks (all type==event APIs, including dropped categories): "
        f"hooked_set_n={hk['hooked_api_set_n']} fired_corpus_wide_n={hk['fired_corpus_wide_n']} "
        f"never_fired_n={hk['never_fired_n']}"
    )
    lines.append(f"- fired: {hk['fired_corpus_wide']}")
    lines.append(f"- never: {hk['never_fired']}")
    lines.append(f"- n hooks fired per session: {_dist_cell(hk['n_hooks_fired_per_session'])}")
    lines.append("")
    lines.append(f"Screens / activities: {run2['screens']['note']}")
    lines.append("")

    lines.append("## Corpus inventory (Run 1)")
    lines.append("")
    s = inv["sessions"]
    lines.append("| | indexed | usable (reference-tier pass) | pass | fail |")
    lines.append("|--|--:|--:|--:|--:|")
    lines.append(
        f"| all | {s['indexed']} | {s['usable_reference_tier_pass']} | "
        f"{s['reference_tier_pass']} | {s['reference_tier_fail']} |"
    )
    lines.append("")
    lines.append("| batch | indexed | pass | fail |")
    lines.append("|-------|--------:|-----:|-----:|")
    for b in sorted(set(s["by_batch_indexed"]) | set(s["by_batch_pass"]) | set(s["by_batch_fail"])):
        lines.append(
            f"| {b} | {s['by_batch_indexed'].get(b, 0)} | "
            f"{s['by_batch_pass'].get(b, 0)} | {s['by_batch_fail'].get(b, 0)} |"
        )
    lines.append("")
    a = inv["apps"]
    lines.append(f"Apps with ≥1 usable session: {a['n_with_ge1_usable']}")
    lines.append(f"GAE-eligible before extension: {a['n_gae_before']}")
    lines.append(f"GAE-eligible after extension: {a['n_gae_after']}")
    lines.append(f"Entered eligibility: {a['entered_eligibility'] or '[]'}")
    lines.append(f"Left eligibility: {a['left_eligibility'] or '[]'}")
    lines.append("")
    lines.append("Session-count distribution (n_sessions → n_apps):")
    lines.append(f"- before (original pass): `{inv['session_count_distribution']['before_extension_original_pass']}`")
    lines.append(f"- after (all pass): `{inv['session_count_distribution']['after_extension_all_pass']}`")
    lines.append("")
    lines.append("| app_id | n before (original pass) | n after (all pass) |")
    lines.append("|--------|-------------------------:|-------------------:|")
    before = inv["per_app_session_counts"]["before_original_pass"]
    after = inv["per_app_session_counts"]["after_all_pass"]
    for app in sorted(set(before) | set(after)):
        lines.append(f"| {app} | {before.get(app, 0)} | {after.get(app, 0)} |")
    lines.append("")
    lines.append("| batch | n | start UTC | end UTC |")
    lines.append("|-------|--:|-----------|---------|")
    for b, r in inv["collection_date_ranges"].items():
        lines.append(f"| {b} | {r['n']} | {r['start_utc']} | {r['end_utc']} |")
    lines.append("")
    lines.append("### Old vs new (original pass vs canary+extend pass)")
    lines.append("")
    lines.append(f"n original={run1['n_original_pass']} n new={run1['n_new_pass']} n pooled={run1['n_pooled_pass']}")
    lines.append("")
    lines.append("| metric | original | new | pooled | MWU |")
    lines.append("|--------|----------|-----|--------|-----|")
    for name, block in ovn.items():
        lines.append(
            f"| {name} | {_dist_cell(block['original'])} | {_dist_cell(block['new'])} | "
            f"{_dist_cell(block['pooled'])} | {_mwu_cell(block['mann_whitney'])} |"
        )
    lines.append("")
    lines.append(
        f"Metrics meeting the material rule (p < {MATERIAL_P} and |δ| ≥ {MATERIAL_CLIFF_SMALL}): "
        f"{run1['old_vs_new_material_metrics'] or '(none)'}"
    )
    lines.append(f"Any material: {run1['old_vs_new_any_material']}")
    lines.append("")
    lines.append("### Reference-tier failures (n=46)")
    lines.append("")
    lines.append(f"- n_apps in canary/extend: {fail['n_apps_in_canary_or_extend']}")
    lines.append(f"- n_apps with ≥1 failure: {fail['n_apps_with_ge1_failure']}")
    lines.append(f"- n_apps where all new slots failed: {fail['n_apps_all_new_slots_failed']}")
    lines.append(f"- per-app failure counts: `{fail['per_app_counts']}`")
    lines.append(f"- reason families: `{fail['reason_family_counts']}`")
    lines.append(f"- fail-rate distribution: {_dist_cell(fail['fail_rate_distribution'])}")
    lines.append(f"- concentration numbers: `{fail['concentration_note_numbers']}`")
    lines.append("")
    lines.append("### Exit codes")
    lines.append("")
    lines.append(
        f"source_meta readable={ex['source_meta_readable']} missing={ex['source_meta_missing']} "
        f"nonzero analysis_exit_code={ex['n_nonzero_analysis_exit_code']}"
    )
    lines.append(f"- exit_code counts: `{ex['exit_code_counts']}`")
    lines.append(f"- analysis_status counts: `{ex['analysis_status_counts']}`")
    if ex["nonzero"]:
        lines.append("")
        lines.append("| app_id | session_id | batch | exit | status |")
        lines.append("|--------|------------|-------|-----:|--------|")
        for r in ex["nonzero"]:
            lines.append(
                f"| {r['app_id']} | {r['session_id']} | {r['batch']} | "
                f"{r['analysis_exit_code']} | {r['analysis_status']} |"
            )
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    for p in figure_paths:
        rel = Path(p)
        try:
            rel = rel.relative_to(OUTPUT_ROOT)
        except ValueError:
            pass
        lines.append(f"- `{rel}`")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_reproduce(verify_exit: int, run1: dict[str, Any], run2: dict[str, Any]) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {
        "module": "abrg.chapter_b",
        "cli": "python -m abrg.chapter_b",
        "corpus": "datasets/v2_extended",
        "verify_export_exit": verify_exit,
        "descriptive_only": True,
        "no_detector": True,
        "no_auc": True,
        "builder_run2": "abrg.androct.graph_build.update_graph_sequence",
        "builder_run1_old_vs_new": "abrg.corpus.build_session_graph",
        "pooled_method": POOLED_METHOD,
        "androct_protocol_wall_sec": ANDROCT_PROTOCOL_WALL_SEC,
        "material_rule": {"p": MATERIAL_P, "cliffs_delta_abs": MATERIAL_CLIFF_SMALL},
        "n_v2_sessions_pass": run1["n_pooled_pass"],
        "n_v2_apps_pass": run2["unit_alignment"]["per_app_pooled_n"],
        "n_androct_benign": run2["androct_benign"]["n"],
        "n_androct_malware": run2["androct_malware"]["n"],
    }
    (ARTIFACTS_DIR / "reproduce_config.json").write_text(
        json.dumps(cfg, indent=2) + "\n", encoding="utf-8"
    )
    md = OUTPUT_ROOT / "artifacts" / "reproduce.md"
    md.write_text(
        "\n".join(
            [
                "# Chapter B — reproduce",
                "",
                "```bash",
                "python3 datasets/v2_extended/verify_export.py   # must exit 0",
                "python -m abrg.chapter_b",
                "```",
                "",
                "Outputs under `abrg/output/v2_chapter_b/`.",
                "Does not write `abrg/output/androct_2017/`, `chapter_a/`, or `abrg/chapter_c/`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (ARTIFACTS_DIR / "run2_comparison.json").write_text(
        json.dumps(json_ready(run2), indent=2) + "\n", encoding="utf-8"
    )
