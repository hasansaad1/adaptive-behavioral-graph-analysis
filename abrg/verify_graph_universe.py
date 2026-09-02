#!/usr/bin/env python3
"""Verify GRAPH_CATEGORY_UNIVERSE (22) is used consistently across graph builds."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from abrg.corpus import build_session_graph
from abrg.features import graph_to_tensors
from abrg.registry import (
    CATEGORY_UNIVERSE,
    DROPPED_CATEGORIES,
    GRAPH_CATEGORY_UNIVERSE,
    NON_GRAPH_HOOK_CATEGORIES,
    _assert_category_universes,
)
from abrg.dataset_paths import current_sessions_dir
from abrg.trace import GRAPH_CATEGORY_INDEX, load_frida_trace

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS = current_sessions_dir()


def find_trace(session_dir: Path) -> Path:
    matches = sorted(session_dir.glob("*_frida.jsonl"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one *_frida.jsonl in {session_dir}, got {matches}")
    return matches[0]


def verify_guard() -> tuple[bool, str]:
    try:
        _assert_category_universes()
    except AssertionError as exc:
        return False, str(exc)
    excluded = set(CATEGORY_UNIVERSE) - set(GRAPH_CATEGORY_UNIVERSE)
    ok = (
        len(CATEGORY_UNIVERSE) == 25
        and len(GRAPH_CATEGORY_UNIVERSE) == 22
        and excluded == NON_GRAPH_HOOK_CATEGORIES
        and not (set(GRAPH_CATEGORY_UNIVERSE) & DROPPED_CATEGORIES)
    )
    return ok, (
        f"|CATEGORY_UNIVERSE|={len(CATEGORY_UNIVERSE)}, "
        f"|GRAPH_CATEGORY_UNIVERSE|={len(GRAPH_CATEGORY_UNIVERSE)}, "
        f"excluded={sorted(excluded)}"
    )


def verify_session(session_dir: Path) -> dict:
    trace_path = find_trace(session_dir)
    if "__" in session_dir.name:
        session_id, package = session_dir.name.split("__", 1)
    else:
        session_id, package = session_dir.name, session_dir.name

    events, report = load_frida_trace(trace_path)
    graph = build_session_graph(events, package)
    x, _, _, cats = graph_to_tensors(graph)

    node_keys = list(graph.nodes.keys())
    forbidden = NON_GRAPH_HOOK_CATEGORIES & set(node_keys)
    kept_in_trace = set(report.distinct_categories)
    trace_forbidden_kept = kept_in_trace & NON_GRAPH_HOOK_CATEGORIES

    inactive = [c for c in GRAPH_CATEGORY_UNIVERSE if graph.nodes[c].act_count == 0]
    inactive_present = all(c in graph.nodes for c in inactive)

    return {
        "session": session_id,
        "package": package,
        "nodes": len(node_keys),
        "ordered_match": node_keys == list(GRAPH_CATEGORY_UNIVERSE),
        "forbidden_nodes": sorted(forbidden),
        "index_map": GRAPH_CATEGORY_INDEX,
        "categories_tensor_order": cats,
        "trace_forbidden_in_kept": sorted(trace_forbidden_kept),
        "events_dropped_category": report.events_dropped_category,
        "inactive_nodes_present": inactive_present,
        "inactive_count": len(inactive),
        "sample_inactive": inactive[:5],
        "feature_rows": x.shape[0],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 22-node graph universe consistency")
    parser.add_argument("--sessions", type=Path, default=DEFAULT_SESSIONS)
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    print("=== STEP 3 — GRAPH UNIVERSE VERIFY ===\n")

    guard_ok, guard_msg = verify_guard()
    print(f"e. Registry guard: {'PASS' if guard_ok else 'FAIL'} — {guard_msg}")
    if not guard_ok:
        return 1

    session_dirs = sorted(p for p in args.sessions.iterdir() if p.is_dir())[: args.count]
    if len(session_dirs) < args.count:
        print(f"FAIL: need {args.count} session dirs, found {len(session_dirs)}")
        return 1

    ref_index: dict[str, int] | None = None
    all_pass = True

    for i, session_dir in enumerate(session_dirs, 1):
        try:
            r = verify_session(session_dir)
        except Exception as exc:
            print(f"\nApp {i} ({session_dir.name}): FAIL — {exc}")
            all_pass = False
            continue

        checks = {
            "a. exactly 22 nodes": r["nodes"] == 22,
            "b. no lifecycle/reflection/navigation nodes": len(r["forbidden_nodes"]) == 0,
            "c. same category→index as reference": ref_index is None or r["index_map"] == ref_index,
            "d. inactive nodes present (zero attrs)": r["inactive_nodes_present"] and r["feature_rows"] == 22,
            "filter: non-graph cats not in kept trace": len(r["trace_forbidden_in_kept"]) == 0,
            "order matches GRAPH_CATEGORY_UNIVERSE": r["ordered_match"],
        }
        if ref_index is None:
            ref_index = r["index_map"]

        failed = [k for k, v in checks.items() if not v]
        status = "PASS" if not failed else "FAIL"
        if failed:
            all_pass = False

        print(f"\nApp {i}: {r['package']} ({r['session']}) — {status}")
        for name, ok in checks.items():
            print(f"  {name}: {'PASS' if ok else 'FAIL'}")
        if failed:
            print(f"  detail: {r}")
        else:
            print(
                f"  dropped_non_graph_events={r['events_dropped_category']}, "
                f"inactive_nodes={r['inactive_count']} (e.g. {r['sample_inactive']})"
            )

    print(f"\nOverall: {'ALL PASS' if all_pass else 'FAILED — see above'}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
