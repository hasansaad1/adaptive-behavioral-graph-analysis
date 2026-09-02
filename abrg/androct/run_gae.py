"""ABRG GAE on AndroCT 2017 — shared N-partition path, arms A (N=1) and B (N=8)."""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import math
import random
import tarfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from torch import Tensor

from abrg.androct.categorize import categorize_soot_callee
from abrg.androct.graph_build import (
    assert_recency_unpopulated,
    assert_universe,
    partition_mapped_indices,
    update_graph_sequence,
)
from abrg.androct.parse import _CALL_RE
from abrg.androct.paths import (
    ANDROCT_OUTPUT_ROOT,
    EXPECTED_ARCHIVES,
    androct_inventory_dir,
    androct_raw_dir,
)
from abrg.autoencoder import (
    build_gae,
    graph_reconstruction_error,
    seed_rng,
    train_gae_multi,
)
from abrg.config import GAE_EPOCHS, GAE_LR, K_BURST
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.graph import ABRGGraph, build_initial_graph
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.static import zero_static_report
from abrg.trace import TraceEvent

# Champion starting pins (not a target).
HIDDEN = 64
EPOCHS = GAE_EPOCHS  # 300
LR = GAE_LR  # 0.01
WD = 0.0
SEED = 42
TEST_RATIO = 0.2
ELIGIBILITY_MIN_MAPPED = 320  # 8 * 40
STATIC_MODE = "dynamic_only"  # AndroZoo APKs not retrieved

assert len(GRAPH_CATEGORY_UNIVERSE) == 22


@dataclass
class AppRecord:
    path: str
    sha: str
    label: str  # benign | malware
    n_mapped: int
    categories: list[str] = field(repr=False)  # mapped-event categories in call order


@dataclass
class SnapshotRecord:
    app_path: str
    sha: str
    label: str
    snap_idx: int
    n_parts: int
    n_mapped_in_snap: int
    n_active: int
    n_edges: int
    x: Tensor
    edge_index: Tensor
    edge_weight: Tensor


