"""Assert app ID lists match Run 3 exactly."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import torch

from abrg.androct.paths import androct_run2_output_dir, androct_run3_output_dir
from abrg.androct.run2_corpus import load_corpus_cache, static_cache_dir


@dataclass
class SplitBundle:
    train: list[Any]
    test_benign: list[Any]
    test_malware: list[Any]
    by_sha: dict[str, Any]
    eligible: list[Any]
    sha_list_digest: str


def _sha_digest(split: dict[str, list[Any]]) -> str:
    parts = []
    for key in ("train", "test_benign", "test_malware"):
        parts.append(key + ":" + ",".join(a.sha256 for a in split[key]))
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _enrich_static(apps: list[Any]) -> None:
    """Load n_perm / component proxies from Run2 static cache (read-only)."""
    sdir = static_cache_dir(androct_run2_output_dir())
    for app in apps:
        sp = sdir / f"{app.sha256.upper()}.pt"
        if not sp.is_file():
            continue
        payload = torch.load(sp, map_location="cpu", weights_only=False)
        if not payload.get("ok"):
            continue
        app.n_perm = int(payload.get("n_perm", 0))
        app.n_cats_nonzero_static = int(payload.get("n_cats_nonzero_static", 0))
        app.static_norm = float(payload.get("static_norm", app.static_norm))
        app.static_ok = True
        report = payload.get("report")
        if report is not None:
            app.static = report
            # component count proxy: sum of per-category reach_v
            app.n_components = int(sum(float(n.reach_v) for n in report.nodes.values()))
        else:
            app.n_components = 0


def load_run3_split() -> SplitBundle:
    bundle = load_corpus_cache(androct_run2_output_dir())
    split = bundle.split
    run3 = json.loads((androct_run3_output_dir() / "comparison.json").read_text(encoding="utf-8"))
    expected = run3["population"]["split"]
    n_tr, n_tb, n_tm = len(split["train"]), len(split["test_benign"]), len(split["test_malware"])
    errors: list[str] = []
    if n_tr != int(expected["train"]):
        errors.append(f"train {n_tr} != run3 {expected['train']}")
    if n_tb != int(expected["test_benign"]):
        errors.append(f"test_benign {n_tb} != run3 {expected['test_benign']}")
    if n_tm != int(expected["test_malware"]):
        errors.append(f"test_malware {n_tm} != run3 {expected['test_malware']}")

    # Exact SHA lists from meta (shared Run2/Run3 corpus cache)
    meta = json.loads(
        (androct_run2_output_dir() / "corpus_cache" / "meta.json").read_text(encoding="utf-8")
    )
    for key in ("train", "test_benign", "test_malware"):
        meta_shas = list(meta["split"][key])
        live_shas = [a.sha256 for a in split[key]]
        if meta_shas != live_shas:
            errors.append(f"{key} SHA list mismatch vs corpus_cache/meta.json")

    if errors:
        raise SystemExit("STOP: app ID lists do not match Run 3:\n  - " + "\n  - ".join(errors))

    all_apps = list(split["train"]) + list(split["test_benign"]) + list(split["test_malware"])
    _enrich_static(all_apps)

    digest = _sha_digest(split)
    print(
        f"[apigraph] Run3 split OK train={n_tr} test_b={n_tb} test_m={n_tm} "
        f"sha_digest={digest[:12]}…",
        flush=True,
    )
    by_sha = {a.sha256: a for a in all_apps}
    return SplitBundle(
        train=list(split["train"]),
        test_benign=list(split["test_benign"]),
        test_malware=list(split["test_malware"]),
        by_sha=by_sha,
        eligible=list(bundle.eligible),
        sha_list_digest=digest,
    )
