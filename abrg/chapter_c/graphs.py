"""Session graph construction + δ retention (timed UpdateGraph path)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import curve_fit

from abrg.chapter_c.config import (
    DELTA_SEC_PIN,
    K_BURST_PIN,
    LAMBDA_REC_PIN,
    WINDOW_SEC_PIN,
)
from abrg.chapter_c.ingest import SessionMeta, Stage0Report, sessions_for_app
from abrg.chapter_c.tensorize import median_iqr
from abrg.config import DELTA_SEC, K_BURST, LAMBDA_REC
from abrg.graph import ABRGGraph, build_initial_graph, update_graph
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.static import StaticReport, analyze_apk_static, zero_static_report
from abrg.trace import TraceEvent, load_frida_trace


@dataclass
class SessionGraphStats:
    app_id: str
    session_id: str
    export_dir_name: str
    session_index_within_app: int
    mapped_events: int
    n_active_nodes: int
    n_edges: int
    density: float
    static_resolved: bool
    lambda_rec: float


@dataclass
class GraphBuildBundle:
    graphs: dict[str, ABRGGraph]  # key = f"{app_id}::{export_dir_name}"
    stats: list[SessionGraphStats]
    static_resolved_apps: list[str]
    static_fallback_apps: list[str]
    static_mode_label: str
    delta_retention: dict[str, Any]
    builder_note: dict[str, Any]
    pins: dict[str, Any]


def graph_key(app_id: str, export_dir_name: str) -> str:
    return f"{app_id}::{export_dir_name}"


def resolve_apk_path(session: SessionMeta) -> Path | None:
    sp = session.source_meta_path
    if not sp:
        return None
    p = Path(sp)
    if not p.is_file():
        return None
    meta = json.loads(p.read_text(encoding="utf-8"))
    raw = meta.get("apk_path")
    if not raw:
        return None
    apk = Path(raw)
    return apk if apk.is_file() else None


def load_static_for_app(
    sessions: list[SessionMeta],
    cache: dict[str, StaticReport | None],
) -> tuple[StaticReport, bool]:
    app_id = sessions[0].app_id
    if app_id in cache:
        rep = cache[app_id]
        if rep is None:
            return zero_static_report(app_id), False
        return rep, True
    for s in sessions:
        apk = resolve_apk_path(s)
        if apk is None:
            continue
        try:
            rep = analyze_apk_static(apk)
            cache[app_id] = rep
            return rep, True
        except Exception:  # noqa: BLE001
            continue
    cache[app_id] = None
    return zero_static_report(app_id), False


def build_session_graph_full(
    events: list[TraceEvent],
    static_report: StaticReport,
    *,
    k_burst: int = K_BURST_PIN,
    delta_sec: float = DELTA_SEC_PIN,
    lambda_rec: float = LAMBDA_REC_PIN,
    window_sec: float = WINDOW_SEC_PIN,
) -> ABRGGraph:
    """
    Timed UpdateGraph with 60s cumulative processing windows (full design).
    Returns the final cumulative graph after the last window so λ_rec decay
    fires between windows (whole-session single window leaves w_cum≡w_rec).
    """
    from abrg.windows import WindowMode, split_events

    graph = build_initial_graph(static_report=static_report)
    windows = split_events(events, WindowMode.TIME_SEC, window_sec)
    if not windows:
        update_graph(
            graph,
            events,
            k_burst=k_burst,
            delta_sec=delta_sec,
            lambda_rec=lambda_rec,
        )
        assert len(graph.nodes) == len(GRAPH_CATEGORY_UNIVERSE)
        return graph
    for window in windows:
        update_graph(
            graph,
            window.events,
            t_now=window.t_end_sec,
            k_burst=k_burst,
            delta_sec=delta_sec,
            lambda_rec=lambda_rec,
        )
    assert len(graph.nodes) == len(GRAPH_CATEGORY_UNIVERSE)
    return graph


def measure_delta_retention_for_events(
    events: list[TraceEvent],
    *,
    k_burst: int = K_BURST_PIN,
    delta_sec: float = DELTA_SEC_PIN,
) -> tuple[int, int]:
    """
    Among ordered pairs with sequence distance ≤ k_burst (and u≠v),
    count how many also satisfy Δt ≤ delta_sec.
    Returns (n_k_candidates, n_also_delta).
    """
    n = len(events)
    n_k = 0
    n_d = 0
    for i in range(n):
        t_u = events[i].timestamp_ms / 1000.0
        u = events[i].category
        for j in range(i + 1, min(i + k_burst + 1, n)):
            v = events[j].category
            if u == v:
                continue
            n_k += 1
            t_v = events[j].timestamp_ms / 1000.0
            if t_v - t_u <= delta_sec:
                n_d += 1
    return n_k, n_d


def _fit_retention_curve(
    n_events: list[int], retention: list[float]
) -> dict[str, Any]:
    """Fit retention ≈ a - b*exp(-c*n) (increasing toward asymptote); eval at 5k/10k/50k."""
    x = np.asarray(n_events, dtype=np.float64)
    y = np.asarray(retention, dtype=np.float64)
    mask = np.isfinite(x) & np.isfinite(y) & (x > 0)
    x, y = x[mask], y[mask]
    out: dict[str, Any] = {
        "model": "a - b*exp(-c*n)",
        "n_points": int(x.size),
        "params": None,
        "at_5k": None,
        "at_10k": None,
        "at_50k": None,
        "fit_ok": False,
    }
    if x.size < 4:
        return out

    def f(n, a, b, c):
        return a - b * np.exp(-c * n)

    try:
        p0 = (float(np.max(y)), float(np.max(y) - np.min(y)), 1e-3)
        popt, _ = curve_fit(
            f, x, y, p0=p0, maxfev=50000, bounds=([0.0, 0.0, 0.0], [1.5, 1.5, 1.0])
        )
        a, b, c = (float(popt[0]), float(popt[1]), float(popt[2]))
        out["params"] = {"a": a, "b": b, "c": c}
        for label, n in (("at_5k", 5000), ("at_10k", 10000), ("at_50k", 50000)):
            out[label] = float(f(n, a, b, c))
        out["fit_ok"] = True
    except Exception as exc:  # noqa: BLE001
        out["fit_error"] = str(exc)
    return out


def builder_difference_note() -> dict[str, Any]:
    return {
        "androct_tensor_builder": "abrg.androct.graph_build.update_graph_sequence",
        "androct_properties": {
            "timestamps": False,
            "delta_filter": False,
            "w_cum": True,
            "w_rec": False,
            "assert_recency_unpopulated": True,
            "k_burst": K_BURST,
        },
        "chapter_c_builder": "abrg.graph.update_graph",
        "chapter_c_properties": {
            "timestamps": True,
            "delta_filter": True,
            "delta_sec": DELTA_SEC,
            "w_cum": True,
            "w_rec": True,
            "lambda_rec": LAMBDA_REC,
            "k_burst": K_BURST,
            "processing_windows": "time_sec_cumulative",
            "window_sec": WINDOW_SEC_PIN,
        },
        "choice": (
            "Chapter C uses abrg.graph.update_graph (same schema / universe / "
            "shares-not-counts tensorization as AndroCT) because AndroCT's "
            "update_graph_sequence cannot exercise δ or recency. Export-time "
            "graph_metrics also used build_session_graph → update_graph. "
            "Session graphs are 60s multi-window cumulative finals so λ_rec "
            "decay separates w_rec from w_cum."
        ),
        "pins": {
            "k_burst": K_BURST_PIN,
            "delta_sec": DELTA_SEC_PIN,
            "lambda_rec_default": LAMBDA_REC_PIN,
            "lambda_rec_source": "abrg.config.LAMBDA_REC",
            "window_sec": WINDOW_SEC_PIN,
        },
    }


def build_all_session_graphs(
    report: Stage0Report,
    *,
    lambda_rec: float = LAMBDA_REC_PIN,
    apps: list[str] | None = None,
) -> GraphBuildBundle:
    assert len(GRAPH_CATEGORY_UNIVERSE) == 22
    usable = [s for s in report.sessions if s.usable]
    if apps is not None:
        app_set = set(apps)
        usable = [s for s in usable if s.app_id in app_set]

    by_app: dict[str, list[SessionMeta]] = {}
    for s in usable:
        by_app.setdefault(s.app_id, []).append(s)

    static_cache: dict[str, StaticReport | None] = {}
    graphs: dict[str, ABRGGraph] = {}
    stats: list[SessionGraphStats] = []
    resolved: list[str] = []
    fallback: list[str] = []

    ret_n_k = 0
    ret_n_d = 0
    per_session_ret: list[dict[str, Any]] = []

    for app_id, sess_list in sorted(by_app.items()):
        sess_list = sessions_for_app(report, app_id)
        if apps is not None and app_id not in apps:
            continue
        static_report, ok = load_static_for_app(sess_list, static_cache)
        if ok:
            resolved.append(app_id)
        else:
            fallback.append(app_id)

        for s in sess_list:
            events, load_rep = load_frida_trace(Path(s.events_path))
            nk, nd = measure_delta_retention_for_events(events)
            ret_n_k += nk
            ret_n_d += nd
            frac = (nd / nk) if nk else float("nan")
            per_session_ret.append(
                {
                    "app_id": app_id,
                    "export_dir_name": s.export_dir_name,
                    "n_mapped_events": len(events),
                    "n_k_candidates": nk,
                    "n_delta_retained": nd,
                    "retention": frac,
                }
            )
            g = build_session_graph_full(
                events, static_report, lambda_rec=lambda_rec
            )
            key = graph_key(app_id, s.export_dir_name)
            graphs[key] = g
            n_active = len(g.active_nodes())
            n_edges = len(g.edges)
            dens = (n_edges / (22 * 21)) if n_edges else 0.0
            stats.append(
                SessionGraphStats(
                    app_id=app_id,
                    session_id=s.session_id,
                    export_dir_name=s.export_dir_name,
                    session_index_within_app=s.session_index_within_app,
                    mapped_events=load_rep.events_kept,
                    n_active_nodes=n_active,
                    n_edges=n_edges,
                    density=float(dens),
                    static_resolved=ok,
                    lambda_rec=lambda_rec,
                )
            )

    # Quartile stratification by session event count (equal-count bins via ranks)
    ev_counts = np.asarray([r["n_mapped_events"] for r in per_session_ret], dtype=np.float64)
    stratified: list[dict[str, Any]] = []
    if ev_counts.size:
        # rank-based quartile labels 1..4
        order = np.argsort(ev_counts)
        ranks = np.empty(ev_counts.size, dtype=np.int64)
        ranks[order] = np.arange(ev_counts.size)
        qlab = np.minimum(4, (ranks * 4) // max(ev_counts.size, 1) + 1)
        for qi in range(1, 5):
            subset = [per_session_ret[i] for i in range(len(per_session_ret)) if qlab[i] == qi]
            sk = sum(r["n_k_candidates"] for r in subset)
            sd = sum(r["n_delta_retained"] for r in subset)
            evs = [r["n_mapped_events"] for r in subset]
            stratified.append(
                {
                    "quartile": qi,
                    "n_events_lo": float(min(evs)) if evs else float("nan"),
                    "n_events_hi": float(max(evs)) if evs else float("nan"),
                    "n_sessions": len(subset),
                    "n_k_candidates": sk,
                    "n_delta_retained": sd,
                    "retention": (sd / sk) if sk else float("nan"),
                }
            )

    fit = _fit_retention_curve(
        [int(r["n_mapped_events"]) for r in per_session_ret],
        [float(r["retention"]) for r in per_session_ret],
    )

    overall = (ret_n_d / ret_n_k) if ret_n_k else float("nan")
    mapped = [s.mapped_events for s in stats]
    act = [s.n_active_nodes for s in stats]
    edges = [s.n_edges for s in stats]
    dens = [s.density for s in stats]

    delta_retention = {
        "k_burst": K_BURST_PIN,
        "delta_sec": DELTA_SEC_PIN,
        "n_k_candidates": ret_n_k,
        "n_delta_retained": ret_n_d,
        "retention_overall": overall,
        "by_event_count_quartile": stratified,
        "fitted_curve": fit,
        "per_session": per_session_ret,
    }

    static_mode = (
        "static_dynamic_fusion"
        if not fallback
        else (
            "mixed_static_and_dynamic_only_fallback"
            if resolved
            else "dynamic_only"
        )
    )

    return GraphBuildBundle(
        graphs=graphs,
        stats=stats,
        static_resolved_apps=sorted(resolved),
        static_fallback_apps=sorted(fallback),
        static_mode_label=static_mode,
        delta_retention=delta_retention,
        builder_note=builder_difference_note(),
        pins={
            "k_burst": K_BURST_PIN,
            "delta_sec": DELTA_SEC_PIN,
            "lambda_rec": lambda_rec,
            "normalize": "shares_not_counts",
            "n_nodes": 22,
            "static_mode": static_mode,
            "n_apps_static_resolved": len(resolved),
            "n_apps_static_fallback": len(fallback),
            "corpus_stats": {
                "mapped_events": median_iqr(mapped),
                "n_active_nodes": median_iqr(act),
                "n_edges": median_iqr(edges),
                "density": median_iqr(dens),
                "n_sessions": len(stats),
            },
        },
    )


def stats_as_rows(bundle: GraphBuildBundle) -> list[dict[str, Any]]:
    return [asdict(s) for s in bundle.stats]
