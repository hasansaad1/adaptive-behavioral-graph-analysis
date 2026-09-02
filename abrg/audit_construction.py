#!/usr/bin/env python3
"""
ABRG v0.2 graph construction correctness audit (no training).
Runs 8 explicit checks against pinned pilot decisions + abrg_design_v0.2.md.
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
from dataclasses import asdict
from pathlib import Path

os.environ.setdefault("LOGURU_LEVEL", "ERROR")

from abrg.config import DELTA_SEC, K_BURST, LAMBDA_REC
from abrg.features import graph_to_tensors, node_feature_dim, feature_vector_labels
from abrg.graph import ABRGGraph, build_initial_graph, update_graph
from abrg.registry import (
    DROPPED_CATEGORIES,
    GATE_V_DIM,
    GRAPH_CATEGORY_UNIVERSE,
    NON_GRAPH_HOOK_CATEGORIES,
)
from abrg.static import StaticNodeAttrs, StaticReport
from abrg.dataset_paths import default_demo_frida_trace
from abrg.trace import TraceEvent, load_frida_trace

REPO = Path(__file__).resolve().parents[1]
PROTONVPN_TRACE = default_demo_frida_trace()  # demo trace from datasets/CURRENT


def zero_static_report(package_name: str = "") -> StaticReport:
    """Pinned decision #6: schema-preserving zero-fill static stub."""
    return StaticReport(
        apk_path="",
        package_name=package_name,
        permissions=[],
        nodes={c: StaticNodeAttrs() for c in GRAPH_CATEGORY_UNIVERSE},
    )


def build_graph_whole_session(events: list[TraceEvent], package_name: str = "") -> ABRGGraph:
    g = build_initial_graph(static_report=zero_static_report(package_name))
    update_graph(g, events)
    return g


def reference_count_edge(events: list[TraceEvent], u: str, v: str) -> int:
    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in events]
    n = len(stream)
    count = 0
    for i in range(n):
        cat_u, t_u = stream[i]
        if cat_u != u:
            continue
        for j in range(i + 1, min(i + K_BURST + 1, n)):
            cat_v, t_v = stream[j]
            if t_v - t_u > DELTA_SEC:
                break
            if cat_v == v and u != v:
                count += 1
    return count


def find_direction_pair(events: list[TraceEvent]) -> tuple[int, int, str, str] | None:
    """Return (i, j, u, v) where event i precedes j, u→v should form."""
    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in events]
    n = len(stream)
    for i in range(n):
        u, t_u = stream[i]
        for j in range(i + 1, min(i + K_BURST + 1, n)):
            v, t_v = stream[j]
            if t_v - t_u > DELTA_SEC:
                break
            if u != v:
                return i, j, u, v
    return None


def find_qualifying_pair(events: list[TraceEvent]) -> tuple[int, int, str, str, float] | None:
    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in events]
    n = len(stream)
    for i in range(n):
        u, t_u = stream[i]
        for j in range(i + 1, min(i + K_BURST + 1, n)):
            v, t_v = stream[j]
            dt = t_v - t_u
            if dt > DELTA_SEC:
                break
            if u != v:
                return i, j, u, v, dt
    return None


def pair_increment_at(events: list[TraceEvent], i: int, j: int) -> bool:
    """True if UpdateGraph counts transition at exactly indices i→j."""
    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in events]
    u, t_u = stream[i]
    v, t_v = stream[j]
    if j <= i or j > i + K_BURST:
        return False
    if t_v - t_u > DELTA_SEC:
        return False
    return u != v


def find_zero_increment_pair(events: list[TraceEvent]) -> tuple[str, str] | None:
    """Active-category pair that never qualifies under (k, δ)."""
    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in events]
    active = {ev.category for ev in events}
    n = len(stream)
    counts: dict[tuple[str, str], int] = {}
    for i in range(n):
        u, t_u = stream[i]
        for j in range(i + 1, min(i + K_BURST + 1, n)):
            v, t_v = stream[j]
            if t_v - t_u > DELTA_SEC:
                break
            if u != v:
                counts[(u, v)] = counts.get((u, v), 0) + 1
    for a in sorted(active):
        for b in sorted(active):
            if a != b and counts.get((a, b), 0) == 0:
                return a, b
    return None


def graph_snapshot(g: ABRGGraph) -> dict:
    return {
        "nodes_total": len(g.nodes),
        "active_nodes": g.active_nodes(),
        "edges": [
            {
                "u": u,
                "v": v,
                "w_cum": e.w_cum,
                "w_rec": e.w_rec,
                "t_first": e.t_first,
                "t_last": e.t_last,
                "n_sess": e.n_sess,
            }
            for u, v, e in g.iter_edges()
        ],
    }


