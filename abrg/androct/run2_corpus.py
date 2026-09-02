"""Shared AndroCT Run-2 corpus prep with on-disk tensor cache."""

from __future__ import annotations

import csv
import io
import json
import random
import tarfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch

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
from abrg.androct.run_gae_run2 import (
    STATIC_SLICE,
    AppRec,
    SEED,
    TEST_RATIO,
    load_manifest,
    split_apps,
)
from abrg.config import K_BURST
from abrg.features import graph_to_tensors, node_feature_dim
from abrg.graph import build_initial_graph
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.static import analyze_apk_static, zero_static_report

CACHE_DIRNAME = "corpus_cache"
CACHE_META = "meta.json"
CACHE_TENSORS = "tensors.pt"
CACHE_APPS = "apps.jsonl"
STATIC_SUBDIR = "static"  # per-APK Androguard reports; never re-extract if present


@dataclass
class CorpusBundle:
    apps_fetch: list[AppRec]
    eligible: list[AppRec]
    split: dict[str, list[AppRec]]
    tensors: dict[str, dict[str, Any]]
    eligibility: dict[str, Any]
    feat_diff_mean: float
    cache_dir: Path


def cache_dir(out: Optional[Path] = None) -> Path:
    root = out or androct_run2_output_dir()
    d = root / CACHE_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def static_cache_dir(out: Optional[Path] = None) -> Path:
    d = cache_dir(out) / STATIC_SUBDIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _static_path(static_dir: Path, sha256: str) -> Path:
    return static_dir / f"{sha256.upper()}.pt"


def _load_resolution(out: Path) -> dict[str, dict]:
    res_path = out / "resolution_rows_manifest.csv"
    resolution: dict[str, dict] = {}
    with res_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            resolution[r["sha256"].upper()] = r
    return resolution


def _apply_static_payload(app: AppRec, payload: dict[str, Any]) -> None:
    if payload.get("ok"):
        app.static = payload["report"]
        app.static_ok = True
        app.n_perm = int(payload["n_perm"])
        app.n_cats_nonzero_static = int(payload["n_cats_nonzero_static"])
        app.static_norm = float(payload["static_norm"])
        app.static_zero = bool(payload["static_zero"])
        if payload.get("apk_path"):
            app.apk_path = str(payload["apk_path"])
    else:
        app.static = zero_static_report(app.sha256)
        app.static_ok = False
        app.static_zero = True


def _static_worker(args: tuple[str, str, str, str]) -> dict[str, Any]:
    """
    Process-pool worker: (sha256, apk_path, label, out_path) → result dict.

    Writes `{out_path}` immediately so a killed parent still keeps finished APKs.
    """
    sha256, apk_path, label, out_path_s = args
    out_path = Path(out_path_s)
    try:
        report = analyze_apk_static(Path(apk_path))
        nz = 0
        for n in report.nodes.values():
            if n.declared_v > 0 or n.reach_v > 0 or n.s_v > 0 or any(n.gate_v):
                nz += 1
        vec: list[float] = []
        for cat in GRAPH_CATEGORY_UNIVERSE:
            node = report.nodes[cat]
            vec.extend([node.s_v, node.declared_v, *node.gate_v, node.reach_v, node.epoch_v])
        arr = np.array(vec, dtype=np.float64)
        static_norm = float(np.linalg.norm(arr))
        payload = {
            "sha256": sha256,
            "ok": True,
            "report": report,
            "n_perm": len(report.permissions),
            "n_cats_nonzero_static": nz,
            "static_norm": static_norm,
            "static_zero": static_norm < 1e-12,
            "label": label,
            "apk_path": apk_path,
        }
    except Exception as exc:  # noqa: BLE001
        payload = {
            "sha256": sha256,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:300],
            "label": label,
            "apk_path": apk_path,
        }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".pt.part")
    torch.save(payload, tmp)
    tmp.replace(out_path)
    return {"sha256": sha256, "ok": bool(payload.get("ok")), "cached": str(out_path)}


