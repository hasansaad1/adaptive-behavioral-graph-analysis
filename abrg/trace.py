"""Frida trace loading and event filtering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from abrg.registry import GRAPH_CATEGORY_UNIVERSE, CATEGORY_UNIVERSE, DROPPED_CATEGORIES

GRAPH_CATEGORY_INDEX: dict[str, int] = {
    name: i for i, name in enumerate(GRAPH_CATEGORY_UNIVERSE)
}


@dataclass(frozen=True)
class TraceEvent:
    category: str
    api: str
    timestamp_ms: int


@dataclass
class TraceLoadReport:
    path: str
    lines_read: int
    lines_parsed: int
    events_kept: int
    events_dropped_type: int
    events_dropped_category: int
    events_dropped_unknown_category: int
    distinct_categories: list[str]
    category_counts: dict[str, int]


def load_frida_trace(path: Path) -> tuple[list[TraceEvent], TraceLoadReport]:
    """Load Frida JSONL; keep type==event.

    Raw traces may include lifecycle/reflection/navigation (hook collection).
    Those labels are dropped here; kept events map to GRAPH_CATEGORY_UNIVERSE only.
    """
    events: list[TraceEvent] = []
    dropped_type = 0
    dropped_category = 0
    dropped_unknown = 0
    lines_read = 0
    lines_parsed = 0
    category_counts: dict[str, int] = {}

    for raw in path.read_text(encoding="utf-8").splitlines():
        lines_read += 1
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        lines_parsed += 1

        if obj.get("type") != "event":
            dropped_type += 1
            continue

        category = obj.get("category")
        if category is None:
            dropped_unknown += 1
            continue

        if category in DROPPED_CATEGORIES:
            dropped_category += 1
            continue

        if category not in GRAPH_CATEGORY_INDEX:
            if category in CATEGORY_UNIVERSE:
                raise ValueError(
                    f"Event category {category!r} is in hook taxonomy but not in "
                    f"GRAPH_CATEGORY_UNIVERSE — should have been dropped."
                )
            raise ValueError(
                f"Event category {category!r} not in CATEGORY_UNIVERSE — "
                "cannot map to fixed node set (pin #1)."
            )

        ts = obj.get("timestamp")
        if ts is None:
            raise ValueError(f"Event missing timestamp: {obj!r}")

        events.append(
            TraceEvent(
                category=category,
                api=str(obj.get("api", "")),
                timestamp_ms=int(ts),
            )
        )
        category_counts[category] = category_counts.get(category, 0) + 1

    report = TraceLoadReport(
        path=str(path),
        lines_read=lines_read,
        lines_parsed=lines_parsed,
        events_kept=len(events),
        events_dropped_type=dropped_type,
        events_dropped_category=dropped_category,
        events_dropped_unknown_category=dropped_unknown,
        distinct_categories=sorted(category_counts.keys()),
        category_counts=dict(sorted(category_counts.items())),
    )
    return events, report
