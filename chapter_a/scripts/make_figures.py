"""Stage 4 — thesis figures from saved artifacts only.

Each function names the artifact it reads.
"""
from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from lib import ANDROCT, CHAPTER_A, load_json

FIGS = CHAPTER_A / "figures"
MASTER = CHAPTER_A / "MASTER_RESULTS.csv"


def _master():
    with MASTER.open() as f:
        return list(csv.DictReader(f))


def _f(r, k):
    try:
        return float(r[k])
    except (TypeError, ValueError):
        return None


def _style():
    plt.rcParams.update(
        {
            "font.size": 9,
            "axes.titlesize": 10,
            "figure.dpi": 120,
            "savefig.bbox": "tight",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.hashsalt": "chapter_a",
        }
    )


def _save(fig, stem: str):
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{stem}.pdf")
    fig.savefig(FIGS / f"{stem}.svg")
    plt.close(fig)


def f1_ladder():
    """Reads: MASTER_RESULTS.csv; CIs from ladder/rung1.json, rung2/behavioral_group_holdout.json, control/random_group_holdout.json."""
    m = _master()
    labels, vals, lo, hi = [], [], [], []
    specs = [
        ("rung 1", lambda r: r["experiment"] == "ladder" and r["detector"] == "HGB" and r["method"] == "supervised"),
        ("rung 2 pooled OOF", lambda r: r["detector"] == "HGB_pooled_oof_raw"),
        ("random-group", lambda r: "random_group" in r["method"] and r["detector"] == "HGB_mean_auc_floor"),
    ]
    for lab, pred in specs:
        r = next(x for x in m if pred(x))
        labels.append(lab)
        vals.append(_f(r, "auc_floor"))
        lo.append(_f(r, "ci_low") if r["ci_low"] else _f(r, "auc_floor"))
        hi.append(_f(r, "ci_high") if r["ci_high"] else _f(r, "auc_floor"))
    yerr = np.vstack([np.array(vals) - np.array(lo), np.array(hi) - np.array(vals)])
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    ax.errorbar(range(len(vals)), vals, yerr=yerr, fmt="o", capsize=4, color="black")
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=15)
    ax.set_ylabel("AUC floor")
    ax.set_ylim(0.5, 1.02)
    ax.set_title("Supervision ladder")
    _save(fig, "F1_ladder")


def f2_trained_vs_untrained():
    """Reads: ocdev/validation/check2_randominit/check2.json families + run8/comparison.json for embedding 6dp."""
    d = load_json(ANDROCT / "ocdev" / "validation" / "check2_randominit" / "check2.json")["families"]
    c8 = load_json(ANDROCT / "run8" / "comparison.json")
    names, deltas = [], []
    order = [
        ("GAE_reconstruction", "GAE recon"),
        ("GAE_embedding_distance", "GAE embed"),
        ("OCGIN", "OCGIN"),
        ("GLocalKD", "GLocalKD"),
        ("OCGTL", "OCGTL"),
    ]
    for key, lab in order:
        rec = d[key]
        if key == "GAE_embedding_distance":
            t = c8["by_encoder"]["trained_run5"]["reps"]["mean"]["scorers"]["centroid_euclidean"]["auc_floor"]
            u = c8["by_encoder"]["random_init"]["reps"]["mean"]["scorers"]["centroid_euclidean"]["auc_floor"]
            delta = t - u
        elif "trained_mean" in rec:
            delta = rec["trained_mean"] - rec["random_init_mean"]
        else:
            delta = rec["trained"] - rec["random_init"]
        names.append(lab)
        deltas.append(delta)
    fig, ax = plt.subplots(figsize=(4.8, 3.2))
    ax.axhline(0.0, color="0.4", lw=1)
    ax.bar(range(len(deltas)), deltas, color=["C0" if x >= 0 else "C3" for x in deltas])
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=20)
    ax.set_ylabel("trained − untrained AUC floor")
    ax.set_title("Trained vs untrained")
    _save(fig, "F2_trained_vs_untrained")


def _roc_from_points(points):
    fpr = [p["fpr"] for p in points]
    tpr = [p["tpr"] for p in points]
    return fpr, tpr


