#!/usr/bin/env python3
"""
ABRG v0.2 pilot: dynamic graph + optional multi-window processing + GAE smoke test.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("LOGURU_LEVEL", "ERROR")
logging.getLogger("androguard").setLevel(logging.ERROR)

from abrg.autoencoder import build_gae, reconstruction_sanity, train_gae
from abrg.config import (
    DEFAULT_WINDOW_SEC,
    GAE_EPOCHS,
    GAE_HIDDEN_DIM,
    GAE_LR,
    LAMBDA_REC,
)
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.session import run_windowed_session
from abrg.static import StaticReport, analyze_apk_static
from abrg.api_category_map import apk_path_from_session_dir
from abrg.dataset_paths import default_demo_frida_trace, find_frida_trace
from abrg.trace import load_frida_trace
from abrg.windows import WindowMode

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSION = default_demo_frida_trace()
MIN_MEANINGFUL_CATEGORIES = 3


def report_step_a(trace_path: Path) -> tuple[list, dict]:
    events, load_report = load_frida_trace(trace_path)
    data = {
        "step": "A",
        "trace_path": str(trace_path),
        "events_kept": load_report.events_kept,
        "distinct_categories": load_report.distinct_categories,
        "category_counts": load_report.category_counts,
        "lines_read": load_report.lines_read,
        "dropped_non_event": load_report.events_dropped_type,
        "dropped_low_signal_category": load_report.events_dropped_category,
    }
    if len(load_report.distinct_categories) < MIN_MEANINGFUL_CATEGORIES:
        raise RuntimeError(
            f"Only {len(load_report.distinct_categories)} meaningful categories after filter "
            f"(need ≥{MIN_MEANINGFUL_CATEGORIES}): {load_report.distinct_categories}"
        )
    return events, data


def report_step_b(apk_path: Path) -> tuple[StaticReport, dict]:
    static_report = analyze_apk_static(apk_path)
    declared = [c for c in GRAPH_CATEGORY_UNIVERSE if static_report.nodes[c].declared_v > 0]
    gated = [c for c in GRAPH_CATEGORY_UNIVERSE if any(static_report.nodes[c].gate_v)]
    data = {
        "step": "B",
        "apk_path": str(apk_path),
        "package_name": static_report.package_name,
        "permissions_count": len(static_report.permissions),
        "nodes_in_universe": len(GRAPH_CATEGORY_UNIVERSE),
        "edges": 0,
        "static_layer": "androguard",
        "feature_dim": node_feature_dim(),
        "declared_categories": declared,
        "permission_gated_categories": gated,
        "static_summary": {
            cat: {
                "s_v": static_report.nodes[cat].s_v,
                "declared_v": static_report.nodes[cat].declared_v,
                "gate_v": static_report.nodes[cat].gate_v,
                "reach_v": static_report.nodes[cat].reach_v,
            }
            for cat in sorted(set(declared) | set(gated))
        },
    }
    return static_report, data


def report_step_c(
    events: list,
    window_mode: WindowMode,
    window_sec: float,
    apk_path: Path,
    static_report: StaticReport,
) -> tuple:
    result = run_windowed_session(
        events,
        mode=window_mode,
        window_sec=window_sec,
        static_report=static_report,
    )
    graph = result.graph

    window_rows = [
        {
            "window": s.window_index,
            "events": s.events_in_window,
            "t_start": round(s.t_start_sec, 3),
            "t_end": round(s.t_end_sec, 3),
            "edges_touched": s.update.edges_touched,
            "edges_total": s.edges_after,
            "active_nodes": s.active_nodes_after,
            "sum_w_cum": round(s.snapshot_w_cum_sum, 1),
            "sum_w_rec": round(s.snapshot_w_rec_sum, 1),
        }
        for s in result.steps
    ]

    edge_list = [
        {
            "u": u,
            "v": v,
            "w_cum": e.w_cum,
            "w_rec": e.w_rec,
            "w_rec_ratio": round(e.w_rec / e.w_cum, 4) if e.w_cum > 0 else 0.0,
            "t_first": e.t_first,
            "t_last": e.t_last,
            "n_sess": e.n_sess,
        }
        for u, v, e in graph.iter_edges()
    ]

    data = {
        "step": "C",
        "processing_window_mode": window_mode.value,
        "processing_window_sec": window_sec if window_mode == WindowMode.TIME_SEC else None,
        "processing_windows_count": len(result.windows),
        "windows_processed_total": graph.windows_processed,
        "lambda_rec_per_sec": LAMBDA_REC,
        "final_active_nodes": graph.active_nodes(),
        "final_edges_formed": len(graph.edges),
        "window_trajectory": window_rows,
        "edge_list": edge_list,
    }
    return graph, data


def report_steps_d_e_f(graph) -> dict:
    x, edge_index, edge_weight, categories = graph_to_tensors(graph)
    data_d = {
        "step": "D",
        "num_nodes": len(categories),
        "feature_dim": int(x.shape[1]),
        "num_directed_edges": int(edge_index.shape[1]),
        "adjacency": "raw_w_cum_edge_weights",
        "normalization": "none_D7_deferred",
        "static_features": "androguard_s_v_declared_gate_reach_epoch",
    }

    if edge_index.shape[1] == 0:
        raise RuntimeError("No edges formed — cannot train GAE.")

    model = build_gae(in_channels=x.shape[1], hidden_channels=GAE_HIDDEN_DIM)
    losses, final_loss = train_gae(model, x, edge_index, epochs=GAE_EPOCHS, lr=GAE_LR)
    sanity = reconstruction_sanity(model, x, edge_index, edge_weight)

    n = len(losses)
    chunk = max(1, n // 5)
    loss_start = sum(losses[:chunk]) / chunk
    loss_end = sum(losses[-chunk:]) / chunk
    converged = loss_end < loss_start and loss_end < losses[0]

    data_e = {
        "step": "E",
        "model": "GAE_GCN_encoder",
        "hidden_dim": GAE_HIDDEN_DIM,
        "epochs": GAE_EPOCHS,
        "lr": GAE_LR,
        "loss_first_epoch": losses[0],
        "loss_final": final_loss,
        "loss_curve": losses,
    }
    data_f = {
        "step": "F",
        "converged_heuristic": converged,
        "loss_mean_first_20pct": loss_start,
        "loss_mean_last_20pct": loss_end,
        "final_reconstruction_loss": final_loss,
        "sanity": sanity,
    }
    return {"D": data_d, "E": data_e, "F": data_f}


def write_summary(path: Path, reports: dict) -> None:
    c = reports["C"]
    node_sess = reports.get("node_sess", {})
    sess_parts = ", ".join(f"{n}={node_sess.get(n, '?')}" for n in c["final_active_nodes"])
    summary = (
        f"ABRG v0.2 pilot: {reports['A']['events_kept']} events, "
        f"{len(reports['A']['distinct_categories'])} categories. "
        f"Processing: {c['processing_window_mode']} "
        f"({c['processing_windows_count']} windows). "
        f"Final graph: {c['final_edges_formed']} directed edges, "
        f"{len(c['final_active_nodes'])} active nodes. "
        f"sess_v on active nodes: {sess_parts}. "
        f"GAE final loss={reports['E']['loss_final']:.6f}. "
        f"Smoke test only — not detection."
    )
    path.write_text(summary + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="ABRG v0.2 pilot smoke test")
    parser.add_argument("--trace", type=Path, default=DEFAULT_SESSION)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "abrg" / "output" / "pilot_protonvpn_multiwindow",
    )
    parser.add_argument(
        "--window-mode",
        choices=[m.value for m in WindowMode],
        default=WindowMode.TIME_SEC.value,
        help="whole_session or time_sec (§3.6 processing window)",
    )
    parser.add_argument(
        "--apk",
        type=Path,
        default=None,
        help="APK path (default: read from session *_dynamic_metadata.json)",
    )
    parser.add_argument(
        "--window-sec",
        type=float,
        default=DEFAULT_WINDOW_SEC,
        help="Processing window size in seconds when mode=time_sec",
    )
    args = parser.parse_args()

    trace_path = args.trace.resolve()
    if not trace_path.is_file():
        if trace_path.is_dir():
            trace_path = find_frida_trace(trace_path)
        else:
            print(f"Trace not found: {trace_path}", file=sys.stderr)
            return 1

    apk_path = args.apk
    if apk_path is None:
        apk_path = apk_path_from_session_dir(trace_path.parent)
    if apk_path is None or not Path(apk_path).is_file():
        print(
            f"APK not found: {apk_path}. Pass --apk or ensure "
            f"*_dynamic_metadata.json has a valid apk_path.",
            file=sys.stderr,
        )
        return 1
    apk_path = Path(apk_path).resolve()

    window_mode = WindowMode(args.window_mode)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports: dict = {}

    print("=== Step A: Load & filter trace ===")
    events, reports["A"] = report_step_a(trace_path)
    print(json.dumps(reports["A"], indent=2))

    print("\n=== Step B: BuildInitialGraph (Androguard static) ===")
    static_report, reports["B"] = report_step_b(apk_path)
    print(json.dumps({k: v for k, v in reports["B"].items() if k != "static_summary"}, indent=2))
    print("  static_summary (declared/gated categories):")
    for cat, attrs in reports["B"]["static_summary"].items():
        print(f"    {cat}: s_v={attrs['s_v']}, declared={attrs['declared_v']}, "
              f"gate={attrs['gate_v']}, reach={attrs['reach_v']}")

    print(f"\n=== Step C: UpdateGraph ({window_mode.value}, "
          f"{args.window_sec}s windows) ===")
    graph, reports["C"] = report_step_c(
        events, window_mode, args.window_sec, apk_path, static_report
    )
    reports["node_sess"] = {c: graph.nodes[c].sess_v for c in graph.active_nodes()}

    print(json.dumps({k: v for k, v in reports["C"].items() if k != "edge_list"}, indent=2))
    print("\n  window_trajectory:")
    for row in reports["C"]["window_trajectory"]:
        print(
            f"    w{row['window']:2d}: {row['events']:4d} events, "
            f"touched={row['edges_touched']:3d}, edges_total={row['edges_total']:2d}, "
            f"sum_w_cum={row['sum_w_cum']:8.1f}, sum_w_rec={row['sum_w_rec']:8.1f}"
        )
    print(f"\n  final edge_list ({len(reports['C']['edge_list'])} edges):")
    for e in reports["C"]["edge_list"]:
        print(
            f"    {e['u']} → {e['v']}: w_cum={e['w_cum']}, w_rec={e['w_rec']}, "
            f"rec/cum={e['w_rec_ratio']}, n_sess={e['n_sess']}"
        )
    print("\n  active node sess_v (fraction of windows active):")
    for cat in reports["C"]["final_active_nodes"]:
        n = graph.nodes[cat]
        print(f"    {cat}: sess_v={n.sess_v:.3f}, act={n.act_count}, rec_v={n.rec_v:.1f}")

    print("\n=== Steps D–F: Features, GAE train, evaluate ===")
    reports.update(report_steps_d_e_f(graph))
    print(json.dumps(reports["D"], indent=2))
    print(json.dumps({k: v for k, v in reports["E"].items() if k != "loss_curve"}, indent=2))
    print(
        f"  loss_curve: first={reports['E']['loss_first_epoch']:.6f} "
        f"final={reports['E']['loss_final']:.6f}"
    )
    print(json.dumps(reports["F"], indent=2))

    report_path = args.output_dir / "pilot_report.json"
    report_path.write_text(json.dumps(reports, indent=2), encoding="utf-8")
    write_summary(args.output_dir / "pilot_summary.txt", reports)

    print(f"\nWrote {report_path}")
    print(f"Wrote {args.output_dir / 'pilot_summary.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
