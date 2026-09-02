"""Repair Run 2 diagnostics (no retrain): AUC exclusions, NaN-filtered metrics, eligibility."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.stats import spearmanr

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import prepare_corpus
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import (
    HIDDEN,
    _auc_with_bootstrap,
    _dist,
    floor_aucs,
)
from abrg.autoencoder import build_gae, graph_reconstruction_error
from abrg.features import node_feature_dim


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def main() -> None:
    out = androct_run2_output_dir()
    bundle = prepare_corpus(force_rebuild=False, out=out)
    split = bundle.split
    tensors = bundle.tensors

    ckpt = torch.load(out / "gae_androct_run2_model.pt", map_location="cpu", weights_only=False)
    model = build_gae(node_feature_dim(), HIDDEN)
    model.encoder = EdgeWeightProbeEncoder(model.encoder)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    def score_app(sha: str) -> float:
        t = tensors[sha]
        return graph_reconstruction_error(model, t["x"], t["edge_index"], t["edge_weight"])

    test_apps = split["test_benign"] + split["test_malware"]
    rows: list[dict[str, Any]] = []
    for a in test_apps:
        t = tensors[a.sha256]
        sc = score_app(a.sha256)
        rows.append(
            {
                "sha256": a.sha256,
                "label": a.label,
                "score": sc,
                "n_mapped": int(t["n_mapped"]),
                "n_events": int(t["n_events"]),
                "n_active": int(t["n_active"]),
                "n_edges": int(t["n_edges"]),
                "density": float(t["density"]),
                "static_norm": float(t["static_norm"]),
                "empty_edge_index": bool(t["edge_index"].numel() == 0),
            }
        )

    excluded = [r for r in rows if not math.isfinite(r["score"])]
    by_cause = Counter(
        "empty_edge_index_nan_score" if r["empty_edge_index"] else "other_nan_score"
        for r in excluded
    )
    by_label = Counter(r["label"] for r in excluded)
    n_test_b = len(split["test_benign"])
    n_test_m = len(split["test_malware"])
    n_ex_b = by_label.get("benign", 0)
    n_ex_m = by_label.get("malware", 0)

    scores = [r["score"] for r in rows]
    labels = [1 if r["label"] == "malware" else 0 for r in rows]
    auc_block = _auc_with_bootstrap(scores, labels)

    finite = [r for r in rows if math.isfinite(r["score"])]
    sc = [float(r["score"]) for r in finite]
    leak = {
        "mapped_event_count": _rho(sc, [float(r["n_mapped"]) for r in finite]),
        "total_event_count": _rho(sc, [float(r["n_events"]) for r in finite]),
        "active_nodes": _rho(sc, [float(r["n_active"]) for r in finite]),
        "edge_count": _rho(sc, [float(r["n_edges"]) for r in finite]),
        "graph_density": _rho(sc, [float(r["density"]) for r in finite]),
        "static_feature_norm": _rho(sc, [float(r["static_norm"]) for r in finite]),
    }
    largest_rho = max(leak.items(), key=lambda kv: abs(kv[1]) if math.isfinite(kv[1]) else -1)

    def part_density(apps):
        act = [float(tensors[a.sha256]["n_active"]) for a in apps]
        ed = [float(tensors[a.sha256]["n_edges"]) for a in apps]
        dens = [float(tensors[a.sha256]["density"]) for a in apps]
        return {"active_nodes": _dist(act), "edges": _dist(ed), "density": _dist(dens)}

    density = {
        "train_benign": part_density(split["train"]),
        "test_benign": part_density(split["test_benign"]),
        "test_malware": part_density(split["test_malware"]),
    }
    densest = max(
        density.items(),
        key=lambda kv: (
            kv[1]["edges"]["median"] if math.isfinite(kv[1]["edges"]["median"]) else -1,
            kv[1]["active_nodes"]["median"] if math.isfinite(kv[1]["active_nodes"]["median"]) else -1,
        ),
    )[0]

    floors = floor_aucs(test_apps, tensors)
    # eligibility from cache or recompute summary
    elig = bundle.eligibility
    if not elig:
        elig_path = out / "postmortem_eligibility.json"
        if elig_path.is_file():
            elig = json.loads(elig_path.read_text(encoding="utf-8"))

    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "n_test": len(rows),
        "n_auc": auc_block["n"],
        "n_excluded": len(excluded),
        "excluded_by_label": dict(by_label),
        "excluded_rates": {
            "test_benign": {"n_ex": n_ex_b, "n": n_test_b, "rate": n_ex_b / n_test_b if n_test_b else None},
            "test_malware": {"n_ex": n_ex_m, "n": n_test_m, "rate": n_ex_m / n_test_m if n_test_m else None},
        },
        "excluded_by_cause": dict(by_cause),
        "excluded_apps": excluded,
        "asymmetry_note": (
            f"benign exclusion rate {n_ex_b}/{n_test_b}={n_ex_b/n_test_b:.4f} vs "
            f"malware {n_ex_m}/{n_test_m}={n_ex_m/n_test_m:.4f}"
            if n_test_b and n_test_m
            else ""
        ),
        "auc_nan_filtered": auc_block,
        "leak_spearman_nan_filtered": leak,
        "largest_abs_rho": {"metric": largest_rho[0], "rho": largest_rho[1]},
        "density_by_partition": density,
        "densest_partition_by_median_edges": densest,
        "eligibility": elig,
        "floors_same_population": {
            k: {
                "auc": v["auc"],
                "auc_floor": v["auc_floor"],
                "direction": v["direction"],
                "ci95_floor": v["ci95_floor"],
            }
            for k, v in floors.items()
        },
    }
    (out / "POSTMORTEM.json").write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# AndroCT Run 2 — POSTMORTEM (diagnostics repair, no retrain)",
        f"- UTC: {report['utc']}",
        "",
        "## A1 — AUC exclusions",
        f"- test apps: {len(rows)}; AUC n (finite scores): {auc_block['n']}; excluded: {len(excluded)}",
        f"- by class: benign={n_ex_b}/{n_test_b} malware={n_ex_m}/{n_test_m}",
        f"- **asymmetry:** {report['asymmetry_note']}",
        f"- cause counts: {dict(by_cause)}",
        "- cause: `graph_reconstruction_error` returns NaN when `edge_index.numel()==0` "
        "(no directed inter-category edges after k=5 sequence update; self-transitions skipped).",
        "",
        "## A2 — NaN-filtered metrics",
        f"- auc={auc_block['auc']:.6f} auc_floor={auc_block['auc_floor']:.6f} "
        f"direction={auc_block['direction']}",
        f"- bootstrap 95% CI auc=[{auc_block['ci95'][0]:.6f}, {auc_block['ci95'][1]:.6f}]",
        f"- bootstrap 95% CI auc_floor=[{auc_block['ci95_floor'][0]:.6f}, {auc_block['ci95_floor'][1]:.6f}]",
        "- Spearman ρ (finite score pairs only):",
    ]
    for k, v in leak.items():
        lines.append(f"  - {k}: {v:.6f}" if math.isfinite(v) else f"  - {k}: nan")
    lines.append(f"- largest |ρ|: {largest_rho[0]} = {largest_rho[1]:.6f}")
    lines.extend(["", "## A3 — density (active nodes / edges)"])
    for part, d in density.items():
        lines.append(
            f"- {part}: active_nodes med={d['active_nodes']['median']:.3f} "
            f"IQR={d['active_nodes']['iqr']:.3f}; "
            f"edges med={d['edges']['median']:.3f} IQR={d['edges']['iqr']:.3f}"
        )
    lines.append(f"- densest partition (by median edges): **{densest}**")
    lines.extend(["", "## A4 — eligibility reconciliation"])
    lines.append(f"- fetch: {elig.get('fetch_by_label', elig)}")
    if "arithmetic" in elig:
        lines.append(f"- {elig['arithmetic']}")
    if "drop_n_mapped_0" in elig:
        lines.append(f"- drop n_mapped==0: {elig['drop_n_mapped_0']}")
    if "drop_empty_categories" in elig:
        lines.append(f"- drop empty categories after re-parse: {elig['drop_empty_categories']}")
    if "note_user_764" in elig:
        lines.append(f"- note: {elig['note_user_764']}")
    elif elig.get("fetch_by_label", {}).get("benign") == 763:
        lines.append(
            "- note: fetch benign=763 (not 764); total=2505 (not 2506). "
            f"2505−2403={2505-len(bundle.eligible)} accounted below."
        )
    lines.append("")
    lines.append(f"Artifacts: `POSTMORTEM.json` ({len(excluded)} excluded app rows).")
    (out / "POSTMORTEM.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    print(f"[repair] wrote {out/'POSTMORTEM.md'}", flush=True)


if __name__ == "__main__":
    main()