def _stage2_static(
    apps: list[AppRec],
    resolution: dict[str, dict],
    *,
    workers: int = 6,
    out: Optional[Path] = None,
) -> dict[str, int]:
    """
    Androguard static with durable per-APK cache under corpus_cache/static/.

    Existing `*.pt` files are loaded and never re-extracted.
    """
    apk_dir = androct_apk_dir()
    sdir = static_cache_dir(out)
    app_by_sha = {a.sha256: a for a in apps}
    jobs: list[tuple[str, str, str, str]] = []
    loaded = 0
    for app in apps:
        row = resolution.get(app.sha256)
        if not row or row.get("status") != "resolved":
            continue
        apk = Path(row["apk_path"]) if row.get("apk_path") else apk_dir / f"{app.sha256}.apk"
        app.apk_path = str(apk)
        sp = _static_path(sdir, app.sha256)
        if sp.is_file():
            payload = torch.load(sp, map_location="cpu", weights_only=False)
            _apply_static_payload(app, payload)
            loaded += 1
            continue
        jobs.append((app.sha256, str(apk), app.label, str(sp)))

    print(
        f"[corpus] Stage 2 static: cached={loaded} to_extract={len(jobs)} "
        f"workers={workers} dir={sdir}",
        flush=True,
    )
    extracted = 0
    if jobs:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for result in ex.map(_static_worker, jobs, chunksize=4):
                extracted += 1
                app = app_by_sha[result["sha256"]]
                payload = torch.load(
                    _static_path(sdir, result["sha256"]),
                    map_location="cpu",
                    weights_only=False,
                )
                _apply_static_payload(app, payload)
                if extracted % 50 == 0 or extracted == len(jobs):
                    print(
                        f"  … static extract {extracted}/{len(jobs)} "
                        f"(disk total≈{loaded + extracted})",
                        flush=True,
                    )
    # index for humans / future gates
    n_ok = sum(1 for a in apps if a.static_ok)
    index = {
        "n_resolved_apps": len(apps),
        "n_cached_loaded": loaded,
        "n_extracted_this_run": extracted,
        "n_static_ok": n_ok,
        "static_dir": str(sdir),
    }
    (cache_dir(out) / "static_index.json").write_text(json.dumps(index, indent=2) + "\n")
    print(f"[corpus] Stage 2 durable cache: {index}", flush=True)
    return index


def _load_categories(apps: list[AppRec]) -> None:
    want = {a.path: a for a in apps}
    raw = androct_raw_dir()
    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        print(f"[corpus] load traces {label} …", flush=True)
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
                    print(
                        f"  … scanned={n} filled={sum(1 for a in want.values() if a.categories)}",
                        flush=True,
                    )
        print(f"  {label} done scanned={n}", flush=True)


def _build_tensor(app: AppRec) -> dict[str, Any]:
    if not app.categories:
        raise ValueError("no categories")
    if app.static is None or app.static_zero or not app.static_ok:
        raise ValueError("static missing/zero")
    graph = build_initial_graph(static_report=app.static)
    assert_universe(graph)
    update_graph_sequence(graph, app.categories, k_burst=K_BURST)
    assert_recency_unpopulated(graph)
    x, ei, ew, _ = graph_to_tensors(graph, normalize=True, edge_weight_channel="w_cum")
    x_raw, _, _, _ = graph_to_tensors(graph, normalize=False, edge_weight_channel="w_cum")
    static_slice = x[:, :STATIC_SLICE]
    n_active = len(graph.active_nodes())
    n_edges = sum(1 for _ in graph.iter_edges())
    possible = 22 * 21
    density = n_edges / possible if possible else 0.0
    return {
        "x": x,
        "edge_index": ei,
        "edge_weight": ew,
        "static_slice_norm": float(static_slice.norm().item()),
        "n_active": n_active,
        "n_edges": n_edges,
        "density": density,
        "feat_diff_L2": float((x - x_raw).norm().item()),
        "static_norm": float(app.static_norm),
        "n_mapped": int(app.n_mapped),
        "n_events": int(app.n_events),
        "label": app.label,
        "sha256": app.sha256,
    }


def _cache_complete(d: Path) -> bool:
    return (d / CACHE_META).is_file() and (d / CACHE_TENSORS).is_file() and (d / CACHE_APPS).is_file()


def save_corpus_cache(bundle: CorpusBundle) -> None:
    d = bundle.cache_dir
    d.mkdir(parents=True, exist_ok=True)
    torch.save(bundle.tensors, d / CACHE_TENSORS)
    with (d / CACHE_APPS).open("w", encoding="utf-8") as f:
        for a in bundle.eligible:
            f.write(
                json.dumps(
                    {
                        "sha256": a.sha256,
                        "path": a.path,
                        "label": a.label,
                        "n_mapped": a.n_mapped,
                        "n_events": a.n_events,
                        "n_active_cats": a.n_active_cats,
                        "source": a.source,
                        "static_norm": a.static_norm,
                        "static_ok": a.static_ok,
                        "static_zero": a.static_zero,
                    }
                )
                + "\n"
            )
    meta = {
        "n_fetch": len(bundle.apps_fetch),
        "n_eligible": len(bundle.eligible),
        "split": {k: [a.sha256 for a in v] for k, v in bundle.split.items()},
        "eligibility": bundle.eligibility,
        "feat_diff_mean": bundle.feat_diff_mean,
        "node_feature_dim": node_feature_dim(),
        "static_slice": STATIC_SLICE,
        "seed": SEED,
        "test_ratio": TEST_RATIO,
        "k_burst": K_BURST,
    }
    (d / CACHE_META).write_text(json.dumps(meta, indent=2) + "\n")
    print(f"[corpus] cache written → {d}", flush=True)


