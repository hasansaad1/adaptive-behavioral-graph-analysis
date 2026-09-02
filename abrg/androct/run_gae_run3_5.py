"""
AndroCT Run 3.5 — supervised representation capacity probe (DIAGNOSTIC ONLY).

Not a proposed detection method. Measures whether flattened graph tensors
carry benign/malware signal under standard tabular classifiers.

Same corpus cache / tensors as Run 2–3. GAE train is benign-only, so a
literal GAE split cannot fit a binary classifier; this probe uses a
stratified 80/20 split with the same seed=42 and test_ratio=0.2 on the
same 2403 eligible apps (both classes in train and test).
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from abrg.androct.paths import androct_run2_output_dir, androct_run3_5_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import (
    BOOTSTRAP_N,
    BOOTSTRAP_SEED,
    SEED,
    TEST_RATIO,
    _auc_with_bootstrap,
)
from abrg.features import feature_vector_labels
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

N_NODES = 22
assert len(GRAPH_CATEGORY_UNIVERSE) == N_NODES

FEAT_NAMES = feature_vector_labels(normalize=True)
N_FEAT = len(FEAT_NAMES)  # 10
assert N_FEAT == 10


def _adj_matrix(edge_index: torch.Tensor, edge_weight: torch.Tensor, n: int = N_NODES) -> np.ndarray:
    A = np.zeros((n, n), dtype=np.float64)
    if edge_index.numel() == 0:
        return A
    src = edge_index[0].cpu().numpy()
    dst = edge_index[1].cpu().numpy()
    w = edge_weight.cpu().numpy().astype(np.float64)
    for i, j, ww in zip(src, dst, w):
        A[int(i), int(j)] = float(ww)
    return A


def _node_feature_names() -> list[str]:
    names: list[str] = []
    for cat in GRAPH_CATEGORY_UNIVERSE:
        for f in FEAT_NAMES:
            names.append(f"node:{cat}:{f}")
    return names


def _adj_feature_names() -> list[str]:
    names: list[str] = []
    for u in GRAPH_CATEGORY_UNIVERSE:
        for v in GRAPH_CATEGORY_UNIVERSE:
            names.append(f"edge:{u}->{v}")
    return names


def _vectorize(
    tensors: dict[str, dict[str, Any]],
    apps: list,
    *,
    mode: str,
) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    """mode: full | node_only | adj_only"""
    node_names = _node_feature_names()
    adj_names = _adj_feature_names()
    if mode == "full":
        names = node_names + adj_names
    elif mode == "node_only":
        names = node_names
    elif mode == "adj_only":
        names = adj_names
    else:
        raise ValueError(mode)

    rows: list[np.ndarray] = []
    labels: list[int] = []
    shas: list[str] = []
    for a in apps:
        t = tensors[a.sha256]
        x = t["x"].detach().cpu().numpy().astype(np.float64).reshape(-1)  # 220
        A = _adj_matrix(t["edge_index"], t["edge_weight"]).reshape(-1)  # 484
        if mode == "full":
            vec = np.concatenate([x, A])
        elif mode == "node_only":
            vec = x
        else:
            vec = A
        rows.append(vec)
        labels.append(1 if a.label == "malware" else 0)
        shas.append(a.sha256)
    X = np.stack(rows, axis=0)
    y = np.array(labels, dtype=np.int32)
    return X, y, names, shas


def _stratified_split(apps: list, *, seed: int = SEED, test_ratio: float = TEST_RATIO):
    """Both-class stratified split (required for supervised binary fit)."""
    rng = np.random.default_rng(seed)
    benign = [a for a in apps if a.label == "benign"]
    malware = [a for a in apps if a.label == "malware"]
    rng.shuffle(benign)
    rng.shuffle(malware)
    n_tb = max(1, int(round(len(benign) * test_ratio)))
    n_tm = max(1, int(round(len(malware) * test_ratio)))
    return {
        "train": benign[n_tb:] + malware[n_tm:],
        "test_benign": benign[:n_tb],
        "test_malware": malware[:n_tm],
    }


def _floor_aucs_from_apps(test_apps: list, tensors: dict[str, dict]) -> dict[str, Any]:
    labels = [1 if a.label == "malware" else 0 for a in test_apps]

    def run(name: str, values: list[float]) -> dict[str, Any]:
        block = _auc_with_bootstrap(values, labels)
        return {
            "metric": name,
            "auc": block["auc"],
            "auc_floor": block["auc_floor"],
            "direction": block["direction"],
            "ci95": block["ci95"],
            "ci95_floor": block["ci95_floor"],
            "n": block["n"],
        }

    return {
        "mapped_event_count": run(
            "mapped_event_count", [float(tensors[a.sha256]["n_mapped"]) for a in test_apps]
        ),
        "total_event_count": run(
            "total_event_count", [float(tensors[a.sha256]["n_events"]) for a in test_apps]
        ),
        "distinct_active_categories": run(
            "distinct_active_categories", [float(a.n_active_cats) for a in test_apps]
        ),
        "active_nodes": run(
            "active_nodes", [float(tensors[a.sha256]["n_active"]) for a in test_apps]
        ),
        "edge_count": run(
            "edge_count", [float(tensors[a.sha256]["n_edges"]) for a in test_apps]
        ),
        "graph_density": run(
            "graph_density", [float(tensors[a.sha256]["density"]) for a in test_apps]
        ),
    }


def _top_abs(names: list[str], values: np.ndarray, k: int = 30) -> list[dict[str, Any]]:
    idx = np.argsort(np.abs(values))[::-1][:k]
    out = []
    for i in idx:
        out.append({"feature": names[int(i)], "value": float(values[int(i)])})
    return out


def _group_importance(names: list[str], values: np.ndarray) -> dict[str, Any]:
    """Aggregate |weight| by node category, edge endpoints, feature channel."""
    by_node: dict[str, float] = {c: 0.0 for c in GRAPH_CATEGORY_UNIVERSE}
    by_channel: dict[str, float] = {f: 0.0 for f in FEAT_NAMES}
    by_edge_src: dict[str, float] = {c: 0.0 for c in GRAPH_CATEGORY_UNIVERSE}
    by_edge_dst: dict[str, float] = {c: 0.0 for c in GRAPH_CATEGORY_UNIVERSE}
    node_mass = 0.0
    edge_mass = 0.0
    for name, val in zip(names, values):
        a = abs(float(val))
        if name.startswith("node:"):
            # node:cat:feat
            _, cat, feat = name.split(":", 2)
            by_node[cat] = by_node.get(cat, 0.0) + a
            by_channel[feat] = by_channel.get(feat, 0.0) + a
            node_mass += a
        elif name.startswith("edge:"):
            # edge:u->v
            body = name[len("edge:") :]
            u, v = body.split("->", 1)
            by_edge_src[u] = by_edge_src.get(u, 0.0) + a
            by_edge_dst[v] = by_edge_dst.get(v, 0.0) + a
            edge_mass += a

    def top_dict(d: dict[str, float], k: int = 15) -> list[dict[str, Any]]:
        items = sorted(d.items(), key=lambda kv: -kv[1])[:k]
        return [{"key": k_, "abs_mass": float(v_)} for k_, v_ in items]

    return {
        "node_feature_mass": node_mass,
        "adjacency_mass": edge_mass,
        "top_nodes_by_abs": top_dict(by_node),
        "top_channels_by_abs": top_dict(by_channel),
        "top_edge_sources_by_abs": top_dict(by_edge_src),
        "top_edge_dests_by_abs": top_dict(by_edge_dst),
    }


def _fit_eval(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    names: list[str],
    *,
    model_name: str,
) -> dict[str, Any]:
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
        coef = pipe.named_steps["clf"].coef_.reshape(-1)
        # scale coefficients back to original feature space approx via scaler
        scale = pipe.named_steps["scaler"].scale_
        coef_orig = coef / scale
        importance = {
            "type": "logistic_coefficient",
            "top_abs_coefficients": _top_abs(names, coef_orig, k=40),
            "grouped": _group_importance(names, coef_orig),
        }
    elif model_name == "hist_gradient_boosting":
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
        # sklearn >=1.4 has feature_importances_ via permutation optional;
        # use permutation importance on a subsample for stability
        from sklearn.inspection import permutation_importance

        rng_idx = np.random.default_rng(SEED).choice(
            len(X_test), size=min(800, len(X_test)), replace=False
        )
        imp = permutation_importance(
            clf,
            X_test[rng_idx],
            y_test[rng_idx],
            n_repeats=5,
            random_state=SEED,
            scoring="roc_auc",
            n_jobs=-1,
        )
        importance = {
            "type": "permutation_importance_auc",
            "top_abs_importances": _top_abs(names, imp.importances_mean, k=40),
            "grouped": _group_importance(names, imp.importances_mean),
        }
    else:
        raise ValueError(model_name)

    auc_block = _auc_with_bootstrap(scores, y_test.tolist())
    return {
        "model": model_name,
        "auc": auc_block,
        "importance": importance,
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "n_train_pos": int(y_train.sum()),
        "n_train_neg": int((1 - y_train).sum()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT Run 3.5 — supervised capacity probe")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    out = args.output_dir or androct_run3_5_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    run2 = androct_run2_output_dir()

    print("[run3.5] DIAGNOSTIC capacity probe — not a proposed method", flush=True)
    print("[run3.5] load corpus cache …", flush=True)
    bundle = load_corpus_cache(run2)
    tensors = bundle.tensors
    eligible = bundle.eligible

    # Supervised stratified split (both classes). Same seed/ratio pins.
    split = _stratified_split(eligible, seed=SEED, test_ratio=TEST_RATIO)
    test_apps = split["test_benign"] + split["test_malware"]
    train_apps = split["train"]
    print(
        f"[run3.5] stratified split train={len(train_apps)} "
        f"(benign={sum(1 for a in train_apps if a.label=='benign')} "
        f"malware={sum(1 for a in train_apps if a.label=='malware')}) "
        f"test_benign={len(split['test_benign'])} test_malware={len(split['test_malware'])}",
        flush=True,
    )

    floors = _floor_aucs_from_apps(test_apps, tensors)
    highest_floor = max(v["auc_floor"] for v in floors.values())
    (out / "floors.json").write_text(json.dumps(floors, indent=2) + "\n")

    # Reference: Run3 GAE-test floors (same size metrics, GAE test population)
    run3_floors_path = run2.parent / "run3" / "floors.json"
    run3_floors_ref: Optional[dict] = None
    if run3_floors_path.is_file():
        run3_floors_ref = json.loads(run3_floors_path.read_text(encoding="utf-8"))

    results: dict[str, Any] = {
        "run": "run3_5",
        "diagnostic_only": True,
        "not_a_proposed_method": True,
        "purpose": "representation_capacity_ceiling",
        "utc": datetime.now(timezone.utc).isoformat(),
        "pins": {
            "seed": SEED,
            "test_ratio": TEST_RATIO,
            "bootstrap_n": BOOTSTRAP_N,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "split": "stratified_both_class (GAE benign-only train cannot fit binary clf)",
            "tensors": "shared run2 corpus_cache",
        },
        "population": {
            "n_eligible": len(eligible),
            "split": {
                "train": len(train_apps),
                "train_benign": sum(1 for a in train_apps if a.label == "benign"),
                "train_malware": sum(1 for a in train_apps if a.label == "malware"),
                "test_benign": len(split["test_benign"]),
                "test_malware": len(split["test_malware"]),
            },
        },
        "floors_probe_test": floors,
        "highest_floor_probe_test": highest_floor,
        "floors_run3_gae_test_reference": (
            {
                k: {
                    "auc_floor": v.get("auc_floor"),
                    "direction": v.get("direction"),
                    "ci95_floor": v.get("ci95_floor"),
                }
                for k, v in run3_floors_ref.items()
            }
            if run3_floors_ref
            else None
        ),
        "modes": {},
    }

    modes = ("full", "node_only", "adj_only")
    models = ("logistic_regression", "hist_gradient_boosting")

    for mode in modes:
        print(f"[run3.5] vectorize mode={mode} …", flush=True)
        X_tr, y_tr, names, _ = _vectorize(tensors, train_apps, mode=mode)
        X_te, y_te, _, _ = _vectorize(tensors, test_apps, mode=mode)
        # replace non-finite
        X_tr = np.nan_to_num(X_tr, nan=0.0, posinf=0.0, neginf=0.0)
        X_te = np.nan_to_num(X_te, nan=0.0, posinf=0.0, neginf=0.0)
        mode_block: dict[str, Any] = {
            "n_features": len(names),
            "models": {},
        }
        for model_name in models:
            print(f"  fit {model_name} …", flush=True)
            mode_block["models"][model_name] = _fit_eval(
                X_tr, y_tr, X_te, y_te, names, model_name=model_name
            )
            ab = mode_block["models"][model_name]["auc"]
            print(
                f"    auc={ab['auc']:.4f} floor={ab['auc_floor']:.4f} "
                f"CI_floor=[{ab['ci95_floor'][0]:.4f},{ab['ci95_floor'][1]:.4f}]",
                flush=True,
            )
        results["modes"][mode] = mode_block

    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")

    # SUMMARY
    lines = [
        "# AndroCT Run 3.5 — DIAGNOSTIC representation capacity probe",
        "",
        "> **Not a proposed method.** Supervised tabular classifiers on flattened",
        "> ABRG tensors measure a capacity ceiling for the representation.",
        "> Do not cite as an ABRG detection result.",
        "",
        f"- UTC: {results['utc']}",
        f"- tensors: shared `run2/corpus_cache` (same as Run 3)",
        f"- split: stratified both-class seed={SEED} test_ratio={TEST_RATIO}",
        "  (GAE Run2/3 train is benign-only; binary supervised fit requires both classes)",
        f"- train={len(train_apps)} "
        f"(B={results['population']['split']['train_benign']} "
        f"M={results['population']['split']['train_malware']}) "
        f"test=B{len(split['test_benign'])}+M{len(split['test_malware'])}",
        "",
        "## Size floors (probe test set)",
    ]
    for k, b in floors.items():
        lines.append(
            f"- {k}: floor={b['auc_floor']:.6f} dir={b['direction']} "
            f"CI_floor=[{b['ci95_floor'][0]:.6f}, {b['ci95_floor'][1]:.6f}]"
        )
    lines.append(f"- highest_floor={highest_floor:.6f}")
    if run3_floors_ref:
        lines.extend(
            [
                "",
                "## Size floors reference (Run 3 GAE test population — for comparison)",
            ]
        )
        for k, v in run3_floors_ref.items():
            lines.append(
                f"- {k}: floor={v['auc_floor']:.6f} dir={v['direction']} "
                f"CI_floor=[{v['ci95_floor'][0]:.6f}, {v['ci95_floor'][1]:.6f}]"
            )

    lines.extend(["", "## AUC by representation mode × model"])
    lines.append("| mode | model | AUC | AUC_floor | CI_floor | vs highest size floor |")
    lines.append("|---|---|---:|---:|---|---|")
    for mode in modes:
        for model_name in models:
            ab = results["modes"][mode]["models"][model_name]["auc"]
            vs = "above" if ab["auc_floor"] >= highest_floor else "below"
            lines.append(
                f"| {mode} | {model_name} | {ab['auc']:.4f} | {ab['auc_floor']:.4f} | "
                f"[{ab['ci95_floor'][0]:.4f}, {ab['ci95_floor'][1]:.4f}] | {vs} |"
            )

    lines.extend(["", "## Where is the information? (full mode, top signals)"])
    for model_name in models:
        imp = results["modes"]["full"]["models"][model_name]["importance"]
        g = imp["grouped"]
        lines.append(f"### {model_name} ({imp['type']})")
        lines.append(
            f"- mass node_features={g['node_feature_mass']:.4f} "
            f"adjacency={g['adjacency_mass']:.4f}"
        )
        lines.append("- top nodes: " + ", ".join(
            f"{x['key']}={x['abs_mass']:.3f}" for x in g["top_nodes_by_abs"][:8]
        ))
        lines.append("- top channels: " + ", ".join(
            f"{x['key']}={x['abs_mass']:.3f}" for x in g["top_channels_by_abs"][:8]
        ))
        lines.append("- top features: " + ", ".join(
            f"{x['feature']}={x['value']:.4f}"
            for x in (imp.get("top_abs_coefficients") or imp.get("top_abs_importances") or [])[:8]
        ))

    lines.extend(
        [
            "",
            "## Localization (AUC_floor summary)",
        ]
    )
    for mode in modes:
        lr = results["modes"][mode]["models"]["logistic_regression"]["auc"]["auc_floor"]
        gb = results["modes"][mode]["models"]["hist_gradient_boosting"]["auc"]["auc_floor"]
        lines.append(f"- {mode}: LR_floor={lr:.4f} HGB_floor={gb:.4f}")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (out / "RUN.md").write_text(
        "\n".join(
            [
                "# RUN CARD — androct_2017 / run3_5 (DIAGNOSTIC ONLY)",
                "",
                "AXIS: supervised capacity probe on flattened tensors (not a method)",
                "PINS: seed=42 stratified both-class test_ratio=0.2 shared corpus_cache",
                "BASELINE: size floors on probe test; Run3 GAE floors as reference",
                "NOTES: Do not report as ABRG detection. GAE benign-only train cannot host binary clf.",
            ]
        )
        + "\n"
    )
    print("\n".join(lines), flush=True)
    print(f"[run3.5] done → {out}", flush=True)


if __name__ == "__main__":
    main()
