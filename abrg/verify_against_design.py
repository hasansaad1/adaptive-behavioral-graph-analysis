#!/usr/bin/env python3
"""
Independent verification: ABRG implementation vs abrg_design_v0.2.md §2–§3.2.

Runs schema audit, reference UpdateGraph (literal pseudocode translation), and
multi-window cumulative update checks. Exit 0 = all checks pass.
"""

from __future__ import annotations

import copy
import math
import sys
from dataclasses import fields
from pathlib import Path

from abrg.api_category_map import apk_path_from_session_dir
from abrg.config import DELTA_SEC, K_BURST, LAMBDA_REC
from abrg.dataset_paths import default_demo_frida_trace
from abrg.graph import ABRGGraph, EdgeState, NodeState, build_initial_graph, update_graph
from abrg.registry import CATEGORY_UNIVERSE, GATE_V_DIM, GRAPH_CATEGORY_UNIVERSE
from abrg.trace import TraceEvent, load_frida_trace

REPO = Path(__file__).resolve().parents[1]
PROTONVPN = default_demo_frida_trace()  # demo trace from datasets/CURRENT

# --- §2.3 / §2.1 expected schema (design doc field names) ---
EDGE_FIELDS = {"w_cum", "w_rec", "t_first", "t_last", "n_sess", "epoch"}
NODE_STATIC = {"s_v", "declared_v", "gate_v", "reach_v", "epoch_v"}
NODE_DYNAMIC = {"act_count", "sess_v", "rec_v"}  # act_count → act_v log-scaled in X


def audit_schema() -> list[str]:
    """Verify dataclass fields cover §2.1 node vector and §2.3 edge record."""
    issues: list[str] = []
    node_fields = {f.name for f in fields(NodeState)} - {"category"}
    edge_fields = {f.name for f in fields(EdgeState)}

    if edge_fields != EDGE_FIELDS:
        issues.append(f"§2.3 edge fields mismatch: got {edge_fields}, expected {EDGE_FIELDS}")

    expected_node = NODE_STATIC | NODE_DYNAMIC
    if node_fields != expected_node:
        issues.append(f"§2.1 node fields mismatch: got {node_fields}, expected {expected_node}")

    if len(GRAPH_CATEGORY_UNIVERSE) != 22:
        issues.append(f"§2.1 graph universe must be 22 nodes, got {len(GRAPH_CATEGORY_UNIVERSE)}")
    if len(CATEGORY_UNIVERSE) != 25:
        issues.append(f"§2.1 hook taxonomy must be 25 categories, got {len(CATEGORY_UNIVERSE)}")

    apk_path = apk_path_from_session_dir(PROTONVPN.parent)
    if apk_path is None or not apk_path.is_file():
        issues.append("§3.1 APK not found for static audit — skip static checks")
        return issues

    g = build_initial_graph(apk_path=apk_path)
    if g.version_epoch != 0:
        issues.append("§3.1 version_epoch should start at 0")
    if len(g.nodes) != len(GRAPH_CATEGORY_UNIVERSE):
        issues.append("§3.1 must instantiate entire category universe")
    if g.edges:
        issues.append("§3.1 E must be empty at cold start")
    declared_any = False
    for cat, node in g.nodes.items():
        if node.act_count != 0 or node.sess_v != 0 or node.rec_v != 0:
            issues.append(f"§3.1 dynamic attrs should be 0 at cold start for {cat}")
        if len(node.gate_v) != GATE_V_DIM:
            issues.append(f"§3.1 gate_v wrong dim for {cat}")
        if node.declared_v > 0 or node.s_v > 0 or node.reach_v > 0:
            declared_any = True
    if not declared_any:
        issues.append("§3.1 Androguard produced no static signal on any category")

    return issues


