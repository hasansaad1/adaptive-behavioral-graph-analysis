"""Figures from saved run2 artefacts only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from abrg.chapter_b.config import FIGURES_DIR


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, format="svg", bbox_inches="tight")
    plt.close(fig)


def fig_category_fire(comparison: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    rows = list(comparison["category_fire"])
    rows_sorted = sorted(rows, key=lambda r: r["diff_v2_minus_androct"])
    cats = [r["category"] for r in rows_sorted]
    v2 = [r["v2_frac"] for r in rows_sorted]
    ac = [r["androct_benign_frac"] for r in rows_sorted]
    y = np.arange(len(cats))
    fig, ax = plt.subplots(figsize=(8, 10))
    h = 0.38
    ax.barh(y - h / 2, v2, height=h, label="v2 per-app pooled")
    ax.barh(y + h / 2, ac, height=h, label="AndroCT benign")
    ax.set_yticks(y)
    ax.set_yticklabels(cats, fontsize=8)
    ax.set_xlabel("fraction of apps with ≥1 mapped event in category")
    ax.set_xlim(0, 1)
    ax.legend(fontsize=8)
    ax.set_title("Category fire rate")
    fig.tight_layout()
    path = out_dir / "category_fire_rate.svg"
    _save(fig, path)
    return path


def fig_active_nodes(comparison: dict[str, Any], v2_units: dict[str, Any], androct_rows: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    v2p = [int(r["n_active"]) for r in v2_units["pooled"]]
    v2s = [int(r["n_active"]) for r in v2_units["session"]]
    acb = [int(r["n_active"]) for r in androct_rows["benign"]]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(acb, bins=range(0, 24), alpha=0.45, density=True, label="AndroCT benign")
    ax.hist(v2p, bins=range(0, 24), alpha=0.55, density=True, label="v2 per-app pooled")
    ax.hist(v2s, bins=range(0, 24), alpha=0.35, density=True, histtype="step", label="v2 per-session")
    ax.set_xlabel("active nodes")
    ax.set_ylabel("density")
    ax.legend(fontsize=8)
    ax.set_title("Active-node distribution")
    fig.tight_layout()
    path = out_dir / "active_nodes_dist.svg"
    _save(fig, path)
    return path


def fig_edges(v2_units: dict[str, Any], androct_rows: dict[str, Any], out_dir: Path = FIGURES_DIR) -> Path:
    v2p = [int(r["n_edges"]) for r in v2_units["pooled"]]
    v2s = [int(r["n_edges"]) for r in v2_units["session"]]
    acb = [int(r["n_edges"]) for r in androct_rows["benign"]]
    cap = 40
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bins = list(range(0, cap + 1))
    ax.hist([min(x, cap) for x in acb], bins=bins, alpha=0.45, density=True, label="AndroCT benign (capped)")
    ax.hist([min(x, cap) for x in v2p], bins=bins, alpha=0.55, density=True, label="v2 per-app pooled (capped)")
    ax.hist([min(x, cap) for x in v2s], bins=bins, alpha=0.35, density=True, histtype="step", label="v2 per-session (capped)")
    ax.set_xlabel(f"edges (values >{cap} stacked in last bin)")
    ax.set_ylabel("density")
    ax.legend(fontsize=8)
    ax.set_title("Edge-count distribution")
    fig.tight_layout()
    path = out_dir / "edges_dist.svg"
    _save(fig, path)
    return path


def make_figures(
    comparison: dict[str, Any],
    v2_units: dict[str, Any],
    androct_cache: dict[str, Any],
    out_dir: Path = FIGURES_DIR,
) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        fig_category_fire(comparison, out_dir),
        fig_active_nodes(comparison, v2_units, androct_cache["rows"], out_dir),
        fig_edges(v2_units, androct_cache["rows"], out_dir),
    ]
    return [str(p) for p in paths]