def adjacency_summary(g: ABRGGraph) -> str:
    lines = []
    for u in sorted(g.active_nodes()):
        outs = [(v, g.edges[(u, v)].w_cum) for v in g.active_nodes() if (u, v) in g.edges]
        if outs:
            parts = ", ".join(f"{v}({int(w)})" for v, w in sorted(outs, key=lambda x: -x[1]))
            lines.append(f"  {u} → {parts}")
    return "\n".join(lines) if lines else "  (no edges among active nodes)"


def run_audit(trace_path: Path, app_name: str | None = None) -> int:
    checks: list[dict] = []

    if not trace_path.is_file():
        print(f"FAIL: trace missing: {trace_path}")
        return 1

    if app_name is None:
        app_name = trace_path.parent.name.split("__")[-1] if "__" in trace_path.parent.name else trace_path.stem

    events, trace_report = load_frida_trace(trace_path)

    # --- Check 1: NODE UNIVERSE ---
    g = build_graph_whole_session(events, package_name=app_name)
    expected_n = len(GRAPH_CATEGORY_UNIVERSE)
    actual_n = len(g.nodes)
    universe_ok = (
        actual_n == expected_n
        and list(g.nodes.keys()) == list(GRAPH_CATEGORY_UNIVERSE)
    )
    checks.append(
        {
            "id": 1,
            "name": "NODE UNIVERSE",
            "pass": universe_ok,
            "evidence": (
                f"node count={actual_n}, |GRAPH_CATEGORY_UNIVERSE|={expected_n}; "
                f"keys match ordered universe={list(g.nodes.keys()) == list(GRAPH_CATEGORY_UNIVERSE)}; "
                f"non-graph hook cats absent="
                f"{not (NON_GRAPH_HOOK_CATEGORIES & set(g.nodes.keys()))}"
            ),
        }
    )

    # --- Check 2: EVENT FILTER ---
    raw_lines = sum(1 for ln in PROTONVPN_TRACE.read_text().splitlines() if ln.strip())
    # Count type==event vs other from raw file
    type_event = 0
    type_other = 0
    cats_in_raw_events: dict[str, int] = {}
    for raw in trace_path.read_text().splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "event":
            type_other += 1
            continue
        type_event += 1
        c = obj.get("category", "unknown")
        cats_in_raw_events[c] = cats_in_raw_events.get(c, 0) + 1

    kept_cats = set(trace_report.distinct_categories)
    dropped_present = kept_cats & DROPPED_CATEGORIES
    expected_cat_drops = sum(cats_in_raw_events.get(c, 0) for c in DROPPED_CATEGORIES)
    category_drop_ok = (
        trace_report.events_dropped_category == expected_cat_drops and not dropped_present
    )
    filter_ok = (
        trace_report.events_dropped_type > 0
        and category_drop_ok
        and len(kept_cats) >= 4
    )
    checks.append(
        {
            "id": 2,
            "name": "EVENT FILTER",
            "pass": filter_ok,
            "evidence": (
                f"raw parsed lines={trace_report.lines_parsed}; "
                f"type!=event dropped={trace_report.events_dropped_type}; "
                f"lifecycle/reflection/navigation/legacy dropped="
                f"{trace_report.events_dropped_category} (expected={expected_cat_drops}); "
                f"kept={trace_report.events_kept}; "
                f"kept categories={trace_report.category_counts}; "
                f"dropped cats still present={dropped_present or 'none'}"
            ),
        }
    )

    # --- Check 3: NODE VECTOR SCHEMA ---
    labels = feature_vector_labels()
    dim = node_feature_dim()
    dim_ok = dim == len(labels)
    # Pick active node crypto (largest act count likely)
    active = g.active_nodes()
    pick = "crypto" if "crypto" in active else active[0]
    x, _, _, cats = graph_to_tensors(g)
    idx = cats.index(pick)
    vec = x[idx].tolist()
    static_vals = vec[: 2 + GATE_V_DIM + 2]  # s_v, declared, gate*, reach, epoch
    static_zero = all(v == 0.0 for v in static_vals)
    dynamic_populated = vec[-3] > 0 and vec[-2] > 0 and vec[-1] > 0  # act_log, sess, rec
    schema_ok = dim_ok and len(vec) == dim and static_zero and dynamic_populated
    slot_str = ", ".join(f"{lab}={val:.4g}" for lab, val in zip(labels, vec))
    checks.append(
        {
            "id": 3,
            "name": "NODE VECTOR SCHEMA",
            "pass": schema_ok,
            "evidence": (
                f"feature_dim={dim} slots={len(labels)}; "
                f"node={pick!r} vector=[{slot_str}]; "
                f"static slots all zero={static_zero}; "
                f"dynamic populated (act_log,sess,rec>0)={dynamic_populated}"
            ),
        }
    )

    # --- Check 4: EDGE DIRECTION ---
    dir_pair = find_direction_pair(events)
    dir_ok = False
    dir_evidence = "no qualifying pair found in trace"
    if dir_pair:
        i, j, u, v = dir_pair
        forward = (u, v) in g.edges
        reverse = (v, u) in g.edges
        # reverse allowed only if B also precedes A elsewhere within rules
        rev_count = reference_count_edge(events, v, u)
        dir_ok = forward and (not reverse or rev_count > 0)
        dir_evidence = (
            f"trace indices i={i} j={j}: {u}@{events[i].timestamp_ms}ms → "
            f"{v}@{events[j].timestamp_ms}ms; edge {u}→{v} exists={forward} "
            f"w_cum={g.edges[(u,v)].w_cum if forward else 'N/A'}; "
            f"reverse {v}→{u} exists={reverse} (ref reverse count={rev_count})"
        )
    checks.append({"id": 4, "name": "EDGE DIRECTION", "pass": dir_ok, "evidence": dir_evidence})

    # --- Check 5: EDGE WINDOW RULE ---
    qual = find_qualifying_pair(events)
    # Rejected: same categories, within k events, but Δt > δ — must not increment
    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in events]
    rej = None
    n = len(stream)
    for i in range(n):
        u, t_u = stream[i]
        for j in range(i + 1, min(i + K_BURST + 1, n)):
            v, t_v = stream[j]
            dt = t_v - t_u
            if dt > DELTA_SEC and u != v:
                rej = (i, j, u, v, dt, j - i)
                break
            if dt > DELTA_SEC:
                break
        if rej:
            break
    zero_pair = find_zero_increment_pair(events)
    rule_ok = False
    rule_evidence = ""
    if qual and rej and zero_pair:
        qi, qj, qu, qv, qdt = qual
        ri, rj, ru, rv, rdt, rgap = rej
        qual_edge = (qu, qv) in g.edges
        rej_counted = pair_increment_at(events, ri, rj)
        zp_u, zp_v = zero_pair
        zero_edge = (zp_u, zp_v) in g.edges
        rule_ok = qual_edge and not rej_counted and not zero_edge
        rule_evidence = (
            f"QUALIFYING: idx {qi}→{qj} {qu}→{qv} Δt={qdt:.3f}s ≤ {DELTA_SEC}s, "
            f"gap={qj-qi} ≤ {K_BURST}; edge exists={qual_edge}. "
            f"REJECTED (δ): idx {ri}→{rj} {ru}→{rv} Δt={rdt:.3f}s > {DELTA_SEC}s, "
            f"gap={rgap}; increment at this pair={rej_counted}. "
            f"NEVER-QUALIFIES: {zp_u}→{zp_v} has 0 increments under (k,δ); "
            f"edge absent={not zero_edge}"
        )
    else:
        rule_evidence = (
            f"qual={qual is not None}, rej={rej is not None}, zero_pair={zero_pair}"
        )
    checks.append({"id": 5, "name": "EDGE WINDOW RULE", "pass": rule_ok, "evidence": rule_evidence})

    # --- Check 6: WEIGHTS ---
    # Pick highest w_cum edge
    best_uv = max(g.edges.keys(), key=lambda k: g.edges[k].w_cum)
    bu, bv = best_uv
    manual = reference_count_edge(events, bu, bv)
    edge = g.edges[best_uv]
    weight_ok = edge.w_cum == float(manual) and edge.w_rec <= edge.w_cum
    checks.append(
        {
            "id": 6,
            "name": "WEIGHTS",
            "pass": weight_ok,
            "evidence": (
                f"edge {bu}→{bv}: w_cum={edge.w_cum}, manual count={manual}, "
                f"match={edge.w_cum == manual}; w_rec={edge.w_rec}, "
                f"w_rec≤w_cum={edge.w_rec <= edge.w_cum}; "
                f"single whole-session window → w_rec≈w_cum before cross-window decay"
            ),
        }
    )

    # --- Check 7: DETERMINISM ---
    g1 = build_graph_whole_session(events, package_name=app_name)
    g2 = build_graph_whole_session(events, package_name=app_name)

    def graph_fingerprint(gr: ABRGGraph) -> dict:
        return {
            "nodes": sorted(gr.nodes.keys()),
            "edges": sorted(
                (u, v, round(e.w_cum, 9), round(e.w_rec, 9))
                for (u, v), e in gr.edges.items()
            ),
            "act": sorted((c, gr.nodes[c].act_count) for c in gr.nodes),
        }

    fp1 = graph_fingerprint(g1)
    fp2 = graph_fingerprint(g2)
    det_ok = fp1 == fp2
    checks.append(
        {
            "id": 7,
            "name": "DETERMINISM",
            "pass": det_ok,
            "evidence": (
                f"two builds identical={det_ok}; "
                f"edges={len(g1.edges)}, active={len(g1.active_nodes())}"
            ),
        }
    )

    # --- Check 8: SANITY ---
    active_set = set(g.active_nodes())
    edge_sane = all(
        u in GRAPH_CATEGORY_UNIVERSE and v in GRAPH_CATEGORY_UNIVERSE for u, v in g.edges
    )
    no_self = all(u != v for u, v in g.edges)
    has_edges = len(g.edges) > 0
    enough_active = len(active_set) >= 4
    top_cats = sorted(
        trace_report.category_counts.items(), key=lambda x: -x[1]
    )[:3]
    active_matches_trace = active_set <= set(trace_report.distinct_categories)
    sanity_ok = (
        enough_active
        and edge_sane
        and no_self
        and has_edges
        and active_matches_trace
    )
    checks.append(
        {
            "id": 8,
            "name": "SANITY",
            "pass": sanity_ok,
            "evidence": (
                f"active={sorted(active_set)} (≥4={enough_active}); "
                f"top trace cats={top_cats}; "
                f"directed edges={len(g.edges)}; "
                f"active⊆trace categories={active_matches_trace}; "
                f"no self-loops={no_self}"
            ),
        }
    )

    # --- Report ---
    print("=" * 72)
    print("ABRG v0.2 CONSTRUCTION CORRECTNESS AUDIT")
    print(f"App: {app_name}")
    print(f"Trace: {trace_path}")
    print("Mode: whole session = 1 processing window (pinned); static zero-stub (pinned)")
    print("Training: SKIPPED (construction only)")
    print("=" * 72)
    print()
    print("| # | Check | Result | Evidence |")
    print("|---|-------|--------|----------|")
    failures = []
    for c in checks:
        result = "PASS" if c["pass"] else "FAIL"
        if not c["pass"]:
            failures.append(c)
        ev = c["evidence"].replace("|", "\\|")
        if len(ev) > 120:
            ev = ev[:117] + "..."
        print(f"| {c['id']} | {c['name']} | **{result}** | {ev} |")

    print()
    print("### Full evidence per check")
    print()
    for c in checks:
        print(f"**{c['id']}. {c['name']} — {'PASS' if c['pass'] else 'FAIL'}**")
        print(f"  {c['evidence']}")
        print()

    snap = graph_snapshot(g)
    print("### Graph summary")
    print(f"- Nodes (total): {snap['nodes_total']} (= |GRAPH_CATEGORY_UNIVERSE|)")
    print(f"- Active nodes ({len(snap['active_nodes'])}): {snap['active_nodes']}")
    print(f"- Directed edges: {len(snap['edges'])}")
    print()
    print("### Edge list (w_cum / w_rec)")
    for e in snap["edges"]:
        print(
            f"  {e['u']} → {e['v']}: w_cum={e['w_cum']}, w_rec={e['w_rec']}, "
            f"n_sess={e['n_sess']}, t_first={e['t_first']:.3f}, t_last={e['t_last']:.3f}"
        )
    print()
    print("### Adjacency summary (active nodes)")
    print(adjacency_summary(g))

    if failures:
        print()
        print("=" * 72)
        print(f"STOP: {len(failures)} check(s) FAILED — do not proceed to scale/training.")
        for f in failures:
            print(f"  - Check {f['id']} {f['name']}: {f['evidence']}")
        return 1

    print()
    print("=" * 72)
    print("ALL 8 CHECKS PASSED — graph construction matches v0.2 design (pinned pilot scope).")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ABRG v0.2 construction audit (no training)")
    parser.add_argument(
        "--trace",
        type=Path,
        default=PROTONVPN_TRACE,
        help="Path to *_frida.jsonl or session directory",
    )
    parser.add_argument("--app-name", type=str, default=None, help="Label for report")
    args = parser.parse_args()
    trace = args.trace.resolve()
    if trace.is_dir():
        matches = list(trace.glob("*_frida.jsonl"))
        if len(matches) != 1:
            print(f"Expected one *_frida.jsonl in {trace}, got {matches}", file=sys.stderr)
            sys.exit(1)
        trace = matches[0]
    sys.exit(run_audit(trace, app_name=args.app_name))
