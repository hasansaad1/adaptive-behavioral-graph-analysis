"""Stream-parse AndroCT tarballs and write corpus inventory (no graph build)."""

from __future__ import annotations

import hashlib
import json
import math
import tarfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abrg.androct.parse import AndroCTParseReport, parse_androct_text_stream
from abrg.androct.paths import (
    ANDROCT_2017_ROOT,
    EXPECTED_ARCHIVES,
    androct_inventory_dir,
    androct_raw_dir,
)
from abrg.registry import GRAPH_CATEGORY_UNIVERSE


@dataclass
class ClassInventory:
    label: str
    archive: str
    inner_dir: str
    md5_ok: bool
    n_files: int = 0
    n_header_only: int = 0
    n_effective: int = 0
    total_events: int = 0
    total_mapped_events: int = 0
    total_call_events: int = 0
    total_icc_events: int = 0
    total_reflection_calls: int = 0
    total_dropped_lines: int = 0
    total_lines: int = 0
    category_totals: dict[str, int] = field(default_factory=dict)
    corpus_active_categories: set[str] = field(default_factory=set)
    # per-app (effective only)
    per_app_n_events: list[int] = field(default_factory=list)
    per_app_n_mapped: list[int] = field(default_factory=list)
    per_app_n_active_cats: list[int] = field(default_factory=list)
    per_app_rows: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mapped_rate(self) -> float:
        return (self.total_mapped_events / self.total_events) if self.total_events else 0.0


def _md5_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def _summarize_dist(vals: list[int]) -> dict[str, float]:
    if not vals:
        return {"n": 0, "min": math.nan, "p25": math.nan, "p50": math.nan, "p75": math.nan, "p90": math.nan, "max": math.nan, "mean": math.nan}
    s = sorted(float(v) for v in vals)
    return {
        "n": len(s),
        "min": s[0],
        "p25": _percentile(s, 25),
        "p50": _percentile(s, 50),
        "p75": _percentile(s, 75),
        "p90": _percentile(s, 90),
        "max": s[-1],
        "mean": sum(s) / len(s),
    }


