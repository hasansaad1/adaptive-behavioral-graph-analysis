#!/usr/bin/env python3
"""Build export/v2_extended/ — read-only on session artefacts; writes only under export/v2_extended/."""
from __future__ import annotations

import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CTX = Path("$CONTEXTDROID_ROOT")
ABGA = Path(".")
OUT = CTX / "export" / "v2_extended"
SESSIONS_PASS = OUT / "sessions"
SESSIONS_FAIL = OUT / "sessions_failed_reference"
INDEX = OUT / "sessions_index.jsonl"

sys.path.insert(0, str(ABGA))
from abrg.corpus import build_corpus_graphs, build_session_graph  # noqa: E402
from abrg.trace import load_frida_trace  # noqa: E402
from abrg.windows import WindowMode  # noqa: E402


def iso_from_ms(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def check_timestamps(events: list[dict[str, Any]]) -> dict[str, Any]:
    ts: list[int] = []
    missing = 0
    for ev in events:
        if "timestamp" not in ev or ev["timestamp"] is None:
            missing += 1
            continue
        ts.append(int(ev["timestamp"]))
    nonmono = 0
    for i in range(1, len(ts)):
        if ts[i] < ts[i - 1]:
            nonmono += 1
    return {
        "n_events": len(events),
        "n_with_timestamp": len(ts),
        "n_missing_timestamp": missing,
        "monotonic": nonmono == 0 and missing == 0 and len(ts) == len(events),
        "n_non_monotonic_steps": nonmono,
    }


def load_frida_events(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    events: list[dict[str, Any]] = []
    bad: list[int] = []
    for i, line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            bad.append(i)
    return events, bad


def graph_metrics(frida_path: Path, package: str) -> dict[str, Any]:
    events, rep = load_frida_trace(frida_path)
    g = build_session_graph(events, package)
    active = g.active_nodes()
    mapped = int(rep.events_kept)
    total_parsed = int(rep.lines_parsed)
    return {
        "total_events": total_parsed,
        "mapped_events": mapped,
        "mapped_rate": (mapped / total_parsed) if total_parsed else None,
        "active_categories": list(rep.distinct_categories),
        "hooks_fired": sorted({e.api for e in events if e.api}),
        "n_active_nodes": len(active),
        "n_edges": len(g.edges),
        "gae_eligible": len(active) >= 2 and len(g.edges) >= 1,
    }


def clear_data_dirs() -> None:
    """Remove prior export data without deleting this script."""
    for name in (
        "sessions",
        "sessions_failed_reference",
        "sessions_index.jsonl",
        "EXPORT_SET.json",
        "_export_stats.json",
        "MANIFEST.csv",
        "README.md",
        "PROVENANCE.md",
        "OVERRIDE.md",
        "REPORT.md",
        "verify_export.py",
    ):
        p = OUT / name
        if p.is_dir():
            shutil.rmtree(p)
        elif p.is_file():
            p.unlink()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    clear_data_dirs()
    SESSIONS_PASS.mkdir(parents=True)
    SESSIONS_FAIL.mkdir(parents=True)

    apps40 = json.loads(
        (CTX / "abrg/output/v2_extend/collection/apps_gae40.json").read_text()
    )["apps"]
    gae_pkgs = [a["package"] for a in apps40]

    orig_recs = build_corpus_graphs(
        ABGA / "datasets/v2/sessions",
        window_mode=WindowMode.WHOLE_SESSION,
        snapshots=False,
    )
    assert len(orig_recs) == 168, len(orig_recs)

    originals: list[dict[str, Any]] = []
    for r in orig_recs:
        sdir = ABGA / "datasets/v2/sessions" / r.session_dir
        meta_path = next(sdir.glob("*_dynamic_metadata.json"))
        frida_path = next(sdir.glob("*_frida.jsonl"))
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        start_ms = meta.get("started_at_epoch_ms")
        elapsed = meta.get("elapsed_sec")
        end_ms = (
            int(start_ms) + int(float(elapsed) * 1000)
            if start_ms is not None and elapsed is not None
            else None
        )
        originals.append(
            {
                "app_id": r.package,
                "session_id": r.session_id,
                "batch": "original",
                "reference_tier_pass": True,
                "failure_reason": None,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "wall_duration_s": float(elapsed) if elapsed is not None else None,
                "frida_src": frida_path,
                "meta_src": meta_path,
            }
        )

    slots = [
        json.loads(l)
        for l in (
            CTX / "abrg/output/v2_extend/collection/state/completed_slots.jsonl"
        )
        .read_text()
        .splitlines()
        if l.strip()
    ]
    assert len(slots) == 220, len(slots)

    news: list[dict[str, Any]] = []
    for s in slots:
        meta_path = Path(s["meta_path"]) if s.get("meta_path") else None
        if not meta_path or not meta_path.exists():
            art = s.get("artifact_dir")
            if art:
                meta_path = Path(art) / f"{s['package']}_dynamic_metadata.json"
        if not meta_path or not meta_path.exists():
            raise SystemExit(
                f"missing meta for {s['package']} {s.get('target_session_index')}"
            )
        frida_path = meta_path.parent / f"{s['package']}_frida.jsonl"
        if not frida_path.exists():
            raise SystemExit(f"missing frida for {frida_path}")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        start_ms = meta.get("started_at_epoch_ms")
        elapsed = meta.get("elapsed_sec")
        wall = s.get("wall_duration_sec")
        if wall is None and elapsed is not None:
            wall = float(elapsed)
        end_ms = (
            int(start_ms) + int(float(elapsed) * 1000)
            if start_ms is not None and elapsed is not None
            else None
        )
        fail_reasons = s.get("reference_fail_reasons") or []
        news.append(
            {
                "app_id": s["package"],
                "session_id": s.get("session_id") or meta.get("session_id"),
                "batch": "canary" if s.get("source") == "canary" else "extend",
                "reference_tier_pass": bool(s.get("reference_pass")),
                "failure_reason": (
                    None
                    if s.get("reference_pass")
                    else (",".join(fail_reasons) if fail_reasons else "unspecified")
                ),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "wall_duration_s": float(wall) if wall is not None else None,
                "frida_src": frida_path,
                "meta_src": meta_path,
                "exit_status": s.get("exit_status"),
                "analysis_status": s.get("analysis_status") or meta.get("analysis_status"),
            }
        )

    all_rows = originals + news
    by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in all_rows:
        by_app[row["app_id"]].append(row)
    for rows in by_app.values():
        rows.sort(
            key=lambda r: (
                r["start_ms"] is None,
                r["start_ms"] if r["start_ms"] is not None else 0,
                r["session_id"],
            )
        )
        for i, r in enumerate(rows, start=1):
            r["session_index_within_app"] = i

    ts_issues: list[dict[str, Any]] = []
    index_rows: list[dict[str, Any]] = []
    n = len(all_rows)
    for idx, row in enumerate(all_rows, start=1):
        if idx % 40 == 0 or idx == 1:
            print(f"export {idx}/{n} {row['batch']} {row['app_id']}", flush=True)
        raw_events, bad_lines = load_frida_events(row["frida_src"])
        ts_check = check_timestamps(raw_events)
        ts_check["n_unparseable_lines"] = len(bad_lines)
        if bad_lines:
            ts_check["unparseable_line_numbers_sample"] = bad_lines[:20]
        if (
            not ts_check["monotonic"]
            or ts_check["n_missing_timestamp"]
            or bad_lines
        ):
            ts_issues.append(
                {"session_id": row["session_id"], "app_id": row["app_id"], **ts_check}
            )

        gm = graph_metrics(row["frida_src"], row["app_id"])
        meta_out: dict[str, Any] = {
            "app_id": row["app_id"],
            "session_id": row["session_id"],
            "export_dir_name": f"{row['session_id']}__{row['batch']}",
            "session_index_within_app": row["session_index_within_app"],
            "batch": row["batch"],
            "start_timestamp": iso_from_ms(row["start_ms"]),
            "end_timestamp": iso_from_ms(row["end_ms"]),
            "start_timestamp_ms": row["start_ms"],
            "end_timestamp_ms": row["end_ms"],
            "wall_duration_s": row["wall_duration_s"],
            "reference_tier_pass": row["reference_tier_pass"],
            "failure_reason": row["failure_reason"],
            "event_counts": {
                "total": gm["total_events"],
                "mapped": gm["mapped_events"],
                "mapped_rate": gm["mapped_rate"],
            },
            "active_categories": gm["active_categories"],
            "hooks_fired": gm["hooks_fired"],
            "n_active_nodes": gm["n_active_nodes"],
            "n_edges": gm["n_edges"],
            "gae_eligible": gm["gae_eligible"],
            "timestamps_ok": bool(ts_check["monotonic"]) and not bad_lines,
            "timestamp_check": ts_check,
            "source_frida_path": str(row["frida_src"]),
            "source_meta_path": str(row["meta_src"]),
            "event_schema": {
                "format": "Frida JSONL (ContextDroid / ABRG)",
                "fields": ["type", "timestamp", "api", "category", "args"],
                "notes": "Copied verbatim; no resample/truncate/dedupe/filter.",
            },
            "graph_metrics_source": (
                "ABRG abrg.corpus.build_session_graph + abrg.trace.load_frida_trace "
                "at export time from unchanged Frida JSONL"
            ),
        }
        if row["batch"] != "original":
            meta_out["analyze_exit_status"] = row.get("exit_status")
            meta_out["analysis_status"] = row.get("analysis_status")

        dest_root = SESSIONS_PASS if row["reference_tier_pass"] else SESSIONS_FAIL
        # session_id alone is not unique across batches (same APK sample_id reused).
        dest_name = f"{row['session_id']}__{row['batch']}"
        dest = dest_root / row["app_id"] / dest_name
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "metadata.json").write_text(
            json.dumps(meta_out, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copy2(row["frida_src"], dest / "events.jsonl")

        index_rows.append(
            {
                "app_id": row["app_id"],
                "session_id": row["session_id"],
                "export_dir_name": dest_name,
                "session_index_within_app": row["session_index_within_app"],
                "batch": row["batch"],
                "reference_tier_pass": row["reference_tier_pass"],
                "failure_reason": row["failure_reason"],
                "rel_dir": f"{dest_root.name}/{row['app_id']}/{dest_name}",
                "start_timestamp": meta_out["start_timestamp"],
                "n_active_nodes": gm["n_active_nodes"],
                "n_edges": gm["n_edges"],
                "gae_eligible": gm["gae_eligible"],
                "mapped_events": gm["mapped_events"],
            }
        )

    with INDEX.open("w", encoding="utf-8") as f:
        for r in sorted(
            index_rows,
            key=lambda x: (x["app_id"], x["session_index_within_app"], x["session_id"]),
        ):
            f.write(json.dumps(r, sort_keys=True) + "\n")

    pass_n = sum(1 for r in all_rows if r["reference_tier_pass"])
    fail_n = sum(1 for r in all_rows if not r["reference_tier_pass"])
    batch_c = Counter(r["batch"] for r in all_rows)
    app_counts = {pkg: len(rows) for pkg, rows in by_app.items()}
    gae_counts = sorted(app_counts[p] for p in gae_pkgs)
    dist = dict(Counter(gae_counts))

    still_gae = []
    fell_out = []
    for pkg in gae_pkgs:
        pass_rows = [
            r for r in index_rows if r["app_id"] == pkg and r["reference_tier_pass"]
        ]
        if any(r["gae_eligible"] for r in pass_rows):
            still_gae.append(pkg)
        else:
            fell_out.append(pkg)

    fail_by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in all_rows:
        if not r["reference_tier_pass"]:
            fail_by_app[r["app_id"]].append(
                {
                    "session_id": r["session_id"],
                    "batch": r["batch"],
                    "failure_reason": r["failure_reason"],
                }
            )

    stage1 = {
        "total_exported": len(all_rows),
        "breakdown": {
            "original_reference_tier": batch_c["original"],
            "canary": batch_c["canary"],
            "extend": batch_c["extend"],
            "reference_tier_pass": pass_n,
            "reference_tier_fail": fail_n,
        },
        "gae40_session_count_distribution": dist,
        "gae40_per_app_counts": {p: app_counts[p] for p in gae_pkgs},
        "all_apps_in_export": sorted(app_counts.keys()),
        "n_apps_in_export": len(app_counts),
        "gae40_still_eligible_after_extension": len(still_gae),
        "gae40_fell_out_of_eligibility": fell_out,
        "failed_reference_tier": {
            "count": fail_n,
            "per_app": {k: v for k, v in sorted(fail_by_app.items())},
        },
        "timestamp_issues": ts_issues,
        "excluded_from_export": [],
    }
    (OUT / "EXPORT_SET.json").write_text(json.dumps(stage1, indent=2) + "\n")

    (OUT / "OVERRIDE.md").write_text(
        """# Operator override (2026-08-14) — frida-server version only

Copied verbatim from `abrg/output/v2_extend/identity_check/REPORT.md`
(file `OVERRIDE.md` was not present in that directory at export time).

Explicit override of the Stage 1 UNRECOVERABLE gate **for frida-server version**, recorded verbatim:

- client 17.9.3, installed 2026-04-30, no upgrade trail through the July window
- frida enforces client/server version compatibility at attach; July sessions
  attached successfully, so the server was 17.9.3-compatible
- no frida commands in shell history during July
- current `tools/frida-server-android-arm64` strings report 17.9.3; the 2026-08-05
  mtime reflects a file write, not a verified content change

**Remaining HARD gaps (not overridden):** emulator system image identity, LLM planner
model digest, prompt template SHA256 — still UNRECOVERABLE from July artifacts.
"""
    )

    nonzero = [
        {
            "app_id": r["app_id"],
            "session_id": r["session_id"],
            "exit_status": r.get("exit_status"),
            "analysis_status": r.get("analysis_status"),
            "failure_reason": r["failure_reason"],
        }
        for r in news
        if r["batch"] == "extend" and r.get("exit_status") not in (0, "0", None)
    ]

    date_ranges = {}
    for batch in ("original", "canary", "extend"):
        starts = [r["start_ms"] for r in all_rows if r["batch"] == batch and r["start_ms"]]
        ends = [r["end_ms"] for r in all_rows if r["batch"] == batch and r["end_ms"]]
        date_ranges[batch] = {
            "start": iso_from_ms(min(starts)) if starts else None,
            "end": iso_from_ms(max(ends)) if ends else None,
            "n": sum(1 for r in all_rows if r["batch"] == batch),
        }

    stats = {
        "stage1": stage1,
        "date_ranges": date_ranges,
        "nonzero_analyze": nonzero,
        "transitions": {p: app_counts[p] - 1 for p in sorted(app_counts.keys())},
        "pass_by_batch": {
            b: sum(1 for r in all_rows if r["batch"] == b and r["reference_tier_pass"])
            for b in ("original", "canary", "extend")
        },
        "fail_by_batch": {
            b: sum(
                1 for r in all_rows if r["batch"] == b and not r["reference_tier_pass"]
            )
            for b in ("original", "canary", "extend")
        },
        "app_counts": app_counts,
    }
    (OUT / "_export_stats.json").write_text(json.dumps(stats, indent=2) + "\n")
    print(
        json.dumps(
            {
                "exported": len(all_rows),
                "pass": pass_n,
                "fail": fail_n,
                "ts_issues": len(ts_issues),
                "fell_out": fell_out,
                "dist": dist,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
