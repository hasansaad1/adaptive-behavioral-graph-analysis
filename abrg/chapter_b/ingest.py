"""Load v2_extended index + per-session metadata. Verify first; stop on non-zero."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from abrg.chapter_b.config import EXPORT_ROOT, GAE_MIN_ACTIVE, GAE_MIN_EDGES
from abrg.trace import load_frida_trace


@dataclass
class SessionRow:
    app_id: str
    session_id: str
    export_dir_name: str
    session_index_within_app: int
    batch: str
    reference_tier_pass: bool
    failure_reason: str | None
    gae_eligible_meta: bool
    rel_dir: str
    start_timestamp: str | None
    end_timestamp: str | None
    wall_duration_s: float | None
    mapped_meta: int | None
    total_meta: int | None
    mapped_rate_meta: float | None
    n_active_meta: int | None
    n_edges_meta: int | None
    active_categories: list[str]
    hooks_fired: list[str]
    events_path: str
    metadata_path: str
    source_meta_path: str | None
    analysis_status: str | None
    analyze_exit_status: str | None
    timestamps_ok_meta: bool | None


def run_verify_export(export_root: Path = EXPORT_ROOT) -> tuple[int, str]:
    script = export_root / "verify_export.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(export_root),
        capture_output=True,
        text=True,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    return int(proc.returncode), text


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    s = ts.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def load_sessions(export_root: Path = EXPORT_ROOT) -> list[SessionRow]:
    index_path = export_root / "sessions_index.jsonl"
    rows: list[SessionRow] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        idx = json.loads(line)
        rel = idx["rel_dir"]
        meta_path = export_root / rel / "metadata.json"
        events_path = export_root / rel / "events.jsonl"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        counts = meta.get("event_counts") or {}
        rows.append(
            SessionRow(
                app_id=idx["app_id"],
                session_id=idx["session_id"],
                export_dir_name=idx.get("export_dir_name", meta.get("export_dir_name", "")),
                session_index_within_app=int(idx["session_index_within_app"]),
                batch=str(idx["batch"]),
                reference_tier_pass=bool(idx["reference_tier_pass"]),
                failure_reason=idx.get("failure_reason") or meta.get("failure_reason"),
                gae_eligible_meta=bool(idx.get("gae_eligible", meta.get("gae_eligible", False))),
                rel_dir=rel,
                start_timestamp=meta.get("start_timestamp") or idx.get("start_timestamp"),
                end_timestamp=meta.get("end_timestamp"),
                wall_duration_s=(
                    float(meta["wall_duration_s"])
                    if meta.get("wall_duration_s") is not None
                    else None
                ),
                mapped_meta=counts.get("mapped"),
                total_meta=counts.get("total"),
                mapped_rate_meta=counts.get("mapped_rate"),
                n_active_meta=meta.get("n_active_nodes"),
                n_edges_meta=meta.get("n_edges"),
                active_categories=list(meta.get("active_categories") or []),
                hooks_fired=list(meta.get("hooks_fired") or []),
                events_path=str(events_path),
                metadata_path=str(meta_path),
                source_meta_path=meta.get("source_meta_path"),
                analysis_status=meta.get("analysis_status"),
                analyze_exit_status=(
                    str(meta["analyze_exit_status"])
                    if meta.get("analyze_exit_status") is not None
                    else None
                ),
                timestamps_ok_meta=meta.get("timestamps_ok"),
            )
        )
    rows.sort(key=lambda r: (r.app_id, r.session_index_within_app, r.batch))
    return rows


def pass_sessions(rows: list[SessionRow]) -> list[SessionRow]:
    return [r for r in rows if r.reference_tier_pass]


def fail_sessions(rows: list[SessionRow]) -> list[SessionRow]:
    return [r for r in rows if not r.reference_tier_pass]


def gae_eligible_from_graph(n_active: int, n_edges: int) -> bool:
    return n_active >= GAE_MIN_ACTIVE and n_edges >= GAE_MIN_EDGES


def batch_date_range(rows: list[SessionRow]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by: dict[str, list[SessionRow]] = defaultdict(list)
    for r in rows:
        by[r.batch].append(r)
    for batch, xs in sorted(by.items()):
        starts = [_parse_iso(r.start_timestamp) for r in xs]
        ends = [_parse_iso(r.end_timestamp) for r in xs]
        starts_ok = [t for t in starts if t is not None]
        ends_ok = [t for t in ends if t is not None]
        out[batch] = {
            "n": len(xs),
            "start_utc": min(starts_ok).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if starts_ok else None,
            "end_utc": max(ends_ok).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if ends_ok else None,
        }
    return out


def session_count_table(
    rows: list[SessionRow],
) -> tuple[dict[str, int], dict[str, int]]:
    """Return (value_counts of n_sessions, per-app counts)."""
    per_app = Counter(r.app_id for r in rows)
    dist = Counter(per_app.values())
    return {str(k): int(v) for k, v in sorted(dist.items())}, dict(sorted(per_app.items()))


def count_type_event(events_path: Path) -> int:
    n = 0
    with events_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "event":
                n += 1
    return n


def event_apis(events_path: Path) -> set[str]:
    """API names on all type==event records (including dropped categories)."""
    apis: set[str] = set()
    with events_path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "event":
                continue
            api = obj.get("api")
            if api:
                apis.add(str(api))
    return apis


def mapped_and_total(events_path: Path) -> tuple[int, int, dict[str, int], list[str]]:
    """Mapped via load_frida_trace; total = type==event including dropped cats."""
    events, rep = load_frida_trace(events_path)
    total = count_type_event(events_path)
    apis = sorted({e.api for e in events if e.api})
    return len(events), total, dict(rep.category_counts), apis


def load_source_meta(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def as_jsonable(row: SessionRow) -> dict[str, Any]:
    return asdict(row)
