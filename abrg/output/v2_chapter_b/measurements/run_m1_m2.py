#!/usr/bin/env python3
"""Read-only M1 (phase split) and M2 (session-mode replication) for Chapter B.

Joins through datasets/v2_extended (the analysis index). Action logs and
session_mode/agent_seed come from collection metadata (not the export).
Writes JSON artefacts under this directory. No detector, no AUC.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from abrg.chapter_b.config import EXPORT_ROOT, OUTPUT_ROOT
from abrg.dataset_paths import REPO_ROOT
from abrg.chapter_b.graphs_seq import graph_from_events, topology
from abrg.chapter_b.ingest import load_sessions, load_source_meta, pass_sessions
from abrg.chapter_b.stats import json_ready, mann_whitney, summarize_dist
from abrg.chapter_c.tensorize import distances, median_iqr, session_vector
from abrg.registry import GRAPH_CATEGORY_UNIVERSE, NON_GRAPH_HOOK_CATEGORIES
from abrg.trace import load_frida_trace

OUT = OUTPUT_ROOT / "measurements"
HOOKS_CSV = REPO_ROOT / "docs" / "contextdroid_hooks.csv"
V2_PACKAGED = REPO_ROOT / "datasets" / "v2" / "sessions"
BFS_HASH = "bfs_navigation_phase"


def _actions_path(row, src: dict | None) -> Path | None:
    pkg = (src or {}).get("package_name") or row.app_id
    if row.source_meta_path:
        cand = Path(row.source_meta_path).parent / f"{pkg}_llm_actions.jsonl"
        if cand.is_file():
            return cand
    packaged = V2_PACKAGED / f"{row.session_id}__{row.app_id}" / f"{row.app_id}_llm_actions.jsonl"
    if packaged.is_file():
        return packaged
    return None


def _iter_jsonl(path: Path):
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _load_steps(path: Path) -> list[dict]:
    steps = []
    for obj in _iter_jsonl(path):
        steps.append(
            {
                "step": obj.get("step"),
                "ts_epoch_ms": obj.get("ts_epoch_ms"),
                "prompt_hash": obj.get("prompt_hash"),
                "pipeline_phase": obj.get("pipeline_phase"),
                "screen_hash": obj.get("screen_hash"),
                "execution_kind": obj.get("execution_kind"),
            }
        )
    return steps


def _event_timestamps(events_path: Path) -> tuple[list[int], list[int]]:
    """Return (all type==event timestamps, mapped GRAPH timestamps)."""
    all_ts: list[int] = []
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
            ts = obj.get("timestamp")
            if ts is None:
                continue
            try:
                all_ts.append(int(ts))
            except (TypeError, ValueError):
                continue
    mapped, _ = load_frida_trace(Path(events_path))
    mapped_ts = [int(e.timestamp_ms) for e in mapped]
    return all_ts, mapped_ts


def _ratio(a: int, b: int) -> float | None:
    if b == 0:
        return None
    return a / b


def _summarize_ratios(vals: list[float]) -> dict:
    finite = [v for v in vals if v is not None and v == v]
    return summarize_dist(finite)


def hook_category_table() -> dict:
    rows = []
    with HOOKS_CSV.open(encoding="utf-8") as f:
        for rec in csv.DictReader(f):
            rows.append(rec)
    by_cat: dict[str, dict] = {}
    names_direct = set()
    for rec in rows:
        cat = rec["category"]
        name = rec["hook_name"]
        fired = rec["fired_in_v2_corpus"] == "yes"
        slot = by_cat.setdefault(
            cat, {"n_hooks": 0, "n_fired": 0, "n_never": 0, "hooks": []}
        )
        slot["n_hooks"] += 1
        slot["n_fired"] += int(fired)
        slot["n_never"] += int(not fired)
        slot["hooks"].append({"name": name, "fired": fired, "state": rec["v2_state"]})
        names_direct.add(name)
    graph_rows = []
    for cat in GRAPH_CATEGORY_UNIVERSE:
        slot = by_cat.get(cat, {"n_hooks": 0, "n_fired": 0, "n_never": 0, "hooks": []})
        graph_rows.append(
            {
                "category": cat,
                "n_hooks": slot["n_hooks"],
                "n_fired": slot["n_fired"],
                "n_never": slot["n_never"],
            }
        )
    dropped = {
        cat: {
            "n_hooks": by_cat.get(cat, {}).get("n_hooks", 0),
            "n_fired": by_cat.get(cat, {}).get("n_fired", 0),
        }
        for cat in sorted(NON_GRAPH_HOOK_CATEGORIES)
    }
    return {
        "csv_rows": len(rows),
        "distinct_hook_names": len(names_direct),
        "graph_categories": graph_rows,
        "dropped_categories": dropped,
        "n_graph_hooks": sum(r["n_hooks"] for r in graph_rows),
        "n_graph_fired": sum(r["n_fired"] for r in graph_rows),
        "n_graph_never": sum(r["n_never"] for r in graph_rows),
        "n_graph_cats_with_zero_fired": sum(1 for r in graph_rows if r["n_fired"] == 0),
    }


def census_steps(sessions_with_steps: list[dict]) -> dict:
    total_steps = 0
    bfs = 0
    other_hash = 0
    missing_hash = 0
    phase_counts: Counter[str] = Counter()
    missing_phase = 0
    per_session = []
    per_batch = defaultdict(lambda: Counter())
    bfs_fracs = []
    explore_over_execute = []
    explore_over_nonexplore = []
    screens_n = []
    screens_explore = []
    screens_nonexplore = []
    mapped_vs_screens = []  # filled later if mapped known

    for s in sessions_with_steps:
        steps = s["steps"]
        n = len(steps)
        total_steps += n
        n_bfs = sum(1 for st in steps if st.get("prompt_hash") == BFS_HASH)
        n_other = sum(
            1
            for st in steps
            if st.get("prompt_hash") not in (None, "", BFS_HASH)
        )
        n_miss_h = n - n_bfs - n_other
        bfs += n_bfs
        other_hash += n_other
        missing_hash += n_miss_h
        ph = Counter(str(st.get("pipeline_phase") or "MISSING") for st in steps)
        phase_counts.update(ph)
        missing_phase += ph.get("MISSING", 0)
        per_batch[s["batch"]]["sessions"] += 1
        per_batch[s["batch"]]["steps"] += n
        per_batch[s["batch"]]["bfs"] += n_bfs
        per_batch[s["batch"]]["other_hash"] += n_other
        n_explore = ph.get("explore", 0)
        n_execute = ph.get("execute", 0)
        n_primary = ph.get("primary_ux", 0)
        n_non = n - n_explore
        hashes = {st["screen_hash"] for st in steps if st.get("screen_hash")}
        hashes_ex = {
            st["screen_hash"]
            for st in steps
            if st.get("screen_hash") and st.get("pipeline_phase") == "explore"
        }
        hashes_nx = {
            st["screen_hash"]
            for st in steps
            if st.get("screen_hash") and st.get("pipeline_phase") != "explore"
        }
        rec = {
            "app_id": s["app_id"],
            "session_id": s["session_id"],
            "batch": s["batch"],
            "pass": s["pass"],
            "n_steps": n,
            "n_bfs": n_bfs,
            "n_other_hash": n_other,
            "n_missing_hash": n_miss_h,
            "phase_counts": dict(ph),
            "n_distinct_screens": len(hashes),
            "n_distinct_screens_explore": len(hashes_ex),
            "n_distinct_screens_nonexplore": len(hashes_nx),
            "bfs_frac": (n_bfs / n) if n else None,
            "explore_execute_ratio": _ratio(n_explore, n_execute),
            "explore_nonexplore_ratio": _ratio(n_explore, n_non) if n_non else None,
            "mapped_meta": s.get("mapped_meta"),
        }
        per_session.append(rec)
        if n:
            bfs_fracs.append(n_bfs / n)
        if n_execute:
            explore_over_execute.append(n_explore / n_execute)
        if n_non:
            explore_over_nonexplore.append(n_explore / n_non)
        screens_n.append(len(hashes))
        screens_explore.append(len(hashes_ex))
        screens_nonexplore.append(len(hashes_nx))
        if s.get("mapped_meta") is not None:
            mapped_vs_screens.append((len(hashes), int(s["mapped_meta"])))

    spearman = None
    if len(mapped_vs_screens) >= 3:
        from scipy.stats import spearmanr

        xs = [a for a, _ in mapped_vs_screens]
        ys = [b for _, b in mapped_vs_screens]
        rho, p = spearmanr(xs, ys)
        spearman = {"rho": float(rho), "p_value": float(p), "n": len(mapped_vs_screens)}

    return {
        "n_sessions_with_actions": len(sessions_with_steps),
        "n_steps_total": total_steps,
        "prompt_hash": {
            "bfs_navigation_phase": bfs,
            "other_sha": other_hash,
            "missing": missing_hash,
            "bfs_frac_of_steps": (bfs / total_steps) if total_steps else None,
        },
        "pipeline_phase": dict(phase_counts),
        "missing_pipeline_phase_steps": missing_phase,
        "per_batch": {k: dict(v) for k, v in sorted(per_batch.items())},
        "per_session_bfs_frac": summarize_dist(bfs_fracs),
        "explore_over_execute_ratio": _summarize_ratios(explore_over_execute),
        "explore_over_nonexplore_ratio": _summarize_ratios(explore_over_nonexplore),
        "distinct_screens_per_session": summarize_dist(screens_n),
        "distinct_screens_explore_phase": summarize_dist(screens_explore),
        "distinct_screens_nonexplore_phase": summarize_dist(screens_nonexplore),
        "spearman_distinct_screens_vs_mapped_meta": spearman,
        "per_session": per_session,
    }


def clock_diagnostic(rows_joined: list[dict]) -> dict:
    offsets_start = []
    offsets_end = []
    overlap_fracs = []
    n_no_overlap = 0
    n_ok = 0
    samples = []
    for s in rows_joined:
        steps = s["steps"]
        action_ts = [int(st["ts_epoch_ms"]) for st in steps if st.get("ts_epoch_ms") is not None]
        all_ts, mapped_ts = s["event_ts_all"], s["event_ts_mapped"]
        if not action_ts or not all_ts:
            continue
        n_ok += 1
        off0 = all_ts[0] - action_ts[0]
        off1 = all_ts[-1] - action_ts[-1]
        offsets_start.append(off0)
        offsets_end.append(off1)
        a0, a1 = min(action_ts), max(action_ts)
        e0, e1 = min(all_ts), max(all_ts)
        inter = max(0, min(a1, e1) - max(a0, e0))
        union = max(a1, e1) - min(a0, e0)
        frac = (inter / union) if union else None
        if frac is not None:
            overlap_fracs.append(frac)
            if inter == 0:
                n_no_overlap += 1
        if len(samples) < 8:
            samples.append(
                {
                    "session_id": s["session_id"],
                    "batch": s["batch"],
                    "first_action_ms": action_ts[0],
                    "first_event_ms": all_ts[0],
                    "offset_start_ms": off0,
                    "n_actions": len(action_ts),
                    "n_events": len(all_ts),
                    "n_mapped": len(mapped_ts),
                    "interval_overlap_frac": frac,
                }
            )
    return {
        "n_sessions_compared": n_ok,
        "offset_start_ms": summarize_dist(offsets_start) if offsets_start else None,
        "offset_end_ms": summarize_dist(offsets_end) if offsets_end else None,
        "interval_overlap_frac": summarize_dist(overlap_fracs) if overlap_fracs else None,
        "n_zero_interval_overlap": n_no_overlap,
        "attribution_computed": False,
        "attribution_reason": (
            "Frida events use Date.now() in the JS runtime; action logs use host "
            "time.time(). Spec §3.5: clock domains are not synchronized in code. "
            "Empirical offsets (this run) are reported; mapped-event attribution "
            "by action-step windows was not computed."
        ),
        "samples": samples,
    }


def mode_census(usable: list[dict]) -> dict:
    modes = Counter(s.get("session_mode") or "MISSING" for s in usable)
    by_batch = defaultdict(Counter)
    for s in usable:
        by_batch[s["batch"]][s.get("session_mode") or "MISSING"] += 1
    missing_mode = [s["session_id"] for s in usable if not s.get("session_mode")]
    missing_seed = [s["session_id"] for s in usable if s.get("agent_seed") is None]

    # identical-mode seed sharing within app
    by_app: dict[str, list[dict]] = defaultdict(list)
    for s in usable:
        by_app[s["app_id"]].append(s)

    seed_checks = []
    n_ident_pairs_share = 0
    n_ident_pairs_differ = 0
    n_apps_all_ident_one_seed = 0
    n_apps_ident_multiple_seeds = 0
    n_apps_with_ident_pair = 0
    for app, xs in by_app.items():
        ident = [s for s in xs if s.get("session_mode") == "identical"]
        seeds = {s.get("agent_seed") for s in ident if s.get("agent_seed") is not None}
        if len(ident) >= 2:
            n_apps_with_ident_pair += 1
            if len(seeds) == 1:
                n_apps_all_ident_one_seed += 1
            elif len(seeds) > 1:
                n_apps_ident_multiple_seeds += 1
            for i in range(len(ident)):
                for j in range(i + 1, len(ident)):
                    a, b = ident[i], ident[j]
                    share = a.get("agent_seed") is not None and a.get("agent_seed") == b.get(
                        "agent_seed"
                    )
                    if share:
                        n_ident_pairs_share += 1
                    else:
                        n_ident_pairs_differ += 1
        seed_checks.append(
            {
                "app_id": app,
                "n_usable": len(xs),
                "n_identical": len(ident),
                "n_varied": sum(1 for s in xs if s.get("session_mode") == "varied"),
                "distinct_identical_seeds": len(seeds),
                "identical_seeds": sorted(seeds) if seeds and len(seeds) <= 8 else list(seeds)[:8],
            }
        )

    return {
        "n_usable": len(usable),
        "mode_counts": dict(modes),
        "mode_counts_by_batch": {k: dict(v) for k, v in sorted(by_batch.items())},
        "n_missing_session_mode": len(missing_mode),
        "n_missing_agent_seed": len(missing_seed),
        "identical_seed_sharing": {
            "n_apps_with_ge2_identical": n_apps_with_ident_pair,
            "n_apps_all_identical_share_one_seed": n_apps_all_ident_one_seed,
            "n_apps_identical_multiple_seeds": n_apps_ident_multiple_seeds,
            "n_identical_pairs_same_seed": n_ident_pairs_share,
            "n_identical_pairs_different_seed": n_ident_pairs_differ,
        },
        "per_app": seed_checks,
    }


def screen_overlap(usable_with_steps: list[dict]) -> dict:
    by_app = defaultdict(list)
    for s in usable_with_steps:
        if s.get("session_mode") != "identical":
            continue
        hashes = {st["screen_hash"] for st in s["steps"] if st.get("screen_hash")}
        by_app[s["app_id"]].append(
            {
                "session_id": s["session_id"],
                "batch": s["batch"],
                "agent_seed": s.get("agent_seed"),
                "hashes": hashes,
            }
        )
    jaccards_same_seed = []
    jaccards_diff_seed = []
    jaccards_all_ident = []
    n_pairs = 0
    for app, xs in by_app.items():
        if len(xs) < 2:
            continue
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                a, b = xs[i], xs[j]
                inter = len(a["hashes"] & b["hashes"])
                union = len(a["hashes"] | b["hashes"])
                jac = (inter / union) if union else None
                n_pairs += 1
                if jac is not None:
                    jaccards_all_ident.append(jac)
                    if a.get("agent_seed") is not None and a.get("agent_seed") == b.get(
                        "agent_seed"
                    ):
                        jaccards_same_seed.append(jac)
                    else:
                        jaccards_diff_seed.append(jac)
    return {
        "n_identical_pairs_with_screens": n_pairs,
        "jaccard_all_identical_pairs": summarize_dist(jaccards_all_ident)
        if jaccards_all_ident
        else None,
        "jaccard_identical_same_seed": summarize_dist(jaccards_same_seed)
        if jaccards_same_seed
        else None,
        "jaccard_identical_different_seed": summarize_dist(jaccards_diff_seed)
        if jaccards_diff_seed
        else None,
    }


def pair_type(ma: str, mb: str) -> str | None:
    s = {ma, mb}
    if s == {"identical"}:
        return "identical-identical"
    if s == {"identical", "varied"}:
        return "identical-varied"
    if s == {"varied"}:
        return "varied-varied"
    return None


def graph_pairwise(usable: list[dict]) -> dict:
    """Sequence-proximity graphs (Chapter B run2 builder), flattened w_cum tensor."""
    by_app = defaultdict(list)
    build_fail = 0
    for s in usable:
        events, _ = load_frida_trace(Path(s["events_path"]))
        g = graph_from_events(events, package=s["app_id"])
        n_active, n_edges, density = topology(g)
        vec = session_vector(g, channel="w_cum")
        s["n_active_seq"] = n_active
        s["n_edges_seq"] = n_edges
        s["density_seq"] = density
        s["vec"] = vec
        s["vec_norm"] = float(np.linalg.norm(vec))
        by_app[s["app_id"]].append(s)

    buckets: dict[str, list[dict]] = defaultdict(list)
    empty_empty = Counter()
    for app, xs in by_app.items():
        if len(xs) < 2:
            continue
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                a, b = xs[i], xs[j]
                ptype = pair_type(a.get("session_mode") or "", b.get("session_mode") or "")
                if ptype is None:
                    continue
                d = distances(a["vec"], b["vec"], channel="w_cum")
                both_empty = a["n_edges_seq"] == 0 and b["n_edges_seq"] == 0
                rec = {
                    "app_id": app,
                    "pair": [a["session_id"], b["session_id"]],
                    "pair_type": ptype,
                    "same_agent_seed": a.get("agent_seed") is not None
                    and a.get("agent_seed") == b.get("agent_seed"),
                    "both_zero_edges": both_empty,
                    "gae_pair": (a["n_active_seq"] >= 2 and a["n_edges_seq"] >= 1)
                    and (b["n_active_seq"] >= 2 and b["n_edges_seq"] >= 1),
                    **d,
                }
                buckets[ptype].append(rec)
                if both_empty:
                    empty_empty[ptype] += 1

    def _block(recs: list[dict], key: str, pred=None) -> dict:
        xs = [r[key] for r in recs if (pred is None or pred(r)) and r[key] == r[key]]
        return summarize_dist(xs) if xs else {"n": 0}

    summary = {}
    for ptype, recs in buckets.items():
        summary[ptype] = {
            "n_pairs": len(recs),
            "n_both_zero_edges": int(empty_empty[ptype]),
            "n_gae_pairs": sum(1 for r in recs if r["gae_pair"]),
            "all_pairs": {
                "cosine_combined": _block(recs, "cosine_combined"),
                "frobenius_combined": _block(recs, "frobenius_combined"),
                "cosine_adj": _block(recs, "cosine_adj"),
                "frobenius_adj": _block(recs, "frobenius_adj"),
            },
            "gae_pairs": {
                "cosine_combined": _block(recs, "cosine_combined", lambda r: r["gae_pair"]),
                "frobenius_combined": _block(recs, "frobenius_combined", lambda r: r["gae_pair"]),
                "cosine_adj": _block(recs, "cosine_adj", lambda r: r["gae_pair"]),
                "frobenius_adj": _block(recs, "frobenius_adj", lambda r: r["gae_pair"]),
            },
        }

    tests = {}
    ii = [r["cosine_combined"] for r in buckets.get("identical-identical", [])]
    iv = [r["cosine_combined"] for r in buckets.get("identical-varied", [])]
    vv = [r["cosine_combined"] for r in buckets.get("varied-varied", [])]
    ii_g = [
        r["cosine_combined"]
        for r in buckets.get("identical-identical", [])
        if r["gae_pair"]
    ]
    iv_g = [
        r["cosine_combined"]
        for r in buckets.get("identical-varied", [])
        if r["gae_pair"]
    ]
    if len(ii) >= 2 and len(iv) >= 2:
        tests["cosine_combined_ii_vs_iv"] = mann_whitney(
            ii, iv, label_x="identical-identical", label_y="identical-varied"
        )
    if len(ii_g) >= 2 and len(iv_g) >= 2:
        tests["cosine_combined_ii_vs_iv_gae"] = mann_whitney(
            ii_g, iv_g, label_x="identical-identical_gae", label_y="identical-varied_gae"
        )
    if len(ii) >= 2 and len(vv) >= 2:
        tests["cosine_combined_ii_vs_vv"] = mann_whitney(
            ii, vv, label_x="identical-identical", label_y="varied-varied"
        )

    ii_f = [r["frobenius_combined"] for r in buckets.get("identical-identical", [])]
    iv_f = [r["frobenius_combined"] for r in buckets.get("identical-varied", [])]
    if len(ii_f) >= 2 and len(iv_f) >= 2:
        tests["frobenius_combined_ii_vs_iv"] = mann_whitney(
            ii_f, iv_f, label_x="identical-identical", label_y="identical-varied"
        )

    return {
        "builder": "abrg.chapter_b.graphs_seq.graph_from_events (update_graph_sequence, k=5, zero static)",
        "flattening": "abrg.chapter_c.tensorize.session_vector channel=w_cum (node block + outgoing-share adj)",
        "cosine_is_distance": "1 - cosine_similarity (tensorize._cosine)",
        "n_apps": len(by_app),
        "n_sessions_tensorized": sum(len(v) for v in by_app.values()),
        "build_fail": build_fail,
        "by_pair_type": summary,
        "tests": tests,
    }


def original_metadata_checks(usable_original: list[dict]) -> dict:
    shas = Counter()
    pm = Counter()
    snap = Counter()
    duration = Counter()
    arm = Counter()
    hook_ver = Counter()
    for s in usable_original:
        src = s.get("source_meta") or {}
        shas[src.get("hook_script_sha256") or "MISSING"] += 1
        pm[str(src.get("pm_clear_rc", "MISSING"))] += 1
        snap[str(src.get("snapshot_restored", "MISSING"))] += 1
        duration[str(src.get("duration_sec", "MISSING"))] += 1
        arm[str(src.get("arm", "MISSING"))] += 1
        hook_ver[str(src.get("hook_version", "MISSING"))] += 1
    return {
        "n": len(usable_original),
        "hook_script_sha256": dict(shas),
        "pm_clear_rc": dict(pm),
        "snapshot_restored": dict(snap),
        "duration_sec": dict(duration),
        "arm": dict(arm),
        "hook_version": dict(hook_ver),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = load_sessions(EXPORT_ROOT)
    passed = pass_sessions(rows)

    packaging = {
        "export_layout": "metadata.json + events.jsonl only (no llm_actions.jsonl)",
        "n_indexed": len(rows),
        "n_usable": len(passed),
        "n_v2_packaged_llm_actions": len(list(V2_PACKAGED.glob("*/*_llm_actions.jsonl"))),
        "extend_actions_in_abrg_export": False,
        "collection_trees_on_disk": {
            "original_bulk": "$CONTEXTDROID_ROOT/logs/bulk_llm_benign_v2",
            "extend": "$CONTEXTDROID_ROOT/logs/v2_extend_collection",
            "canary": "$CONTEXTDROID_ROOT/logs/v2_extend_canary",
        },
        "join_rule": "export sessions_index → source_meta_path sibling *_llm_actions.jsonl; fallback datasets/v2/sessions",
        "note_bulk_larger_than_export": (
            "ContextDroid logs/bulk_llm_benign_v2 contains more *_llm_actions.jsonl "
            "than the curated original 168. Measurements use the export index, not the raw tree."
        ),
    }

    joined = []
    n_actions_found = 0
    n_actions_missing = 0
    missing_list = []
    for r in rows:
        src = load_source_meta(r.source_meta_path)
        ap = _actions_path(r, src)
        rec = {
            "app_id": r.app_id,
            "session_id": r.session_id,
            "export_dir_name": r.export_dir_name,
            "batch": r.batch,
            "pass": r.reference_tier_pass,
            "events_path": r.events_path,
            "mapped_meta": r.mapped_meta,
            "source_meta": src,
            "session_mode": (src or {}).get("session_mode"),
            "agent_seed": (src or {}).get("agent_seed"),
            "pm_clear_rc": (src or {}).get("pm_clear_rc"),
            "actions_path": str(ap) if ap else None,
        }
        if ap:
            rec["steps"] = _load_steps(ap)
            n_actions_found += 1
        else:
            rec["steps"] = []
            n_actions_missing += 1
            missing_list.append(
                {"session_id": r.session_id, "batch": r.batch, "pass": r.reference_tier_pass}
            )
        joined.append(rec)

    packaging["n_indexed_with_actions"] = n_actions_found
    packaging["n_indexed_missing_actions"] = n_actions_missing
    packaging["missing_actions_sample"] = missing_list[:20]

    usable = [s for s in joined if s["pass"]]
    usable_with_steps = [s for s in usable if s["steps"]]
    original_usable = [s for s in usable if s["batch"] == "original"]
    original_with_steps = [s for s in original_usable if s["steps"]]

    # M1 populations
    m1_all_usable = census_steps(usable_with_steps)
    m1_original = census_steps(original_with_steps)
    m1_extend = census_steps(
        [s for s in usable_with_steps if s["batch"] == "extend"]
    )
    m1_canary = census_steps(
        [s for s in usable_with_steps if s["batch"] == "canary"]
    )

    # Clock diagnostic on original usable (smaller + packaged)
    clock_rows = []
    for s in original_with_steps:
        all_ts, mapped_ts = _event_timestamps(Path(s["events_path"]))
        clock_rows.append({**s, "event_ts_all": all_ts, "event_ts_mapped": mapped_ts})
    clock = clock_diagnostic(clock_rows)

    m1 = {
        "population_note": (
            "Primary census is usable sessions in the v2_extended analysis set "
            "that have a collection *_llm_actions.jsonl. Original 168 are packaged "
            "under datasets/v2/sessions; extend/canary actions are in ContextDroid "
            "collection logs, not in the ABRG export."
        ),
        "packaging": packaging,
        "usable_all_with_actions": {
            k: v for k, v in m1_all_usable.items() if k != "per_session"
        },
        "usable_original": {k: v for k, v in m1_original.items() if k != "per_session"},
        "usable_extend": {k: v for k, v in m1_extend.items() if k != "per_session"},
        "usable_canary": {k: v for k, v in m1_canary.items() if k != "per_session"},
        "clock": clock,
        "per_session_usable": m1_all_usable["per_session"],
    }

    m2_census = mode_census(usable)
    m2_overlap = screen_overlap(usable_with_steps)
    print("tensorizing", len(usable), "usable sessions…", flush=True)
    m2_graph = graph_pairwise(usable)

    orig_checks = original_metadata_checks(original_usable)
    extend_checks = original_metadata_checks(
        [s for s in usable if s["batch"] == "extend"]
    )

    hooks = hook_category_table()

    m2 = {
        "population_note": (
            "Usable = reference_tier_pass in v2_extended (n=342). session_mode and "
            "agent_seed are read from collection dynamic_metadata.json via "
            "source_meta_path; they are absent from the export metadata.json schema."
        ),
        "census": {k: v for k, v in m2_census.items() if k != "per_app"},
        "per_app_mode": m2_census["per_app"],
        "screen_hash_overlap_identical": m2_overlap,
        "pairwise_graph_distance": m2_graph,
        "original_metadata_pins": orig_checks,
        "extend_metadata_pins": extend_checks,
    }

    (OUT / "m1_phase_split.json").write_text(
        json.dumps(json_ready(m1), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT / "m2_session_mode.json").write_text(
        json.dumps(json_ready(m2), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (OUT / "hook_category_summary.json").write_text(
        json.dumps(json_ready(hooks), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print("wrote", OUT / "m1_phase_split.json")
    print("wrote", OUT / "m2_session_mode.json")
    print("M1 usable with actions", m1_all_usable["n_sessions_with_actions"])
    print("M1 steps", m1_all_usable["n_steps_total"], "bfs", m1_all_usable["prompt_hash"])
    print("M1 phases", m1_all_usable["pipeline_phase"])
    print("M2 modes", m2_census["mode_counts"])
    print("M2 seed", m2_census["identical_seed_sharing"])
    print("clock offset start", clock.get("offset_start_ms"))


if __name__ == "__main__":
    main()