def _mann_whitney_u(x: list[int], y: list[int]) -> dict[str, Any]:
    """Two-sided Mann–Whitney U (scipy if available, else exact-rank fallback note)."""
    try:
        from scipy.stats import mannwhitneyu
    except ImportError:
        return {"error": "scipy not installed", "n_x": len(x), "n_y": len(y)}
    if len(x) < 2 or len(y) < 2:
        return {"error": "insufficient n", "n_x": len(x), "n_y": len(y)}
    res = mannwhitneyu(x, y, alternative="two-sided")
    return {
        "test": "mannwhitneyu",
        "alternative": "two-sided",
        "U": float(res.statistic),
        "p_value": float(res.pvalue),
        "n_benign": len(x),
        "n_malware": len(y),
        "benign_median": float(sorted(x)[len(x) // 2]),
        "malware_median": float(sorted(y)[len(y) // 2]),
    }


def invent_archive(archive_path: Path, meta: dict[str, str]) -> ClassInventory:
    label = meta["label"]
    expected_md5 = meta["md5"]
    inner_dir = meta["inner_dir"]
    got = _md5_file(archive_path)
    inv = ClassInventory(
        label=label,
        archive=archive_path.name,
        inner_dir=inner_dir,
        md5_ok=(got == expected_md5),
        category_totals={c: 0 for c in GRAPH_CATEGORY_UNIVERSE},
    )
    if not inv.md5_ok:
        raise SystemExit(
            f"MD5 mismatch for {archive_path.name}: expected {expected_md5}, got {got}"
        )

    with tarfile.open(archive_path, "r:gz") as tf:
        for member in tf:
            if not member.isfile() or not member.name.endswith(".apk.logcat"):
                continue
            top = member.name.split("/", 1)[0]
            if top != inner_dir:
                raise SystemExit(
                    f"Year-dir mismatch in {archive_path.name}: expected top dir "
                    f"{inner_dir!r}, saw {top!r} ({member.name}). Stop."
                )
            inv.n_files += 1
            if inv.n_files % 100 == 0:
                print(
                    f"  … {label} {inv.n_files} files "
                    f"(effective={inv.n_effective}, header_only={inv.n_header_only})",
                    flush=True,
                )
            handle = tf.extractfile(member)
            if handle is None:
                continue
            # Stream decode without loading whole multi-100MB members.
            import io

            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            try:
                report, _ = parse_androct_text_stream(
                    text, path=member.name, label=label, yield_events=False
                )
            finally:
                text.detach()

            inv.total_lines += report.n_lines
            inv.total_dropped_lines += report.n_dropped
            inv.total_call_events += report.n_call_events
            inv.total_icc_events += report.n_icc_events
            inv.total_reflection_calls += report.n_reflection_calls
            inv.total_events += report.n_events
            inv.total_mapped_events += report.n_mapped_events
            for c, n in report.category_counts.items():
                if c in inv.category_totals:
                    inv.category_totals[c] += n
                if n > 0:
                    inv.corpus_active_categories.add(c)

            if report.header_only:
                inv.n_header_only += 1
                inv.per_app_rows.append(
                    {
                        "sha256": report.sha256,
                        "path": member.name,
                        "header_only": True,
                        "n_events": 0,
                        "n_mapped": 0,
                        "n_active_cats": 0,
                        "n_dropped": report.n_dropped,
                        "mapped_rate": 0.0,
                    }
                )
                continue

            inv.n_effective += 1
            active = report.active_categories
            inv.per_app_n_events.append(report.n_events)
            inv.per_app_n_mapped.append(report.n_mapped_events)
            inv.per_app_n_active_cats.append(len(active))
            inv.per_app_rows.append(
                {
                    "sha256": report.sha256,
                    "path": member.name,
                    "header_only": False,
                    "n_events": report.n_events,
                    "n_mapped": report.n_mapped_events,
                    "n_active_cats": len(active),
                    "n_dropped": report.n_dropped,
                    "mapped_rate": report.mapped_rate,
                    "active_categories": sorted(active),
                }
            )
    return inv


def run_inventory(*, raw_dir: Path | None = None, out_dir: Path | None = None) -> dict[str, Any]:
    raw_dir = raw_dir or androct_raw_dir()
    out_dir = out_dir or androct_inventory_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    classes: dict[str, ClassInventory] = {}
    for fname, meta in EXPECTED_ARCHIVES.items():
        path = raw_dir / fname
        if not path.is_file():
            raise SystemExit(f"Missing archive: {path}")
        print(f"[androct] inventory {fname} …", flush=True)
        classes[meta["label"]] = invent_archive(path, meta)

    benign = classes["benign"]
    malware = classes["malware"]

    length_test_events = _mann_whitney_u(benign.per_app_n_events, malware.per_app_n_events)
    length_test_mapped = _mann_whitney_u(benign.per_app_n_mapped, malware.per_app_n_mapped)

    def class_block(inv: ClassInventory) -> dict[str, Any]:
        return {
            "label": inv.label,
            "archive": inv.archive,
            "inner_dir": inv.inner_dir,
            "md5_ok": inv.md5_ok,
            "n_files": inv.n_files,
            "n_header_only": inv.n_header_only,
            "n_effective": inv.n_effective,
            "total_events": inv.total_events,
            "total_mapped_events": inv.total_mapped_events,
            "mapped_event_rate": inv.mapped_rate,
            "total_call_events": inv.total_call_events,
            "total_icc_events": inv.total_icc_events,
            "total_reflection_calls": inv.total_reflection_calls,
            "total_dropped_lines": inv.total_dropped_lines,
            "total_lines": inv.total_lines,
            "n_universe_cats_active": len(inv.corpus_active_categories),
            "universe_cats_active": sorted(inv.corpus_active_categories),
            "category_totals": inv.category_totals,
            "dist_n_events": _summarize_dist(inv.per_app_n_events),
            "dist_n_mapped": _summarize_dist(inv.per_app_n_mapped),
            "dist_n_active_cats": _summarize_dist(inv.per_app_n_active_cats),
        }

    summary = {
        "corpus_id": "androct_2017",
        "source": "Zenodo 4470320 (AndroCT; Li, Fu, Cai; MSR 2021)",
        "license_note": "CC-BY-4.0 + author restrictions (faculty sponsor, no redistribution, no commercial use, cite MSR 2021)",
        "isolation": "Separate from datasets/v1|v2; CURRENT pin untouched; dedicated output under abrg/output/androct_2017/",
        "scored_at_utc": datetime.now(timezone.utc).isoformat(),
        "graph_universe_size": len(GRAPH_CATEGORY_UNIVERSE),
        "classes": {k: class_block(v) for k, v in classes.items()},
        "trace_length_significance": {
            "metric_total_events": length_test_events,
            "metric_mapped_events": length_test_mapped,
            "note": (
                "If classes differ systematically in event count, length is a confound "
                "for any later label-aligned reconstruction signal."
            ),
        },
        "cross_corpus_warning": (
            "Any comparison to Frida datasets/v2 (or other AbrG runs) is across corpora "
            "and must be labeled as such."
        ),
    }

    (out_dir / "inventory_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    # Per-app CSVs (light).
    for label, inv in classes.items():
        rows = inv.per_app_rows
        csv_path = out_dir / f"per_app_{label}.csv"
        cols = [
            "sha256",
            "path",
            "header_only",
            "n_events",
            "n_mapped",
            "n_active_cats",
            "n_dropped",
            "mapped_rate",
        ]
        with csv_path.open("w", encoding="utf-8") as f:
            f.write(",".join(cols) + "\n")
            for r in rows:
                f.write(
                    ",".join(
                        str(r.get(c, ""))
                        for c in cols
                    )
                    + "\n"
                )

    md = _render_markdown(summary)
    (out_dir / "INVENTORY.md").write_text(md, encoding="utf-8")
    print(md)
    return summary


def _render_markdown(summary: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# AndroCT 2017 — parse inventory (pre-graph)\n")
    lines.append(f"- Source: {summary['source']}")
    lines.append(f"- Isolation: {summary['isolation']}")
    lines.append(f"- Scored (UTC): {summary['scored_at_utc']}")
    lines.append("")
    lines.append("## Per class\n")
    lines.append(
        "| Class | Files | Header-only | Effective n | Events | Mapped | Mapped rate | "
        "Active cats / 22 | Dropped lines |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for label in ("benign", "malware"):
        c = summary["classes"][label]
        lines.append(
            f"| {label} | {c['n_files']} | {c['n_header_only']} | {c['n_effective']} | "
            f"{c['total_events']} | {c['total_mapped_events']} | {c['mapped_event_rate']:.4f} | "
            f"{c['n_universe_cats_active']} | {c['total_dropped_lines']} |"
        )
    lines.append("")
    lines.append("## Distinct active categories (per-app distribution)\n")
    for label in ("benign", "malware"):
        d = summary["classes"][label]["dist_n_active_cats"]
        lines.append(
            f"- **{label}**: n={d['n']}, min={d['min']}, p25={d['p25']:.1f}, "
            f"p50={d['p50']:.1f}, p75={d['p75']:.1f}, max={d['max']}, mean={d['mean']:.2f}"
        )
    lines.append("")
    lines.append("## Trace-length distribution (total events, effective apps)\n")
    for label in ("benign", "malware"):
        d = summary["classes"][label]["dist_n_events"]
        lines.append(
            f"- **{label}**: min={d['min']}, p25={d['p25']:.0f}, p50={d['p50']:.0f}, "
            f"p75={d['p75']:.0f}, p90={d['p90']:.0f}, max={d['max']}, mean={d['mean']:.1f}"
        )
    lines.append("")
    lines.append("## Trace-length significance (Mann–Whitney U, two-sided)\n")
    for key, title in (
        ("metric_total_events", "Total events"),
        ("metric_mapped_events", "Mapped events"),
    ):
        t = summary["trace_length_significance"][key]
        if "error" in t:
            lines.append(f"- **{title}**: {t}")
        else:
            lines.append(
                f"- **{title}**: U={t['U']:.3g}, p={t['p_value']:.3g}, "
                f"median_benign={t['benign_median']:.0f}, median_malware={t['malware_median']:.0f}"
            )
    lines.append("")
    lines.append("## Corpus-wide category coverage\n")
    for label in ("benign", "malware"):
        c = summary["classes"][label]
        lines.append(
            f"- **{label}**: {c['n_universe_cats_active']}/22 — "
            f"{', '.join(c['universe_cats_active']) or '(none)'}"
        )
    lines.append("")
    lines.append(
        f"> {summary['cross_corpus_warning']}\n"
    )
    return "\n".join(lines) + "\n"
