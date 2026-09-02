"""RUN 2 — unit-aligned v2 vs AndroCT representation comparison."""

from __future__ import annotations

import csv
import io
import json
import tarfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from abrg.androct.parse import parse_androct_text_stream
from abrg.androct.paths import EXPECTED_ARCHIVES, androct_inventory_dir, androct_raw_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import STATIC_SLICE
from abrg.api_category_map import HOOK_API_TO_CATEGORY
from abrg.chapter_c.graphs import load_static_for_app
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.static import zero_static_report
from abrg.trace import load_frida_trace

from abrg.chapter_b.config import (
    ANDROCT_PROTOCOL_WALL_SEC,
    HOOK_SCRIPT,
    N_NODES,
    POOLED_JUSTIFICATION,
    POOLED_METHOD,
    RUN2_DIR,
    STATIC_COORD_LABELS,
    STATIC_SLICE_DIM,
)
from abrg.chapter_b.graphs_seq import graph_from_categories, graph_from_events, topology
from abrg.chapter_b.ingest import SessionRow, event_apis, mapped_and_total, pass_sessions
from abrg.chapter_b.stats import json_ready, mann_whitney, summarize_dist, value_counts


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(obj), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def _hook_api_set() -> set[str]:
    """Distinct logEvent API name literals from the SHA-matched hook file, else HOOK_API_TO_CATEGORY."""
    import re

    apis: set[str] = set()
    if HOOK_SCRIPT.is_file():
        text = HOOK_SCRIPT.read_text(encoding="utf-8", errors="replace")
        apis.update(re.findall(r'logEvent\(\s*"([^"]+)"', text))
    if not apis:
        apis = set(HOOK_API_TO_CATEGORY)
    return apis


def _block(vals: list[float]) -> dict[str, Any]:
    d = summarize_dist(vals)
    return d


def _fire_frac(n_apps: int, n_fire: int) -> float:
    return (n_fire / n_apps) if n_apps else float("nan")


def _load_inventory_event_dists() -> dict[str, Any]:
    """Reuse AndroCT inventory artefacts (same parser; do not reimplement)."""
    inv_dir = androct_inventory_dir()
    summary = json.loads((inv_dir / "inventory_summary.json").read_text(encoding="utf-8"))
    out: dict[str, Any] = {"summary": {}, "per_app": {}}
    for label in ("benign", "malware"):
        csv_path = inv_dir / f"per_app_{label}.csv"
        mapped: list[float] = []
        total: list[float] = []
        rate: list[float] = []
        with csv_path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if str(r.get("header_only", "")).lower() in {"true", "1"}:
                    continue
                total.append(float(r["n_events"]))
                mapped.append(float(r["n_mapped"]))
                rate.append(float(r["mapped_rate"]))
        cls = summary["classes"][label]
        out["summary"][label] = {
            "n_files": cls["n_files"],
            "n_header_only": cls["n_header_only"],
            "n_effective": cls["n_effective"],
            "total_events": cls["total_events"],
            "total_mapped_events": cls["total_mapped_events"],
            "mapped_event_rate": cls["mapped_event_rate"],
            "universe_cats_active": cls["universe_cats_active"],
            "n_universe_cats_active": cls["n_universe_cats_active"],
            "category_totals": cls["category_totals"],
        }
        out["per_app"][label] = {
            "mapped": _block(mapped),
            "total": _block(total),
            "mapped_rate": _block(rate),
        }
    return out


