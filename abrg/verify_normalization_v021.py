#!/usr/bin/env python3
"""Verify v0.2.1 tensor normalization (stored raw vs GAE-fed normalized)."""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict

import numpy as np
import torch

from abrg.corpus import build_session_graph
from abrg.dataset_paths import current_sessions_dir
from abrg.features import (
    feature_vector_labels,
    graph_to_tensors,
    node_feature_dim,
    snapshot_raw_w_cum,
)
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.trace import load_frida_trace

TOL = 1e-5


def load_v2_graphs() -> list[tuple[str, object]]:
    sessions = current_sessions_dir()
    graphs: list[tuple[str, object]] = []
    for session_dir in sorted(p for p in sessions.iterdir() if p.is_dir()):
        traces = list(session_dir.glob("*_frida.jsonl"))
        if len(traces) != 1:
            continue
        package = session_dir.name.split("__", 1)[-1] if "__" in session_dir.name else session_dir.name
        events, _ = load_frida_trace(traces[0])
        if not events:
            continue
        g = build_session_graph(events, package)
        graphs.append((session_dir.name, g))
    return graphs


def outgoing_raw_w_cum(graph, cat: str) -> list[tuple[str, float]]:
    return sorted(
        ((v, float(e.w_cum)) for (u, v), e in graph.edges.items() if u == cat and e.w_cum > 0),
        key=lambda t: -t[1],
    )


def verify_graph(name: str, graph) -> dict:
    raw_before = snapshot_raw_w_cum(graph)
    x, edge_index, edge_weight, cats = graph_to_tensors(graph)
    raw_after = snapshot_raw_w_cum(graph)

    # (d) stored raw unchanged
    if raw_before != raw_after:
        raise AssertionError(f"{name}: w_cum mutated by tensorization")

    x_np = x.numpy()
    ew_np = edge_weight.numpy() if edge_weight.numel() else np.array([], dtype=np.float32)

    if not np.isfinite(x_np).all():
        raise AssertionError(f"{name}: non-finite values in node tensor")
    if ew_np.size and not np.isfinite(ew_np).all():
        raise AssertionError(f"{name}: non-finite values in edge_weight")

    # (c) act fractions sum to 1 or 0
    act_col = feature_vector_labels().index("act_v_frac")
    act_sum = float(x_np[:, act_col].sum())
    total_events = sum(graph.nodes[c].act_count for c in GRAPH_CATEGORY_UNIVERSE)
    if total_events == 0:
        if act_sum > TOL:
            raise AssertionError(f"{name}: empty graph act fractions sum={act_sum}")
    else:
        if abs(act_sum - 1.0) > TOL:
            raise AssertionError(f"{name}: act fractions sum={act_sum}, expected 1.0")

    # per-source outgoing totals (raw vs normalized)
    out_raw: dict[str, float] = defaultdict(float)
    for (u, v), w in raw_before.items():
        if w > 0:
            out_raw[u] += w

    # (a) nodes with outgoing edges: normalized weights sum to 1
    nodes_checked = 0
    if edge_index.numel():
        src = edge_index[0].numpy()
        for ui in np.unique(src):
            mask = src == ui
            s = float(ew_np[mask].sum())
            cat = cats[ui]
            if out_raw.get(cat, 0.0) > 0:
                nodes_checked += 1
                if abs(s - 1.0) > TOL:
                    raise AssertionError(
                        f"{name}: node {cat} normalized outgoing sum={s}, expected 1.0"
                    )

    # (b) terminal nodes: no outgoing edges in tensor; no nan/inf already checked
    terminal = [
        c for c in GRAPH_CATEGORY_UNIVERSE
        if out_raw.get(c, 0.0) <= 0.0
    ]
    if edge_index.numel():
        src_set = set(edge_index[0].tolist())
        for cat in terminal:
            ui = cats.index(cat)
            if ui in src_set:
                mask = edge_index[0].numpy() == ui
                if float(ew_np[mask].sum()) != 0.0:
                    raise AssertionError(f"{name}: terminal node {cat} has non-zero out-weight")

    rec_vals = [graph.nodes[c].rec_v for c in GRAPH_CATEGORY_UNIVERSE]

    return {
        "name": name,
        "nodes_checked": nodes_checked,
        "terminal_nodes": len(terminal),
        "act_sum": act_sum,
        "total_events": total_events,
        "rec_vals": rec_vals,
        "graph": graph,
        "edge_index": edge_index,
        "edge_weight": edge_weight,
        "cats": cats,
        "raw_before": raw_before,
    }