def load_corpus_cache(out: Optional[Path] = None) -> CorpusBundle:
    root = out or androct_run2_output_dir()
    d = cache_dir(root)
    if not _cache_complete(d):
        raise FileNotFoundError(f"corpus cache incomplete under {d}")
    meta = json.loads((d / CACHE_META).read_text(encoding="utf-8"))
    tensors: dict[str, dict[str, Any]] = torch.load(
        d / CACHE_TENSORS, map_location="cpu", weights_only=False
    )
    apps_by_sha: dict[str, AppRec] = {}
    with (d / CACHE_APPS).open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            app = AppRec(
                sha256=r["sha256"],
                path=r["path"],
                label=r["label"],
                n_mapped=int(r["n_mapped"]),
                n_events=int(r["n_events"]),
                n_active_cats=int(r["n_active_cats"]),
                source=r["source"],
                static_norm=float(r.get("static_norm", 0.0)),
                static_ok=bool(r.get("static_ok", True)),
                static_zero=bool(r.get("static_zero", False)),
            )
            apps_by_sha[app.sha256] = app
    eligible = [apps_by_sha[s] for s in tensors.keys() if s in apps_by_sha]
    # preserve split order from meta
    split = {
        k: [apps_by_sha[s] for s in shas if s in apps_by_sha]
        for k, shas in meta["split"].items()
    }
    apps_fetch = load_manifest()
    return CorpusBundle(
        apps_fetch=apps_fetch,
        eligible=eligible,
        split=split,
        tensors=tensors,
        eligibility=meta.get("eligibility", {}),
        feat_diff_mean=float(meta.get("feat_diff_mean", float("nan"))),
        cache_dir=d,
    )


def prepare_corpus(*, force_rebuild: bool = False, out: Optional[Path] = None) -> CorpusBundle:
    """Build or load Run-2 eligible graphs (static + sequence, N=1)."""
    root = out or androct_run2_output_dir()
    d = cache_dir(root)
    if not force_rebuild and _cache_complete(d):
        print(f"[corpus] loading cache {d}", flush=True)
        return load_corpus_cache(root)

    print("[corpus] building (static + traces + graphs) …", flush=True)
    apps = load_manifest()
    resolution = _load_resolution(root)
    resolved = [a for a in apps if resolution.get(a.sha256, {}).get("status") == "resolved"]
    print(f"[corpus] Stage 2 static on {len(resolved)} …", flush=True)
    _stage2_static(resolved, resolution, out=root)

    ge1 = [a for a in resolved if a.static_ok and not a.static_zero and a.n_mapped >= 1]
    zmap = [a for a in resolved if a.n_mapped < 1]
    print(
        f"[corpus] ge1={len(ge1)} (benign={sum(1 for a in ge1 if a.label=='benign')} "
        f"malware={sum(1 for a in ge1 if a.label=='malware')})",
        flush=True,
    )
    _load_categories(ge1)
    empty_cats = [a for a in ge1 if not a.categories]
    with_cats = [a for a in ge1 if a.categories]
    print(
        f"[corpus] empty_categories={len(empty_cats)} with_categories={len(with_cats)}",
        flush=True,
    )

    tensors: dict[str, dict[str, Any]] = {}
    feat_diffs: list[float] = []
    for i, app in enumerate(with_cats):
        try:
            tensors[app.sha256] = _build_tensor(app)
            feat_diffs.append(tensors[app.sha256]["feat_diff_L2"])
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {app.sha256}: {exc}", flush=True)
        if (i + 1) % 100 == 0:
            print(f"  … graphs {i+1}/{len(with_cats)}", flush=True)
    eligible = [a for a in with_cats if a.sha256 in tensors]
    split = split_apps(eligible)

    from collections import Counter

    eligibility = {
        "fetch_total": len(apps),
        "fetch_by_label": dict(Counter(a.label for a in apps)),
        "drop_n_mapped_0": {
            "n": len(zmap),
            "by_label": dict(Counter(a.label for a in zmap)),
        },
        "ge1_static_ok": {
            "n": len(ge1),
            "by_label": dict(Counter(a.label for a in ge1)),
        },
        "drop_empty_categories": {
            "n": len(empty_cats),
            "by_label": dict(Counter(a.label for a in empty_cats)),
            "shas": [a.sha256 for a in empty_cats],
        },
        "eligible": {
            "n": len(eligible),
            "by_label": dict(Counter(a.label for a in eligible)),
        },
        "arithmetic": (
            f"{len(apps)} - {len(zmap)} - {len(empty_cats)} = {len(eligible)} "
            f"(graph-build skips={len(with_cats)-len(eligible)})"
        ),
    }
    feat_mean = float(sum(feat_diffs) / len(feat_diffs)) if feat_diffs else float("nan")
    bundle = CorpusBundle(
        apps_fetch=apps,
        eligible=eligible,
        split=split,
        tensors=tensors,
        eligibility=eligibility,
        feat_diff_mean=feat_mean,
        cache_dir=d,
    )
    save_corpus_cache(bundle)
    return bundle
