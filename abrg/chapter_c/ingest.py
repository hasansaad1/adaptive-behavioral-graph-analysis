"""Stage 0 — ingest and verify v2_extended export."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from abrg.chapter_c.config import (
    EXPORT_ROOT,
    MIN_APPS_WITH_GE5,
    MIN_SESSIONS_FOR_CURVE,
)
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.trace import load_frida_trace


@dataclass
class SessionMeta:
    app_id: str
    session_id: str
    export_dir_name: str
    session_index_within_app: int
    batch: str
    reference_tier_pass: bool
    failure_reason: str | None
    gae_eligible: bool
    rel_dir: str
    start_timestamp: str | None
    start_timestamp_ms: int | None
    events_path: str
    metadata_path: str
    source_meta_path: str | None
    timestamps_ok: bool
    timestamp_exclude_reason: str | None = None
    usable: bool = False


@dataclass
class Stage0Report:
    verify_exit_code: int
    verify_ok: bool
    n_sessions_index: int
    n_pass: int
    n_fail_reference: int
    batch_pass: dict[str, int]
    batch_fail: dict[str, int]
    n_apps_pass: int
    per_app_pass_counts: dict[str, int]
    n_apps_ge5_usable: int
    gate_apps_ge5: bool
    n_nodes_universe: int
    session_index_contiguous: bool
    noncontiguous_apps: list[str]
    timestamp_exclusions: list[dict[str, str]]
    sessions: list[SessionMeta] = field(default_factory=list, repr=False)

    def to_jsonable(self) -> dict[str, Any]:
        d = asdict(self)
        d["sessions"] = [asdict(s) for s in self.sessions]
        return d


def run_verify_export(export_root: Path = EXPORT_ROOT) -> int:
    script = export_root / "verify_export.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(export_root),
        capture_output=True,
        text=True,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    return int(proc.returncode)


def _check_event_timestamps(events_path: Path) -> tuple[bool, str | None]:
    prev: int | None = None
    n_event = 0
    with events_path.open(encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "event":
                continue
            n_event += 1
            if "timestamp" not in obj or obj["timestamp"] is None:
                return False, f"missing_timestamp_line_{lineno}"
            ts = int(obj["timestamp"])
            if prev is not None and ts < prev:
                return False, f"non_monotonic_line_{lineno}_{ts}_lt_{prev}"
            prev = ts
    if n_event == 0:
        return False, "no_parseable_events"
    # Also ensure load_frida_trace can obtain ≥1 kept event with timestamps.
    try:
        events, _ = load_frida_trace(events_path)
    except Exception as exc:  # noqa: BLE001
        return False, f"load_frida_trace_error:{exc}"
    if not events:
        return False, "zero_mapped_events_after_filter"
    for i in range(1, len(events)):
        if events[i].timestamp_ms < events[i - 1].timestamp_ms:
            return False, "mapped_events_non_monotonic"
    return True, None


def load_stage0(export_root: Path = EXPORT_ROOT) -> Stage0Report:
    assert len(GRAPH_CATEGORY_UNIVERSE) == 22, "fixed 22-node universe required"
    exit_code = run_verify_export(export_root)
    if exit_code != 0:
        return Stage0Report(
            verify_exit_code=exit_code,
            verify_ok=False,
            n_sessions_index=0,
            n_pass=0,
            n_fail_reference=0,
            batch_pass={},
            batch_fail={},
            n_apps_pass=0,
            per_app_pass_counts={},
            n_apps_ge5_usable=0,
            gate_apps_ge5=False,
            n_nodes_universe=len(GRAPH_CATEGORY_UNIVERSE),
            session_index_contiguous=False,
            noncontiguous_apps=[],
            timestamp_exclusions=[],
            sessions=[],
        )

    index_path = export_root / "sessions_index.jsonl"
    index_rows = [
        json.loads(l)
        for l in index_path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]

    by_app_indices: dict[str, list[int]] = defaultdict(list)
    for row in index_rows:
        by_app_indices[row["app_id"]].append(int(row["session_index_within_app"]))
    noncontiguous: list[str] = []
    for app, idxs in by_app_indices.items():
        s = sorted(idxs)
        if s != list(range(1, len(s) + 1)):
            noncontiguous.append(app)

    sessions: list[SessionMeta] = []
    ts_excl: list[dict[str, str]] = []
    for row in index_rows:
        rel = row["rel_dir"]
        meta_path = export_root / rel / "metadata.json"
        events_path = export_root / rel / "events.jsonl"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ok, reason = _check_event_timestamps(events_path)
        if not ok:
            ts_excl.append(
                {
                    "app_id": row["app_id"],
                    "export_dir_name": row.get("export_dir_name", ""),
                    "rel_dir": rel,
                    "reason": reason or "unknown",
                }
            )
        sm = SessionMeta(
            app_id=row["app_id"],
            session_id=row["session_id"],
            export_dir_name=row.get("export_dir_name", meta.get("export_dir_name", "")),
            session_index_within_app=int(row["session_index_within_app"]),
            batch=row["batch"],
            reference_tier_pass=bool(row["reference_tier_pass"]),
            failure_reason=row.get("failure_reason"),
            gae_eligible=bool(row.get("gae_eligible", meta.get("gae_eligible", False))),
            rel_dir=rel,
            start_timestamp=meta.get("start_timestamp"),
            start_timestamp_ms=meta.get("start_timestamp_ms"),
            events_path=str(events_path),
            metadata_path=str(meta_path),
            source_meta_path=meta.get("source_meta_path"),
            timestamps_ok=ok,
            timestamp_exclude_reason=reason,
            usable=bool(row["reference_tier_pass"]) and ok,
        )
        sessions.append(sm)

    pass_usable = [s for s in sessions if s.usable]
    fail_ref = [s for s in sessions if not s.reference_tier_pass]
    batch_pass = Counter(s.batch for s in pass_usable)
    batch_fail = Counter(s.batch for s in fail_ref)
    per_app = Counter(s.app_id for s in pass_usable)
    n_ge5 = sum(1 for _, c in per_app.items() if c >= MIN_SESSIONS_FOR_CURVE)

    return Stage0Report(
        verify_exit_code=exit_code,
        verify_ok=True,
        n_sessions_index=len(sessions),
        n_pass=len(pass_usable),
        n_fail_reference=len(fail_ref),
        batch_pass=dict(sorted(batch_pass.items())),
        batch_fail=dict(sorted(batch_fail.items())),
        n_apps_pass=len(per_app),
        per_app_pass_counts=dict(sorted(per_app.items())),
        n_apps_ge5_usable=n_ge5,
        gate_apps_ge5=n_ge5 >= MIN_APPS_WITH_GE5,
        n_nodes_universe=len(GRAPH_CATEGORY_UNIVERSE),
        session_index_contiguous=len(noncontiguous) == 0,
        noncontiguous_apps=sorted(noncontiguous),
        timestamp_exclusions=ts_excl,
        sessions=sessions,
    )


def convergence_apps(report: Stage0Report) -> list[str]:
    """Apps with ≥ MIN_SESSIONS_FOR_CURVE usable (pass + timestamps_ok) sessions."""
    return sorted(
        a
        for a, c in report.per_app_pass_counts.items()
        if c >= MIN_SESSIONS_FOR_CURVE
    )


def sessions_for_app(report: Stage0Report, app_id: str) -> list[SessionMeta]:
    xs = [s for s in report.sessions if s.app_id == app_id and s.usable]
    xs.sort(
        key=lambda s: (
            s.start_timestamp_ms if s.start_timestamp_ms is not None else 0,
            s.session_index_within_app,
        )
    )
    return xs
