"""Figures for Chapter C (vector SVG from saved artefacts only)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from abrg.chapter_c.config import FIGURES_DIR


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def fig_per_app_convergence(artefacts: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    conv = artefacts["stage2"]["convergence"]
    per = conv["per_app"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for app, row in per.items():
        ks = list(range(1, len(row["drift_primary"]) + 1))
        axes[0].plot(ks, row["drift_primary"], alpha=0.35, linewidth=0.8)
        axes[1].plot(
            list(range(1, len(row["heldout_primary"]) + 1)),
            row["heldout_primary"],
            alpha=0.35,
            linewidth=0.8,
        )
    axes[0].set_xlabel("k")
    axes[0].set_ylabel("d(R_k, R_{k+1})")
    axes[0].set_title("Per-app reference drift")
    axes[1].set_xlabel("k")
    axes[1].set_ylabel("e(R_k, S_{k+1})")
    axes[1].set_title("Per-app held-out session error")
    fig.tight_layout()
    path = out_dir / "F1_per_app_convergence.svg"
    _save(fig, path)
    return path


def fig_pooled_band(artefacts: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    conv = artefacts["stage2"]["convergence"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, key, ylab in (
        (axes[0], "pooled_drift_band", "d(R_k, R_{k+1})"),
        (axes[1], "pooled_heldout_band", "e(R_k, S_{k+1})"),
    ):
        band = conv[key]
        k = np.asarray(band["k"])
        med = np.asarray(band["median"])
        q1 = np.asarray(band["q1"])
        q3 = np.asarray(band["q3"])
        ax.fill_between(k, q1, q3, alpha=0.25)
        ax.plot(k, med, linewidth=1.5)
        # shuffle overlay (median of seed medians)
        sh = artefacts["stage2"]["shuffle"]["per_seed"]
        if sh:
            # interpolate onto k
            seed_meds = []
            for s in sh:
                b = s[key]
                seed_meds.append(np.interp(k, b["k"], b["median"], left=np.nan, right=np.nan))
            sm = np.nanmean(seed_meds, axis=0)
            ax.plot(k, sm, linestyle="--", linewidth=1.2, label="shuffle mean-of-medians")
            ax.legend(fontsize=8)
        ax.set_xlabel("k")
        ax.set_ylabel(ylab)
    axes[0].set_title("Pooled drift (median ± IQR)")
    axes[1].set_title("Pooled held-out error (median ± IQR)")
    fig.tight_layout()
    path = out_dir / "F2_pooled_median_iqr.svg"
    _save(fig, path)
    return path


def fig_within_cross(artefacts: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    cross = artefacts["stage2"]["cross_app"]
    # values stored in stage2 private dump
    within = artefacts["stage2"].get("_within") or []
    cross_v = artefacts["stage2"].get("_cross") or []
    fig, ax = plt.subplots(figsize=(6, 4))
    data = [within, cross_v]
    ax.boxplot(data, tick_labels=["within-app", "cross-app"], showfliers=False)
    ax.set_ylabel("held-out / cross error (frobenius_combined)")
    ax.set_title("Within-app vs cross-app error")
    fig.tight_layout()
    path = out_dir / "F3_within_vs_cross.svg"
    _save(fig, path)
    return path


def fig_recency_memory(artefacts: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    variants = artefacts["stage3"]["variants"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ch, style in (("w_cum", "-"), ("w_rec", "--"), ("both", ":")):
        band = variants[ch]["convergence"]["pooled_heldout_band"]
        axes[0].plot(band["k"], band["median"], linestyle=style, label=ch)
        ca = variants[ch]["cross_app"]
        axes[1].bar(
            [ch],
            [ca["cross_app"]["median"] - ca["within_app"]["median"]],
            label=ch,
        )
    axes[0].set_xlabel("k")
    axes[0].set_ylabel("median e(R_k, S_{k+1})")
    axes[0].set_title("Held-out error by edge-weight variant")
    axes[0].legend(fontsize=8)
    axes[1].set_ylabel("cross_med − within_med")
    axes[1].set_title("Within–cross separation")
    fig.tight_layout()
    path = out_dir / "F4_recency_vs_memory.svg"
    _save(fig, path)
    return path


def make_all_figures(artefacts_path: Path, out_dir: Path = FIGURES_DIR) -> list[str]:
    artefacts = json.loads(artefacts_path.read_text(encoding="utf-8"))
    paths = [
        fig_per_app_convergence(artefacts, out_dir),
        fig_pooled_band(artefacts, out_dir),
        fig_within_cross(artefacts, out_dir),
        fig_recency_memory(artefacts, out_dir),
    ]
    return [str(p) for p in paths]