def f3_roc_headlines():
    """Reads: D1 centroid JSON roc_points; check1_summary R0; D3 HGB seed42 in results_trained.json;
    ladder/rung1.json; run3/floors.json mapped_event_count."""
    d1 = load_json(
        ANDROCT
        / "ocdev"
        / "partA_profiles"
        / "splitA_trained"
        / "trained__D1__none__centroid_euclidean__splitA__foldNA.json"
    )
    ocp = load_json(ANDROCT / "validation" / "check1_residualization" / "check1_summary.json")
    d3 = load_json(ANDROCT / "devread" / "splitA" / "results_trained.json")
    r1 = load_json(ANDROCT / "ladder" / "rung1" / "rung1.json")
    fl = load_json(ANDROCT / "run3" / "floors.json")
    series = [
        ("D1 centroid", d1["auc"]["roc_points"]),
        ("OCPool_mean", ocp["R0"]["auc"]["roc_points"]),
        ("D3+HGB", d3["D3"]["HGB"]["per_seed"][0]["auc"]["roc_points"]),
        ("HGB full", r1["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]["roc_points"]),
        ("mapped floor", fl["mapped_event_count"]["roc_points"]),
    ]
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    for name, pts in series:
        if not pts:
            continue
        fpr, tpr = _roc_from_points(pts)
        ax.plot(fpr, tpr, label=name, lw=1.4)
    ax.axvline(0.01, color="0.35", ls="--", lw=1, label="1% FPR")
    ax.plot([0, 1], [0, 1], color="0.7", lw=0.8)
    ax.set_xlabel("FPR")
    ax.set_ylabel("TPR")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=7, loc="lower right")
    ax.set_title("Headline ROCs")
    _save(fig, "F3_roc_headlines")


def f4_d1_node_ablation():
    """Reads: final_validation/check3_d1_volume/check3.json per_node_ablation_ranked."""
    d = load_json(ANDROCT / "final_validation" / "check3_d1_volume" / "check3.json")
    ranked = d["per_node_ablation_ranked"]
    names = [r["node"] for r in ranked]
    drops = [r["delta_auc_floor"] for r in ranked]
    fig, ax = plt.subplots(figsize=(6.5, 3.4))
    ax.bar(range(len(names)), drops, color="C0")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=90, fontsize=7)
    ax.set_ylabel("AUC-floor drop")
    ax.set_title("D1 per-node ablation")
    _save(fig, "F4_d1_node_ablation")


def f5_message_passing():
    """Reads: MASTER_RESULTS.csv rows experiment=supgnn, detector=GIN_mean_seeds / GIN_pooled_oof."""
    m = _master()
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), sharey=True)
    for ax, split, det in (
        (axes[0], "splitA_stratified", "GIN_mean_seeds"),
        (axes[1], "splitB_ward30", "GIN_pooled_oof"),
    ):
        rows = [r for r in m if r["experiment"] == "supgnn" and r["split"] == split and r["detector"] == det]
        if not rows:
            rows = [r for r in m if r["experiment"] == "supgnn" and r["split"] == split]
        labels, vals, colors = [], [], []
        cmap = {"M1_full": "C0", "M2_no_edges": "C1", "M3_const_feats": "C2"}
        for r in rows:
            labels.append(f"{r['representation']}\n{r['method']}")
            vals.append(_f(r, "auc_floor"))
            colors.append(cmap.get(r["method"], "0.5"))
        ax.bar(range(len(vals)), vals, color=colors)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=5, rotation=90)
        ax.set_title(split)
        ax.set_ylim(0.4, 1.0)
    axes[0].set_ylabel("AUC floor")
    fig.suptitle("M1 / M2 / M3")
    _save(fig, "F5_message_passing")


def f6_granularity():
    """Reads: run3/floors.json, apigraph/floors/K1000_floors.json,
    transitions/partA_invocation/no_self_loops_floors.json (22-category mapper)."""
    t22 = load_json(ANDROCT / "run3" / "floors.json")
    t1k = load_json(ANDROCT / "apigraph" / "floors" / "K1000_floors.json")
    inv = load_json(
        ANDROCT / "transitions" / "partA_invocation" / "no_self_loops_floors.json"
    )
    metrics = ["edge_count", "graph_density", "active_nodes"]
    reps = [("T22", t22), ("API-1000", t1k), ("invocation", inv)]
    x = np.arange(len(metrics))
    width = 0.25
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    for i, (name, blob) in enumerate(reps):
        vals = []
        for m in metrics:
            rec = blob.get(m) or blob.get("graph_density" if m == "density" else m)
            vals.append(rec["auc_floor"] if rec else np.nan)
        ax.bar(x + i * width, vals, width, label=name)
    ax.axhline(0.5, color="0.4", lw=1)
    ax.set_xticks(x + width)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("AUC floor")
    ax.set_ylim(0.45, 0.85)
    ax.legend(fontsize=8)
    ax.set_title("Structural floors across representations")
    _save(fig, "F6_granularity")


def make_figures():
    _style()
    f1_ladder()
    f2_trained_vs_untrained()
    f3_roc_headlines()
    f4_d1_node_ablation()
    f5_message_passing()
    f6_granularity()


if __name__ == "__main__":
    make_figures()
    print("figures written to", FIGS)
