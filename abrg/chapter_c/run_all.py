"""Orchestrate Chapter C stages 0–4 and write artefacts."""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from abrg.chapter_c.config import (
    ARTIFACTS_DIR,
    FIGURES_DIR,
    LAMBDA_REC_PIN,
    LAMBDA_REC_SWEEP,
    OUTPUT_ROOT,
    REFERENCE_COMBINE,
    REFERENCE_COMBINE_JUSTIFICATION,
    TENSORS_DIR,
)
from abrg.chapter_c.converge import (
    run_cold_start,
    run_convergence,
    run_cross_app_control,
    run_shuffle_control,
    run_stage3_variants,
    strip_private,
)
from abrg.chapter_c.figures import make_all_figures
from abrg.chapter_c.graphs import (
    build_session_graph_full,
    graph_key,
    load_static_for_app,
    measure_delta_retention_for_events,
    stats_as_rows,
)
from abrg.chapter_c.ingest import (
    Stage0Report,
    convergence_apps,
    load_stage0,
    sessions_for_app,
)
from abrg.chapter_c.report import write_summary
from abrg.chapter_c.tensorize import Channel, mean_reference, session_vector
from abrg.static import StaticReport
from abrg.trace import load_frida_trace


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def build_lambda_bundles(
    report: Stage0Report,
    lambdas: tuple[float, ...],
) -> dict[float, Any]:
    """Share Androguard static cache across λ rebuilds."""
    from abrg.chapter_c.graphs import GraphBuildBundle, SessionGraphStats, builder_difference_note
    from abrg.chapter_c.tensorize import median_iqr
    from abrg.registry import GRAPH_CATEGORY_UNIVERSE

    assert len(GRAPH_CATEGORY_UNIVERSE) == 22
    static_cache: dict[str, StaticReport | None] = {}
    apps_all = sorted({s.app_id for s in report.sessions if s.usable})

    # Resolve static once
    resolved: list[str] = []
    fallback: list[str] = []
    static_by_app: dict[str, StaticReport] = {}
    for app in apps_all:
        sess = sessions_for_app(report, app)
        rep, ok = load_static_for_app(sess, static_cache)
        static_by_app[app] = rep
        if ok:
            resolved.append(app)
        else:
            fallback.append(app)

    # Load events once
    events_by_key: dict[str, list] = {}
    load_stats: dict[str, int] = {}
    for app in apps_all:
        for s in sessions_for_app(report, app):
            key = graph_key(app, s.export_dir_name)
            events, load_rep = load_frida_trace(Path(s.events_path))
            events_by_key[key] = events
            load_stats[key] = load_rep.events_kept

    # δ retention once (independent of λ)
    ret_n_k = 0
    ret_n_d = 0
    per_session_ret: list[dict[str, Any]] = []
    for app in apps_all:
        for s in sessions_for_app(report, app):
            key = graph_key(app, s.export_dir_name)
            events = events_by_key[key]
            nk, nd = measure_delta_retention_for_events(events)
            ret_n_k += nk
            ret_n_d += nd
            per_session_ret.append(
                {
                    "app_id": app,
                    "export_dir_name": s.export_dir_name,
                    "n_mapped_events": len(events),
                    "n_k_candidates": nk,
                    "n_delta_retained": nd,
                    "retention": (nd / nk) if nk else float("nan"),
                }
            )

    from abrg.chapter_c.graphs import _fit_retention_curve

    ev_counts = np.asarray([r["n_mapped_events"] for r in per_session_ret], dtype=np.float64)
    stratified: list[dict[str, Any]] = []
    if ev_counts.size:
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
    delta_retention = {
        "k_burst": 5,
        "delta_sec": 5.0,
        "n_k_candidates": ret_n_k,
        "n_delta_retained": ret_n_d,
        "retention_overall": (ret_n_d / ret_n_k) if ret_n_k else float("nan"),
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
    note = builder_difference_note()
    bundles: dict[float, Any] = {}

    for lam in lambdas:
        graphs = {}
        stats = []
        for app in apps_all:
            static_report = static_by_app[app]
            ok = app in resolved
            for s in sessions_for_app(report, app):
                key = graph_key(app, s.export_dir_name)
                g = build_session_graph_full(
                    events_by_key[key], static_report, lambda_rec=lam
                )
                graphs[key] = g
                n_active = len(g.active_nodes())
                n_edges = len(g.edges)
                dens = (n_edges / (22 * 21)) if n_edges else 0.0
                stats.append(
                    SessionGraphStats(
                        app_id=app,
                        session_id=s.session_id,
                        export_dir_name=s.export_dir_name,
                        session_index_within_app=s.session_index_within_app,
                        mapped_events=load_stats[key],
                        n_active_nodes=n_active,
                        n_edges=n_edges,
                        density=float(dens),
                        static_resolved=ok,
                        lambda_rec=lam,
                    )
                )
        mapped = [s.mapped_events for s in stats]
        act = [s.n_active_nodes for s in stats]
        edges = [s.n_edges for s in stats]
        dens = [s.density for s in stats]
        bundles[lam] = GraphBuildBundle(
            graphs=graphs,
            stats=stats,
            static_resolved_apps=sorted(resolved),
            static_fallback_apps=sorted(fallback),
            static_mode_label=static_mode,
            delta_retention=delta_retention if lam == LAMBDA_REC_PIN else {},
            builder_note=note,
            pins={
                "k_burst": 5,
                "delta_sec": 5.0,
                "lambda_rec": lam,
                "window_sec": 60.0,
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
    return bundles


def persist_tensors(
    report: Stage0Report,
    bundle: Any,
    conv: dict[str, Any],
    *,
    channel: Channel = "both",
) -> None:
    TENSORS_DIR.mkdir(parents=True, exist_ok=True)
    apps = convergence_apps(report)
    for app in apps:
        sess = sessions_for_app(report, app)
        vecs = [
            session_vector(
                bundle.graphs[graph_key(app, s.export_dir_name)], channel=channel
            )
            for s in sess
        ]
        app_dir = TENSORS_DIR / app
        app_dir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            app_dir / "session_vectors.npz",
            **{f"S_{i+1}": v for i, v in enumerate(vecs)},
        )
        # references at each k
        refs = {}
        for k in range(1, len(vecs) + 1):
            refs[f"R_{k}"] = mean_reference(vecs[:k])
        np.savez_compressed(app_dir / "references.npz", **refs)
        # distance / error matrices from conv
        row = conv["per_app"].get(app)
        if row:
            _dump(app_dir / "curves.json", row)


def write_reproduce(versions: dict[str, Any]) -> None:
    cfg = {
        "chapter": "C",
        "corpus": "datasets/v2_extended",
        "output": "abrg/output/v2_chapter_c",
        "command": "python -m abrg.chapter_c",
        "pins": {
            "k_burst": 5,
            "delta_sec": 5.0,
            "lambda_rec": LAMBDA_REC_PIN,
            "lambda_rec_sweep": list(LAMBDA_REC_SWEEP),
            "window_sec": 60.0,
            "reference_combine": REFERENCE_COMBINE,
            "edge_weight_variants": ["w_cum", "w_rec", "both"],
            "primary_metric": "frobenius_combined",
            "shuffle_seeds": [0, 1, 2, 3, 4],
            "stabilisation_frac": 0.10,
        },
        "reference_combine_justification": REFERENCE_COMBINE_JUSTIFICATION,
        "library_versions": versions,
    }
    _dump(OUTPUT_ROOT / "reproduce_config.json", cfg)
    (OUTPUT_ROOT / "reproduce.md").write_text(
        "# Reproduce Chapter C\n\n"
        "From the repository root, with the project virtualenv:\n\n"
        "```bash\n"
        ".venv/bin/python -m abrg.chapter_c\n"
        "```\n\n"
        "This regenerates every number under `abrg/output/v2_chapter_c/` "
        "(SUMMARY.md, artefacts, tensors, figures).\n",
        encoding="utf-8",
    )


def main() -> int:
    t0 = time.time()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=== STAGE 0 ===", flush=True)
    report = load_stage0()
    s0 = {k: v for k, v in report.to_jsonable().items() if k != "sessions"}
    _dump(ARTIFACTS_DIR / "stage0.json", s0)
    if not report.verify_ok:
        print("STOP: verify_export non-zero", flush=True)
        write_summary({"stage0": s0, "stage1": {}, "stage2": {}, "stage3": {}, "stage4": {}, "exclusions": ["verify_export failed"]})
        return 2
    if not report.gate_apps_ge5:
        print(
            f"STOP: only {report.n_apps_ge5_usable} apps with ≥5 usable sessions "
            f"(need ≥30)",
            flush=True,
        )
        write_summary(
            {
                "stage0": s0,
                "stage1": {},
                "stage2": {},
                "stage3": {},
                "stage4": {},
                "exclusions": [
                    f"gate_fail_apps_ge5={report.n_apps_ge5_usable}",
                ],
            }
        )
        return 3

    print(
        f"Stage0 OK: pass={report.n_pass} fail_ref={report.n_fail_reference} "
        f"apps_ge5={report.n_apps_ge5_usable}",
        flush=True,
    )

    print("=== STAGE 1 (+ λ rebuilds) ===", flush=True)
    bundles = build_lambda_bundles(report, LAMBDA_REC_SWEEP)
    base = bundles[LAMBDA_REC_PIN]
    stage1 = {
        "builder_note": base.builder_note,
        "pins": base.pins,
        "delta_retention": {
            k: v
            for k, v in base.delta_retention.items()
            if k != "per_session"
        },
        "delta_retention_per_session_path": str(
            ARTIFACTS_DIR / "delta_retention_per_session.json"
        ),
        "session_stats": stats_as_rows(base),
        "static_resolved_apps": base.static_resolved_apps,
        "static_fallback_apps": base.static_fallback_apps,
        "static_mode_label": base.static_mode_label,
    }
    _dump(
        ARTIFACTS_DIR / "delta_retention_per_session.json",
        base.delta_retention.get("per_session", []),
    )
    # attach full delta for summary
    stage1_full = dict(stage1)
    stage1_full["delta_retention"] = {
        k: v for k, v in base.delta_retention.items() if k != "per_session"
    }
    # keep fitted + stratified in summary object
    stage1_full["delta_retention"] = {
        **{k: v for k, v in base.delta_retention.items() if k != "per_session"},
    }
    _dump(ARTIFACTS_DIR / "stage1.json", stage1_full)

    print("=== STAGE 2 ===", flush=True)
    conv = run_convergence(report, base, channel="both")
    cross = run_cross_app_control(conv)
    shuffle = run_shuffle_control(report, base, channel="both")
    stage2 = {
        "convergence": strip_private(conv),
        "cross_app": strip_private(cross),
        "shuffle": shuffle,
        "_within": cross["_within"],
        "_cross": cross["_cross"],
    }
    _dump(
        ARTIFACTS_DIR / "stage2.json",
        {
            "convergence": stage2["convergence"],
            "cross_app": stage2["cross_app"],
            "shuffle": stage2["shuffle"],
            "_within": stage2["_within"],
            "_cross": stage2["_cross"],
        },
    )
    persist_tensors(report, base, conv, channel="both")

    print("=== STAGE 3 ===", flush=True)
    stage3_raw = run_stage3_variants(report, bundles)
    # strip privates for disk
    stage3_disk = {
        "recency_adds_criterion": stage3_raw["recency_adds_criterion"],
        "lambda_rec_pin": stage3_raw["lambda_rec_pin"],
        "pairwise_deltas": stage3_raw["pairwise_deltas"],
        "lambda_sweep": stage3_raw["lambda_sweep"],
        "variants": {
            ch: {
                "convergence": block["convergence"],
                "cross_app": block["cross_app"],
                "shuffle": block["shuffle"],
            }
            for ch, block in stage3_raw["variants"].items()
        },
    }
    _dump(ARTIFACTS_DIR / "stage3.json", stage3_disk)

    print("=== STAGE 4 ===", flush=True)
    # cold start on both-channel temporal conv
    stage4 = run_cold_start(conv, report, base)
    _dump(ARTIFACTS_DIR / "stage4.json", stage4)

    exclusions: list[str] = []
    for e in report.timestamp_exclusions:
        exclusions.append(
            f"timestamp:{e['app_id']}/{e['export_dir_name']}:{e['reason']}"
        )
    for s in report.sessions:
        if not s.reference_tier_pass:
            exclusions.append(
                f"reference_tier_fail:{s.app_id}/{s.export_dir_name}:"
                f"{s.failure_reason}"
            )
    # apps with usable but <5 sessions — excluded from convergence curves
    for app, n in report.per_app_pass_counts.items():
        if n < 5:
            exclusions.append(f"convergence_corpus_lt5:{app}:n={n}")

    artefacts = {
        "stage0": s0,
        "stage1": {
            **stage1_full,
            "delta_retention": {
                k: v
                for k, v in base.delta_retention.items()
                if k != "per_session"
            },
        },
        "stage2": stage2,
        "stage3": stage3_disk,
        "stage4": stage4,
        "exclusions": exclusions,
    }
    # figures need within/cross arrays
    art_path = ARTIFACTS_DIR / "artefacts.json"
    _dump(art_path, artefacts)

    print("=== FIGURES ===", flush=True)
    fig_paths = make_all_figures(art_path, FIGURES_DIR)

    print("=== SUMMARY / REPRODUCE ===", flush=True)
    # SUMMARY uses stage1 with full delta_retention (no per_session)
    summary_art = {
        "stage0": s0,
        "stage1": {
            "builder_note": base.builder_note,
            "pins": base.pins,
            "delta_retention": {
                k: v
                for k, v in base.delta_retention.items()
                if k != "per_session"
            },
            "session_stats": stats_as_rows(base),
        },
        "stage2": stage2,
        "stage3": stage3_disk,
        "stage4": stage4,
        "exclusions": exclusions,
    }
    write_summary(summary_art)

    import matplotlib
    import scipy
    import torch

    versions = {
        "python": sys.version,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "torch": torch.__version__,
        "matplotlib": matplotlib.__version__,
    }
    write_reproduce(versions)
    _dump(
        ARTIFACTS_DIR / "run_meta.json",
        {
            "elapsed_sec": time.time() - t0,
            "figures": fig_paths,
            "versions": versions,
        },
    )
    print(f"DONE in {time.time() - t0:.1f}s → {OUTPUT_ROOT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