def _parse_androct_graphs(cache_path: Path) -> dict[str, Any]:
    """
    Stream-parse AndroCT tarballs with inventory parser (yield_events=True),
    then update_graph_sequence. Cached as JSON.
    """
    if cache_path.is_file():
        print(f"[chapter_b] loading AndroCT graph cache {cache_path}", flush=True)
        return json.loads(cache_path.read_text(encoding="utf-8"))

    raw = androct_raw_dir()
    rows: dict[str, list[dict[str, Any]]] = {"benign": [], "malware": []}
    fire: dict[str, dict[str, int]] = {
        lab: {c: 0 for c in GRAPH_CATEGORY_UNIVERSE} for lab in ("benign", "malware")
    }
    n_eff: dict[str, int] = {"benign": 0, "malware": 0}

    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        path = raw / fname
        print(f"[chapter_b] AndroCT parse+graph {label} {fname} …", flush=True)
        n = 0
        with tarfile.open(path, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                if member.name.split("/", 1)[0] != inner:
                    raise SystemExit(f"year-dir mismatch {member.name}")
                n += 1
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                try:
                    report, events = parse_androct_text_stream(
                        text, path=member.name, label=label, yield_events=True
                    )
                finally:
                    text.detach()
                if report.header_only:
                    continue
                n_eff[label] += 1
                cats = [e.category for e in events or [] if e.category]
                del events
                g = graph_from_categories(cats, package=report.sha256)
                n_active, n_edges, dens = topology(g)
                active = sorted(report.active_categories)
                for c in active:
                    if c in fire[label]:
                        fire[label][c] += 1
                rows[label].append(
                    {
                        "sha256": report.sha256,
                        "path": member.name,
                        "n_events": report.n_events,
                        "n_mapped": report.n_mapped_events,
                        "mapped_rate": report.mapped_rate,
                        "n_active": n_active,
                        "n_edges": n_edges,
                        "density": dens,
                        "n_active_cats": len(active),
                        "active_categories": active,
                    }
                )
                if n % 100 == 0:
                    print(
                        f"  … {label} files={n} effective={n_eff[label]}",
                        flush=True,
                    )
        print(f"  {label} done files={n} effective={n_eff[label]}", flush=True)

    payload = {"rows": rows, "fire_counts": fire, "n_effective": n_eff}
    _dump(cache_path, payload)
    return payload


def _static_vector(report) -> np.ndarray:
    vec: list[float] = []
    for cat in GRAPH_CATEGORY_UNIVERSE:
        node = report.nodes[cat]
        vec.extend([node.s_v, node.declared_v, *list(node.gate_v), node.reach_v, node.epoch_v])
    arr = np.asarray(vec, dtype=np.float64)
    assert arr.size == N_NODES * STATIC_SLICE_DIM
    return arr


def _v2_session_and_pooled(pass_rows: list[SessionRow]) -> dict[str, Any]:
    by_app: dict[str, list[SessionRow]] = defaultdict(list)
    for r in pass_rows:
        by_app[r.app_id].append(r)
    for app in by_app:
        by_app[app].sort(key=lambda s: s.session_index_within_app)

    sess_rows: list[dict[str, Any]] = []
    pooled_rows: list[dict[str, Any]] = []
    fire_sess = {c: 0 for c in GRAPH_CATEGORY_UNIVERSE}
    fire_app = {c: 0 for c in GRAPH_CATEGORY_UNIVERSE}
    hooks_session_sets: list[list[str]] = []
    hooks_union: set[str] = set()
    walls: list[float] = []
    mapped_ps: list[float] = []
    total_ps: list[float] = []

    for app_id, sess in sorted(by_app.items()):
        concat: list[str] = []
        app_cats: set[str] = set()
        for r in sess:
            events, _rep = load_frida_trace(Path(r.events_path))
            mapped, total, cat_counts, _mapped_apis = mapped_and_total(Path(r.events_path))
            g = graph_from_events(events, package=app_id)
            n_active, n_edges, dens = topology(g)
            fired_cats = sorted(c for c, n in cat_counts.items() if n > 0)
            for c in fired_cats:
                fire_sess[c] += 1
                app_cats.add(c)
            apis = sorted(event_apis(Path(r.events_path)))
            hooks_session_sets.append(apis)
            hooks_union.update(apis)
            wall = float(r.wall_duration_s) if r.wall_duration_s is not None else float("nan")
            walls.append(wall)
            mapped_ps.append((mapped / wall) if wall and wall > 0 else float("nan"))
            total_ps.append((total / wall) if wall and wall > 0 else float("nan"))
            sess_rows.append(
                {
                    "unit": "per_session",
                    "app_id": app_id,
                    "export_dir_name": r.export_dir_name,
                    "batch": r.batch,
                    "mapped": mapped,
                    "total": total,
                    "mapped_rate": (mapped / total) if total else 0.0,
                    "n_active": n_active,
                    "n_edges": n_edges,
                    "density": dens,
                    "wall_duration_s": r.wall_duration_s,
                    "n_hooks_fired": len(apis),
                    "active_categories": fired_cats,
                }
            )
            concat.extend(e.category for e in events)
        for c in app_cats:
            fire_app[c] += 1
        gp = graph_from_categories(concat, package=app_id)
        na, ne, dens = topology(gp)
        # pooled event counts = sum of sessions (concatenated stream)
        mapped_sum = sum(x["mapped"] for x in sess_rows if x["app_id"] == app_id)
        total_sum = sum(x["total"] for x in sess_rows if x["app_id"] == app_id)
        wall_sum = sum(
            float(x["wall_duration_s"])
            for x in sess_rows
            if x["app_id"] == app_id and x["wall_duration_s"] is not None
        )
        pooled_rows.append(
            {
                "unit": "per_app_pooled",
                "app_id": app_id,
                "n_sessions": len(sess),
                "mapped": mapped_sum,
                "total": total_sum,
                "mapped_rate": (mapped_sum / total_sum) if total_sum else 0.0,
                "n_active": na,
                "n_edges": ne,
                "density": dens,
                "wall_duration_s": wall_sum,
                "n_concat_mapped": len(concat),
                "active_categories": sorted(app_cats),
            }
        )

    return {
        "session_rows": sess_rows,
        "pooled_rows": pooled_rows,
        "fire_session": fire_sess,
        "fire_app": fire_app,
        "n_sessions": len(sess_rows),
        "n_apps": len(pooled_rows),
        "hooks_union": sorted(hooks_union),
        "hooks_per_session": [sorted(s) for s in hooks_session_sets],
        "wall": walls,
        "mapped_per_sec": mapped_ps,
        "total_per_sec": total_ps,
    }


def _androct_blocks(ac: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for label in ("benign", "malware"):
        rows = ac["rows"][label]
        n_app = len(rows)
        fire = ac["fire_counts"][label]
        mapped = [float(r["n_mapped"]) for r in rows]
        total = [float(r["n_events"]) for r in rows]
        rate = [float(r["mapped_rate"]) for r in rows]
        active = [int(r["n_active"]) for r in rows]
        edges = [int(r["n_edges"]) for r in rows]
        dens = [float(r["density"]) for r in rows]
        le2 = sum(1 for e in edges if e <= 2)
        out[label] = {
            "n": n_app,
            "mapped": _block(mapped),
            "total": _block(total),
            "mapped_rate": _block(rate),
            "n_active": _block(active),
            "n_active_value_counts": value_counts(active),
            "n_edges": _block(edges),
            "frac_le2_edges": (le2 / n_app) if n_app else float("nan"),
            "n_le2_edges": le2,
            "density": _block(dens),
            "wall_protocol_s": ANDROCT_PROTOCOL_WALL_SEC,
            "events_per_sec": _block([t / ANDROCT_PROTOCOL_WALL_SEC for t in total]),
            "mapped_per_sec": _block([m / ANDROCT_PROTOCOL_WALL_SEC for m in mapped]),
            "category_fire_frac": {
                c: _fire_frac(n_app, int(fire.get(c, 0))) for c in GRAPH_CATEGORY_UNIVERSE
            },
            "category_fire_n": {c: int(fire.get(c, 0)) for c in GRAPH_CATEGORY_UNIVERSE},
            "dead_categories": [
                c for c in GRAPH_CATEGORY_UNIVERSE if int(fire.get(c, 0)) == 0
            ],
        }
    return out


def _unit_block(rows: list[dict[str, Any]], fire: dict[str, int], n_units: int) -> dict[str, Any]:
    mapped = [float(r["mapped"]) for r in rows]
    total = [float(r["total"]) for r in rows]
    rate = [float(r["mapped_rate"]) for r in rows]
    active = [int(r["n_active"]) for r in rows]
    edges = [int(r["n_edges"]) for r in rows]
    dens = [float(r["density"]) for r in rows]
    walls = [float(r["wall_duration_s"]) for r in rows if r.get("wall_duration_s") is not None]
    le2 = sum(1 for e in edges if e <= 2)
    return {
        "n": n_units,
        "mapped": _block(mapped),
        "total": _block(total),
        "mapped_rate": _block(rate),
        "n_active": _block(active),
        "n_active_value_counts": value_counts(active),
        "n_edges": _block(edges),
        "frac_le2_edges": (le2 / n_units) if n_units else float("nan"),
        "n_le2_edges": le2,
        "density": _block(dens),
        "wall_duration_s": _block(walls),
        "category_fire_frac": {
            c: _fire_frac(n_units, int(fire.get(c, 0))) for c in GRAPH_CATEGORY_UNIVERSE
        },
        "category_fire_n": {c: int(fire.get(c, 0)) for c in GRAPH_CATEGORY_UNIVERSE},
        "dead_categories": [c for c in GRAPH_CATEGORY_UNIVERSE if int(fire.get(c, 0)) == 0],
    }


def _v2_static(pass_rows: list[SessionRow]) -> dict[str, Any]:
    by_app: dict[str, list[SessionRow]] = defaultdict(list)
    for r in pass_rows:
        by_app[r.app_id].append(r)
    cache: dict[str, Any] = {}
    vecs: list[np.ndarray] = []
    resolved: list[str] = []
    fallback: list[str] = []
    norms: list[float] = []
    n_zero = 0
    for app_id, sess in sorted(by_app.items()):
        report, ok = load_static_for_app(sess, cache)
        if not ok:
            fallback.append(app_id)
            arr = _static_vector(zero_static_report(app_id))
        else:
            resolved.append(app_id)
            arr = _static_vector(report)
        nrm = float(np.linalg.norm(arr))
        norms.append(nrm)
        if nrm < 1e-12:
            n_zero += 1
        vecs.append(arr)
    mat = np.stack(vecs, axis=0) if vecs else np.zeros((0, N_NODES * STATIC_SLICE_DIM))
    per_coord = []
    for j, lab in enumerate(STATIC_COORD_LABELS):
        # pool 22 nodes: column j, j+7, j+14, ...
        cols = mat[:, j::STATIC_SLICE_DIM].reshape(-1) if mat.size else np.array([])
        per_app_mean = mat[:, j::STATIC_SLICE_DIM].mean(axis=1) if mat.size else np.array([])
        per_coord.append(
            {
                "coordinate": lab,
                "index": j,
                "all_nodes_all_apps": _block(cols.tolist()),
                "per_app_mean_over_22_nodes": _block(per_app_mean.tolist()),
            }
        )
    return {
        "n_apps": len(by_app),
        "n_static_resolved": len(resolved),
        "n_static_fallback": len(fallback),
        "resolved_apps": resolved,
        "fallback_apps": fallback,
        "n_all_zero_static_vector": n_zero,
        "l2_norm": _block(norms),
        "per_coordinate": per_coord,
        "static_slice_dim": STATIC_SLICE_DIM,
        "n_nodes": N_NODES,
    }


def _androct_static() -> dict[str, Any]:
    """Static slice from Run-2 corpus cache tensors (GAE-eligible; same graph_to_tensors layout)."""
    try:
        bundle = load_corpus_cache()
    except FileNotFoundError as exc:
        return {"error": str(exc), "available": False}
    by_label: dict[str, list[np.ndarray]] = {"benign": [], "malware": []}
    n_zero = {"benign": 0, "malware": 0}
    for sha, t in bundle.tensors.items():
        lab = str(t.get("label", ""))
        if lab not in by_label:
            continue
        x = t["x"]
        if hasattr(x, "detach"):
            x = x.detach().cpu().numpy()
        sl = np.asarray(x[:, :STATIC_SLICE], dtype=np.float64)
        vec = sl.reshape(-1)
        by_label[lab].append(vec)
        if float(np.linalg.norm(vec)) < 1e-12:
            n_zero[lab] += 1
    out: dict[str, Any] = {
        "available": True,
        "source": "abrg.androct.run2_corpus.load_corpus_cache tensors x[:, :STATIC_SLICE]",
        "static_slice": STATIC_SLICE,
        "n_eligible_tensors": len(bundle.tensors),
        "classes": {},
    }
    for lab, vecs in by_label.items():
        mat = np.stack(vecs, axis=0) if vecs else np.zeros((0, N_NODES * STATIC_SLICE_DIM))
        norms = [float(np.linalg.norm(v)) for v in vecs]
        per_coord = []
        for j, name in enumerate(STATIC_COORD_LABELS):
            cols = mat[:, j::STATIC_SLICE_DIM].reshape(-1) if mat.size else np.array([])
            per_app_mean = mat[:, j::STATIC_SLICE_DIM].mean(axis=1) if mat.size else np.array([])
            per_coord.append(
                {
                    "coordinate": name,
                    "index": j,
                    "all_nodes_all_apps": _block(cols.tolist()),
                    "per_app_mean_over_22_nodes": _block(per_app_mean.tolist()),
                }
            )
        out["classes"][lab] = {
            "n": len(vecs),
            "n_all_zero": n_zero[lab],
            "l2_norm": _block(norms),
            "per_coordinate": per_coord,
        }
    return out


def run2(pass_rows: list[SessionRow], out_dir: Path = RUN2_DIR) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[chapter_b] run2 unit alignment: v2 per-session + per-app pooled …", flush=True)
    v2 = _v2_session_and_pooled(pass_rows)
    inv = _load_inventory_event_dists()
    ac_cache = out_dir / "androct_graph_cache.json"
    ac = _parse_androct_graphs(ac_cache)
    ac_blocks = _androct_blocks(ac)

    sess_block = _unit_block(v2["session_rows"], v2["fire_session"], v2["n_sessions"])
    pool_block = _unit_block(v2["pooled_rows"], v2["fire_app"], v2["n_apps"])
    # events/sec for v2
    sess_block["events_per_sec"] = _block(v2["total_per_sec"])
    sess_block["mapped_per_sec"] = _block(v2["mapped_per_sec"])
    pool_block["events_per_sec"] = _block(
        [
            r["total"] / r["wall_duration_s"]
            for r in v2["pooled_rows"]
            if r.get("wall_duration_s")
        ]
    )
    pool_block["mapped_per_sec"] = _block(
        [
            r["mapped"] / r["wall_duration_s"]
            for r in v2["pooled_rows"]
            if r.get("wall_duration_s")
        ]
    )

    def col(rows: list[dict[str, Any]], key: str) -> list[float]:
        return [float(r[key]) for r in rows]

    mwu: dict[str, Any] = {}
    material: list[str] = []
    keymap = {
        "mapped": "n_mapped",
        "total": "n_events",
        "mapped_rate": "mapped_rate",
        "n_active": "n_active",
        "n_edges": "n_edges",
        "density": "density",
    }
    for key, name in (
        ("mapped", "mapped_events"),
        ("total", "total_events"),
        ("mapped_rate", "mapped_event_rate"),
        ("n_active", "active_nodes"),
        ("n_edges", "edges"),
        ("density", "density"),
        ("wall_duration_s", "trace_or_session_length"),
    ):
        if key == "wall_duration_s":
            mwu[name] = {
                "note": (
                    "AndroCT traces have no wall-clock. Protocol duration is "
                    f"{ANDROCT_PROTOCOL_WALL_SEC}s for every effective app. "
                    "MWU on wall seconds is not computed. Event-count length is metric total_events."
                )
            }
            continue
        xv = col(v2["pooled_rows"], key)
        ya = [float(r[keymap[key]]) for r in ac["rows"]["benign"]]
        test = mann_whitney(xv, ya, label_x="v2_per_app_pooled", label_y="androct_benign")
        mwu[name] = test
        if test.get("material_by_declared_rule"):
            material.append(name)

    # Category table: v2 per-app fire vs AndroCT benign fire, ranked by difference
    n_v2 = v2["n_apps"]
    n_ab = ac_blocks["benign"]["n"]
    cat_rows = []
    for c in GRAPH_CATEGORY_UNIVERSE:
        fv = _fire_frac(n_v2, v2["fire_app"][c])
        fa = ac_blocks["benign"]["category_fire_frac"][c]
        cat_rows.append(
            {
                "category": c,
                "v2_n_apps_fire": v2["fire_app"][c],
                "v2_frac": fv,
                "androct_benign_n_apps_fire": ac_blocks["benign"]["category_fire_n"][c],
                "androct_benign_frac": fa,
                "diff_v2_minus_androct": fv - fa,
            }
        )
    cat_rows.sort(key=lambda r: -abs(r["diff_v2_minus_androct"]))
    specials = {}
    for c in ("sms", "dynamic_code_loading", "telephony", "camera", "clipboard"):
        specials[c] = {
            "v2_n_apps": v2["fire_app"][c],
            "v2_frac": _fire_frac(n_v2, v2["fire_app"][c]),
            "androct_benign_n": ac_blocks["benign"]["category_fire_n"][c],
            "androct_malware_n": ac_blocks["malware"]["category_fire_n"][c],
            "androct_benign_dead": c in ac_blocks["benign"]["dead_categories"],
            "androct_malware_dead": c in ac_blocks["malware"]["dead_categories"],
            "v2_dead": c in pool_block["dead_categories"],
        }

    # Hooks
    hooked = sorted(_hook_api_set())
    union = set(v2["hooks_union"])
    never = sorted(set(hooked) - union)
    per_sess_n = [len(s) for s in v2["hooks_per_session"]]
    n_sess_fire: dict[str, int] = Counter()
    for s in v2["hooks_per_session"]:
        for h in set(s):
            n_sess_fire[h] += 1

    # Spearman mapped-rate vs wall (session)
    walls = np.asarray(v2["wall"], dtype=np.float64)
    mapped_s = np.asarray([r["mapped"] for r in v2["session_rows"]], dtype=np.float64)
    total_s = np.asarray([r["total"] for r in v2["session_rows"]], dtype=np.float64)
    mask = np.isfinite(walls) & (walls > 0)
    sp_mapped = spearmanr(mapped_s[mask], walls[mask]) if mask.sum() >= 3 else None
    sp_total = spearmanr(total_s[mask], walls[mask]) if mask.sum() >= 3 else None
    sp_mapped_rate = (
        spearmanr(np.asarray(v2["mapped_per_sec"], dtype=np.float64)[mask], walls[mask])
        if mask.sum() >= 3
        else None
    )

    def _sp(res) -> dict[str, Any] | None:
        if res is None:
            return None
        return {"rho": float(res.statistic), "p_value": float(res.pvalue), "n": int(mask.sum())}

    print("[chapter_b] run2 static slices …", flush=True)
    v2_static = _v2_static(pass_rows)
    ac_static = _androct_static()

    # screens: not in export
    screens = {
        "in_export": False,
        "export_files_per_session": ["metadata.json", "events.jsonl"],
        "note": (
            "v2_extended export does not include exploration logs "
            "(llm_actions.jsonl / navigation artifacts). Distinct activities "
            "or screens per session are not computable from the export."
        ),
    }

    comparison = {
        "unit_alignment": {
            "method": POOLED_METHOD,
            "justification": POOLED_JUSTIFICATION,
            "per_session_n": v2["n_sessions"],
            "per_app_pooled_n": v2["n_apps"],
            "androct_unit": "one whole-trace graph per app (effective traces)",
            "builder": "abrg.androct.graph_build.update_graph_sequence",
            "k_burst": 5,
            "static_for_topology": "zero_static_report (static does not change act_count/edges)",
        },
        "v2_per_session": sess_block,
        "v2_per_app_pooled": pool_block,
        "androct_benign": ac_blocks["benign"],
        "androct_malware": ac_blocks["malware"],
        "inventory_event_dists_reused": inv["per_app"],
        "mwu_v2_pooled_vs_androct_benign": mwu,
        "mwu_material_metrics": material,
        "category_fire": cat_rows,
        "special_categories": specials,
        "dead_v2_per_app": pool_block["dead_categories"],
        "dead_androct_benign": ac_blocks["benign"]["dead_categories"],
        "dead_androct_malware": ac_blocks["malware"]["dead_categories"],
        "static_v2": v2_static,
        "static_androct": ac_static,
        "event_yield": {
            "v2_session_wall_s": _block(v2["wall"]),
            "v2_events_per_sec": _block(v2["total_per_sec"]),
            "v2_mapped_per_sec": _block(v2["mapped_per_sec"]),
            "androct_protocol_wall_s": ANDROCT_PROTOCOL_WALL_SEC,
            "androct_benign_events_per_sec": ac_blocks["benign"]["events_per_sec"],
            "androct_benign_mapped_per_sec": ac_blocks["benign"]["mapped_per_sec"],
            "androct_malware_events_per_sec": ac_blocks["malware"]["events_per_sec"],
            "androct_malware_mapped_per_sec": ac_blocks["malware"]["mapped_per_sec"],
            "spearman_mapped_vs_wall": _sp(sp_mapped),
            "spearman_total_vs_wall": _sp(sp_total),
            "spearman_mapped_per_sec_vs_wall": _sp(sp_mapped_rate),
        },
        "hooks": {
            "scope": "all type==event api fields (including lifecycle/reflection/navigation dropped from graphs)",
            "hooked_api_set_n": len(hooked),
            "hooked_api_set": hooked,
            "fired_corpus_wide": sorted(union),
            "fired_corpus_wide_n": len(union),
            "never_fired": never,
            "never_fired_n": len(never),
            "n_hooks_fired_per_session": _block([float(x) for x in per_sess_n]),
            "n_sessions_hook_fired": dict(sorted(n_sess_fire.items(), key=lambda kv: (-kv[1], kv[0]))),
        },
        "screens": screens,
    }

    _dump(out_dir / "comparison.json", comparison)
    _dump(out_dir / "v2_units.json", {"session": v2["session_rows"], "pooled": v2["pooled_rows"]})
    _write_csv(
        out_dir / "category_fire.csv",
        cat_rows,
        [
            "category",
            "v2_n_apps_fire",
            "v2_frac",
            "androct_benign_n_apps_fire",
            "androct_benign_frac",
            "diff_v2_minus_androct",
        ],
    )
    _write_csv(
        out_dir / "v2_per_session.csv",
        v2["session_rows"],
        [
            "app_id",
            "export_dir_name",
            "batch",
            "mapped",
            "total",
            "mapped_rate",
            "n_active",
            "n_edges",
            "density",
            "wall_duration_s",
        ],
    )
    _write_csv(
        out_dir / "v2_per_app_pooled.csv",
        v2["pooled_rows"],
        [
            "app_id",
            "n_sessions",
            "mapped",
            "total",
            "mapped_rate",
            "n_active",
            "n_edges",
            "density",
            "wall_duration_s",
        ],
    )
    _write_csv(
        out_dir / "androct_benign_graphs.csv",
        ac["rows"]["benign"],
        ["sha256", "path", "n_events", "n_mapped", "mapped_rate", "n_active", "n_edges", "density"],
    )
    _write_csv(
        out_dir / "androct_malware_graphs.csv",
        ac["rows"]["malware"],
        ["sha256", "path", "n_events", "n_mapped", "mapped_rate", "n_active", "n_edges", "density"],
    )
    print(
        f"[chapter_b] run2 done v2_sess={v2['n_sessions']} v2_apps={v2['n_apps']} "
        f"androct_b={ac_blocks['benign']['n']} androct_m={ac_blocks['malware']['n']}",
        flush=True,
    )
    return comparison