def reference_update_graph_spec(
    graph: ABRGGraph,
    stream: list[tuple[str, float]],
    t_now: float,
    k: int = K_BURST,
    delta: float = DELTA_SEC,
    lam: float = LAMBDA_REC,
) -> set[tuple[str, str]]:
    # Step 0: decay recency only
    for edge in graph.edges.values():
        edge.w_rec *= math.exp(-lam * (t_now - edge.t_last))

    touched: set[tuple[str, str]] = set()
    active: set[str] = set()
    n = len(stream)

    # Step 2: edge formation — for i in 1..len(S); j in i+1 .. min(i+k, len(S))
    for i in range(n):
        u, t_u = stream[i]
        graph.nodes[u].act_count += 1
        active.add(u)
        for j in range(i + 1, min(i + k + 1, n)):
            v, t_v = stream[j]
            if t_v - t_u > delta:
                break
            if u == v:
                continue
            key = (u, v)
            if key not in graph.edges:
                graph.edges[key] = EdgeState(
                    w_cum=0.0,
                    w_rec=0.0,
                    t_first=t_v,
                    t_last=t_v,
                    n_sess=0,
                    epoch=graph.version_epoch,
                )
            e = graph.edges[key]
            e.w_cum += 1.0
            e.w_rec += 1.0
            e.t_last = t_v
            touched.add(key)

    for key in touched:
        graph.edges[key].n_sess += 1

    graph.windows_processed += 1
    for cat in active:
        graph._node_active_windows[cat] = graph._node_active_windows.get(cat, 0) + 1
    total = graph.windows_processed
    for category in GRAPH_CATEGORY_UNIVERSE:
        graph.nodes[category].sess_v = graph._node_active_windows.get(category, 0) / total

    # Step 5: rec_v
    for node in graph.nodes.values():
        node.rec_v = 0.0
    for (u, v), edge in graph.edges.items():
        graph.nodes[u].rec_v += edge.w_rec
        graph.nodes[v].rec_v += edge.w_rec

    graph._last_active = active  # noqa: SLF001 — test helper
    return touched


def graphs_equal_edges(a: ABRGGraph, b: ABRGGraph) -> list[str]:
    issues: list[str] = []
    if set(a.edges.keys()) != set(b.edges.keys()):
        issues.append(f"edge keys differ: impl={len(a.edges)} ref={len(b.edges)}")
    for key in set(a.edges.keys()) | set(b.edges.keys()):
        if key not in a.edges or key not in b.edges:
            issues.append(f"missing edge {key}")
            continue
        ea, eb = a.edges[key], b.edges[key]
        for attr in EDGE_FIELDS:
            va, vb = getattr(ea, attr), getattr(eb, attr)
            if isinstance(va, float) and abs(va - vb) > 1e-9:
                issues.append(f"edge {key}.{attr}: impl={va} ref={vb}")
            elif va != vb:
                issues.append(f"edge {key}.{attr}: impl={va} ref={vb}")
    for cat in GRAPH_CATEGORY_UNIVERSE:
        na, nb = a.nodes[cat], b.nodes[cat]
        if na.act_count != nb.act_count:
            issues.append(f"node {cat}.act_count: impl={na.act_count} ref={nb.act_count}")
        if abs(na.rec_v - nb.rec_v) > 1e-9:
            issues.append(f"node {cat}.rec_v: impl={na.rec_v} ref={nb.rec_v}")
        if abs(na.sess_v - nb.sess_v) > 1e-9:
            issues.append(f"node {cat}.sess_v: impl={na.sess_v} ref={nb.sess_v}")
    return issues


def compare_update_on_trace(events: list[TraceEvent], apk_path: Path) -> list[str]:
    stream = [(e.category, e.timestamp_ms / 1000.0) for e in events]
    t_now = stream[-1][1] if stream else 0.0

    g_impl = build_initial_graph(apk_path=apk_path)
    update_graph(g_impl, events)

    g_ref = build_initial_graph(apk_path=apk_path)
    reference_update_graph_spec(g_ref, stream, t_now)

    return graphs_equal_edges(g_impl, g_ref)


