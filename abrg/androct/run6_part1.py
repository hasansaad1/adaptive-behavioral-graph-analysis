"""Run 6 Part 1 — supervised ceiling localization via node ablations."""

from __future__ import annotations

import argparse
import io
import json
import math
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from abrg.androct.categorize import categorize_soot_callee
from abrg.androct.parse import _CALL_RE
from abrg.androct.paths import (
    EXPECTED_ARCHIVES,
    androct_raw_dir,
    androct_run2_output_dir,
    androct_run6_output_dir,
)
from abrg.androct.run2_corpus import load_corpus_cache, static_cache_dir, _static_path
from abrg.androct.run_diagnostics import _class_from_sig, _is_tls_network_caller
from abrg.androct.run_gae_run2 import SEED, TEST_RATIO, _auc_with_bootstrap, _dist
from abrg.androct.run_gae_run3_5 import (
    FEAT_NAMES,
    N_FEAT,
    N_NODES,
    _adj_matrix,
    _stratified_split,
    _vectorize,
)
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

ACT_V_FRAC_IDX = FEAT_NAMES.index("act_v_frac")
CRYPTO_IDX = GRAPH_CATEGORY_UNIVERSE.index("crypto")

CONDITIONS: list[tuple[str, tuple[str, ...], bool]] = [
    # name, cats_to_zero, zero_edges
    ("a_baseline", (), True),
    ("b_crypto_zeroed", ("crypto",), True),
    ("b2_crypto_features_only", ("crypto",), False),  # edges retained
    ("c_file_io_zeroed", ("file_io",), True),
    ("d_crypto_and_file_io_zeroed", ("crypto", "file_io"), True),
    ("e_control_notifications_zeroed", ("notifications",), True),
    ("f_control_process_zeroed", ("process",), True),
]


def _ablate_tensor(
    t: dict[str, Any],
    cats: tuple[str, ...],
    *,
    zero_edges: bool,
) -> dict[str, Any]:
    if not cats:
        return t
    idxs = {GRAPH_CATEGORY_UNIVERSE.index(c) for c in cats}
    x = t["x"].clone()
    for i in idxs:
        x[i] = 0.0
    ei = t["edge_index"]
    ew = t["edge_weight"]
    if zero_edges and ei.numel() > 0:
        src = ei[0]
        dst = ei[1]
        keep = torch.ones(ei.size(1), dtype=torch.bool)
        for i in idxs:
            keep &= (src != i) & (dst != i)
        ei = ei[:, keep]
        ew = ew[keep] if ew.numel() == keep.numel() else ew[keep]
    out = dict(t)
    out["x"] = x
    out["edge_index"] = ei
    out["edge_weight"] = ew
    return out


def _ablate_all(
    tensors: dict[str, dict[str, Any]],
    cats: tuple[str, ...],
    *,
    zero_edges: bool,
) -> dict[str, dict[str, Any]]:
    if not cats:
        return tensors
    return {sha: _ablate_tensor(t, cats, zero_edges=zero_edges) for sha, t in tensors.items()}


def _fit_auc_only(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    *,
    model_name: str,
) -> dict[str, Any]:
    X_train = np.nan_to_num(X_train, nan=0.0, posinf=0.0, neginf=0.0)
    X_test = np.nan_to_num(X_test, nan=0.0, posinf=0.0, neginf=0.0)
    if model_name == "logistic_regression":
        pipe = Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=4000,
                        class_weight="balanced",
                        solver="lbfgs",
                        random_state=SEED,
                    ),
                ),
            ]
        )
        pipe.fit(X_train, y_train)
        scores = pipe.predict_proba(X_test)[:, 1].tolist()
    else:
        clf = HistGradientBoostingClassifier(
            max_depth=6,
            learning_rate=0.08,
            max_iter=300,
            random_state=SEED,
            early_stopping=True,
            validation_fraction=0.1,
            n_iter_no_change=20,
        )
        clf.fit(X_train, y_train)
        scores = clf.predict_proba(X_test)[:, 1].tolist()
    return _auc_with_bootstrap(scores, y_test.tolist())


