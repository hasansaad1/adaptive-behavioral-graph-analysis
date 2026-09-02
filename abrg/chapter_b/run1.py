"""RUN 1 — corpus inventory, old vs new, failures, exit codes."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from abrg.corpus import build_session_graph
from abrg.trace import load_frida_trace

from abrg.chapter_b.config import POSSIBLE_EDGES, RUN1_DIR
from abrg.chapter_b.graphs_seq import topology
from abrg.chapter_b.ingest import (
    SessionRow,
    batch_date_range,
    fail_sessions,
    gae_eligible_from_graph,
    load_source_meta,
    mapped_and_total,
    pass_sessions,
    session_count_table,
)
from abrg.chapter_b.stats import json_ready, mann_whitney, summarize_dist, value_counts


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(obj), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _reason_family(reason: str | None) -> str:
    if not reason:
        return "none"
    r = reason.lower()
    if "failed_frida_reattach" in r:
        return "failed_frida_reattach"
    if "webview_dominant" in r:
        return "webview_dominant"
    if "bad_handoff" in r:
        return "partial:bad_handoff"
    if "no_goal_progress" in r:
        return "partial:no_goal_progress"
    if "ux_quality_gate" in r:
        return "partial:ux_quality_gate"
    if "dominant_screen" in r:
        return "flailing:dominant_screen"
    if "same_element_cycle" in r:
        return "flailing:same_element_cycle"
    if "flailing" in r:
        return "flailing:other"
    return reason.split(",")[0][:80]


def _session_metrics(row: SessionRow) -> dict[str, Any]:
    """Recompute mapped/total via mapper; graph topology via export-time timed builder."""
    events_path = Path(row.events_path)
    mapped, total, _cats, _apis = mapped_and_total(events_path)
    events, _ = load_frida_trace(events_path)
    g = build_session_graph(events, row.app_id)
    n_active, n_edges, dens = topology(g)
    wall = row.wall_duration_s
    return {
        "app_id": row.app_id,
        "session_id": row.session_id,
        "export_dir_name": row.export_dir_name,
        "batch": row.batch,
        "reference_tier_pass": row.reference_tier_pass,
        "mapped": mapped,
        "total": total,
        "mapped_rate": (mapped / total) if total else 0.0,
        "n_active": n_active,
        "n_edges": n_edges,
        "density": dens,
        "wall_duration_s": wall,
        "mapped_meta": row.mapped_meta,
        "n_active_meta": row.n_active_meta,
        "n_edges_meta": row.n_edges_meta,
        "gae_eligible": gae_eligible_from_graph(n_active, n_edges),
    }


def run1(rows: list[SessionRow], out_dir: Path = RUN1_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    indexed = rows
    passing = pass_sessions(rows)
    failing = fail_sessions(rows)
    usable = passing  # analysis set = reference-tier pass (export sessions/)

    by_batch_all = Counter(r.batch for r in indexed)
    by_batch_pass = Counter(r.batch for r in passing)
    by_batch_fail = Counter(r.batch for r in failing)

    orig_pass = [r for r in passing if r.batch == "original"]
    new_pass = [r for r in passing if r.batch in {"canary", "extend"}]

    dist_all, per_app_all = session_count_table(passing)
    dist_orig, per_app_orig = session_count_table(orig_pass)
    dist_new, per_app_new = session_count_table(new_pass)

    apps_ge1 = sorted({r.app_id for r in usable})

    print("[chapter_b] run1 recomputing per-session graphs (timed export path) …", flush=True)
    metrics = [_session_metrics(r) for r in indexed]
    metrics_pass = [m for m in metrics if m["reference_tier_pass"]]
    metrics_by_key = {(m["app_id"], m["export_dir_name"]): m for m in metrics}

    def apps_gae(subset: list[SessionRow]) -> set[str]:
        out: set[str] = set()
        for r in subset:
            m = metrics_by_key[(r.app_id, r.export_dir_name)]
            if m["gae_eligible"]:
                out.add(r.app_id)
        return out

    gae_before = apps_gae(orig_pass)
    gae_after = apps_gae(passing)
    entered = sorted(gae_after - gae_before)
    left = sorted(gae_before - gae_after)

    # Failures
    fail_rows = []
    fail_per_app: dict[str, int] = defaultdict(int)
    fail_reason_family = Counter()
    apps_in_new = {r.app_id for r in indexed if r.batch in {"canary", "extend"}}
    new_slots_per_app: dict[str, int] = Counter(
        r.app_id for r in indexed if r.batch in {"canary", "extend"}
    )
    for r in failing:
        fam = _reason_family(r.failure_reason)
        fail_reason_family[fam] += 1
        fail_per_app[r.app_id] += 1
        fail_rows.append(
            {
                "app_id": r.app_id,
                "session_id": r.session_id,
                "batch": r.batch,
                "failure_reason": r.failure_reason,
                "failure_family": fam,
            }
        )
    fail_rate_per_app = []
    for app in sorted(apps_in_new):
        n_new = int(new_slots_per_app[app])
        n_fail = int(fail_per_app.get(app, 0))
        fail_rate_per_app.append(
            {
                "app_id": app,
                "n_new_slots": n_new,
                "n_fail": n_fail,
                "fail_rate": (n_fail / n_new) if n_new else None,
            }
        )
    fail_rates = [float(x["fail_rate"]) for x in fail_rate_per_app if x["fail_rate"] is not None]
    n_apps_with_fail = sum(1 for x in fail_rate_per_app if x["n_fail"] > 0)
    n_apps_all_fail = sum(
        1 for x in fail_rate_per_app if x["n_fail"] > 0 and x["n_fail"] == x["n_new_slots"]
    )

    # Exit codes from export fields + source_meta_path when present.
    exit_rows = []
    nonzero = []
    source_readable = 0
    source_missing = 0
    for r in indexed:
        src = load_source_meta(r.source_meta_path)
        exit_code = None
        status = r.analysis_status
        if src:
            source_readable += 1
            if src.get("analysis_exit_code") is not None:
                exit_code = src.get("analysis_exit_code")
            status = src.get("analysis_status") or status
        else:
            source_missing += 1
        rec = {
            "app_id": r.app_id,
            "session_id": r.session_id,
            "batch": r.batch,
            "reference_tier_pass": r.reference_tier_pass,
            "analyze_exit_status_export": r.analyze_exit_status,
            "analysis_status": status,
            "analysis_exit_code": exit_code,
            "source_meta_readable": src is not None,
            "failure_reason": r.failure_reason,
        }
        exit_rows.append(rec)
        if exit_code not in (None, 0, "0"):
            nonzero.append(rec)

    def col(ms: list[dict[str, Any]], key: str) -> list[float]:
        out: list[float] = []
        for m in ms:
            v = m.get(key)
            if v is None:
                continue
            out.append(float(v))
        return out

    orig_m = [metrics_by_key[(r.app_id, r.export_dir_name)] for r in orig_pass]
    new_m = [metrics_by_key[(r.app_id, r.export_dir_name)] for r in new_pass]
    pool_m = metrics_pass

    metric_keys = [
        ("mapped", "mapped_events_per_session"),
        ("total", "total_events_per_session"),
        ("n_active", "active_nodes_per_graph"),
        ("n_edges", "edges_per_graph"),
        ("density", "graph_density"),
        ("wall_duration_s", "wall_duration_s"),
    ]
    old_vs_new: dict[str, Any] = {}
    material_hits: list[str] = []
    for key, name in metric_keys:
        xo, xn, xp = col(orig_m, key), col(new_m, key), col(pool_m, key)
        test = mann_whitney(xo, xn, label_x="original", label_y="new_canary_extend")
        old_vs_new[name] = {
            "original": summarize_dist(xo),
            "new": summarize_dist(xn),
            "pooled": summarize_dist(xp),
            "mann_whitney": test,
        }
        if test.get("material_by_declared_rule"):
            material_hits.append(name)

    # Metadata vs recompute check (pass sessions).
    n_mapped_mismatch = sum(
        1
        for m in metrics_pass
        if m["mapped_meta"] is not None and int(m["mapped_meta"]) != int(m["mapped"])
    )
    n_active_mismatch = sum(
        1
        for m in metrics_pass
        if m["n_active_meta"] is not None and int(m["n_active_meta"]) != int(m["n_active"])
    )

    inventory = {
        "sessions": {
            "indexed": len(indexed),
            "usable_reference_tier_pass": len(usable),
            "reference_tier_pass": len(passing),
            "reference_tier_fail": len(failing),
            "by_batch_indexed": dict(sorted(by_batch_all.items())),
            "by_batch_pass": dict(sorted(by_batch_pass.items())),
            "by_batch_fail": dict(sorted(by_batch_fail.items())),
        },
        "apps": {
            "n_with_ge1_usable": len(apps_ge1),
            "gae_eligible_before_extension": sorted(gae_before),
            "n_gae_before": len(gae_before),
            "gae_eligible_after_extension": sorted(gae_after),
            "n_gae_after": len(gae_after),
            "entered_eligibility": entered,
            "left_eligibility": left,
        },
        "session_count_distribution": {
            "before_extension_original_pass": dist_orig,
            "after_extension_all_pass": dist_all,
            "new_pass_only": dist_new,
        },
        "per_app_session_counts": {
            "before_original_pass": per_app_orig,
            "after_all_pass": per_app_all,
        },
        "collection_date_ranges": batch_date_range(indexed),
        "graph_recompute": {
            "builder": "abrg.corpus.build_session_graph (timed update_graph; export path)",
            "density_denominator": POSSIBLE_EDGES,
            "n_mapped_mismatch_vs_meta": n_mapped_mismatch,
            "n_active_mismatch_vs_meta": n_active_mismatch,
        },
    }

    failures = {
        "n": len(failing),
        "per_app_counts": dict(sorted(fail_per_app.items(), key=lambda kv: (-kv[1], kv[0]))),
        "reason_family_counts": dict(sorted(fail_reason_family.items(), key=lambda kv: (-kv[1], kv[0]))),
        "n_apps_in_canary_or_extend": len(apps_in_new),
        "n_apps_with_ge1_failure": n_apps_with_fail,
        "n_apps_all_new_slots_failed": n_apps_all_fail,
        "fail_rate_distribution": summarize_dist(fail_rates),
        "fail_rate_value_counts": value_counts(
            [int(round(100 * x["fail_rate"])) for x in fail_rate_per_app if x["fail_rate"] is not None]
        ),
        "concentration_note_numbers": {
            "max_failures_on_one_app": max(fail_per_app.values()) if fail_per_app else 0,
            "median_failures_among_apps_with_fail": (
                sorted(fail_per_app.values())[len(fail_per_app) // 2] if fail_per_app else 0
            ),
        },
    }

    exits = {
        "n_sessions": len(indexed),
        "source_meta_readable": source_readable,
        "source_meta_missing": source_missing,
        "n_nonzero_analysis_exit_code": len(nonzero),
        "nonzero": nonzero,
        "exit_code_counts": dict(
            Counter(
                str(r["analysis_exit_code"])
                for r in exit_rows
                if r["analysis_exit_code"] is not None
            )
        ),
        "analysis_status_counts": dict(
            Counter(str(r["analysis_status"]) for r in exit_rows if r["analysis_status"])
        ),
    }

    report = {
        "inventory": inventory,
        "old_vs_new": old_vs_new,
        "old_vs_new_material_metrics": material_hits,
        "old_vs_new_any_material": bool(material_hits),
        "failures": failures,
        "exit_codes": exits,
        "n_original_pass": len(orig_pass),
        "n_new_pass": len(new_pass),
        "n_pooled_pass": len(pool_m),
    }

    _dump(out_dir / "inventory.json", inventory)
    _dump(out_dir / "old_vs_new.json", old_vs_new)
    _dump(out_dir / "failures.json", failures)
    _dump(out_dir / "exit_codes.json", exits)
    _dump(out_dir / "run1.json", report)
    _write_csv(
        out_dir / "per_session_metrics.csv",
        metrics,
        [
            "app_id",
            "session_id",
            "export_dir_name",
            "batch",
            "reference_tier_pass",
            "mapped",
            "total",
            "mapped_rate",
            "n_active",
            "n_edges",
            "density",
            "wall_duration_s",
            "gae_eligible",
        ],
    )
    _write_csv(
        out_dir / "reference_tier_failures.csv",
        fail_rows,
        ["app_id", "session_id", "batch", "failure_family", "failure_reason"],
    )
    _write_csv(
        out_dir / "fail_rate_per_app.csv",
        fail_rate_per_app,
        ["app_id", "n_new_slots", "n_fail", "fail_rate"],
    )
    _write_csv(
        out_dir / "per_app_session_counts.csv",
        [
            {
                "app_id": app,
                "n_before_original_pass": per_app_orig.get(app, 0),
                "n_after_all_pass": per_app_all.get(app, 0),
            }
            for app in sorted(set(per_app_orig) | set(per_app_all))
        ],
        ["app_id", "n_before_original_pass", "n_after_all_pass"],
    )
    print(
        f"[chapter_b] run1 done indexed={len(indexed)} pass={len(passing)} fail={len(failing)} "
        f"gae {len(gae_before)}→{len(gae_after)} entered={entered} left={left}",
        flush=True,
    )
    return report
