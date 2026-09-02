"""Build ABRG graphs across the working-dataset session corpus."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path

from abrg.graph import ABRGGraph, build_initial_graph, update_graph
from abrg.static import zero_static_report
from abrg.trace import TraceEvent, load_frida_trace
from abrg.windows import WindowMode, split_events


@dataclass
class SessionGraphRecord:
    session_dir: str
    session_id: str
    package: str
    faithfulness: str
    trace_path: str
    events_kept: int
    distinct_categories: list[str]
    n_active_nodes: int
    n_edges: int
    active_nodes: list[str]
    trainable: bool
    gae_eligible: bool
    window_index: int | None = None
    processing_windows_count: int | None = None
    build_error: str | None = None
    graph: ABRGGraph | None = field(default=None, repr=False)


def _snapshot_graph(graph: ABRGGraph) -> ABRGGraph:
    return copy.deepcopy(graph)


def _parse_session_dir(session_dir: Path) -> tuple[str, str]:
    name = session_dir.name
    if "__" in name:
        session_id, package = name.split("__", 1)
        return session_id, package
    return name, name


def _faithfulness(session_dir: Path) -> str:
    idx = session_dir / "SESSION_INDEX.json"
    if idx.is_file():
        return json.loads(idx.read_text(encoding="utf-8")).get("faithfulness_verdict", "?")
    return "?"


def build_session_graph(
    events: list[TraceEvent],
    package: str,
    *,
    k_burst: int | None = None,
    delta_sec: float | None = None,
    lambda_rec: float | None = None,
) -> ABRGGraph:
    """Whole session = one processing window; zero static stub (pinned)."""
    graph = build_initial_graph(static_report=zero_static_report(package))
    kw: dict = {}
    if k_burst is not None:
        kw["k_burst"] = k_burst
    if delta_sec is not None:
        kw["delta_sec"] = delta_sec
    if lambda_rec is not None:
        kw["lambda_rec"] = lambda_rec
    update_graph(graph, events, **kw)
    return graph


def build_session_graph_snapshots(
    events: list[TraceEvent],
    package: str,
    mode: WindowMode = WindowMode.TIME_SEC,
    window_sec: float = 60.0,
    *,
    k_burst: int | None = None,
    delta_sec: float | None = None,
    lambda_rec: float | None = None,
) -> list[tuple[int, ABRGGraph]]:
    """
    §3.6 cumulative snapshots: after each processing window, deep-copy graph state.
    Returns (window_index, cumulative_graph) pairs.
    """
    windows = split_events(events, mode, window_sec)
    graph = build_initial_graph(static_report=zero_static_report(package))
    snapshots: list[tuple[int, ABRGGraph]] = []
    kw: dict = {}
    if k_burst is not None:
        kw["k_burst"] = k_burst
    if delta_sec is not None:
        kw["delta_sec"] = delta_sec
    if lambda_rec is not None:
        kw["lambda_rec"] = lambda_rec
    for window in windows:
        update_graph(graph, window.events, t_now=window.t_end_sec, **kw)
        snapshots.append((window.index, _snapshot_graph(graph)))
    return snapshots


def _record_from_graph(
    session_dir: Path,
    session_id: str,
    package: str,
    verdict: str,
    trace_path: Path,
    rep,
    graph: ABRGGraph,
    window_index: int | None = None,
    processing_windows_count: int | None = None,
) -> SessionGraphRecord:
    active = graph.active_nodes()
    n_active = len(active)
    n_edges = len(graph.edges)
    trainable = n_active >= 2
    gae_eligible = trainable and n_edges >= 1
    return SessionGraphRecord(
        session_dir=session_dir.name,
        session_id=session_id,
        package=package,
        faithfulness=verdict,
        trace_path=str(trace_path),
        events_kept=rep.events_kept,
        distinct_categories=rep.distinct_categories,
        n_active_nodes=n_active,
        n_edges=n_edges,
        active_nodes=active,
        trainable=trainable,
        gae_eligible=gae_eligible,
        window_index=window_index,
        processing_windows_count=processing_windows_count,
        graph=graph,
    )


def load_corpus_sessions(sessions_root: Path) -> list[Path]:
    return sorted(p for p in sessions_root.iterdir() if p.is_dir())


def build_corpus_graphs(
    sessions_root: Path,
    window_mode: WindowMode = WindowMode.WHOLE_SESSION,
    window_sec: float = 60.0,
    snapshots: bool = False,
    *,
    k_burst: int | None = None,
    delta_sec: float | None = None,
    lambda_rec: float | None = None,
) -> list[SessionGraphRecord]:
    """
    Build graphs for all sessions.

    snapshots=False: one final graph per session (whole session or last window only).
    snapshots=True: one cumulative graph snapshot after each processing window.
    """
    edge_kw: dict = {}
    if k_burst is not None:
        edge_kw["k_burst"] = k_burst
    if delta_sec is not None:
        edge_kw["delta_sec"] = delta_sec
    if lambda_rec is not None:
        edge_kw["lambda_rec"] = lambda_rec

    records: list[SessionGraphRecord] = []
    for session_dir in load_corpus_sessions(sessions_root):
        session_id, package = _parse_session_dir(session_dir)
        verdict = _faithfulness(session_dir)
        traces = list(session_dir.glob("*_frida.jsonl"))
        if len(traces) != 1:
            records.append(
                SessionGraphRecord(
                    session_dir=session_dir.name,
                    session_id=session_id,
                    package=package,
                    faithfulness=verdict,
                    trace_path="",
                    events_kept=0,
                    distinct_categories=[],
                    n_active_nodes=0,
                    n_edges=0,
                    active_nodes=[],
                    trainable=False,
                    gae_eligible=False,
                    build_error=f"expected 1 frida trace, got {len(traces)}",
                )
            )
            continue

        trace_path = traces[0]
        try:
            events, rep = load_frida_trace(trace_path)
            if snapshots:
                snaps = build_session_graph_snapshots(
                    events,
                    package,
                    mode=window_mode,
                    window_sec=window_sec,
                    **edge_kw,
                )
                n_windows = len(snaps)
                for w_idx, graph in snaps:
                    records.append(
                        _record_from_graph(
                            session_dir,
                            session_id,
                            package,
                            verdict,
                            trace_path,
                            rep,
                            graph,
                            window_index=w_idx,
                            processing_windows_count=n_windows,
                        )
                    )
            else:
                if window_mode == WindowMode.WHOLE_SESSION:
                    graph = build_session_graph(events, package, **edge_kw)
                else:
                    snaps = build_session_graph_snapshots(
                        events,
                        package,
                        mode=window_mode,
                        window_sec=window_sec,
                        **edge_kw,
                    )
                    graph = snaps[-1][1] if snaps else build_initial_graph(
                        static_report=zero_static_report(package)
                    )
                records.append(
                    _record_from_graph(
                        session_dir, session_id, package, verdict, trace_path, rep, graph
                    )
                )
        except Exception as exc:
            records.append(
                SessionGraphRecord(
                    session_dir=session_dir.name,
                    session_id=session_id,
                    package=package,
                    faithfulness=verdict,
                    trace_path=str(trace_path),
                    events_kept=0,
                    distinct_categories=[],
                    n_active_nodes=0,
                    n_edges=0,
                    active_nodes=[],
                    trainable=False,
                    gae_eligible=False,
                    build_error=str(exc),
                )
            )
    return records
