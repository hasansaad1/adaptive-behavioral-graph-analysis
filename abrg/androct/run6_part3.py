"""Run 6 Part 3 — Arm B N=8 windowing (dual recon α=0.2, hidden=8)."""

from __future__ import annotations

import argparse
import io
import json
import math
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from scipy.stats import spearmanr

from abrg.androct.categorize import categorize_soot_callee
from abrg.androct.graph_build import (
    assert_recency_unpopulated,
    assert_universe,
    partition_mapped_indices,
    update_graph_sequence,
)
from abrg.androct.parse import _CALL_RE
from abrg.androct.paths import (
    EXPECTED_ARCHIVES,
    androct_raw_dir,
    androct_run2_output_dir,
    androct_run6_output_dir,
)
from abrg.androct.run2_corpus import load_corpus_cache, static_cache_dir, _static_path
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import (
    EPOCHS,
    LR,
    SEED,
    WD,
    AppRec,
    _auc_with_bootstrap,
    _dist,
    floor_aucs,
    split_apps,
)
from abrg.autoencoder import (
    FeatureDecoder,
    build_gae,
    graph_reconstruction_error_dual,
    seed_rng,
    train_gae_multi_dual,
)
from abrg.config import K_BURST
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.graph import build_initial_graph
from abrg.static import StaticReport, zero_static_report

N_PARTS = 8
ALPHA = 0.2
HIDDEN = 8
SENSITIVITY_FLOOR = 320


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def _load_static(sha: str) -> StaticReport:
    sp = _static_path(static_cache_dir(androct_run2_output_dir()), sha)
    if not sp.is_file():
        return zero_static_report(sha)
    payload = torch.load(sp, map_location="cpu", weights_only=False)
    if payload.get("ok") and payload.get("report") is not None:
        return payload["report"]
    return zero_static_report(sha)


def _load_categories(eligible: list[AppRec]) -> None:
    want = {a.path: a for a in eligible}
    raw = androct_raw_dir()
    for fname, meta in EXPECTED_ARCHIVES.items():
        print(f"[run6/p3] load traces {meta['label']} …", flush=True)
        n = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                app = want.get(member.name)
                if app is None:
                    continue
                n += 1
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                cats: list[str] = []
                try:
                    for line in text:
                        m = _CALL_RE.match(line.rstrip("\n\r"))
                        if not m:
                            continue
                        cat = categorize_soot_callee(m.group(2))
                        if cat is not None:
                            cats.append(cat)
                finally:
                    text.detach()
                app.categories = cats
                app.n_mapped = len(cats)
                if n % 200 == 0:
                    print(f"  … {meta['label']} {n}", flush=True)


def _build_snapshots(
    app: AppRec, static: StaticReport
) -> list[dict[str, Any]]:
    """Always N=8 snapshots; empty ranges → empty-edge graphs with static features."""
    events = app.categories or []
    ranges = partition_mapped_indices(max(len(events), 1), N_PARTS) if events else [
        (0, 0)
    ] * N_PARTS
    if not events:
        ranges = [(0, 0)] * N_PARTS
    snaps: list[dict[str, Any]] = []
    for snap_idx, (start, end) in enumerate(ranges):
        chunk = events[start:end] if events else []
        graph = build_initial_graph(static_report=static)
        assert_universe(graph)
        if chunk:
            update_graph_sequence(graph, chunk, k_burst=K_BURST)
        assert_recency_unpopulated(graph)
        x, ei, ew, _ = graph_to_tensors(graph, normalize=True, edge_weight_channel="w_cum")
        n_edges = sum(1 for _ in graph.iter_edges())
        n_active = len(graph.active_nodes())
        possible = 22 * 21
        snaps.append(
            {
                "sha256": app.sha256,
                "label": app.label,
                "path": app.path,
                "snap_idx": snap_idx,
                "n_mapped_in_snap": len(chunk),
                "n_active": n_active,
                "n_edges": n_edges,
                "density": n_edges / possible if possible else 0.0,
                "x": x,
                "edge_index": ei,
                "edge_weight": ew,
                "static_norm": float(app.static_norm),
                "n_mapped_app": int(app.n_mapped),
                "n_events_app": int(app.n_events),
            }
        )
    # If events existed but partition returned fewer than 8 (shouldn't), pad
    while len(snaps) < N_PARTS:
        snaps.append(snaps[-1] if snaps else {
            "sha256": app.sha256,
            "label": app.label,
            "path": app.path,
            "snap_idx": len(snaps),
            "n_mapped_in_snap": 0,
            "n_active": 0,
            "n_edges": 0,
            "density": 0.0,
            "x": torch.zeros(22, node_feature_dim()),
            "edge_index": torch.zeros(2, 0, dtype=torch.long),
            "edge_weight": torch.zeros(0),
            "static_norm": float(app.static_norm),
            "n_mapped_app": int(app.n_mapped),
            "n_events_app": int(app.n_events),
        })
    return snaps[:N_PARTS]


