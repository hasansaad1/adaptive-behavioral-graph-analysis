"""Sequence-proximity graphs via the AndroCT builder (read-only import)."""

from __future__ import annotations

from abrg.androct.graph_build import (
    assert_recency_unpopulated,
    assert_universe,
    update_graph_sequence,
)
from abrg.config import K_BURST
from abrg.graph import ABRGGraph, build_initial_graph
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.static import zero_static_report
from abrg.trace import TraceEvent

from abrg.chapter_b.config import K_BURST_PIN, POSSIBLE_EDGES


def graph_from_categories(
    categories: list[str],
    *,
    package: str = "",
    k_burst: int = K_BURST_PIN,
) -> ABRGGraph:
    """AndroCT path: k-burst only, w_cum, recency asserted empty. Zero static stub."""
    assert k_burst == K_BURST
    graph = build_initial_graph(static_report=zero_static_report(package))
    assert_universe(graph)
    if categories:
        update_graph_sequence(graph, categories, k_burst=k_burst)
    assert_recency_unpopulated(graph)
    assert len(graph.nodes) == len(GRAPH_CATEGORY_UNIVERSE)
    return graph


def graph_from_events(events: list[TraceEvent], *, package: str = "") -> ABRGGraph:
    return graph_from_categories([e.category for e in events], package=package)


def topology(graph: ABRGGraph) -> tuple[int, int, float]:
    """Same formulas as abrg.androct.run2_corpus._build_tensor."""
    n_active = len(graph.active_nodes())
    n_edges = sum(1 for _ in graph.iter_edges())
    density = n_edges / POSSIBLE_EDGES if POSSIBLE_EDGES else 0.0
    return n_active, n_edges, density