def pick_example(result: dict) -> dict | None:
    graph = result["graph"]
    for cat in GRAPH_CATEGORY_UNIVERSE:
        raw_edges = outgoing_raw_w_cum(graph, cat)
        if len(raw_edges) >= 2:
            ui = result["cats"].index(cat)
            ei, ew = result["edge_index"], result["edge_weight"]
            norm_edges: list[tuple[str, float]] = []
            if ei.numel():
                src = ei[0].numpy()
                dst = ei[1].numpy()
                for j in range(len(ew)):
                    if src[j] == ui:
                        norm_edges.append((result["cats"][dst[j]], float(ew[j].item())))
            norm_edges.sort(key=lambda t: -t[1])
            return {
                "session": result["name"],
                "source": cat,
                "raw_outgoing": raw_edges,
                "normalized_outgoing": norm_edges,
                "raw_total": sum(w for _, w in raw_edges),
            }
    return None


def main() -> int:
    print("=== v0.2.1 NORMALIZATION VERIFY ===\n")
    graphs = load_v2_graphs()
    print(f"Loaded {len(graphs)} v2 session graphs from {current_sessions_dir()}\n")

    if not graphs:
        print("FAIL: no graphs loaded")
        return 1

    results: list[dict] = []
    for name, g in graphs:
        results.append(verify_graph(name, g))

    total_nodes_checked = sum(r["nodes_checked"] for r in results)
    print(f"(a) Outgoing-normalized nodes checked: {total_nodes_checked} (across {len(results)} graphs)")
    print("    PASS — each source with outgoing edges sums to 1.0 (±{:.0e})".format(TOL))

    total_terminal = sum(r["terminal_nodes"] for r in results)
    print(f"\n(b) Terminal nodes (no raw outgoing w_cum): {total_terminal}")
    print("    PASS — no non-zero normalized out-weight; no NaN/inf in tensors")

    print(f"\n(c) act_v_frac sums to 1.0 (or 0 if empty): PASS ({len(results)} graphs)")

    print("\n(d) Raw w_cum unchanged after graph_to_tensors: PASS (all graphs)")

    example = None
    for r in sorted(results, key=lambda x: -x["total_events"]):
        example = pick_example(r)
        if example:
            break
    print("\n(e) Example (raw w_cum vs normalized transition probability):")
    if example:
        print(f"    Session: {example['session']}")
        print(f"    Source node: {example['source']}")
        print(f"    Raw outgoing total w_cum: {example['raw_total']:.1f}")
        print("    Side-by-side:")
        for (v, raw_w), (v2, norm_p) in zip(
            example["raw_outgoing"],
            example["normalized_outgoing"],
            strict=True,
        ):
            assert v == v2
            print(f"      {example['source']} → {v}:  raw={raw_w:.1f}  →  P={norm_p:.6f}")
    else:
        print("    (no multi-edge source found)")

    all_rec: list[float] = []
    for r in results:
        all_rec.extend(r["rec_vals"])
    all_rec_sorted = sorted(all_rec)
    n = len(all_rec_sorted)
    p90 = all_rec_sorted[int(0.9 * (n - 1))] if n else float("nan")

    print("\n(5) w_rec / rec_v distribution across v2 graphs (report only):")
    print(f"    samples: {n} (22 nodes × {len(results)} graphs)")
    print(f"    min:     {min(all_rec_sorted) if n else 0:.4g}")
    print(f"    median:  {statistics.median(all_rec_sorted) if n else 0:.4g}")
    print(f"    p90:     {p90:.4g}")
    print(f"    max:     {max(all_rec_sorted) if n else 0:.4g}")

    labels = feature_vector_labels()
    dim = node_feature_dim()
    print(f"\n(6) Tensor layout: {dim} columns (unchanged count)")
    print("    Node feature columns:")
    for i, lab in enumerate(labels):
        layer = "static" if lab in {
            "s_v", "declared_v", "reach_v", "epoch_v"
        } or lab.startswith("gate_v") else "dynamic"
        fed = lab
        if lab == "act_v_frac":
            fed += " (v0.2.1: act_count / total events; log1p superseded)"
        elif lab == "rec_v":
            fed += " (fed as-is; range-check only)"
        print(f"      [{i}] {lab:12} {layer:8} {fed}")
    print("    Edge tensor: edge_weight = transition probability per source node (v0.2.1)")
    print("    Stored graph: E[u][v].w_cum remains raw (graph.py untouched)")

    print("\n=== ALL CHECKS PASSED ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