def _load_package_names(shas: set[str]) -> dict[str, str]:
    sdir = static_cache_dir(androct_run2_output_dir())
    out: dict[str, str] = {}
    for sha in shas:
        sp = _static_path(sdir, sha)
        if not sp.is_file():
            continue
        payload = torch.load(sp, map_location="cpu", weights_only=False)
        if payload.get("ok") and payload.get("report") is not None:
            out[sha] = str(getattr(payload["report"], "package_name", "") or "")
    return out


def _is_app_caller(caller_class: str, package_name: str) -> bool:
    pkg = (package_name or "").strip()
    if not pkg or not caller_class:
        return False
    return caller_class == pkg or caller_class.startswith(pkg + ".")


def _per_app_crypto_tls_share(eligible: list, pkg_by_sha: dict[str, str]) -> dict[str, dict[str, float]]:
    """Per-app share of crypto events with TLS/net library callers."""
    want = {a.path: a for a in eligible}
    stats: dict[str, dict[str, int]] = {
        a.sha256: {"crypto": 0, "tls": 0, "app": 0, "other": 0} for a in eligible
    }
    raw = androct_raw_dir()
    for fname, meta in EXPECTED_ARCHIVES.items():
        print(f"[run6/p1] TLS-share scan {meta['label']} …", flush=True)
        n = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                app = want.get(member.name)
                if app is None:
                    continue
                n += 1
                pkg = pkg_by_sha.get(app.sha256, "")
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                try:
                    for line in text:
                        m = _CALL_RE.match(line.rstrip("\n\r"))
                        if not m:
                            continue
                        if categorize_soot_callee(m.group(2)) != "crypto":
                            continue
                        caller = _class_from_sig(m.group(1)) or ""
                        st = stats[app.sha256]
                        st["crypto"] += 1
                        if _is_tls_network_caller(caller):
                            st["tls"] += 1
                        elif _is_app_caller(caller, pkg):
                            st["app"] += 1
                        else:
                            st["other"] += 1
                finally:
                    text.detach()
                if n % 200 == 0:
                    print(f"  … {meta['label']} {n}", flush=True)
    out: dict[str, dict[str, float]] = {}
    for sha, st in stats.items():
        tot = st["crypto"]
        out[sha] = {
            "n_crypto": float(tot),
            "tls_share": (st["tls"] / tot) if tot else float("nan"),
            "app_share": (st["app"] / tot) if tot else float("nan"),
            "other_share": (st["other"] / tot) if tot else float("nan"),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 6 Part 1 — supervised node ablations")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    out = args.output_dir or (androct_run6_output_dir() / "part1_ablation")
    out.mkdir(parents=True, exist_ok=True)
    bundle = load_corpus_cache(androct_run2_output_dir())
    tensors = bundle.tensors
    eligible = bundle.eligible
    split = _stratified_split(eligible, seed=SEED, test_ratio=TEST_RATIO)
    train_apps = split["train"]
    test_apps = split["test_benign"] + split["test_malware"]
    print(
        f"[run6/p1] stratified train={len(train_apps)} "
        f"test=B{len(split['test_benign'])}+M{len(split['test_malware'])}",
        flush=True,
    )

    # crypto:act_v_frac distributions
    crypto_act = {
        "benign": [],
        "malware": [],
    }
    for a in eligible:
        v = float(tensors[a.sha256]["x"][CRYPTO_IDX, ACT_V_FRAC_IDX].item())
        crypto_act[a.label].append(v)

    # TLS share + Spearman
    tls_cache = out / "per_app_crypto_tls_share.json"
    if tls_cache.is_file():
        tls_by_sha = json.loads(tls_cache.read_text(encoding="utf-8"))
        print(f"[run6/p1] loaded TLS share cache n={len(tls_by_sha)}", flush=True)
    else:
        pkg = _load_package_names({a.sha256 for a in eligible})
        tls_by_sha = _per_app_crypto_tls_share(eligible, pkg)
        tls_cache.write_text(json.dumps(tls_by_sha, indent=2) + "\n")

    act_vals = []
    tls_vals = []
    for a in eligible:
        act = float(tensors[a.sha256]["x"][CRYPTO_IDX, ACT_V_FRAC_IDX].item())
        tls = tls_by_sha.get(a.sha256, {}).get("tls_share", float("nan"))
        if math.isfinite(act) and math.isfinite(tls):
            act_vals.append(act)
            tls_vals.append(float(tls))
    rho_act_tls = float(spearmanr(act_vals, tls_vals).correlation) if len(act_vals) >= 3 else float("nan")

    modes = ("full", "node_only", "adj_only")
    models = ("logistic_regression", "hist_gradient_boosting")
    results: dict[str, Any] = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "part": 1,
        "diagnostic_only": True,
        "split": {
            "train": len(train_apps),
            "test_benign": len(split["test_benign"]),
            "test_malware": len(split["test_malware"]),
        },
        "crypto_act_v_frac": {
            "benign": _dist(crypto_act["benign"]),
            "malware": _dist(crypto_act["malware"]),
        },
        "spearman_crypto_act_v_frac_vs_tls_caller_share": {
            "rho": rho_act_tls,
            "n_pairs": len(act_vals),
        },
        "conditions": {},
    }

    baseline_floors: dict[str, dict[str, float]] = {}

    for cond_name, cats, zero_edges in CONDITIONS:
        print(f"[run6/p1] condition={cond_name} cats={cats} zero_edges={zero_edges}", flush=True)
        ablated = _ablate_all(tensors, cats, zero_edges=zero_edges)
        cond_block: dict[str, Any] = {
            "cats_zeroed": list(cats),
            "edges_removed": bool(cats) and zero_edges,
            "modes": {},
        }
        for mode in modes:
            X_tr, y_tr, _, _ = _vectorize(ablated, train_apps, mode=mode)
            X_te, y_te, _, _ = _vectorize(ablated, test_apps, mode=mode)
            mode_block: dict[str, Any] = {"models": {}}
            for model_name in models:
                auc = _fit_auc_only(X_tr, y_tr, X_te, y_te, model_name=model_name)
                key = f"{mode}|{model_name}"
                if cond_name == "a_baseline":
                    baseline_floors[key] = auc["auc_floor"]
                delta = (
                    auc["auc_floor"] - baseline_floors[key]
                    if key in baseline_floors
                    else float("nan")
                )
                mode_block["models"][model_name] = {
                    "auc": auc["auc"],
                    "auc_floor": auc["auc_floor"],
                    "direction": auc["direction"],
                    "ci95_floor": auc["ci95_floor"],
                    "delta_auc_floor_vs_baseline": delta,
                    "n": auc["n"],
                }
                print(
                    f"  {mode} {model_name}: floor={auc['auc_floor']:.4f} Δ={delta:+.4f}",
                    flush=True,
                )
            cond_block["modes"][mode] = mode_block
        results["conditions"][cond_name] = cond_block

    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")

    lines = [
        "# Run 6 Part 1 — supervised ceiling localization (ablations)",
        f"- UTC: {results['utc']}",
        f"- population: run-3 eligible n={len(eligible)}; stratified seed={SEED}",
        "",
        "## crypto:act_v_frac by class",
        f"- benign: med={results['crypto_act_v_frac']['benign']['median']:.6f} "
        f"IQR={results['crypto_act_v_frac']['benign']['iqr']:.6f} "
        f"n={results['crypto_act_v_frac']['benign']['n']}",
        f"- malware: med={results['crypto_act_v_frac']['malware']['median']:.6f} "
        f"IQR={results['crypto_act_v_frac']['malware']['iqr']:.6f} "
        f"n={results['crypto_act_v_frac']['malware']['n']}",
        f"- Spearman(crypto:act_v_frac, TLS-caller share): "
        f"ρ={rho_act_tls:.6f} n={len(act_vals)}",
        "",
        "## AUC_floor by condition × mode × model (Δ vs baseline)",
        "| condition | mode | model | AUC_floor | CI_floor | Δ vs baseline |",
        "|---|---|---|---:|---|---:|",
    ]
    for cond_name, _, _ in CONDITIONS:
        cb = results["conditions"][cond_name]
        for mode in modes:
            for model_name in models:
                m = cb["modes"][mode]["models"][model_name]
                lines.append(
                    f"| {cond_name} | {mode} | {model_name} | {m['auc_floor']:.4f} | "
                    f"[{m['ci95_floor'][0]:.4f}, {m['ci95_floor'][1]:.4f}] | "
                    f"{m['delta_auc_floor_vs_baseline']:+.4f} |"
                )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(f"[run6/p1] done → {out}", flush=True)


if __name__ == "__main__":
    main()