def _sha_from_member(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if base.endswith(".apk.logcat"):
        return base[: -len(".apk.logcat")]
    return base


def load_mapped_events_from_archives(
    raw_dir: Path,
    *,
    min_mapped: int | None = None,
) -> list[AppRecord]:
    """Stream archives; keep only mapped-category call events in order."""
    apps: list[AppRecord] = []
    assert tuple(GRAPH_CATEGORY_UNIVERSE)  # universe asserted at load
    if len(GRAPH_CATEGORY_UNIVERSE) != 22:
        raise AssertionError("GRAPH_CATEGORY_UNIVERSE must be 22")

    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        archive = raw_dir / fname
        print(f"[androct-gae] load mapped events {label} …", flush=True)
        n = 0
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                if member.name.split("/", 1)[0] != inner:
                    raise SystemExit(f"year-dir mismatch {member.name}")
                n += 1
                if n % 200 == 0:
                    print(f"  … {label} files={n} apps_kept={len(apps)}", flush=True)
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                events: list[TraceEvent] = []
                try:
                    for raw in text:
                        line = raw.rstrip("\n\r")
                        m = _CALL_RE.match(line)
                        if not m:
                            continue
                        cat = categorize_soot_callee(m.group(2))
                        if cat is None:
                            continue
                        # ordinal index as placeholder timestamp (unused by sequence update)
                        events.append(
                            TraceEvent(category=cat, api=m.group(2)[:120], timestamp_ms=len(events))
                        )
                finally:
                    text.detach()
                if min_mapped is not None and len(events) < min_mapped:
                    # still record for exclusion report via separate pass — skip storing events
                    apps.append(
                        AppRecord(
                            path=member.name,
                            sha=_sha_from_member(member.name),
                            label=label,
                            n_mapped=len(events),
                            mapped_events=[],  # empty = excluded placeholder
                        )
                    )
                    # Actually we need n_mapped for excluded distribution; store count only
                    continue
                apps.append(
                    AppRecord(
                        path=member.name,
                        sha=_sha_from_member(member.name),
                        label=label,
                        n_mapped=len(events),
                        mapped_events=events,
                    )
                )
        print(f"  {label} done files={n}", flush=True)
    return apps


def load_all_mapped_counts(raw_dir: Path) -> list[dict[str, Any]]:
    """Lightweight pass: n_mapped per app without storing events (for exclusion report)."""
    rows: list[dict[str, Any]] = []
    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        print(f"[androct-gae] count mapped {label} …", flush=True)
        with tarfile.open(raw_dir / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                if member.name.split("/", 1)[0] != inner:
                    raise SystemExit(f"year-dir mismatch {member.name}")
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                n_mapped = 0
                try:
                    for raw in text:
                        m = _CALL_RE.match(raw.rstrip("\n\r"))
                        if not m:
                            continue
                        if categorize_soot_callee(m.group(2)) is not None:
                            n_mapped += 1
                finally:
                    text.detach()
                rows.append(
                    {
                        "path": member.name,
                        "sha": _sha_from_member(member.name),
                        "label": label,
                        "n_mapped": n_mapped,
                    }
                )
    return rows


def build_snapshots_for_app(
    app: AppRecord, n_parts: int, *, keep_raw_for_diff: bool = False
) -> tuple[list[SnapshotRecord], dict[str, Any] | None]:
    """One independent graph per partition (not cumulative)."""
    events = app.categories
    ranges = partition_mapped_indices(len(events), n_parts)
    out: list[SnapshotRecord] = []
    feat_diff: dict[str, Any] | None = None
    for snap_idx, (start, end) in enumerate(ranges):
        chunk = events[start:end]
        if not chunk:
            continue
        graph = build_initial_graph(static_report=zero_static_report(app.sha))
        assert_universe(graph)
        update_graph_sequence(graph, chunk, k_burst=K_BURST)
        assert_recency_unpopulated(graph)
        x, edge_index, edge_weight, _ = graph_to_tensors(
            graph, normalize=True, edge_weight_channel="w_cum"
        )
        if keep_raw_for_diff and feat_diff is None and edge_index.numel() > 0:
            x_raw, _, _, _ = graph_to_tensors(
                graph, normalize=False, edge_weight_channel="w_cum"
            )
            diff = (x - x_raw).norm().item()
            feat_diff = {
                "app": app.path,
                "snap_idx": snap_idx,
                "diff_norm_L2": diff,
                "x_norm_sample_row0": x[0].tolist(),
                "x_raw_sample_row0": x_raw[0].tolist(),
                "tensors_differ": diff > 1e-8,
            }
        out.append(
            SnapshotRecord(
                app_path=app.path,
                sha=app.sha,
                label=app.label,
                snap_idx=snap_idx,
                n_parts=n_parts,
                n_mapped_in_snap=len(chunk),
                n_active=len(graph.active_nodes()),
                n_edges=sum(1 for _ in graph.iter_edges()),
                x=x,
                edge_index=edge_index,
                edge_weight=edge_weight,
            )
        )
        del graph
    return out, feat_diff


def split_apps(
    eligible: list[AppRecord],
    *,
    seed: int = SEED,
    test_ratio: float = TEST_RATIO,
) -> dict[str, list[AppRecord]]:
    """
    App-level split. Train = benign only (80% of eligible benign).
    Test = held-out benign (20%) + all eligible malware.
    """
    rng = random.Random(seed)
    benign = [a for a in eligible if a.label == "benign"]
    malware = [a for a in eligible if a.label == "malware"]
    rng.shuffle(benign)
    n_test = max(1, int(round(len(benign) * test_ratio)))
    test_benign = benign[:n_test]
    train_benign = benign[n_test:]
    return {
        "train": train_benign,
        "test_benign": test_benign,
        "test_malware": malware,
        "test": test_benign + malware,
    }


def _auc_roc(scores: list[float], labels: list[int]) -> dict[str, Any]:
    """labels: 1 = malware (positive), 0 = benign. Higher score → more anomalous."""
    pairs = sorted(zip(scores, labels), key=lambda t: t[0])
    # sklearn-style: use ranks; implement via Mann-Whitney / trapezoid on ROC
    try:
        from sklearn.metrics import roc_auc_score, roc_curve
    except ImportError as exc:
        raise SystemExit("sklearn required for AUC-ROC") from exc
    y = np.array(labels, dtype=np.int32)
    s = np.array(scores, dtype=np.float64)
    # drop nan
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return {"auc": float("nan"), "auc_floor": float("nan"), "direction": "undefined", "roc_points": []}
    auc = float(roc_auc_score(y, s))
    fpr, tpr, thr = roc_curve(y, s)
    auc_floor = max(auc, 1.0 - auc)
    direction = "malware_higher_score" if auc >= 0.5 else "benign_higher_score"
    roc_points = [
        {"fpr": float(a), "tpr": float(b), "threshold": float(c)}
        for a, b, c in zip(fpr.tolist(), tpr.tolist(), thr.tolist())
    ]
    return {
        "auc": auc,
        "auc_floor": auc_floor,
        "direction": direction,
        "roc_points": roc_points,
        "n": int(len(y)),
        "n_pos": int(y.sum()),
        "n_neg": int((1 - y).sum()),
    }


def _dist(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {"n": 0, "median": float("nan"), "iqr": float("nan"), "p25": float("nan"), "p75": float("nan")}
    s = sorted(vals)
    n = len(s)

    def pct(p: float) -> float:
        k = (n - 1) * p / 100.0
        f, c = math.floor(k), math.ceil(k)
        if f == c:
            return float(s[int(k)])
        return float(s[f] * (c - k) + s[c] * (k - f))

    p25, p50, p75 = pct(25), pct(50), pct(75)
    return {"n": n, "median": p50, "p25": p25, "p75": p75, "iqr": p75 - p25}


def _spearman(x: list[float], y: list[float]) -> float:
    from scipy.stats import spearmanr

    if len(x) < 3:
        return float("nan")
    r, _ = spearmanr(x, y)
    return float(r)


class EdgeWeightProbeEncoder(torch.nn.Module):
    """Wrap GAE encoder to record edge_weight at GCNConv call site."""

    def __init__(self, inner: torch.nn.Module):
        super().__init__()
        self.inner = inner
        self.last_edge_weight: Optional[Tensor] = None
        self.last_edge_weight_is_none: bool | None = None
        self.n_calls = 0

    def forward(self, x, edge_index, edge_weight=None):
        self.n_calls += 1
        self.last_edge_weight_is_none = edge_weight is None
        if edge_weight is None:
            self.last_edge_weight = None
            if self.n_calls <= 3:
                print(
                    f"[VERIFY edge_weight] call#{self.n_calls} edge_weight=None "
                    f"edge_index.shape={tuple(edge_index.shape)}",
                    flush=True,
                )
        else:
            self.last_edge_weight = edge_weight.detach().cpu().clone()
            if self.n_calls <= 3:
                print(
                    f"[VERIFY edge_weight] call#{self.n_calls} edge_weight.shape={tuple(edge_weight.shape)} "
                    f"dtype={edge_weight.dtype} numel={edge_weight.numel()} "
                    f"min={float(edge_weight.min()) if edge_weight.numel() else 'n/a'} "
                    f"max={float(edge_weight.max()) if edge_weight.numel() else 'n/a'} "
                    f"sample={edge_weight[: min(5, edge_weight.numel())].tolist()}",
                    flush=True,
                )
        return self.inner(x, edge_index, edge_weight)


def run_arm(
    *,
    arm_id: str,
    n_parts: int,
    split: dict[str, list[AppRecord]],
    out_dir: Path,
    exclusion_report: dict[str, Any],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[androct-gae] build snapshots {arm_id} N={n_parts}", flush=True)

    feat_diff: dict[str, Any] = {}
    train_snaps: list[SnapshotRecord] = []
    for i, app in enumerate(split["train"]):
        if (i + 1) % 100 == 0:
            print(f"  … {arm_id} train apps {i+1}/{len(split['train'])}", flush=True)
        snaps, fd = build_snapshots_for_app(
            app, n_parts, keep_raw_for_diff=(not feat_diff)
        )
        train_snaps.extend(snaps)
        if fd:
            feat_diff = fd
            print(
                f"[VERIFY feature diff] L2={fd['diff_norm_L2']} differ={fd['tensors_differ']}",
                flush=True,
            )

    def build_list(apps: list[AppRecord]) -> list[SnapshotRecord]:
        snaps: list[SnapshotRecord] = []
        for i, app in enumerate(apps):
            if (i + 1) % 100 == 0:
                print(f"  … {arm_id} apps {i+1}/{len(apps)}", flush=True)
            s, _ = build_snapshots_for_app(app, n_parts)
            snaps.extend(s)
        return snaps

    test_ben_snaps = build_list(split["test_benign"])
    test_mal_snaps = build_list(split["test_malware"])

    # Counts
    def app_n(apps: list[AppRecord]) -> int:
        return len(apps)

    partition_counts = {
        "train": {
            "n_apps_benign": app_n(split["train"]),
            "n_apps_malware": 0,
            "n_snapshots": len(train_snaps),
        },
        "test": {
            "n_apps_benign": app_n(split["test_benign"]),
            "n_apps_malware": app_n(split["test_malware"]),
            "n_snapshots_benign": len(test_ben_snaps),
            "n_snapshots_malware": len(test_mal_snaps),
            "n_snapshots": len(test_ben_snaps) + len(test_mal_snaps),
        },
    }

    # Train
    seed_rng(SEED)
    model = build_gae(node_feature_dim(), HIDDEN)
    # Probe edge_weight at encoder forward AND at GCNConv.conv1 call site
    probe = EdgeWeightProbeEncoder(model.encoder)
    model.encoder = probe
    gcn_ew_log: dict[str, Any] = {"n_calls": 0, "last_is_none": None, "last_repr": None}
    _orig_conv1 = probe.inner.conv1.forward

    def _conv1_probe(x, edge_index, edge_weight=None, **kwargs):
        gcn_ew_log["n_calls"] += 1
        gcn_ew_log["last_is_none"] = edge_weight is None
        if edge_weight is None:
            gcn_ew_log["last_repr"] = None
            if gcn_ew_log["n_calls"] <= 3:
                print(
                    f"[VERIFY GCNConv.conv1] call#{gcn_ew_log['n_calls']} edge_weight=None",
                    flush=True,
                )
        else:
            gcn_ew_log["last_repr"] = {
                "shape": list(edge_weight.shape),
                "numel": int(edge_weight.numel()),
                "sample": edge_weight[: min(8, edge_weight.numel())].detach().cpu().tolist(),
            }
            if gcn_ew_log["n_calls"] <= 3:
                print(
                    f"[VERIFY GCNConv.conv1] call#{gcn_ew_log['n_calls']} "
                    f"edge_weight.shape={tuple(edge_weight.shape)} "
                    f"sample={gcn_ew_log['last_repr']['sample'][:5]}",
                    flush=True,
                )
        return _orig_conv1(x, edge_index, edge_weight=edge_weight, **kwargs)

    probe.inner.conv1.forward = _conv1_probe  # type: ignore[method-assign]

    train_graphs = [
        (s.x, s.edge_index, s.edge_weight)
        for s in train_snaps
        if s.edge_index.numel() > 0
    ]
    print(
        f"[androct-gae] train {arm_id}: {len(train_graphs)} graphs, "
        f"hidden={HIDDEN} epochs={EPOCHS} lr={LR}",
        flush=True,
    )
    # First encode call for edge_weight verify before full train
    if train_graphs:
        s0 = train_graphs[0]
        model.eval()
        with torch.no_grad():
            _ = model.encode(s0[0], s0[1], s0[2])
    edge_weight_report = {
        "encoder_forward_is_none": probe.last_edge_weight_is_none,
        "encoder_forward_tensor": None
        if probe.last_edge_weight is None
        else {
            "shape": list(probe.last_edge_weight.shape),
            "numel": int(probe.last_edge_weight.numel()),
            "sample": probe.last_edge_weight[: min(8, probe.last_edge_weight.numel())].tolist(),
        },
        "gcnconv_conv1_is_none": gcn_ew_log["last_is_none"],
        "gcnconv_conv1_tensor": gcn_ew_log["last_repr"],
        # compatibility key for SUMMARY
        "received_at_call_site_is_none": gcn_ew_log["last_is_none"],
        "tensor_repr": gcn_ew_log["last_repr"],
    }

    losses, final_loss = train_gae_multi(
        model, train_graphs, EPOCHS, LR, weight_decay=WD
    )

    # Score snapshots
    def score_snaps(snaps: list[SnapshotRecord]) -> list[dict[str, Any]]:
        rows = []
        for s in snaps:
            err = graph_reconstruction_error(model, s.x, s.edge_index, s.edge_weight)
            rows.append(
                {
                    "path": s.app_path,
                    "sha": s.sha,
                    "label": s.label,
                    "snap_idx": s.snap_idx,
                    "n_mapped_in_snap": s.n_mapped_in_snap,
                    "n_active": s.n_active,
                    "n_edges": s.n_edges,
                    "recon_error": err,
                }
            )
        return rows

    train_rows = score_snaps(train_snaps)
    test_ben_rows = score_snaps(test_ben_snaps)
    test_mal_rows = score_snaps(test_mal_snaps)

    def aggregate_app(rows: list[dict[str, Any]], how: str) -> dict[str, float]:
        by: dict[str, list[float]] = defaultdict(list)
        for r in rows:
            if math.isfinite(r["recon_error"]):
                by[r["path"]].append(r["recon_error"])
        out: dict[str, float] = {}
        for path, errs in by.items():
            if how == "mean":
                out[path] = float(sum(errs) / len(errs))
            elif how == "max":
                out[path] = float(max(errs))
            else:
                raise ValueError(how)
        return out

    # Per-app mapped counts for leak check
    mapped_by_path = {
        a.path: a.n_mapped
        for a in split["train"] + split["test_benign"] + split["test_malware"]
    }

    results_agg: dict[str, Any] = {}
    for how in ("mean", "max") if n_parts > 1 else ("mean",):
        # Arm A: mean == direct (one snap)
        tb = aggregate_app(test_ben_rows, how)
        tm = aggregate_app(test_mal_rows, how)
        scores = []
        labels = []
        paths = []
        for p, sc in tb.items():
            scores.append(sc)
            labels.append(0)
            paths.append(p)
        for p, sc in tm.items():
            scores.append(sc)
            labels.append(1)
            paths.append(p)
        auc = _auc_roc(scores, labels)
        # Spearman score vs mapped count on test apps
        xs = [float(mapped_by_path[p]) for p in paths]
        spear = _spearman(scores, xs)
        results_agg[how] = {
            "auc": auc,
            "spearman_score_vs_mapped_count": spear,
            "n_test_apps": len(scores),
        }

    # Error distributions
    def errs(rows: list[dict[str, Any]]) -> list[float]:
        return [r["recon_error"] for r in rows if math.isfinite(r["recon_error"])]

    # Per-app mean errors for distribution / ratio
    train_app = aggregate_app(train_rows, "mean")
    test_ben_app = aggregate_app(test_ben_rows, "mean")
    test_mal_app = aggregate_app(test_mal_rows, "mean")
    d_train = _dist(list(train_app.values()))
    d_tben = _dist(list(test_ben_app.values()))
    d_tmal = _dist(list(test_mal_app.values()))
    ratio = (
        (d_tben["median"] / d_train["median"])
        if d_train["median"] and d_train["median"] == d_train["median"]
        else float("nan")
    )

    # Snapshot diagnostics
    def snap_diag(rows: list[dict[str, Any]]) -> dict[str, Any]:
        act = [float(r["n_active"]) for r in rows]
        ed = [float(r["n_edges"]) for r in rows]
        frac_le2 = (sum(1 for e in ed if e <= 2) / len(ed)) if ed else float("nan")
        return {
            "active_nodes": _dist(act),
            "edges": _dist(ed),
            "fraction_snapshots_edges_le_2": frac_le2,
        }

    diagnostics = {
        "train_benign": snap_diag(train_rows),
        "test_benign": snap_diag(test_ben_rows),
        "test_malware": snap_diag(test_mal_rows),
    }

    # Persist per-snapshot CSV
    with (out_dir / "per_snapshot_errors.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "path", "sha", "label", "snap_idx", "n_mapped_in_snap",
                "n_active", "n_edges", "recon_error", "partition",
            ],
        )
        w.writeheader()
        for r in train_rows:
            w.writerow({**r, "partition": "train"})
        for r in test_ben_rows:
            w.writerow({**r, "partition": "test"})
        for r in test_mal_rows:
            w.writerow({**r, "partition": "test"})

    # Per-app scores
    with (out_dir / "per_app_scores.csv").open("w", newline="", encoding="utf-8") as f:
        fields = ["path", "sha", "label", "n_mapped", "partition", "score_mean"]
        if n_parts > 1:
            fields.append("score_max")
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        tr_mean = aggregate_app(train_rows, "mean")
        tr_max = aggregate_app(train_rows, "max") if n_parts > 1 else {}
        for a in split["train"]:
            row = {
                "path": a.path,
                "sha": a.sha,
                "label": a.label,
                "n_mapped": a.n_mapped,
                "partition": "train",
                "score_mean": tr_mean.get(a.path, float("nan")),
            }
            if n_parts > 1:
                row["score_max"] = tr_max.get(a.path, float("nan"))
            w.writerow(row)
        tb_mean = aggregate_app(test_ben_rows, "mean")
        tb_max = aggregate_app(test_ben_rows, "max") if n_parts > 1 else {}
        tm_mean = aggregate_app(test_mal_rows, "mean")
        tm_max = aggregate_app(test_mal_rows, "max") if n_parts > 1 else {}
        for a in split["test_benign"]:
            row = {
                "path": a.path,
                "sha": a.sha,
                "label": a.label,
                "n_mapped": a.n_mapped,
                "partition": "test",
                "score_mean": tb_mean.get(a.path, float("nan")),
            }
            if n_parts > 1:
                row["score_max"] = tb_max.get(a.path, float("nan"))
            w.writerow(row)
        for a in split["test_malware"]:
            row = {
                "path": a.path,
                "sha": a.sha,
                "label": a.label,
                "n_mapped": a.n_mapped,
                "partition": "test",
                "score_mean": tm_mean.get(a.path, float("nan")),
            }
            if n_parts > 1:
                row["score_max"] = tm_max.get(a.path, float("nan"))
            w.writerow(row)

    torch.save(
        {
            "model_state": model.state_dict(),
            "hidden": HIDDEN,
            "in_channels": node_feature_dim(),
            "arm_id": arm_id,
            "n_parts": n_parts,
        },
        out_dir / "gae_androct_model.pt",
    )
    with (out_dir / "training_curve.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["epoch", "loss"])
        for i, loss in enumerate(losses, 1):
            w.writerow([i, loss])

    comparison = {
        "arm_id": arm_id,
        "n_parts": n_parts,
        "static_mode": STATIC_MODE,
        "static_features": {
            "mode": STATIC_MODE,
            "n_apps_static_resolved": 0,
            "n_apps_dynamic_only_fallback": (
                len(split["train"]) + len(split["test_benign"]) + len(split["test_malware"])
            ),
            "note": "AndroZoo APK retrieval not done; zero_static_report for all apps",
        },
        "pins": {
            "hidden": HIDDEN,
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WD,
            "k_burst": K_BURST,
            "seed": SEED,
            "test_ratio": TEST_RATIO,
            "eligibility_min_mapped": ELIGIBILITY_MIN_MAPPED,
            "edge_weight_channel": "w_cum",
            "normalize": True,
            "scorer": "stochastic_recon_loss",
            "recency": "disabled_asserted",
        },
        "exclusion": exclusion_report,
        "partition_counts": partition_counts,
        "edge_weight_verify": edge_weight_report,
        "feature_diff_verify": feat_diff,
        "final_train_loss": final_loss,
        "recon_error_distributions_per_app_mean": {
            "train_benign": d_train,
            "test_benign": d_tben,
            "test_malware": d_tmal,
            "test_benign_over_train_benign_median_ratio": ratio,
        },
        "auc_by_aggregation": results_agg,
        "diagnostics": diagnostics,
    }
    (out_dir / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")

    reproduce = {
        "corpus": "androct_2017",
        "arm_id": arm_id,
        "n_parts": n_parts,
        "static_mode": STATIC_MODE,
        "pins": comparison["pins"],
        "expected": {
            "auc_floor_mean": results_agg.get("mean", {}).get("auc", {}).get("auc_floor"),
            "final_train_loss": final_loss,
        },
    }
    (out_dir / "reproduce_config.json").write_text(json.dumps(reproduce, indent=2) + "\n", encoding="utf-8")

    # RUN.md
    lines = [
        f"# {arm_id} — AndroCT 2017 GAE (N={n_parts})",
        "",
        f"- static_mode: **{STATIC_MODE}**",
        f"- hidden={HIDDEN} epochs={EPOCHS} lr={LR} wd={WD} k={K_BURST} seed={SEED}",
        f"- eligibility: mapped>={ELIGIBILITY_MIN_MAPPED}",
        f"- edge_weight at GCNConv: is_none={edge_weight_report['received_at_call_site_is_none']} "
        f"tensor={edge_weight_report['tensor_repr']}",
        f"- feature diff L2(norm vs raw)={feat_diff.get('diff_norm_L2')} "
        f"differ={feat_diff.get('tensors_differ')}",
        "",
        "## Partition counts",
        f"```json\n{json.dumps(partition_counts, indent=2)}\n```",
        "",
        "## AUC (per-app)",
    ]
    for how, block in results_agg.items():
        a = block["auc"]
        lines.append(
            f"- agg={how}: auc={a['auc']:.6f} auc_floor={a['auc_floor']:.6f} "
            f"direction={a['direction']} spearman(score,mapped)={block['spearman_score_vs_mapped_count']:.4f}"
        )
    lines.append("")
    lines.append("## Recon error (per-app mean)")
    lines.append(
        f"- train_benign median={d_train['median']:.6f} IQR={d_train['iqr']:.6f}"
    )
    lines.append(
        f"- test_benign median={d_tben['median']:.6f} IQR={d_tben['iqr']:.6f}"
    )
    lines.append(
        f"- test_malware median={d_tmal['median']:.6f} IQR={d_tmal['iqr']:.6f}"
    )
    lines.append(f"- test_benign/train_benign median ratio={ratio:.6f}")
    lines.append("")
    (out_dir / "RUN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return comparison


def floor_aucs(eligible: list[AppRecord], split: dict[str, list[AppRecord]]) -> dict[str, Any]:
    """Recompute trivial floors on post-exclusion test set (benign held-out + malware)."""
    test_apps = split["test_benign"] + split["test_malware"]
    labels = [1 if a.label == "malware" else 0 for a in test_apps]

    def run(metric: str, values: list[float]) -> dict[str, Any]:
        auc = _auc_roc(values, labels)
        return {"metric": metric, **auc}

    mapped = [float(a.n_mapped) for a in test_apps]
    # total events not stored on AppRecord — load from inventory CSV
    inv = androct_inventory_dir()
    total_by_path: dict[str, float] = {}
    active_by_path: dict[str, float] = {}
    for label in ("benign", "malware"):
        with (inv / f"per_app_{label}.csv").open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                total_by_path[row["path"]] = float(row["n_events"])
                active_by_path[row["path"]] = float(row["n_active_cats"])

    totals = [total_by_path.get(a.path, float("nan")) for a in test_apps]
    actives = [active_by_path.get(a.path, float("nan")) for a in test_apps]
    return {
        "mapped_event_count": run("mapped_event_count", mapped),
        "total_event_count": run("total_event_count", totals),
        "distinct_active_categories": run("distinct_active_categories", actives),
        "n_test_apps": len(test_apps),
        "n_test_benign": len(split["test_benign"]),
        "n_test_malware": len(split["test_malware"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT initial GAE arms A/B")
    parser.add_argument(
        "--arm",
        choices=("arm_a_n1", "arm_b_n8", "both"),
        default="both",
    )
    parser.add_argument("--output-dir", type=Path, default=None, help="Output dir when running a single arm")
    args = parser.parse_args()

    raw = androct_raw_dir()
    out_root = ANDROCT_OUTPUT_ROOT
    out_root.mkdir(parents=True, exist_ok=True)


    print("[androct-gae] single-pass load (eligibility + events) …", flush=True)
    apps: list[AppRecord] = []
    excluded_mapped: dict[str, list[int]] = {"benign": [], "malware": []}
    n_eligible = {"benign": 0, "malware": 0}

    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        print(f"[androct-gae] stream {label} …", flush=True)
        n = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                if member.name.split("/", 1)[0] != inner:
                    raise SystemExit(f"year-dir mismatch {member.name}")
                n += 1
                if n % 200 == 0:
                    print(
                        f"  … {label} scanned={n} eligible={n_eligible[label]}",
                        flush=True,
                    )
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text_io = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                cats: list[str] = []
                try:
                    for raw_line in text_io:
                        m = _CALL_RE.match(raw_line.rstrip("\n\r"))
                        if not m:
                            continue
                        cat = categorize_soot_callee(m.group(2))
                        if cat is None:
                            continue
                        cats.append(cat)
                finally:
                    text_io.detach()
                if len(cats) < ELIGIBILITY_MIN_MAPPED:
                    excluded_mapped[label].append(len(cats))
                    continue
                n_eligible[label] += 1
                apps.append(
                    AppRecord(
                        path=member.name,
                        sha=_sha_from_member(member.name),
                        label=label,
                        n_mapped=len(cats),
                        categories=cats,
                    )
                )

    exclusion_report = {
        "min_mapped": ELIGIBILITY_MIN_MAPPED,
        "per_class": {
            label: {
                "n_excluded": len(excluded_mapped[label]),
                "n_eligible": n_eligible[label],
                "excluded_mapped_dist": _dist([float(x) for x in excluded_mapped[label]]),
            }
            for label in ("benign", "malware")
        },
    }
    print(json.dumps(exclusion_report, indent=2), flush=True)
    print(
        f"[androct-gae] eligible loaded: benign="
        f"{sum(1 for a in apps if a.label=='benign')} malware="
        f"{sum(1 for a in apps if a.label=='malware')}",
        flush=True,
    )

    split = split_apps(apps, seed=SEED, test_ratio=TEST_RATIO)
    print(
        f"[androct-gae] split train={len(split['train'])} "
        f"test_benign={len(split['test_benign'])} "
        f"test_malware={len(split['test_malware'])}",
        flush=True,
    )

    floors = floor_aucs(apps, split)
    (out_root / "floors.json").write_text(json.dumps(floors, indent=2) + "\n", encoding="utf-8")

    arms_to_run: list[tuple[str, int, Path]] = []
    if args.arm in ("arm_b_n8", "both"):
        arms_to_run.append(("arm_b_n8", 8, out_root / "arm_b_n8"))
    if args.arm in ("arm_a_n1", "both"):
        arms_to_run.append(("arm_a_n1", 1, out_root / "arm_a_n1"))
    if args.output_dir is not None and len(arms_to_run) == 1:
        arms_to_run[0] = (arms_to_run[0][0], arms_to_run[0][1], args.output_dir)

    arm_results: dict[str, dict[str, Any]] = {}
    for arm_id, n_parts, arm_out in arms_to_run:
        arm_results[arm_id] = run_arm(
            arm_id=arm_id,
            n_parts=n_parts,
            split=split,
            out_dir=arm_out,
            exclusion_report=exclusion_report,
        )

    if args.arm != "both":
        print(f"[androct-gae] done single arm {args.arm} → {arms_to_run[0][2]}")
        return

    arm_b = arm_results["arm_b_n8"]
    arm_a = arm_results["arm_a_n1"]

    lines = [
        "# AndroCT 2017 — ABRG GAE SUMMARY",
        "",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- static_mode: **{STATIC_MODE}**",
        f"- eligibility: mapped >= {ELIGIBILITY_MIN_MAPPED}",
        f"- pins: hidden={HIDDEN} epochs={EPOCHS} lr={LR} wd={WD} k={K_BURST} seed={SEED}",
        "",
        "## Exclusion",
        f"```json\n{json.dumps(exclusion_report, indent=2)}\n```",
        "",
        "## Floors (post-exclusion test set)",
    ]
    for key, block in floors.items():
        if not isinstance(block, dict) or "auc_floor" not in block:
            continue
        lines.append(
            f"- {key}: auc_floor={block['auc_floor']:.6f} "
            f"(raw={block['auc']:.6f}) direction={block['direction']}"
        )
    lines.append("")
    lines.append("## Arm vs arm vs floor")
    lines.append("")
    lines.append(
        "| Method | Aggregation | AUC_floor | Direction | Δ mapped-floor | Δ total-floor | Δ cats-floor |"
    )
    lines.append("|---|---|---:|---|---:|---:|---:|")

    floor_m = floors["mapped_event_count"]["auc_floor"]
    floor_t = floors["total_event_count"]["auc_floor"]
    floor_c = floors["distinct_active_categories"]["auc_floor"]

    def row(name: str, agg: str, block: dict[str, Any]) -> str:
        a = block["auc"]
        af = a["auc_floor"]
        return (
            f"| {name} | {agg} | {af:.6f} | {a['direction']} | "
            f"{af - floor_m:+.4f} | {af - floor_t:+.4f} | {af - floor_c:+.4f} |"
        )

    for arm_name, arm in (("arm_b_n8", arm_b), ("arm_a_n1", arm_a)):
        for agg, block in arm["auc_by_aggregation"].items():
            lines.append(row(arm_name, agg, block))
    lines.append(
        f"| floor_mapped | — | {floor_m:.6f} | {floors['mapped_event_count']['direction']} | 0 | — | — |"
    )
    lines.append(
        f"| floor_total | — | {floor_t:.6f} | {floors['total_event_count']['direction']} | — | 0 | — |"
    )
    lines.append(
        f"| floor_active_cats | — | {floor_c:.6f} | {floors['distinct_active_categories']['direction']} | — | — | 0 |"
    )
    lines.append("")
    lines.append("## Floor gate")
    for arm_name, arm in (("arm_b_n8", arm_b), ("arm_a_n1", arm_a)):
        for agg, block in arm["auc_by_aggregation"].items():
            af = block["auc"]["auc_floor"]
            if af < floor_m:
                lines.append(
                    f"- **{arm_name}/{agg} AUC_floor={af:.6f} is below mapped-event floor "
                    f"{floor_m:.6f}. Not a result.**"
                )
            else:
                lines.append(
                    f"- {arm_name}/{agg} AUC_floor={af:.6f} vs mapped-floor {floor_m:.6f}"
                )
    lines.append("")
    lines.append("## Edge-weight / feature verifies")
    for arm_name, arm in (("arm_b_n8", arm_b), ("arm_a_n1", arm_a)):
        lines.append(f"### {arm_name}")
        lines.append(f"- edge_weight: `{json.dumps(arm['edge_weight_verify'])}`")
        lines.append(f"- feature_diff: `{json.dumps(arm['feature_diff_verify'])}`")
    lines.append("")
    lines.append("## Leak check (Spearman score vs mapped count)")
    for arm_name, arm in (("arm_b_n8", arm_b), ("arm_a_n1", arm_a)):
        for agg, block in arm["auc_by_aggregation"].items():
            lines.append(
                f"- {arm_name}/{agg}: ρ={block['spearman_score_vs_mapped_count']:.6f}"
            )

    (out_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print("[androct-gae] done →", out_root)

if __name__ == "__main__":
    main()
