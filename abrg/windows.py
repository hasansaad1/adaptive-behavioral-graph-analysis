"""§3.6 processing-window splitting (separate from edge-formation k/δ)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from abrg.trace import TraceEvent


class WindowMode(str, Enum):
    WHOLE_SESSION = "whole_session"
    TIME_SEC = "time_sec"


@dataclass(frozen=True)
class ProcessingWindow:
    index: int
    events: list[TraceEvent]
    t_start_sec: float
    t_end_sec: float

    @property
    def duration_sec(self) -> float:
        return self.t_end_sec - self.t_start_sec


def split_by_time(events: list[TraceEvent], window_sec: float) -> list[ProcessingWindow]:
    """Split a session into contiguous time buckets (§3.6 processing windows)."""
    if not events:
        return []
    if window_sec <= 0:
        raise ValueError("window_sec must be positive")

    windows: list[ProcessingWindow] = []
    chunk: list[TraceEvent] = []
    chunk_start = events[0].timestamp_ms / 1000.0
    idx = 0

    for ev in events:
        t = ev.timestamp_ms / 1000.0
        if chunk and (t - chunk_start) >= window_sec:
            windows.append(
                ProcessingWindow(
                    index=idx,
                    events=chunk,
                    t_start_sec=chunk_start,
                    t_end_sec=chunk[-1].timestamp_ms / 1000.0,
                )
            )
            idx += 1
            chunk = []
            chunk_start = t
        chunk.append(ev)

    if chunk:
        windows.append(
            ProcessingWindow(
                index=idx,
                events=chunk,
                t_start_sec=chunk_start,
                t_end_sec=chunk[-1].timestamp_ms / 1000.0,
            )
        )
    return windows


def whole_session_window(events: list[TraceEvent]) -> list[ProcessingWindow]:
    if not events:
        return []
    return [
        ProcessingWindow(
            index=0,
            events=events,
            t_start_sec=events[0].timestamp_ms / 1000.0,
            t_end_sec=events[-1].timestamp_ms / 1000.0,
        )
    ]


def split_events(
    events: list[TraceEvent],
    mode: WindowMode,
    window_sec: float,
) -> list[ProcessingWindow]:
    if mode == WindowMode.WHOLE_SESSION:
        return whole_session_window(events)
    if mode == WindowMode.TIME_SEC:
        return split_by_time(events, window_sec)
    raise ValueError(f"unknown window mode: {mode}")
