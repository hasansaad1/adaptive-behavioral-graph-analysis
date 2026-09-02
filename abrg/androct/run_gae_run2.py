"""AndroCT Run 2 — N=1 GAE with static features on finalized population."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import tarfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score, roc_curve

from abrg.androct.categorize import categorize_soot_callee
from abrg.androct.graph_build import (
    assert_recency_unpopulated,
    assert_universe,
    update_graph_sequence,
)
from abrg.androct.parse import _CALL_RE
from abrg.androct.paths import (
    EXPECTED_ARCHIVES,
    androct_apk_dir,
    androct_raw_dir,
    androct_run2_output_dir,
)
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.autoencoder import (
    build_gae,
    graph_reconstruction_error,
    seed_rng,
    train_gae_multi,
)
from abrg.config import GAE_EPOCHS, GAE_LR, K_BURST
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.graph import build_initial_graph
from abrg.registry import GATE_V_DIM, GRAPH_CATEGORY_UNIVERSE
from abrg.static import StaticReport, analyze_apk_static, zero_static_report

HIDDEN = 64
EPOCHS = GAE_EPOCHS
LR = GAE_LR
WD = 0.0
SEED = 42
TEST_RATIO = 0.2
STATIC_SLICE = 2 + GATE_V_DIM + 2  # s, declared, gate*, reach, epoch
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

assert len(GRAPH_CATEGORY_UNIVERSE) == 22


@dataclass
class AppRec:
    sha256: str
    path: str  # trace path in archive
    label: str
    n_mapped: int
    n_events: int
    n_active_cats: int
    source: str
    categories: list[str] = field(default_factory=list, repr=False)
    static: StaticReport | None = None
    static_ok: bool = False
    static_norm: float = 0.0
    static_zero: bool = True
    n_perm: int = 0
    n_cats_nonzero_static: int = 0
    apk_path: str = ""


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


def _auc_with_bootstrap(
    scores: list[float],
    labels: list[int],
    *,
    n_boot: int = BOOTSTRAP_N,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    y = np.array(labels, dtype=np.int32)
    s = np.array(scores, dtype=np.float64)
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return {
            "auc": float("nan"),
            "auc_floor": float("nan"),
            "direction": "undefined",
            "ci95": [float("nan"), float("nan")],
            "ci95_floor": [float("nan"), float("nan")],
            "roc_points": [],
            "n": int(len(y)),
            "n_pos": int(y.sum()) if len(y) else 0,
            "n_neg": int((1 - y).sum()) if len(y) else 0,
        }
    auc = float(roc_auc_score(y, s))
    fpr, tpr, thr = roc_curve(y, s)
    auc_floor = max(auc, 1.0 - auc)
    direction = "malware_higher_score" if auc >= 0.5 else "benign_higher_score"

    rng = np.random.default_rng(seed)
    boot = []
    boot_floor = []
    pos_idx = np.where(y == 1)[0]
    neg_idx = np.where(y == 0)[0]
    for _ in range(n_boot):
        pi = rng.choice(pos_idx, size=len(pos_idx), replace=True)
        ni = rng.choice(neg_idx, size=len(neg_idx), replace=True)
        idx = np.concatenate([pi, ni])
        yy, ss = y[idx], s[idx]
        if len(np.unique(yy)) < 2:
            continue
        a = float(roc_auc_score(yy, ss))
        boot.append(a)
        boot_floor.append(max(a, 1.0 - a))
    ci = (
        [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))]
        if boot
        else [float("nan"), float("nan")]
    )
    ci_f = (
        [float(np.percentile(boot_floor, 2.5)), float(np.percentile(boot_floor, 97.5))]
        if boot_floor
        else [float("nan"), float("nan")]
    )
    return {
        "auc": auc,
        "auc_floor": auc_floor,
        "direction": direction,
        "ci95": ci,
        "ci95_floor": ci_f,
        "n_boot": len(boot),
        "roc_points": [
            {"fpr": float(a), "tpr": float(b), "threshold": float(c)}
            for a, b, c in zip(fpr.tolist(), tpr.tolist(), thr.tolist())
        ],
        "n": int(len(y)),
        "n_pos": int(y.sum()),
        "n_neg": int((1 - y).sum()),
    }


def load_manifest() -> list[AppRec]:
    out = androct_run2_output_dir()
    rows = []
    with (out / "fetch_manifest.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(
                AppRec(
                    sha256=r["sha256"].upper(),
                    path=r["path"],
                    label=r["label"],
                    n_mapped=int(r["n_mapped"]),
                    n_events=int(r["n_events"]),
                    n_active_cats=int(r["n_active_cats"]),
                    source=r["source"],
                )
            )
    return rows


def stage2_static(apps: list[AppRec], resolution_rows: dict[str, dict]) -> dict[str, Any]:
    """Androguard static on resolved APKs only."""
    apk_dir = androct_apk_dir()
    parse_fail: list[dict[str, str]] = []
    for i, app in enumerate(apps):
        row = resolution_rows.get(app.sha256)
        if not row or row.get("status") != "resolved":
            continue
        apk = Path(row["apk_path"]) if row.get("apk_path") else apk_dir / f"{app.sha256}.apk"
        app.apk_path = str(apk)
        try:
            report = analyze_apk_static(apk)
            app.static = report
            app.static_ok = True
            app.n_perm = len(report.permissions)
            nz = 0
            for n in report.nodes.values():
                if n.declared_v > 0 or n.reach_v > 0 or n.s_v > 0 or any(n.gate_v):
                    nz += 1
            app.n_cats_nonzero_static = nz
            # static vector norm over static attrs
            vec = []
            for cat in GRAPH_CATEGORY_UNIVERSE:
                node = report.nodes[cat]
                vec.extend([node.s_v, node.declared_v, *node.gate_v, node.reach_v, node.epoch_v])
            arr = np.array(vec, dtype=np.float64)
            app.static_norm = float(np.linalg.norm(arr))
            app.static_zero = app.static_norm < 1e-12
        except Exception as exc:  # noqa: BLE001
            parse_fail.append(
                {"sha256": app.sha256, "label": app.label, "detail": f"{type(exc).__name__}: {exc}"[:300]}
            )
            app.static = zero_static_report(app.sha256)
            app.static_ok = False
            app.static_zero = True
        if (i + 1) % 50 == 0:
            print(f"  … static {i+1}/{len(apps)}", flush=True)

    report: dict[str, Any] = {"per_class": {}, "parse_failures": parse_fail}
    for label in ("benign", "malware"):
        cls = [a for a in apps if a.label == label and a.static_ok]
        perms = [float(a.n_perm) for a in cls]
        nz = [float(a.n_cats_nonzero_static) for a in cls]
        n_allzero = sum(1 for a in cls if a.static_zero)
        report["per_class"][label] = {
            "n_static_ok": len(cls),
            "n_parse_fail": sum(1 for a in apps if a.label == label and not a.static_ok and resolution_rows.get(a.sha256, {}).get("status") == "resolved"),
            "declared_permissions": _dist(perms),
            "n_cats_nonzero_static": _dist(nz),
            "n_all_zero_static_vector": n_allzero,
            "nonzero_cats_hist": dict(
                sorted(__import__("collections").Counter(int(x) for x in nz).items())
            ),
        }
    return report


def load_categories_for_eligible(apps: list[AppRec]) -> None:
    """Stream archives; fill categories for apps with n_mapped>=1 that we will train/score."""
    want = {a.path: a for a in apps if a.n_mapped >= 1}
    raw = androct_raw_dir()
    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        print(f"[run2] load traces {label} …", flush=True)
        n = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                if member.name.split("/", 1)[0] != inner:
                    raise SystemExit(f"year-dir mismatch {member.name}")
                n += 1
                app = want.get(member.name)
                if app is None:
                    continue
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
                    print(f"  … scanned={n} filled={sum(1 for a in want.values() if a.categories)}", flush=True)
        print(f"  {label} done scanned={n}", flush=True)


def build_graph_tensors(app: AppRec) -> dict[str, Any]:
    if not app.categories:
        raise ValueError("no categories")
    if app.static is None or app.static_zero or not app.static_ok:
        raise ValueError("static missing/zero — do not train")
    graph = build_initial_graph(static_report=app.static)
    assert_universe(graph)
    update_graph_sequence(graph, app.categories, k_burst=K_BURST)
    assert_recency_unpopulated(graph)
    x, ei, ew, _ = graph_to_tensors(graph, normalize=True, edge_weight_channel="w_cum")
    x_raw, _, _, _ = graph_to_tensors(graph, normalize=False, edge_weight_channel="w_cum")
    static_slice = x[:, :STATIC_SLICE]
    static_norm = float(static_slice.norm().item())
    n_active = len(graph.active_nodes())
    n_edges = sum(1 for _ in graph.iter_edges())
    possible = 22 * 21
    density = n_edges / possible if possible else 0.0
    return {
        "x": x,
        "x_raw": x_raw,
        "edge_index": ei,
        "edge_weight": ew,
        "static_slice_norm": static_norm,
        "static_slice_shape": list(static_slice.shape),
        "x_shape": list(x.shape),
        "n_active": n_active,
        "n_edges": n_edges,
        "density": density,
        "feat_diff_L2": float((x - x_raw).norm().item()),
    }


def split_apps(apps: list[AppRec]) -> dict[str, list[AppRec]]:
    rng = random.Random(SEED)
    benign = [a for a in apps if a.label == "benign"]
    malware = [a for a in apps if a.label == "malware"]
    rng.shuffle(benign)
    n_test = max(1, int(round(len(benign) * TEST_RATIO)))
    return {
        "train": benign[n_test:],
        "test_benign": benign[:n_test],
        "test_malware": malware,
    }


def floor_aucs(test_apps: list[AppRec], tensors: dict[str, dict]) -> dict[str, Any]:
    labels = [1 if a.label == "malware" else 0 for a in test_apps]

    def run(name: str, values: list[float]) -> dict[str, Any]:
        return {"metric": name, **_auc_with_bootstrap(values, labels)}

    mapped = [float(a.n_mapped) for a in test_apps]
    totals = [float(a.n_events) for a in test_apps]
    cats = [float(a.n_active_cats) for a in test_apps]
    act = [float(tensors[a.sha256]["n_active"]) for a in test_apps]
    edg = [float(tensors[a.sha256]["n_edges"]) for a in test_apps]
    dens = [float(tensors[a.sha256]["density"]) for a in test_apps]
    return {
        "mapped_event_count": run("mapped_event_count", mapped),
        "total_event_count": run("total_event_count", totals),
        "distinct_active_categories": run("distinct_active_categories", cats),
        "active_nodes": run("active_nodes", act),
        "edge_count": run("edge_count", edg),
        "graph_density": run("graph_density", dens),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT Run 2 — static fusion + stochastic GAE")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--from-cache",
        action="store_true",
        help="Skip Stage 2/3 rebuild; load corpus_cache from canonical run2 dir",
    )
    args = parser.parse_args()
    out = args.output_dir or androct_run2_output_dir()
    out.mkdir(parents=True, exist_ok=True)

    if args.from_cache:
        from abrg.androct.run2_corpus import load_corpus_cache

        cache_root = androct_run2_output_dir()
        bundle = load_corpus_cache(cache_root)
        static_report = (
            json.loads((cache_root / "stage2_static_report.json").read_text(encoding="utf-8"))
            if (cache_root / "stage2_static_report.json").is_file()
            else {}
        )
        stage3 = (
            json.loads((cache_root / "stage3_fusion.json").read_text(encoding="utf-8"))
            if (cache_root / "stage3_fusion.json").is_file()
            else {}
        )
        feat_diffs = [bundle.tensors[a.sha256]["feat_diff_L2"] for a in bundle.eligible]
        _run2_train_eval(
            out,
            apps=bundle.apps_fetch,
            eligible=bundle.eligible,
            tensors=bundle.tensors,
            split=bundle.split,
            feat_diffs=feat_diffs,
            static_report=static_report,
            stage3=stage3,
        )
        return

    print("[run2] load manifest + resolution …", flush=True)
    apps = load_manifest()
    res_path = out / "resolution_rows_manifest.csv"
    if not res_path.is_file():
        raise SystemExit("resolution_rows_manifest.csv missing — run fetch first")
    resolution: dict[str, dict] = {}
    with res_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            resolution[r["sha256"].upper()] = r

    # Only apps resolved at Stage 1
    resolved_apps = [a for a in apps if resolution.get(a.sha256, {}).get("status") == "resolved"]
    print(f"[run2] Stage 2 static on {len(resolved_apps)} resolved APKs …", flush=True)
    static_report = stage2_static(resolved_apps, resolution)
    (out / "stage2_static_report.json").write_text(json.dumps(static_report, indent=2) + "\n")

    # Eligible for graphs: resolved + static_ok + not static_zero + n_mapped>=1
    eligible = [
        a
        for a in resolved_apps
        if a.static_ok and not a.static_zero and a.n_mapped >= 1
    ]
    flagged_zero = [a for a in resolved_apps if a.static_ok and a.static_zero and a.n_mapped >= 1]
    print(
        f"[run2] eligible={len(eligible)} flagged_static_zero={len(flagged_zero)} "
        f"(benign={sum(1 for a in eligible if a.label=='benign')} "
        f"malware={sum(1 for a in eligible if a.label=='malware')})",
        flush=True,
    )
    stage3 = {
        "n_resolved": len(resolved_apps),
        "n_eligible": len(eligible),
        "flagged_static_zero": {
            "benign": sum(1 for a in flagged_zero if a.label == "benign"),
            "malware": sum(1 for a in flagged_zero if a.label == "malware"),
            "total": len(flagged_zero),
        },
        "static_slice_dims": STATIC_SLICE,
        "node_feature_dim": node_feature_dim(),
    }
    (out / "stage3_fusion.json").write_text(json.dumps(stage3, indent=2) + "\n")

    print("[run2] load mapped event sequences for eligible …", flush=True)
    load_categories_for_eligible(eligible)
    # drop if categories empty after parse
    eligible = [a for a in eligible if a.categories]
    print(f"[run2] with categories: {len(eligible)}", flush=True)

    print("[run2] build graphs …", flush=True)
    tensors: dict[str, dict] = {}
    feat_diffs = []
    for i, app in enumerate(eligible):
        try:
            tensors[app.sha256] = build_graph_tensors(app)
            feat_diffs.append(tensors[app.sha256]["feat_diff_L2"])
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {app.sha256}: {exc}", flush=True)
        if (i + 1) % 100 == 0:
            print(f"  … graphs {i+1}/{len(eligible)}", flush=True)
    eligible = [a for a in eligible if a.sha256 in tensors]
    if eligible:
        t0 = tensors[eligible[0].sha256]
        print(
            f"[VERIFY] x.shape={t0['x_shape']} static_slice_norm={t0['static_slice_norm']} "
            f"feat_diff_L2={t0['feat_diff_L2']}",
            flush=True,
        )
    stage3["feature_diff_L2_sample"] = tensors[eligible[0].sha256]["feat_diff_L2"] if eligible else None
    stage3["static_slice_norm_sample"] = tensors[eligible[0].sha256]["static_slice_norm"] if eligible else None
    stage3["x_shape_sample"] = tensors[eligible[0].sha256]["x_shape"] if eligible else None
    (out / "stage3_fusion.json").write_text(json.dumps(stage3, indent=2) + "\n")

    split = split_apps(eligible)
    _run2_train_eval(
        out,
        apps=apps,
        eligible=eligible,
        tensors=tensors,
        split=split,
        feat_diffs=feat_diffs,
        static_report=static_report,
        stage3=stage3,
    )


def _run2_train_eval(
    out: Path,
    *,
    apps: list[AppRec],
    eligible: list[AppRec],
    tensors: dict[str, dict],
    split: dict[str, list[AppRec]],
    feat_diffs: list[float],
    static_report: dict[str, Any],
    stage3: dict[str, Any],
) -> None:
    out.mkdir(parents=True, exist_ok=True)
    print(
        f"[run2] split train={len(split['train'])} test_benign={len(split['test_benign'])} "
        f"test_malware={len(split['test_malware'])}",
        flush=True,
    )

    # Floors on test
    test_apps = split["test_benign"] + split["test_malware"]
    floors = floor_aucs(test_apps, tensors)
    (out / "floors.json").write_text(json.dumps(floors, indent=2) + "\n")

    # Train
    seed_rng(SEED)
    model = build_gae(node_feature_dim(), HIDDEN)
    probe = EdgeWeightProbeEncoder(model.encoder)
    model.encoder = probe
    gcn_log: dict[str, Any] = {"last_is_none": None}
    _orig = probe.inner.conv1.forward

    def _conv1(x, edge_index, edge_weight=None, **kwargs):
        gcn_log["last_is_none"] = edge_weight is None
        if edge_weight is not None and gcn_log.get("n", 0) < 3:
            gcn_log["n"] = gcn_log.get("n", 0) + 1
            print(
                f"[VERIFY GCNConv] edge_weight.shape={tuple(edge_weight.shape)} "
                f"sample={edge_weight[:5].tolist()}",
                flush=True,
            )
        return _orig(x, edge_index, edge_weight=edge_weight, **kwargs)

    probe.inner.conv1.forward = _conv1  # type: ignore[method-assign]

    train_graphs = [
        (tensors[a.sha256]["x"], tensors[a.sha256]["edge_index"], tensors[a.sha256]["edge_weight"])
        for a in split["train"]
        if tensors[a.sha256]["edge_index"].numel() > 0
    ]
    print(f"[run2] train n_graphs={len(train_graphs)} hidden={HIDDEN} epochs={EPOCHS}", flush=True)
    if train_graphs:
        model.eval()
        with torch.no_grad():
            model.encode(*train_graphs[0])
    edge_weight_verify = {
        "gcnconv_is_none": gcn_log.get("last_is_none"),
        "encoder_is_none": probe.last_edge_weight_is_none,
    }
    losses, final_loss = train_gae_multi(model, train_graphs, EPOCHS, LR, weight_decay=WD)

    # Score
    def score_app(a: AppRec) -> float:
        t = tensors[a.sha256]
        return graph_reconstruction_error(model, t["x"], t["edge_index"], t["edge_weight"])

    train_scores = {a.sha256: score_app(a) for a in split["train"]}
    test_ben_scores = {a.sha256: score_app(a) for a in split["test_benign"]}
    test_mal_scores = {a.sha256: score_app(a) for a in split["test_malware"]}

    scores = [test_ben_scores[a.sha256] for a in split["test_benign"]] + [
        test_mal_scores[a.sha256] for a in split["test_malware"]
    ]
    labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
    auc_block = _auc_with_bootstrap(scores, labels)

    # Leak rhos
    def rho(xs: list[float], ys: list[float]) -> float:
        if len(xs) < 3:
            return float("nan")
        r, _ = spearmanr(xs, ys)
        return float(r)

    test_all = split["test_benign"] + split["test_malware"]
    sc = [scores[i] for i in range(len(test_all))]
    leak = {
        "mapped_event_count": rho(sc, [float(a.n_mapped) for a in test_all]),
        "total_event_count": rho(sc, [float(a.n_events) for a in test_all]),
        "active_nodes": rho(sc, [float(tensors[a.sha256]["n_active"]) for a in test_all]),
        "edge_count": rho(sc, [float(tensors[a.sha256]["n_edges"]) for a in test_all]),
        "graph_density": rho(sc, [float(tensors[a.sha256]["density"]) for a in test_all]),
        "static_feature_norm": rho(sc, [float(a.static_norm) for a in test_all]),
    }
    largest_rho = max(leak.items(), key=lambda kv: abs(kv[1]) if math.isfinite(kv[1]) else -1)

    # Recon distributions
    def app_errs(d: dict[str, float]) -> list[float]:
        return [v for v in d.values() if math.isfinite(v)]

    d_train = _dist(app_errs(train_scores))
    d_tben = _dist(app_errs(test_ben_scores))
    d_tmal = _dist(app_errs(test_mal_scores))
    ratio = (
        d_tben["median"] / d_train["median"]
        if d_train["median"] and d_train["median"] == d_train["median"] and d_train["median"] != 0
        else float("nan")
    )
    higher = (
        "test_malware"
        if d_tmal["median"] > d_tben["median"]
        else ("test_benign" if d_tben["median"] > d_tmal["median"] else "tied")
    )

    # Diagnostics
    def snap_diag(apps_list: list[AppRec]) -> dict[str, Any]:
        act = [float(tensors[a.sha256]["n_active"]) for a in apps_list]
        ed = [float(tensors[a.sha256]["n_edges"]) for a in apps_list]
        frac = (sum(1 for e in ed if e <= 2) / len(ed)) if ed else float("nan")
        return {
            "active_nodes": _dist(act),
            "edges": _dist(ed),
            "fraction_graphs_edges_le_2": frac,
        }

    diagnostics = {
        "train_benign": snap_diag(split["train"]),
        "test_benign": snap_diag(split["test_benign"]),
        "test_malware": snap_diag(split["test_malware"]),
    }

    floor_vals = [floors[k]["auc_floor"] for k in floors]
    highest_floor = max(floor_vals)
    arm_below = auc_block["auc_floor"] < highest_floor

    comparison = {
        "run": "run2",
        "n_parts": 1,
        "static_mode": "androguard_required",
        "pins": {
            "hidden": HIDDEN,
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WD,
            "k_burst": K_BURST,
            "seed": SEED,
            "test_ratio": TEST_RATIO,
            "scorer": "stochastic_recon_loss",
        },
        "population": {
            "n_final_benign_fetch": sum(1 for a in apps if a.label == "benign"),
            "n_malware_fetch": sum(1 for a in apps if a.label == "malware"),
            "n_eligible_train_eval": len(eligible),
            "split": {
                "train": len(split["train"]),
                "test_benign": len(split["test_benign"]),
                "test_malware": len(split["test_malware"]),
            },
        },
        "edge_weight_verify": edge_weight_verify,
        "feature_diff_L2_mean": float(np.mean(feat_diffs)) if feat_diffs else float("nan"),
        "final_train_loss": final_loss,
        "auc": auc_block,
        "floors": floors,
        "highest_floor": highest_floor,
        "arm_below_highest_floor": arm_below,
        "leak_spearman": leak,
        "largest_abs_rho": {"metric": largest_rho[0], "rho": largest_rho[1]},
        "recon_error": {
            "train_benign": d_train,
            "test_benign": d_tben,
            "test_malware": d_tmal,
            "test_benign_over_train_median_ratio": ratio,
            "higher_median_error_class": higher,
        },
        "diagnostics": diagnostics,
        "stage2": static_report,
        "stage3": stage3,
    }
    (out / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    (out / "reproduce_config.json").write_text(
        json.dumps(
            {
                "corpus": "androct_2017",
                "run": "run2",
                "pins": comparison["pins"],
                "expected": {
                    "auc_floor": auc_block["auc_floor"],
                    "auc_ci95_floor": auc_block["ci95_floor"],
                    "final_train_loss": final_loss,
                },
            },
            indent=2,
        )
        + "\n"
    )

    torch.save(
        {"model_state": model.state_dict(), "hidden": HIDDEN, "in_channels": node_feature_dim()},
        out / "gae_androct_run2_model.pt",
    )

    # SUMMARY
    lines = [
        "# AndroCT 2017 Run 2 — SUMMARY",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- static: Androguard mandatory; flagged_zero={stage3['flagged_static_zero']}",
        f"- pins: hidden={HIDDEN} epochs={EPOCHS} lr={LR} seed={SEED}",
        f"- edge_weight GCNConv is_none={edge_weight_verify['gcnconv_is_none']}",
        f"- feat_diff_L2 mean={comparison['feature_diff_L2_mean']}",
        "",
        "## Population / split",
        f"- eligible: {len(eligible)} (train={len(split['train'])} "
        f"test_benign={len(split['test_benign'])} test_malware={len(split['test_malware'])})",
        "",
        "## Arm AUC (per-app, N=1)",
        f"- auc={auc_block['auc']:.6f} auc_floor={auc_block['auc_floor']:.6f} "
        f"direction={auc_block['direction']}",
        f"- bootstrap 95% CI auc=[{auc_block['ci95'][0]:.6f}, {auc_block['ci95'][1]:.6f}]",
        f"- bootstrap 95% CI auc_floor=[{auc_block['ci95_floor'][0]:.6f}, {auc_block['ci95_floor'][1]:.6f}]",
        "",
        "## Floors (auc_floor + CI)",
    ]
    for k, b in floors.items():
        lines.append(
            f"- {k}: floor={b['auc_floor']:.6f} raw={b['auc']:.6f} dir={b['direction']} "
            f"CI_floor=[{b['ci95_floor'][0]:.6f}, {b['ci95_floor'][1]:.6f}]"
        )
    lines += [
        f"- highest_floor={highest_floor:.6f}",
        (
            f"- **Arm AUC_floor={auc_block['auc_floor']:.6f} is below highest floor "
            f"{highest_floor:.6f}. Not a result.**"
            if arm_below
            else f"- Arm AUC_floor={auc_block['auc_floor']:.6f} ≥ highest floor {highest_floor:.6f}"
        ),
        "",
        "## Leak Spearman ρ (score vs …)",
    ]
    for k, v in leak.items():
        lines.append(f"- {k}: {v:.6f}")
    lines.append(f"- largest |ρ|: {largest_rho[0]} = {largest_rho[1]:.6f}")
    lines += [
        "",
        "## Recon error medians",
        f"- train_benign={d_train['median']:.6f} IQR={d_train['iqr']:.6f}",
        f"- test_benign={d_tben['median']:.6f} IQR={d_tben['iqr']:.6f}",
        f"- test_malware={d_tmal['median']:.6f} IQR={d_tmal['iqr']:.6f}",
        f"- ratio test_ben/train={ratio:.6f}",
        f"- higher median error: **{higher}**",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (out / "RUN.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("[run2] done →", out)


if __name__ == "__main__":
    main()
