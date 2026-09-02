"""
E4 Phase 0 — v2_extended inventory and viability (MEASUREMENT ONLY).

No model, no scoring, no AUC, no d vectors. Report and STOP.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from abrg.androct.graph_build import update_graph_sequence
from abrg.chapter_b.config import EXPORT_ROOT, GAE_MIN_ACTIVE, GAE_MIN_EDGES
from abrg.config import K_BURST
from abrg.graph import build_initial_graph
from abrg.registry import DROPPED_CATEGORIES, GRAPH_CATEGORY_UNIVERSE
from abrg.static import zero_static_report
from abrg.trace import load_frida_trace

WINDOW_CANDIDATES_S = (10, 35, 60, 120)
N_NODES = len(GRAPH_CATEGORY_UNIVERSE)


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return float("nan")
    a = np.asarray(vals, dtype=np.float64)
    return float(np.percentile(a, p))


def _summary(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {
            "n": 0,
            "min": float("nan"),
            "p10": float("nan"),
            "p25": float("nan"),
            "median": float("nan"),
            "p75": float("nan"),
            "p90": float("nan"),
            "max": float("nan"),
            "iqr": float("nan"),
            "mean": float("nan"),
        }
    return {
        "n": len(vals),
        "min": float(min(vals)),
        "p10": _pct(vals, 10),
        "p25": _pct(vals, 25),
        "median": _pct(vals, 50),
        "p75": _pct(vals, 75),
        "p90": _pct(vals, 90),
        "max": float(max(vals)),
        "iqr": _pct(vals, 75) - _pct(vals, 25),
        "mean": float(np.mean(vals)),
    }


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _window_has_edge(categories: list[str], *, k: int = K_BURST) -> bool:
    """True if update_graph_sequence would create ≥1 non-self-loop edge."""
    if len(categories) < 2:
        return False
    if len(set(categories)) < 2:
        return False
    g = build_initial_graph(static_report=zero_static_report("phase0"))
    update_graph_sequence(g, categories, k_burst=k)
    return sum(1 for _ in g.iter_edges()) > 0


def main() -> None:
    parser = argparse.ArgumentParser(description="E4 Phase 0 inventory")
    parser.add_argument("--export-root", type=Path, default=EXPORT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("abrg/output/v2_extended/e4_phase0"),
    )
    parser.add_argument(
        "--results-md",
        type=Path,
        default=Path("results/E4_phase0_inventory.md"),
    )
    args = parser.parse_args()
    root: Path = args.export_root
    out: Path = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    index_path = root / "sessions_index.jsonl"
    index = [
        json.loads(l)
        for l in index_path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    # Enrich from metadata when index fields missing
    rows: list[dict[str, Any]] = []
    for idx in index:
        meta_path = root / idx["rel_dir"] / "metadata.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        counts = meta.get("event_counts") or {}
        topo = meta.get("topology") or meta.get("graph_topology") or {}
        row = {
            **idx,
            "start_timestamp_ms": meta.get("start_timestamp_ms") or idx.get("start_timestamp_ms"),
            "end_timestamp_ms": meta.get("end_timestamp_ms") or idx.get("end_timestamp_ms"),
            "wall_duration_s": idx.get("wall_duration_s")
            or meta.get("wall_duration_s")
            or meta.get("duration_s"),
            "start_timestamp": idx.get("start_timestamp") or meta.get("start_timestamp"),
            "end_timestamp": idx.get("end_timestamp") or meta.get("end_timestamp"),
            "mapped_events": idx.get("mapped_events")
            if idx.get("mapped_events") is not None
            else counts.get("mapped") or counts.get("mapped_events"),
            "n_edges": idx.get("n_edges")
            if idx.get("n_edges") is not None
            else topo.get("n_edges") or meta.get("n_edges"),
            "n_active_nodes": idx.get("n_active_nodes")
            if idx.get("n_active_nodes") is not None
            else topo.get("n_active_nodes") or meta.get("n_active_nodes"),
            "gae_eligible": bool(
                idx.get("gae_eligible")
                if idx.get("gae_eligible") is not None
                else meta.get("gae_eligible")
            ),
            "reference_tier_pass": bool(idx.get("reference_tier_pass")),
            "events_path": str(root / idx["rel_dir"] / "events.jsonl"),
            "metadata_path": str(meta_path),
        }
        # Derive wall duration from start/end if needed
        if row["wall_duration_s"] is None:
            t0 = _parse_iso(row["start_timestamp"])
            t1 = _parse_iso(row["end_timestamp"])
            if t0 and t1:
                row["wall_duration_s"] = (t1 - t0).total_seconds()
        rows.append(row)

    total_sessions = len(rows)
    usable = [r for r in rows if r["reference_tier_pass"]]
    failed = [r for r in rows if not r["reference_tier_pass"]]
    apps_all = sorted({r["app_id"] for r in rows})
    apps_usable = sorted({r["app_id"] for r in usable})
    gae_sessions = [
        r
        for r in usable
        if (r["n_active_nodes"] or 0) >= GAE_MIN_ACTIVE
        and (r["n_edges"] or 0) >= GAE_MIN_EDGES
    ]
    # Prefer index gae_eligible when present
    gae_by_flag = [r for r in usable if r["gae_eligible"]]
    graph_eligible_apps = sorted({r["app_id"] for r in gae_by_flag})

    # ── 0a sessions per app (usable) ─────────────────────────
    by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in usable:
        by_app[r["app_id"]].append(r)
    for aid in by_app:
        by_app[aid].sort(
            key=lambda x: (
                _parse_iso(x["start_timestamp"]) or datetime.min.replace(tzinfo=timezone.utc),
                x.get("session_index_within_app") or 0,
            )
        )
    sess_per_app = [len(v) for v in by_app.values()]
    hist = Counter(sess_per_app)

    # ── 0b split eligibility ─────────────────────────────────
    n_ge = {k: sum(1 for c in sess_per_app if c >= k) for k in (6, 8, 10, 15)}
    apps_ge8 = sorted([a for a, v in by_app.items() if len(v) >= 8])

    # ── 0c density from persisted index/meta ─────────────────
    mapped_vals = [float(r["mapped_events"] or 0) for r in usable]
    edges_vals = [float(r["n_edges"] or 0) for r in usable]
    active_vals = [float(r["n_active_nodes"] or 0) for r in usable]
    edges_sum = float(sum(edges_vals))
    # Cross-check: original v2 windowed (norm_ab_v2)
    v2_cross: dict[str, Any] = {
        "cited_579_over_728": "NOT FOUND in persisted artifacts (see W_selection.md)",
        "norm_ab_v2_path": "abrg/output/norm_ab_v2/comparison.json",
    }
    nab = Path("abrg/output/norm_ab_v2/comparison.json")
    if nab.is_file():
        comp = json.loads(nab.read_text())
        build = comp.get("build") or {}
        v2_cross["norm_ab_v2_total_snapshots"] = build.get("total_snapshots")
        v2_cross["norm_ab_v2_trainable_snapshots"] = build.get("trainable_snapshots")
        v2_cross["norm_ab_v2_gae_eligible_snapshots"] = build.get("gae_eligible_snapshots")
        v2_cross["norm_ab_v2_edge_dist_trainable"] = build.get(
            "edge_count_distribution_trainable"
        )
        v2_cross["norm_ab_v2_edge_dist_gae"] = build.get(
            "edge_count_distribution_gae_eligible"
        )
        csv_p = Path("abrg/output/norm_ab_v2/normalized_v021/per_snapshot_errors.csv")
        if csv_p.is_file():
            with csv_p.open(encoding="utf-8") as f:
                rows_c = list(csv.DictReader(f))
            ev = [float(r["n_edges"]) for r in rows_c]
            v2_cross["norm_ab_v2_gae_csv_n"] = len(ev)
            v2_cross["norm_ab_v2_gae_edge_sum"] = float(sum(ev))
            v2_cross["norm_ab_v2_gae_edge_mean"] = float(np.mean(ev))
            v2_cross["norm_ab_v2_gae_edge_median"] = float(np.median(ev))

    # Chapter B Run2 edges (AndroCT-aligned builder) from SUMMARY / CSV
    ch_b = Path("abrg/output/v2_chapter_b/run2_comparison/v2_per_session.csv")
    if not ch_b.is_file():
        ch_b = Path("abrg/output/v2_chapter_b/run1_corpus/per_session_metrics.csv")
    chapter_b_density: dict[str, Any] = {}
    if ch_b.is_file():
        with ch_b.open(encoding="utf-8") as f:
            rd = list(csv.DictReader(f))
        if rd:
            for col in ("n_edges", "edges", "edge_count"):
                if col in rd[0]:
                    ev = [float(r[col]) for r in rd if r.get(col) not in (None, "")]
                    chapter_b_density = {
                        "path": str(ch_b),
                        "n": len(ev),
                        "edges": _summary(ev),
                        "note": "Chapter B persisted per-session metrics",
                    }
                    break
            for col in ("n_active_nodes", "n_active", "active_nodes"):
                if col in rd[0] and chapter_b_density:
                    av = [float(r[col]) for r in rd if r.get(col) not in (None, "")]
                    chapter_b_density["n_active_nodes"] = _summary(av)
                    break
    # Export-time topology (sessions_index)
    export_density = {
        "path": str(index_path),
        "n": len(usable),
        "mapped_events": _summary(mapped_vals),
        "n_edges": _summary(edges_vals),
        "n_active_nodes": _summary(active_vals),
        "edge_sum": edges_sum,
        "edges_per_session_mean": edges_sum / max(len(usable), 1),
        "frac_zero_edges": float(np.mean([e == 0 for e in edges_vals])),
        "builder_note": (
            "Export-time build_session_graph topology fields on sessions_index; "
            "differs from Chapter B Run2 update_graph_sequence (med edges 2 vs 5)."
        ),
    }

    # ── 0d inter-session timing ──────────────────────────────
    gaps_s: list[float] = []
    app_gap_rows: list[dict[str, Any]] = []
    apps_single_day = 0
    apps_multi_day = 0
    for aid, sess in by_app.items():
        starts = [_parse_iso(s["start_timestamp"]) for s in sess]
        starts = [t for t in starts if t is not None]
        if len(starts) >= 2:
            starts_sorted = sorted(starts)
            for i in range(len(starts_sorted) - 1):
                gap = (starts_sorted[i + 1] - starts_sorted[i]).total_seconds()
                gaps_s.append(gap)
                app_gap_rows.append({"app_id": aid, "gap_s": gap})
        if starts:
            days = {t.date() for t in starts}
            if len(days) <= 1:
                apps_single_day += 1
            else:
                apps_multi_day += 1

    # ── 0e + 0f single pass over usable sessions ──────────────
    # Timing + vocabulary require events.jsonl (not in index).
    # Zero-edge under k=5: in-memory update_graph_sequence per window only.
    print("[E4/p0] scanning events.jsonl for vocabulary + timing (0e/0f) …", flush=True)
    cats_seen: Counter[str] = Counter()
    cats_dropped: Counter[str] = Counter()
    cats_unknown: set[str] = set()
    duration_s: list[float] = []
    epm: list[float] = []
    inter_gaps_ms: list[float] = []
    idle_fracs: list[float] = []
    session_timing_rows: list[dict[str, Any]] = []
    window_stats: dict[int, dict[str, list[float]]] = {
        w: {
            "n_windows": [],
            "frac_zero_mapped": [],
            "frac_one_mapped": [],
            "frac_zero_edges": [],
        }
        for w in WINDOW_CANDIDATES_S
    }

    for i, r in enumerate(usable):
        events_path = Path(r["events_path"])
        # dropped / unknown from raw lines
        for line in events_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "event":
                continue
            c = obj.get("category")
            if c in DROPPED_CATEGORIES:
                cats_dropped[str(c)] += 1
            elif c is not None and c not in GRAPH_CATEGORY_UNIVERSE:
                cats_unknown.add(str(c))

        events, _ = load_frida_trace(events_path)
        for e in events:
            cats_seen[e.category] += 1

        ts = [e.timestamp_ms for e in events]
        cats = [e.category for e in events]
        wall = float(r["wall_duration_s"]) if r["wall_duration_s"] is not None else float("nan")
        t0_meta = _parse_iso(r["start_timestamp"])
        t1_meta = _parse_iso(r["end_timestamp"])
        if math.isnan(wall) and t0_meta and t1_meta:
            wall = (t1_meta - t0_meta).total_seconds()

        start_ms = r.get("start_timestamp_ms")
        end_ms = r.get("end_timestamp_ms")
        if start_ms is not None and end_ms is not None:
            start_ms = float(start_ms)
            end_ms = float(end_ms)
        elif t0_meta and t1_meta:
            start_ms = t0_meta.timestamp() * 1000.0
            end_ms = t1_meta.timestamp() * 1000.0
        else:
            start_ms = float(ts[0]) if ts else float("nan")
            end_ms = float(ts[-1]) if ts else float("nan")

        if ts:
            dur = wall if not math.isnan(wall) and wall > 0 else max((ts[-1] - ts[0]) / 1000.0, 1e-6)
            duration_s.append(dur)
            epm.append(len(events) / (dur / 60.0) if dur > 0 else float("nan"))
            gaps = [float(ts[j + 1] - ts[j]) for j in range(len(ts) - 1)]
            inter_gaps_ms.extend(gaps)
            # Idle = fraction of 1s wall-clock bins with zero mapped events
            # (events are instantaneous; point-gap sum including ends ≡ duration.)
            if not math.isnan(start_ms) and not math.isnan(end_ms) and end_ms > start_ms:
                bin_ms = 1000.0
                n_bins = int(math.ceil((end_ms - start_ms) / bin_ms))
                occupied = np.zeros(n_bins, dtype=bool)
                if abs(ts[0] - start_ms) > 3_600_000:
                    origin = float(ts[0])
                    span = max(ts[-1] - ts[0], 1)
                    n_bins = int(math.ceil(span / bin_ms))
                    occupied = np.zeros(max(n_bins, 1), dtype=bool)
                    for t in ts:
                        bi = int((t - origin) // bin_ms)
                        bi = max(0, min(len(occupied) - 1, bi))
                        occupied[bi] = True
                else:
                    for t in ts:
                        bi = int((t - start_ms) // bin_ms)
                        bi = max(0, min(n_bins - 1, bi))
                        occupied[bi] = True
                idle = 1.0 - float(occupied.mean()) if len(occupied) else 1.0
            else:
                idle = float("nan")
            idle_fracs.append(float(np.clip(idle, 0, 1)) if not math.isnan(idle) else float("nan"))
        else:
            if not math.isnan(wall):
                duration_s.append(wall)
            epm.append(0.0)
            idle_fracs.append(1.0)

        sess_row: dict[str, Any] = {
            "app_id": r["app_id"],
            "session_id": r["session_id"],
            "n_mapped": len(events),
            "wall_duration_s": wall,
            "idle_frac": idle_fracs[-1],
            "events_per_min": epm[-1],
        }

        axis_ok = (
            not math.isnan(start_ms)
            and not math.isnan(end_ms)
            and end_ms > start_ms
        )
        for W in WINDOW_CANDIDATES_S:
            w_ms = W * 1000.0
            if not axis_ok:
                n_win = 0
                fz = fo = fe = float("nan")
            else:
                n_win = int(math.ceil((end_ms - start_ms) / w_ms))
                buckets: list[list[str]] = [[] for _ in range(n_win)]
                use_meta = bool(ts) and abs(ts[0] - start_ms) <= 3_600_000
                origin = start_ms if use_meta else (float(ts[0]) if ts else start_ms)
                for t, c in zip(ts, cats):
                    wi = int((t - origin) // w_ms)
                    wi = max(0, min(n_win - 1, wi))
                    buckets[wi].append(c)
                zero_m = sum(1 for b in buckets if len(b) == 0)
                one_m = sum(1 for b in buckets if len(b) == 1)
                zero_e = sum(1 for b in buckets if not _window_has_edge(b))
                fz = zero_m / n_win
                fo = one_m / n_win
                fe = zero_e / n_win
                window_stats[W]["n_windows"].append(float(n_win))
                window_stats[W]["frac_zero_mapped"].append(fz)
                window_stats[W]["frac_one_mapped"].append(fo)
                window_stats[W]["frac_zero_edges"].append(fe)
            sess_row[f"W{W}_n_windows"] = n_win if axis_ok else 0
            sess_row[f"W{W}_frac_zero_mapped"] = fz if axis_ok else float("nan")
            sess_row[f"W{W}_frac_one_mapped"] = fo if axis_ok else float("nan")
            sess_row[f"W{W}_frac_zero_edges"] = fe if axis_ok else float("nan")

        session_timing_rows.append(sess_row)
        if (i + 1) % 50 == 0:
            print(f"  … {i+1}/{len(usable)}", flush=True)

    vocab = {
        "graph_category_universe": list(GRAPH_CATEGORY_UNIVERSE),
        "n_nodes": N_NODES,
        "categories_observed_in_mapped_stream": sorted(cats_seen.keys()),
        "all_mapped_in_universe": set(cats_seen.keys()) <= set(GRAPH_CATEGORY_UNIVERSE),
        "dropped_hook_categories_seen": dict(cats_dropped),
        "unknown_outside_taxonomy": sorted(cats_unknown),
        "n_sessions_scanned": len(usable),
        "sensor_note": (
            "Same 22-node GRAPH_CATEGORY_UNIVERSE labels as AndroCT. "
            "Sensor differs: ContextDroid Frida hooks (hook_apis.js v3) emit "
            "category at capture time; AndroCT/DroidFax maps Soot callee strings "
            "post hoc via api_category_map. Event semantics (what fires a "
            "'network' or 'ipc_intents' event) are instrumentation-specific — "
            "label set matches, generative process does not. E4 stats share the "
            "node vocabulary with E0/E2 but are NOT interchangeable as samples "
            "from the same observation process."
        ),
    }

    window_summary = {
        str(W): {
            "windows_per_session": _summary(window_stats[W]["n_windows"]),
            "frac_zero_mapped": _summary(window_stats[W]["frac_zero_mapped"]),
            "frac_one_mapped": _summary(window_stats[W]["frac_one_mapped"]),
            "frac_zero_edges_k5": _summary(window_stats[W]["frac_zero_edges"]),
            "median_frac_zero_mapped": _pct(window_stats[W]["frac_zero_mapped"], 50),
            "median_frac_zero_edges": _pct(window_stats[W]["frac_zero_edges"], 50),
        }
        for W in WINDOW_CANDIDATES_S
    }

    # Best candidate: lowest median empty-mapped fraction among those with usable n_windows
    best_W = None
    best_empty = float("inf")
    for W in WINDOW_CANDIDATES_S:
        m = window_summary[str(W)]["median_frac_zero_mapped"]
        if not math.isnan(m) and m < best_empty:
            best_empty = m
            best_W = W

    # ── Viability verdicts ───────────────────────────────────
    n8 = n_ge[8]
    if n8 >= 20:
        split_v = "VIABLE"
    elif n8 >= 8:
        split_v = "PROVISIONAL"
    else:
        split_v = "NOT VIABLE"

    med_gap = _pct(gaps_s, 50) if gaps_s else float("nan")
    # minutes / hours / days
    if math.isnan(med_gap):
        recency_v = "NO"
        recency_note = "no consecutive-session gaps computed"
    elif med_gap < 30 * 60:
        recency_v = "NO"
        recency_note = (
            f"median inter-session gap {med_gap/60:.1f} min — sessions too close "
            "for recency weighting to mean anything"
        )
    elif med_gap < 12 * 3600:
        recency_v = "MARGINAL"
        recency_note = f"median gap {med_gap/3600:.2f} h — hours-scale separation"
    else:
        recency_v = "YES"
        recency_note = f"median gap {med_gap/3600:.2f} h ({med_gap/86400:.2f} d)"

    if best_W is None or math.isnan(best_empty):
        tw_v = "NOT VIABLE"
        tw_note = "could not compute empty-window fractions"
    else:
        best_zero_e = window_summary[str(best_W)]["median_frac_zero_edges"]
        # Prefer W that keeps empty-mapped below 0.5; report zero-edge honestly
        if best_empty > 0.50:
            tw_v = "NOT VIABLE AS BEHAVIOUR WINDOWING"
            tw_note = (
                f"best W={best_W}s still has median empty-mapped fraction {best_empty:.3f} > 0.50; "
                "time-windowing measures rhythm / idle structure rather than behaviour on this corpus"
            )
        elif best_zero_e >= 0.50:
            tw_v = "MARGINAL"
            tw_note = (
                f"best empty-mapped W={best_W}s at median empty-mapped={best_empty:.3f}, "
                f"but median zero-edge (k=5) fraction still {best_zero_e:.3f} ≥ 0.50 — "
                "windows often contain events without cross-category edges"
            )
        elif best_empty > 0.30:
            tw_v = "MARGINAL"
            tw_note = (
                f"best W={best_W}s median empty-mapped={best_empty:.3f}; "
                f"zero-edge median={best_zero_e:.3f}; usable but sparse"
            )
        else:
            tw_v = "VIABLE"
            tw_note = (
                f"best W={best_W}s median empty-mapped={best_empty:.3f}, "
                f"zero-edge median={best_zero_e:.3f}"
            )

    # Persist artifacts
    payload = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "export_root": str(root),
        "definitions": {
            "usable_session": "reference_tier_pass == true (analysis set under sessions/)",
            "graph_eligible_session": (
                f"gae_eligible / n_active>={GAE_MIN_ACTIVE} and n_edges>={GAE_MIN_EDGES}"
            ),
            "graph_eligible_app": "≥1 usable gae_eligible session",
        },
        "0a": {
            "total_apps_in_index": len(apps_all),
            "total_sessions_exported": total_sessions,
            "usable_sessions": len(usable),
            "failed_sessions": len(failed),
            "apps_with_usable_sessions": len(apps_usable),
            "graph_eligible_sessions_flag": len(gae_by_flag),
            "graph_eligible_apps": len(graph_eligible_apps),
            "sessions_per_app_usable": _summary([float(c) for c in sess_per_app]),
            "sessions_per_app_histogram": {str(k): hist[k] for k in sorted(hist)},
            "sessions_per_app_full": [
                {"app_id": a, "n_usable_sessions": len(by_app[a])}
                for a in sorted(by_app.keys())
            ],
        },
        "0b": {
            "n_apps_ge_6": n_ge[6],
            "n_apps_ge_8": n_ge[8],
            "n_apps_ge_10": n_ge[10],
            "n_apps_ge_15": n_ge[15],
            "apps_ge_8": apps_ge8,
            "caption_warning": n8 < 20,
        },
        "0c": {
            "export_time_topology": export_density,
            "chapter_b_run2": chapter_b_density,
            "v2_crosscheck": v2_cross,
        },
        "0d": {
            "inter_session_gap_s": _summary(gaps_s),
            "n_gaps": len(gaps_s),
            "apps_all_sessions_single_day": apps_single_day,
            "apps_sessions_multi_day": apps_multi_day,
            "apps_with_usable": len(by_app),
        },
        "0e": vocab,
        "0f": {
            "rebuild_note": (
                "Intra-session timing requires reading events.jsonl timestamps "
                "(not in sessions_index). Zero-edge under k=5 requires in-memory "
                "update_graph_sequence on each time-window's mapped category stream "
                "— no corpus graph rebuild; measurement-only."
            ),
            "session_duration_s": _summary(duration_s),
            "mapped_events_per_minute": _summary(epm),
            "inter_mapped_event_gap_ms": _summary(inter_gaps_ms),
            "idle_fraction_wall_clock": _summary(idle_fracs),
            "windows": window_summary,
            "best_W_s": best_W,
            "best_median_frac_zero_mapped": best_empty,
        },
        "viability": {
            "SPLIT_VIABILITY": split_v,
            "SPLIT_n_ge_8": n8,
            "RECENCY_MEANINGFUL": recency_v,
            "RECENCY_note": recency_note,
            "TIME_WINDOWING": tw_v,
            "TIME_WINDOWING_note": tw_note,
        },
    }
    (out / "inventory.json").write_text(json.dumps(payload, indent=2) + "\n")

    with (out / "sessions_per_app.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["app_id", "n_usable_sessions"])
        w.writeheader()
        for a in sorted(by_app.keys()):
            w.writerow({"app_id": a, "n_usable_sessions": len(by_app[a])})

    with (out / "inter_session_gaps.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["app_id", "gap_s"])
        w.writeheader()
        w.writerows(app_gap_rows)

    with (out / "session_timing.csv").open("w", newline="", encoding="utf-8") as f:
        fields = list(session_timing_rows[0].keys()) if session_timing_rows else []
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(session_timing_rows)

    # ── Markdown ─────────────────────────────────────────────
    def fmt(x: float, nd: int = 3) -> str:
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return "nan"
        if isinstance(x, float):
            return f"{x:.{nd}f}"
        return str(x)

    def fmt_s(sec: float) -> str:
        if math.isnan(sec):
            return "nan"
        if sec < 60:
            return f"{sec:.1f}s"
        if sec < 3600:
            return f"{sec/60:.1f}min"
        if sec < 86400:
            return f"{sec/3600:.2f}h"
        return f"{sec/86400:.2f}d"

    lines: list[str] = []
    L = lines.append
    L("# E4 Phase 0 — v2_extended inventory and viability")
    L("")
    L("**MEASUREMENT ONLY.** No model, no scoring, no AUC. Benign corpus — "
      "nothing here is a detection result. Report and STOP.")
    L("")
    if n8 < 20:
        L(
            f"> **LIMITING FACTOR:** only **{n8}** apps have ≥8 usable sessions "
            f"(needed for a 6/2 split). Every downstream E4 finding is limited by "
            f"this n and must carry it in its caption."
        )
        L("")
    elif n8 <= 30:
        L(
            f"> **Sample-size note:** **{n8}** apps clear ≥8 sessions (barely above the "
            f"~20 threshold). Max usable sessions/app is {int(max(sess_per_app))}, so a "
            f"6/2 split consumes nearly the whole trace. Carry n={n8} in every E4 caption."
        )
        L("")
    L("## Viability verdict (read first)")
    L("")
    L(f"| Decision | Verdict | Detail |")
    L(f"|---|---|---|")
    L(f"| **SPLIT VIABILITY** | **{split_v}** | n apps with ≥8 sessions = **{n8}** |")
    L(f"| **RECENCY MEANINGFUL** | **{recency_v}** | {recency_note} |")
    L(f"| **TIME-WINDOWING** | **{tw_v}** | {tw_note} |")
    L("")
    L(f"Artifacts: `{out}/`")
    L("")
    L("## 0a — Corpus inventory")
    L("")
    a = payload["0a"]
    L(f"| Quantity | n |")
    L(f"|---|---:|")
    L(f"| Total sessions exported | {a['total_sessions_exported']} |")
    L(f"| Usable sessions (`reference_tier_pass`) | {a['usable_sessions']} |")
    L(f"| Failed / non-pass sessions | {a['failed_sessions']} |")
    L(f"| Apps in index | {a['total_apps_in_index']} |")
    L(f"| Apps with ≥1 usable session | {a['apps_with_usable_sessions']} |")
    L(f"| Graph-eligible sessions (`gae_eligible`) | {a['graph_eligible_sessions_flag']} |")
    L(f"| Graph-eligible apps | {a['graph_eligible_apps']} |")
    L("")
    sp = a["sessions_per_app_usable"]
    L(
        f"Sessions per app (usable): min={sp['min']:.0f}, median={sp['median']:.0f}, "
        f"IQR={sp['iqr']:.0f}, max={sp['max']:.0f}."
    )
    L("")
    L("### Full histogram (usable sessions per app)")
    L("")
    L("| n_sessions | n_apps |")
    L("|---:|---:|")
    for k in sorted(hist.keys()):
        L(f"| {k} | {hist[k]} |")
    L("")
    L(f"Per-app table: `{out / 'sessions_per_app.csv'}`")
    L("")
    L("## 0b — Split eligibility (6 ref / 2 test)")
    L("")
    L(f"| Threshold | n apps |")
    L(f"|---|---:|")
    L(f"| ≥6 sessions | **{n_ge[6]}** |")
    L(f"| ≥8 sessions (required for 6/2) | **{n_ge[8]}** |")
    L(f"| ≥10 sessions | **{n_ge[10]}** |")
    L(f"| ≥15 sessions | **{n_ge[15]}** |")
    L("")
    L(f"Apps with ≥8: `{out / 'inventory.json'}` → `0b.apps_ge_8` ({len(apps_ge8)} ids).")
    L("")
    L("## 0c — Per-session graph density")
    L("")
    L("### Export-time topology (`sessions_index.jsonl`)")
    L("")
    em = export_density["mapped_events"]
    ee = export_density["n_edges"]
    ea = export_density["n_active_nodes"]
    L(
        f"Mapped events/session: min={fmt(em['min'],1)}, p25={fmt(em['p25'],1)}, "
        f"median={fmt(em['median'],1)}, p75={fmt(em['p75'],1)}, max={fmt(em['max'],1)}."
    )
    L(
        f"Edges/graph: median={fmt(ee['median'],1)}, IQR={fmt(ee['iqr'],1)} "
        f"(sum={fmt(export_density['edge_sum'],1)}, "
        f"mean={fmt(export_density['edges_per_session_mean'],2)}, "
        f"frac_zero={fmt(export_density['frac_zero_edges'])})."
    )
    L(
        f"Active nodes/graph: median={fmt(ea['median'],1)}, IQR={fmt(ea['iqr'],1)}."
    )
    L(f"_{export_density['builder_note']}_")
    L("")
    if chapter_b_density:
        cb = chapter_b_density["edges"]
        L("### Chapter B Run2 (AndroCT-aligned `update_graph_sequence`)")
        L(
            f"Edges: median={fmt(cb['median'],1)}, IQR={fmt(cb['iqr'],1)} "
            f"(n={chapter_b_density['n']}). Path: `{chapter_b_density['path']}`"
        )
        L("")
    L("### Cross-check vs earlier v2 (~579 edges / ~728 snapshots)")
    L("")
    L(f"- Cited figure: **{v2_cross['cited_579_over_728']}**.")
    if "norm_ab_v2_gae_edge_sum" in v2_cross:
        L(
            f"- Closest persisted: `norm_ab_v2` total_snapshots="
            f"{v2_cross.get('norm_ab_v2_total_snapshots')}, "
            f"gae_eligible_snapshots={v2_cross.get('norm_ab_v2_gae_eligible_snapshots')}, "
            f"GAE edge sum={fmt(v2_cross['norm_ab_v2_gae_edge_sum'],1)}, "
            f"mean edges/snap={fmt(v2_cross['norm_ab_v2_gae_edge_mean'],2)}, "
            f"median={fmt(v2_cross['norm_ab_v2_gae_edge_median'],2)}."
        )
        old_mean = v2_cross["norm_ab_v2_gae_edge_mean"]
        new_mean = export_density["edges_per_session_mean"]
        L(
            f"- v2_extended export-time edges/session mean={fmt(new_mean,2)} vs "
            f"norm_ab_v2 GAE edges/snap mean={fmt(old_mean,2)} "
            f"(Δ={fmt(new_mean - old_mean,2)}; different unit: whole session vs 60s window)."
        )
    if v2_cross.get("norm_ab_v2_edge_dist_trainable"):
        edt = v2_cross["norm_ab_v2_edge_dist_trainable"]
        L(
            f"- Original v2 trainable window edges: median={edt.get('median')}, "
            f"mean={edt.get('mean')} (n_trainable={v2_cross.get('norm_ab_v2_trainable_snapshots')})."
        )
    L(
        f"- v2_extended whole-session edge sum={fmt(edges_sum,1)} over n={len(usable)} "
        f"usable sessions (export-time)."
    )
    L("")
    L("## 0d — Inter-session timing")
    L("")
    g = payload["0d"]["inter_session_gap_s"]
    L(
        f"Elapsed wall-clock between consecutive usable sessions (same app): "
        f"median={fmt_s(g['median'])}, IQR={fmt_s(g['iqr'])}, "
        f"p10={fmt_s(g['p10'])}, p90={fmt_s(g['p90'])}, "
        f"min={fmt_s(g['min'])}, max={fmt_s(g['max'])} (n_gaps={g['n']})."
    )
    L(
        f"Apps with all usable sessions on a **single calendar day**: "
        f"**{apps_single_day}** / {len(by_app)}; "
        f"**multi-day**: **{apps_multi_day}**."
    )
    L("")
    L(
        f"**Recency reading:** {recency_note}. "
        f"Verdict: **{recency_v}**."
    )
    L(f"Gaps CSV: `{out / 'inter_session_gaps.csv'}`")
    L("")
    L("## 0e — Vocabulary comparability")
    L("")
    L(
        f"- Mapped kept-set equals **{N_NODES}-node `GRAPH_CATEGORY_UNIVERSE`**: "
        f"{vocab['all_mapped_in_universe']} "
        f"(scanned {vocab['n_sessions_scanned']} usable sessions)."
    )
    L(f"- Dropped hook categories observed: `{vocab['dropped_hook_categories_seen']}`")
    L(f"- Unknown outside taxonomy: `{vocab['unknown_outside_taxonomy']}`")
    L("")
    L(vocab["sensor_note"])
    L("")
    L("## 0f — Intra-session event timing (NEW)")
    L("")
    L(payload["0f"]["rebuild_note"])
    L("")
    d = payload["0f"]["session_duration_s"]
    e = payload["0f"]["mapped_events_per_minute"]
    ig = payload["0f"]["inter_mapped_event_gap_ms"]
    idl = payload["0f"]["idle_fraction_wall_clock"]
    L(
        f"- Session duration: median={fmt(d['median'],1)}s, IQR={fmt(d['iqr'],1)}s "
        f"(n={d['n']})."
    )
    L(
        f"- Mapped events / minute: median={fmt(e['median'],2)}, IQR={fmt(e['iqr'],2)}."
    )
    L(
        f"- Inter-mapped-event gap: median={fmt(ig['median'],1)}ms, "
        f"IQR={fmt(ig['iqr'],1)}ms, p90={fmt(ig['p90'],1)}ms, max={fmt(ig['max'],1)}ms."
    )
    L(
        f"- Idle fraction of session wall-clock (share of 1s bins with no mapped event): "
        f"median={fmt(idl['median'])}, IQR={fmt(idl['iqr'])}."
    )
    L("")
    L("### Candidate time windows")
    L("")
    L("| W | med windows/sess | med frac zero mapped | med frac one mapped | med frac zero edges (k=5) |")
    L("|---:|---:|---:|---:|---:|")
    for W in WINDOW_CANDIDATES_S:
        ws = window_summary[str(W)]
        L(
            f"| {W}s | {fmt(ws['windows_per_session']['median'],1)} | "
            f"{fmt(ws['median_frac_zero_mapped'])} | "
            f"{fmt(ws['frac_one_mapped']['median'])} | "
            f"{fmt(ws['median_frac_zero_edges'])} |"
        )
    L("")
    L(f"Best empty-mapped median: W={best_W}s → {fmt(best_empty)}.")
    L(f"Per-session timing: `{out / 'session_timing.csv'}`")
    L("")
    L("## Stop")
    L("")
    L("Phase 0 complete. **Do not proceed to E4 Phase 1** from this report alone — "
      "human review of the three viability verdicts first.")
    L("")
    L("---")
    L("")
    L(f"Generated {payload['utc']}. Machine-readable: `{out / 'inventory.json'}`.")

    args.results_md.parent.mkdir(parents=True, exist_ok=True)
    args.results_md.write_text("\n".join(lines) + "\n")
    print(f"[E4/p0] wrote {args.results_md}", flush=True)
    print(
        f"[E4/p0] SPLIT={split_v} (n8={n8}) RECENCY={recency_v} TIMEWIN={tw_v}",
        flush=True,
    )


if __name__ == "__main__":
    main()