def _run_arm(
    *,
    apps: list[AppRec],
    split: dict[str, list[AppRec]],
    snap_cache: dict[str, list[dict[str, Any]]],
    tag: str,
) -> dict[str, Any]:
    tensors_n1 = {
        a.sha256: {
            "n_mapped": snap_cache[a.sha256][0]["n_mapped_app"],
            "n_events": snap_cache[a.sha256][0]["n_events_app"],
            "n_active": max(s["n_active"] for s in snap_cache[a.sha256]),
            "n_edges": sum(s["n_edges"] for s in snap_cache[a.sha256]),
            "density": float(
                np.mean([s["density"] for s in snap_cache[a.sha256]])
            ),
            "static_norm": snap_cache[a.sha256][0]["static_norm"],
        }
        for a in apps
        if a.sha256 in snap_cache
    }
    # For floors use app-level aggregates from N=1 corpus tensors where possible
    # Prefer original N=1 tensor diagnostics for size floors on same apps
    test_apps = split["test_benign"] + split["test_malware"]

    train_graphs = []
    for a in split["train"]:
        for s in snap_cache[a.sha256]:
            if s["edge_index"].numel() > 0:
                train_graphs.append((s["x"], s["edge_index"], s["edge_weight"]))

    print(f"[run6/p3] {tag}: train_graphs={len(train_graphs)} hidden={HIDDEN} alpha={ALPHA}", flush=True)
    seed_rng(SEED)
    model = build_gae(node_feature_dim(), HIDDEN)
    model.encoder = EdgeWeightProbeEncoder(model.encoder)
    feat_dec = FeatureDecoder(HIDDEN, node_feature_dim())
    losses, final_loss = train_gae_multi_dual(
        model, feat_dec, train_graphs, EPOCHS, LR, alpha=ALPHA, weight_decay=WD
    )

    def score_snap(s: dict[str, Any]) -> float:
        return graph_reconstruction_error_dual(
            model, feat_dec, s["x"], s["edge_index"], s["edge_weight"], alpha=ALPHA
        )

    def aggregate(apps_list: list[AppRec], how: str) -> dict[str, float]:
        out: dict[str, float] = {}
        for a in apps_list:
            errs = [score_snap(s) for s in snap_cache[a.sha256]]
            errs = [e for e in errs if math.isfinite(e)]
            if not errs:
                out[a.sha256] = float("nan")
            elif how == "mean":
                out[a.sha256] = float(sum(errs) / len(errs))
            else:
                out[a.sha256] = float(max(errs))
        return out

    # Window diagnostics
    win_sizes = {"benign": [], "malware": []}
    deg0 = {"benign": 0, "malware": 0}
    deg_le2 = {"benign": 0, "malware": 0}
    n_snaps = {"benign": 0, "malware": 0}
    for a in apps:
        for s in snap_cache[a.sha256]:
            win_sizes[a.label].append(float(s["n_mapped_in_snap"]))
            n_snaps[a.label] += 1
            if s["n_edges"] == 0:
                deg0[a.label] += 1
            if s["n_edges"] <= 2:
                deg_le2[a.label] += 1

    # Size floors from original N=1 tensors (same apps)
    bundle = load_corpus_cache(androct_run2_output_dir())
    floors = floor_aucs(test_apps, bundle.tensors)
    highest_floor = max(floors[k]["auc_floor"] for k in floors)

    agg_results: dict[str, Any] = {}
    for how in ("mean", "max"):
        tb = aggregate(split["test_benign"], how)
        tm = aggregate(split["test_malware"], how)
        scores = [tb[a.sha256] for a in split["test_benign"]] + [
            tm[a.sha256] for a in split["test_malware"]
        ]
        labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
        auc = _auc_with_bootstrap(scores, labels)
        sc = list(scores)
        leak = {
            "mapped_event_count": _rho(
                sc, [float(bundle.tensors[a.sha256]["n_mapped"]) for a in test_apps]
            ),
            "total_event_count": _rho(
                sc, [float(bundle.tensors[a.sha256]["n_events"]) for a in test_apps]
            ),
            "active_nodes": _rho(
                sc, [float(bundle.tensors[a.sha256]["n_active"]) for a in test_apps]
            ),
            "edge_count": _rho(
                sc, [float(bundle.tensors[a.sha256]["n_edges"]) for a in test_apps]
            ),
            "graph_density": _rho(
                sc, [float(bundle.tensors[a.sha256]["density"]) for a in test_apps]
            ),
            "static_feature_norm": _rho(
                sc, [float(bundle.tensors[a.sha256]["static_norm"]) for a in test_apps]
            ),
        }
        d_tben = _dist([v for v in tb.values() if math.isfinite(v)])
        d_tmal = _dist([v for v in tm.values() if math.isfinite(v)])
        higher = (
            "test_malware"
            if d_tmal["median"] > d_tben["median"]
            else ("test_benign" if d_tben["median"] > d_tmal["median"] else "tied")
        )
        agg_results[how] = {
            "auc": auc,
            "leak_spearman": leak,
            "recon_error": {
                "test_benign": d_tben,
                "test_malware": d_tmal,
                "higher_median_error_class": higher,
                "benign_malware_error_direction_inverted": higher == "test_benign",
            },
            "arm_below_highest_floor": auc["auc_floor"] < highest_floor,
        }

    return {
        "tag": tag,
        "n_apps": len(apps),
        "n_train_graphs": len(train_graphs),
        "final_train_loss": final_loss,
        "window_size_dist": {
            "benign": _dist(win_sizes["benign"]),
            "malware": _dist(win_sizes["malware"]),
        },
        "degenerate_snapshots": {
            "benign": {
                "n_snaps": n_snaps["benign"],
                "n_zero_edges": deg0["benign"],
                "frac_zero_edges": deg0["benign"] / n_snaps["benign"] if n_snaps["benign"] else float("nan"),
                "n_edges_le_2": deg_le2["benign"],
                "frac_edges_le_2": deg_le2["benign"] / n_snaps["benign"] if n_snaps["benign"] else float("nan"),
            },
            "malware": {
                "n_snaps": n_snaps["malware"],
                "n_zero_edges": deg0["malware"],
                "frac_zero_edges": deg0["malware"] / n_snaps["malware"] if n_snaps["malware"] else float("nan"),
                "n_edges_le_2": deg_le2["malware"],
                "frac_edges_le_2": deg_le2["malware"] / n_snaps["malware"] if n_snaps["malware"] else float("nan"),
            },
        },
        "floors": floors,
        "highest_floor": highest_floor,
        "aggregation": agg_results,
        "pins": {
            "n_parts": N_PARTS,
            "alpha": ALPHA,
            "hidden": HIDDEN,
            "epochs": EPOCHS,
            "seed": SEED,
            "k_burst": K_BURST,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 6 Part 3 — Arm B N=8")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    out = args.output_dir or (androct_run6_output_dir() / "part3_armB")
    out.mkdir(parents=True, exist_ok=True)
    bundle = load_corpus_cache(androct_run2_output_dir())
    eligible = bundle.eligible
    print(f"[run6/p3] eligible={len(eligible)} load categories …", flush=True)
    _load_categories(eligible)
    # restore static_norm from tensors
    for a in eligible:
        t = bundle.tensors[a.sha256]
        a.static_norm = float(t["static_norm"])
        a.static_ok = True
        a.static_zero = False

    print("[run6/p3] build N=8 snapshots …", flush=True)
    snap_cache: dict[str, list[dict[str, Any]]] = {}
    for i, app in enumerate(eligible):
        static = _load_static(app.sha256)
        app.static = static
        snap_cache[app.sha256] = _build_snapshots(app, static)
        if (i + 1) % 100 == 0:
            print(f"  … snaps {i+1}/{len(eligible)}", flush=True)

    split = split_apps(eligible)
    primary = _run_arm(apps=eligible, split=split, snap_cache=snap_cache, tag="primary_no_floor")

    # Sensitivity: mapped >= 320
    floored = [a for a in eligible if a.n_mapped >= SENSITIVITY_FLOOR]
    excl_b = sum(1 for a in eligible if a.label == "benign" and a.n_mapped < SENSITIVITY_FLOOR)
    excl_m = sum(1 for a in eligible if a.label == "malware" and a.n_mapped < SENSITIVITY_FLOOR)
    n_b = sum(1 for a in eligible if a.label == "benign")
    n_m = sum(1 for a in eligible if a.label == "malware")
    split_f = split_apps(floored)
    # Restrict snap cache implicitly by apps in split
    sensitivity = _run_arm(
        apps=floored, split=split_f, snap_cache=snap_cache, tag="sensitivity_floor_320"
    )
    sensitivity["exclusion"] = {
        "floor": SENSITIVITY_FLOOR,
        "benign_excluded": excl_b,
        "benign_total": n_b,
        "benign_exclusion_rate": excl_b / n_b if n_b else float("nan"),
        "malware_excluded": excl_m,
        "malware_total": n_m,
        "malware_exclusion_rate": excl_m / n_m if n_m else float("nan"),
        "n_remaining": len(floored),
    }

    results = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "part": 3,
        "primary": primary,
        "sensitivity_floor_320": sensitivity,
    }
    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")

    def block_lines(title: str, arm: dict[str, Any], *, sensitivity_note: str = "") -> list[str]:
        lines = [f"## {title}", sensitivity_note] if sensitivity_note else [f"## {title}"]
        lines = [x for x in lines if x]
        ws = arm["window_size_dist"]
        lines.append(
            f"- window mapped/snap benign med={ws['benign']['median']:.3f} "
            f"IQR={ws['benign']['iqr']:.3f}; malware med={ws['malware']['median']:.3f} "
            f"IQR={ws['malware']['iqr']:.3f}"
        )
        for lab in ("benign", "malware"):
            d = arm["degenerate_snapshots"][lab]
            lines.append(
                f"- degenerate {lab}: zero_edges={d['n_zero_edges']}/{d['n_snaps']} "
                f"({d['frac_zero_edges']:.4f}); "
                f"edges_le_2={d['n_edges_le_2']}/{d['n_snaps']} ({d['frac_edges_le_2']:.4f})"
            )
        lines.append(f"- highest size floor={arm['highest_floor']:.6f}")
        for how, ag in arm["aggregation"].items():
            ab = ag["auc"]
            inv = ag["recon_error"]["benign_malware_error_direction_inverted"]
            lines.append(f"### aggregation={how}")
            lines.append(
                f"- auc={ab['auc']:.6f} auc_floor={ab['auc_floor']:.6f} "
                f"CI_floor=[{ab['ci95_floor'][0]:.6f}, {ab['ci95_floor'][1]:.6f}] "
                f"direction={ab['direction']}"
            )
            lines.append(
                f"- below_floor={ag['arm_below_highest_floor']} "
                f"higher_err={ag['recon_error']['higher_median_error_class']} inverted={inv}"
            )
            for k, v in ag["leak_spearman"].items():
                lines.append(f"- ρ {k}: {v:.6f}" if math.isfinite(v) else f"- ρ {k}: nan")
        return lines

    lines = [
        "# Run 6 Part 3 — Arm B N=8 windowing",
        f"- UTC: {results['utc']}",
        f"- pins: N={N_PARTS} alpha={ALPHA} hidden={HIDDEN} epochs={EPOCHS} seed={SEED} "
        f"k={K_BURST} dual-recon full-adj+feature",
        f"- eligibility floor: **none** (primary); sensitivity floor={SENSITIVITY_FLOOR} separate",
        f"- n_eligible_primary={len(eligible)}",
        "",
    ]
    lines.extend(block_lines("Primary (no eligibility floor)", primary))
    lines.append("")
    ex = sensitivity["exclusion"]
    lines.extend(
        block_lines(
            "SENSITIVITY CHECK — mapped≥320 floor (not primary)",
            sensitivity,
            sensitivity_note=(
                f"- exclusion: benign {ex['benign_excluded']}/{ex['benign_total']}="
                f"{ex['benign_exclusion_rate']:.4f}; "
                f"malware {ex['malware_excluded']}/{ex['malware_total']}="
                f"{ex['malware_exclusion_rate']:.4f}; remaining={ex['n_remaining']}"
            ),
        )
    )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"[run6/p3] done → {out}", flush=True)


if __name__ == "__main__":
    main()
