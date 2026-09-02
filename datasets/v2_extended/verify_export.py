#!/usr/bin/env python3
"""Verify export/v2_extended integrity. Exit 0 on success, non-zero with failure list."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_event_timestamps(events_path: Path) -> list[str]:
    fails: list[str] = []
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
                fails.append(f"{events_path}: line {lineno}: event missing timestamp")
                continue
            ts = int(obj["timestamp"])
            if prev is not None and ts < prev:
                fails.append(
                    f"{events_path}: line {lineno}: non-monotonic timestamp {ts} < {prev}"
                )
            prev = ts
    if n_event == 0:
        fails.append(f"{events_path}: no type==event records with parseable JSON")
    return fails


def main() -> int:
    fails: list[str] = []
    manifest = ROOT / "MANIFEST.csv"
    index = ROOT / "sessions_index.jsonl"
    if not manifest.is_file():
        print("FAIL: MANIFEST.csv missing", file=sys.stderr)
        return 2
    if not index.is_file():
        print("FAIL: sessions_index.jsonl missing", file=sys.stderr)
        return 2

    with manifest.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        rel = row["relative_path"]
        path = ROOT / rel
        if not path.is_file():
            fails.append(f"manifest path missing: {rel}")
            continue
        got = sha256_file(path)
        if got != row["sha256"]:
            fails.append(f"hash mismatch: {rel}")
        size = path.stat().st_size
        if str(size) != str(row["size_bytes"]):
            fails.append(f"size mismatch: {rel} got {size} expected {row['size_bytes']}")

    index_rows = [
        json.loads(l) for l in index.read_text(encoding="utf-8").splitlines() if l.strip()
    ]
    seen_dirs: set[str] = set()
    for r in index_rows:
        rel = r["rel_dir"]
        seen_dirs.add(rel)
        meta = ROOT / rel / "metadata.json"
        ev = ROOT / rel / "events.jsonl"
        if not meta.is_file():
            fails.append(f"index session missing metadata.json: {rel}")
        if not ev.is_file():
            fails.append(f"index session missing events.jsonl: {rel}")
        else:
            fails.extend(check_event_timestamps(ev))
        if meta.is_file():
            m = json.loads(meta.read_text(encoding="utf-8"))
            if m.get("session_id") != r["session_id"]:
                fails.append(f"metadata session_id mismatch: {rel}")
            if m.get("session_index_within_app") != r["session_index_within_app"]:
                fails.append(f"metadata index mismatch: {rel}")

    for base_name in ("sessions", "sessions_failed_reference"):
        base = ROOT / base_name
        if not base.is_dir():
            fails.append(f"missing directory: {base_name}")
            continue
        for app_dir in sorted(p for p in base.iterdir() if p.is_dir()):
            for sess_dir in sorted(p for p in app_dir.iterdir() if p.is_dir()):
                rel = f"{base_name}/{app_dir.name}/{sess_dir.name}"
                if rel not in seen_dirs:
                    fails.append(f"session dir not in index: {rel}")
                if not (sess_dir / "events.jsonl").is_file():
                    fails.append(f"missing events.jsonl: {rel}")
                if not (sess_dir / "metadata.json").is_file():
                    fails.append(f"missing metadata.json: {rel}")

    by_app: dict[str, list[int]] = defaultdict(list)
    for r in index_rows:
        by_app[r["app_id"]].append(int(r["session_index_within_app"]))
    for app, idxs in sorted(by_app.items()):
        s = sorted(idxs)
        expect = list(range(1, len(s) + 1))
        if s != expect:
            fails.append(f"non-contiguous session_index_within_app for {app}: {s}")

    if fails:
        print(f"VERIFY FAIL — {len(fails)} issue(s):", file=sys.stderr)
        for line in fails[:200]:
            print(f"  - {line}", file=sys.stderr)
        if len(fails) > 200:
            print(f"  ... and {len(fails) - 200} more", file=sys.stderr)
        return 1
    print(f"VERIFY OK — {len(rows)} files, {len(index_rows)} sessions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
