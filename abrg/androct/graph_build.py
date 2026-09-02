"""AndroCT sequence-proximity graph update — k-burst only, no time, no recency."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Union

from abrg.config import K_BURST
from abrg.graph import ABRGGraph, EdgeState, UpdateReport, _recompute_sess_fraction
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.trace import TraceEvent

CategoryStream = Union[Sequence[str], Sequence[TraceEvent]]


def assert_universe(graph: ABRGGraph) -> None:
    keys = tuple(sorted(graph.nodes.keys()))
    expected = tuple(sorted(GRAPH_CATEGORY_UNIVERSE))
    if keys != expected:
        raise AssertionError(
            f"GRAPH_CATEGORY_UNIVERSE mismatch: got {keys!r} expected {expected!r}"
        )
    if len(graph.nodes) != 22:
        raise AssertionError(f"expected 22 nodes, got {len(graph.nodes)}")


def assert_recency_unpopulated(graph: ABRGGraph) -> None:
    """Recency channel is undefined on AndroCT — must never be populated."""
    for (u, v), e in graph.edges.items():
        if e.w_rec != 0.0:
            raise AssertionError(f"w_rec populated on edge {u}->{v}: {e.w_rec}")
    for cat, node in graph.nodes.items():
        if node.rec_v != 0.0:
            raise AssertionError(f"rec_v populated on node {cat}: {node.rec_v}")


def update_graph_sequence(
    graph: ABRGGraph,
    window_trace: CategoryStream,
    *,
    k_burst: int = K_BURST,
) -> UpdateReport:
    """
    UpdateGraph for AndroCT: k-sequence proximity only.

    - No timestamps / no δ filter
    - w_cum only (never increments w_rec, never decays)
    - No cross-snapshot edges (caller passes one snapshot's events)
    """
    if not window_trace:
        return UpdateReport(0, 0, 0, 0, 0.0)

    first = window_trace[0]
    if isinstance(first, TraceEvent):
        stream = [ev.category for ev in window_trace]  # type: ignore[union-attr]
    else:
        stream = list(window_trace)  # type: ignore[arg-type]
    touched_edges: set[tuple[str, str]] = set()
    active_in_window: set[str] = set()
    n = len(stream)

    for i in range(n):
        u = stream[i]
        if u not in graph.nodes:
            raise ValueError(f"category {u!r} not in graph universe")
        graph.nodes[u].act_count += 1
        active_in_window.add(u)

        for j in range(i + 1, min(i + k_burst + 1, n)):
            v = stream[j]
            if u == v:
                continue
            key = (u, v)
            if key not in graph.edges:
                graph.edges[key] = EdgeState(
                    w_cum=0.0,
                    w_rec=0.0,
                    t_first=0.0,
                    t_last=0.0,
                    n_sess=0,
                    epoch=graph.version_epoch,
                )
            edge = graph.edges[key]
            edge.w_cum += 1.0
            # intentionally never touch w_rec
            touched_edges.add(key)

    for key in touched_edges:
        graph.edges[key].n_sess += 1

    graph.windows_processed += 1
    for category in active_in_window:
        graph._node_active_windows[category] = graph._node_active_windows.get(category, 0) + 1
    _recompute_sess_fraction(graph)
    # do NOT call _recompute_node_recency — rec_v stays 0

    assert_recency_unpopulated(graph)

    return UpdateReport(
        events_in_window=n,
        active_nodes=len(active_in_window),
        edges_formed=len(graph.edges),
        edges_touched=len(touched_edges),
        t_now_sec=0.0,
    )


def partition_mapped_indices(n_mapped: int, n_parts: int) -> list[tuple[int, int]]:
    """
    Split [0, n_mapped) into n_parts contiguous ranges.
    Each part gets floor(n_mapped/N); remainder goes to earliest parts.
    """
    if n_parts < 1:
        raise ValueError("n_parts must be >= 1")
    if n_mapped < 1:
        return []
    base = n_mapped // n_parts
    rem = n_mapped % n_parts
    ranges: list[tuple[int, int]] = []
    start = 0
    for i in range(n_parts):
        size = base + (1 if i < rem else 0)
        end = start + size
        ranges.append((start, end))
        start = end
    return ranges


@dataclass
class SnapshotSpec:
    snap_idx: int
    start: int
    end: int
