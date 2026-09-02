"""Run §3.6 windowed cumulative graph updates."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from abrg.graph import ABRGGraph, UpdateReport, build_initial_graph, update_graph
from abrg.trace import TraceEvent
from abrg.windows import ProcessingWindow, WindowMode, split_events


@dataclass
class WindowStepReport:
    window_index: int
    events_in_window: int
    t_start_sec: float
    t_end_sec: float
    update: UpdateReport
    edges_after: int
    active_nodes_after: int
    snapshot_w_cum_sum: float
    snapshot_w_rec_sum: float


@dataclass
class WindowedSessionResult:
    graph: ABRGGraph
    windows: list[ProcessingWindow]
    steps: list[WindowStepReport]


def run_windowed_session(
    events: list[TraceEvent],
    mode: WindowMode = WindowMode.TIME_SEC,
    window_sec: float = 60.0,
    apk_path: Path | None = None,
    static_report: StaticReport | None = None,
) -> WindowedSessionResult:
    """
    §3.6: for each processing window, UpdateGraph then emit cumulative state.
    Returns the final cumulative graph and per-window reports.
    """
    windows = split_events(events, mode, window_sec)
    graph = build_initial_graph(apk_path=apk_path, static_report=static_report)
    steps: list[WindowStepReport] = []

    for window in windows:
        t_now = window.t_end_sec
        report = update_graph(graph, window.events, t_now=t_now)
        w_cum_sum = sum(e.w_cum for e in graph.edges.values())
        w_rec_sum = sum(e.w_rec for e in graph.edges.values())
        steps.append(
            WindowStepReport(
                window_index=window.index,
                events_in_window=len(window.events),
                t_start_sec=window.t_start_sec,
                t_end_sec=window.t_end_sec,
                update=report,
                edges_after=len(graph.edges),
                active_nodes_after=len(graph.active_nodes()),
                snapshot_w_cum_sum=w_cum_sum,
                snapshot_w_rec_sum=w_rec_sum,
            )
        )

    return WindowedSessionResult(graph=graph, windows=windows, steps=steps)


def snapshot_graph(graph: ABRGGraph) -> ABRGGraph:
    """Deep copy for trajectory storage without re-running updates."""
    return copy.deepcopy(graph)
