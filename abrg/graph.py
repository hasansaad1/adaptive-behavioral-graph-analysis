"""ABRG graph schema, BuildInitialGraph, UpdateGraph (v0.2 pilot)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from abrg.config import DELTA_SEC, K_BURST, LAMBDA_REC
from abrg.registry import GRAPH_CATEGORY_UNIVERSE, GATE_V_DIM
from abrg.static import StaticReport, analyze_apk_static
from abrg.trace import TraceEvent


@dataclass
class NodeState:
    category: str
    # Static layer — Androguard (BuildInitialGraph §3.1)
    s_v: float = 0.0
    declared_v: float = 0.0
    gate_v: list[float] = field(default_factory=lambda: [0.0] * GATE_V_DIM)
    reach_v: float = 0.0
    epoch_v: float = 0.0
    # Dynamic layer
    act_count: int = 0
    sess_v: float = 0.0
    rec_v: float = 0.0


@dataclass
class EdgeState:
    w_cum: float = 0.0
    w_rec: float = 0.0
    t_first: float = 0.0
    t_last: float = 0.0
    n_sess: int = 0
    epoch: int = 0


@dataclass
class ABRGGraph:
    version_epoch: int = 0
    nodes: dict[str, NodeState] = field(default_factory=dict)
    edges: dict[tuple[str, str], EdgeState] = field(default_factory=dict)
    windows_processed: int = 0
    _node_active_windows: dict[str, int] = field(default_factory=dict)

    def active_nodes(self) -> list[str]:
        return [c for c, n in self.nodes.items() if n.act_count > 0]

    def iter_edges(self) -> Iterator[tuple[str, str, EdgeState]]:
        for (u, v), e in sorted(self.edges.items()):
            yield u, v, e


def build_initial_graph(
    apk_path: Path | None = None,
    static_report: StaticReport | None = None,
) -> ABRGGraph:
    """§3.1 BuildInitialGraph — fixed universe, static from Androguard, no edges."""
    if static_report is None:
        if apk_path is None:
            raise ValueError("build_initial_graph requires apk_path or static_report")
        static_report = analyze_apk_static(apk_path)

    graph = ABRGGraph(version_epoch=0)
    for category in GRAPH_CATEGORY_UNIVERSE:
        src = static_report.nodes[category]
        graph.nodes[category] = NodeState(
            category=category,
            s_v=src.s_v,
            declared_v=src.declared_v,
            gate_v=list(src.gate_v),
            reach_v=src.reach_v,
            epoch_v=src.epoch_v,
        )
    return graph


def _decay_recency_edges(
    graph: ABRGGraph,
    t_now_sec: float,
    *,
    lambda_rec: float = LAMBDA_REC,
) -> None:
    """§3.2 step 0 — decay w_rec only; w_cum never decays."""
    for edge in graph.edges.values():
        edge.w_rec *= math.exp(-lambda_rec * (t_now_sec - edge.t_last))


def _recompute_node_recency(graph: ABRGGraph) -> None:
    for node in graph.nodes.values():
        node.rec_v = 0.0
    for (u, v), edge in graph.edges.items():
        graph.nodes[u].rec_v += edge.w_rec
        graph.nodes[v].rec_v += edge.w_rec


@dataclass
class UpdateReport:
    events_in_window: int
    active_nodes: int
    edges_formed: int
    edges_touched: int
    t_now_sec: float


def _recompute_sess_fraction(graph: ABRGGraph) -> None:
    """§3.2 step 3 — fraction of processing windows in which category was active."""
    total = graph.windows_processed
    if total == 0:
        return
    for category in GRAPH_CATEGORY_UNIVERSE:
        active = graph._node_active_windows.get(category, 0)
        graph.nodes[category].sess_v = active / total


def update_graph(
    graph: ABRGGraph,
    window_trace: list[TraceEvent],
    t_now: float | None = None,
    *,
    k_burst: int = K_BURST,
    delta_sec: float = DELTA_SEC,
    lambda_rec: float = LAMBDA_REC,
) -> UpdateReport:
    """
    §3.2 UpdateGraph — one processing window.

    t_now: window boundary time in seconds (§3.2). Defaults to last event timestamp.
    k_burst / delta_sec / lambda_rec default to pinned config (override for one-axis runs).
    """
    if not window_trace:
        return UpdateReport(0, 0, 0, 0, 0.0)

    t_now_sec = t_now if t_now is not None else window_trace[-1].timestamp_ms / 1000.0
    _decay_recency_edges(graph, t_now_sec, lambda_rec=lambda_rec)

    stream = [(ev.category, ev.timestamp_ms / 1000.0) for ev in window_trace]
    touched_edges: set[tuple[str, str]] = set()
    active_in_window: set[str] = set()

    n = len(stream)
    delta_limit = delta_sec

    for i in range(n):
        u, t_u = stream[i]
        graph.nodes[u].act_count += 1
        active_in_window.add(u)

        for j in range(i + 1, min(i + k_burst + 1, n)):
            v, t_v = stream[j]
            if t_v - t_u > delta_limit:
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
            edge = graph.edges[key]
            edge.w_cum += 1.0
            edge.w_rec += 1.0
            edge.t_last = t_v
            touched_edges.add(key)

    for key in touched_edges:
        graph.edges[key].n_sess += 1

    graph.windows_processed += 1
    for category in active_in_window:
        graph._node_active_windows[category] = graph._node_active_windows.get(category, 0) + 1
    _recompute_sess_fraction(graph)

    _recompute_node_recency(graph)

    return UpdateReport(
        events_in_window=len(window_trace),
        active_nodes=len(active_in_window),
        edges_formed=len(graph.edges),
        edges_touched=len(touched_edges),
        t_now_sec=t_now_sec,
    )