def check_multi_window_cumulative(events: list[TraceEvent], apk_path: Path) -> list[str]:
    """§3.6: sequential windows; w_cum monotonic; n_sess counts windows; sess_v fraction."""
    issues: list[str] = []
    if len(events) < 100:
        issues.append("not enough events for multi-window test")
        return issues

    mid = len(events) // 2
    w1, w2 = events[:mid], events[mid:]

    g = build_initial_graph(apk_path=apk_path)
    update_graph(g, w1)
    cum_after_w1 = {k: e.w_cum for k, e in g.edges.items()}
    update_graph(g, w2)

    for key, w in cum_after_w1.items():
        if g.edges[key].w_cum < w:
            issues.append(f"§2.4 w_cum decreased on {key}: was {w}, now {g.edges[key].w_cum}")

    if g.windows_processed != 2:
        issues.append(f"expected 2 windows processed, got {g.windows_processed}")

    for cat in ("crypto", "file_io", "network", "storage"):
        if cat in g.active_nodes() and g.nodes[cat].sess_v != 1.0:
            issues.append(f"§3.2 sess_v for always-active {cat} should be 1.0, got {g.nodes[cat].sess_v}")

    touched_w1 = _edges_touched_in_window(build_initial_graph(apk_path=apk_path), w1)
    touched_w2 = _edges_touched_in_window(build_initial_graph(apk_path=apk_path), w2)
    for key in touched_w1 & touched_w2:
        if g.edges[key].n_sess != 2:
            issues.append(f"edge {key} touched in both windows but n_sess={g.edges[key].n_sess}")

    if not g.edges:
        issues.append("multi-window produced no edges")
    return issues


def _edges_touched_in_window(graph: ABRGGraph, window: list[TraceEvent]) -> set[tuple[str, str]]:
    """Edges that receive at least one increment during a single UpdateGraph call."""
    before = {k: (e.w_cum, e.w_rec) for k, e in graph.edges.items()}
    update_graph(graph, window)
    touched: set[tuple[str, str]] = set()
    for key, edge in graph.edges.items():
        if key not in before or edge.w_cum > before[key][0]:
            touched.add(key)
    return touched


def check_pinned_deviations() -> list[str]:
    """Documented intentional deviations from full §3.1 / pilot pins."""
    return []  # informational only


def main() -> int:
    print("=== ABRG v0.2 design conformance review ===\n")

    print("1. Schema audit (§2.1, §2.3, §3.1)")
    schema_issues = audit_schema()
    if schema_issues:
        for i in schema_issues:
            print(f"  FAIL: {i}")
    else:
        print("  PASS: node/edge schema and BuildInitialGraph match design (Androguard static)")

    if not PROTONVPN.is_file():
        print(f"\nSTOP: trace missing {PROTONVPN}")
        return 1

    apk_path = apk_path_from_session_dir(PROTONVPN.parent)
    if apk_path is None or not apk_path.is_file():
        print(f"\nSTOP: APK missing for {PROTONVPN.parent}")
        return 1

    events, report = load_frida_trace(PROTONVPN)
    print(f"\n2. Trace: {report.events_kept} events, {len(report.distinct_categories)} categories")

    print("\n3. UpdateGraph vs reference §3.2 pseudocode (whole session)")
    cmp_issues = compare_update_on_trace(events, apk_path)
    if cmp_issues:
        for i in cmp_issues[:20]:
            print(f"  FAIL: {i}")
        if len(cmp_issues) > 20:
            print(f"  ... and {len(cmp_issues) - 20} more")
    else:
        print("  PASS: implementation matches reference UpdateGraph on ProtonVPN trace")

    print("\n4. Multi-window cumulative behavior (§3.6 / §2.4)")
    mw_issues = check_multi_window_cumulative(events, apk_path)
    if mw_issues:
        for i in mw_issues:
            print(f"  FAIL: {i}")
    else:
        print("  PASS: w_cum monotonic across two sequential windows")

    g = build_initial_graph(apk_path=apk_path)
    update_graph(g, events)
    print(f"\n5. ProtonVPN graph snapshot")
    print(f"  nodes active: {len(g.active_nodes())} / {len(GRAPH_CATEGORY_UNIVERSE)}")
    print(f"  directed edges: {len(g.edges)}")
    print("  static on active nodes:")
    for cat in g.active_nodes():
        n = g.nodes[cat]
        print(f"    {cat}: s_v={n.s_v}, declared={n.declared_v}, gate={n.gate_v}, reach={n.reach_v}")
    for u, v, e in g.iter_edges():
        print(f"    {u} → {v}: w_cum={e.w_cum}, w_rec={e.w_rec}, t_first={e.t_first:.3f}, "
              f"t_last={e.t_last:.3f}, n_sess={e.n_sess}, epoch={e.epoch}")

    all_issues = schema_issues + cmp_issues + mw_issues
    print(f"\n=== Result: {len(all_issues)} issue(s) ===")
    return 1 if all_issues else 0


if __name__ == "__main__":
    sys.exit(main())
