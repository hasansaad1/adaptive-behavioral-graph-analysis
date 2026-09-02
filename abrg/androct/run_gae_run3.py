"""AndroCT Run 3 — same as Run 2 except deterministic full-adjacency weighted recon."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.stats import spearmanr

from abrg.androct.paths import androct_run2_output_dir, androct_run3_output_dir
from abrg.androct.run2_corpus import prepare_corpus
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import (
    EPOCHS,
    HIDDEN,
    LR,
    SEED,
    WD,
    _auc_with_bootstrap,
    _dist,
    floor_aucs,
)
from abrg.autoencoder import (
    build_gae,
    graph_reconstruction_error_full_adjacency_weighted,
    seed_rng,
    train_gae_multi_full_adjacency_weighted,
)
from abrg.config import K_BURST
from abrg.features import node_feature_dim


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT Run 3 — deterministic full-adj weighted BCE")
    parser.add_argument("--output-dir", type=Path, default=None, help="Write outputs here (default: canonical run3 dir)")
    args = parser.parse_args()
    run2 = androct_run2_output_dir()
    out = args.output_dir or androct_run3_output_dir()
    out.mkdir(parents=True, exist_ok=True)

    print("[run3] prepare corpus (shared Run-2 cache) …", flush=True)
    bundle = prepare_corpus(force_rebuild=False, out=run2)
    split = bundle.split
    tensors = bundle.tensors
    test_apps = split["test_benign"] + split["test_malware"]

    floors = floor_aucs(test_apps, tensors)
    (out / "floors.json").write_text(json.dumps(floors, indent=2) + "\n")

    seed_rng(SEED)
    model = build_gae(node_feature_dim(), HIDDEN)
    probe = EdgeWeightProbeEncoder(model.encoder)
    model.encoder = probe
    gcn_log: dict[str, Any] = {"last_is_none": None}
    _orig = probe.inner.conv1.forward

    def _conv1(x, edge_index, edge_weight=None, **kwargs):
        gcn_log["last_is_none"] = edge_weight is None
        return _orig(x, edge_index, edge_weight=edge_weight, **kwargs)

    probe.inner.conv1.forward = _conv1  # type: ignore[method-assign]

    train_graphs = [
        (tensors[a.sha256]["x"], tensors[a.sha256]["edge_index"], tensors[a.sha256]["edge_weight"])
        for a in split["train"]
        if tensors[a.sha256]["edge_index"].numel() > 0
    ]
    print(
        f"[run3] train n_graphs={len(train_graphs)} hidden={HIDDEN} epochs={EPOCHS} "
        f"objective=full_adjacency_weighted_bce",
        flush=True,
    )
    if train_graphs:
        model.eval()
        with torch.no_grad():
            model.encode(*train_graphs[0])
    edge_weight_verify = {
        "gcnconv_is_none": gcn_log.get("last_is_none"),
        "encoder_is_none": probe.last_edge_weight_is_none,
    }
    losses, final_loss = train_gae_multi_full_adjacency_weighted(
        model, train_graphs, EPOCHS, LR, weight_decay=WD
    )

    def score_app(a) -> float:
        t = tensors[a.sha256]
        return graph_reconstruction_error_full_adjacency_weighted(
            model, t["x"], t["edge_index"], t["edge_weight"]
        )

    train_scores = {a.sha256: score_app(a) for a in split["train"]}
    test_ben_scores = {a.sha256: score_app(a) for a in split["test_benign"]}
    test_mal_scores = {a.sha256: score_app(a) for a in split["test_malware"]}

    scores = [test_ben_scores[a.sha256] for a in split["test_benign"]] + [
        test_mal_scores[a.sha256] for a in split["test_malware"]
    ]
    labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
    auc_block = _auc_with_bootstrap(scores, labels)

    sc = list(scores)
    leak = {
        "mapped_event_count": _rho(sc, [float(tensors[a.sha256]["n_mapped"]) for a in test_apps]),
        "total_event_count": _rho(sc, [float(tensors[a.sha256]["n_events"]) for a in test_apps]),
        "active_nodes": _rho(sc, [float(tensors[a.sha256]["n_active"]) for a in test_apps]),
        "edge_count": _rho(sc, [float(tensors[a.sha256]["n_edges"]) for a in test_apps]),
        "graph_density": _rho(sc, [float(tensors[a.sha256]["density"]) for a in test_apps]),
        "static_feature_norm": _rho(sc, [float(tensors[a.sha256]["static_norm"]) for a in test_apps]),
    }
    largest_rho = max(leak.items(), key=lambda kv: abs(kv[1]) if math.isfinite(kv[1]) else -1)

    def app_errs(d: dict[str, float]) -> list[float]:
        return [v for v in d.values() if math.isfinite(v)]

    d_train = _dist(app_errs(train_scores))
    d_tben = _dist(app_errs(test_ben_scores))
    d_tmal = _dist(app_errs(test_mal_scores))
    higher = (
        "test_malware"
        if d_tmal["median"] > d_tben["median"]
        else ("test_benign" if d_tben["median"] > d_tmal["median"] else "tied")
    )
    inverted = higher == "test_benign"

    def part_density(apps):
        act = [float(tensors[a.sha256]["n_active"]) for a in apps]
        ed = [float(tensors[a.sha256]["n_edges"]) for a in apps]
        return {"active_nodes": _dist(act), "edges": _dist(ed)}

    density = {
        "train_benign": part_density(split["train"]),
        "test_benign": part_density(split["test_benign"]),
        "test_malware": part_density(split["test_malware"]),
    }
    densest = max(
        density.items(),
        key=lambda kv: kv[1]["edges"]["median"] if math.isfinite(kv[1]["edges"]["median"]) else -1,
    )[0]

    floor_vals = [floors[k]["auc_floor"] for k in floors]
    highest_floor = max(floor_vals)
    arm_below = auc_block["auc_floor"] < highest_floor

    comparison = {
        "run": "run3",
        "axis": "objective: stochastic_recon_loss → deterministic_full_adjacency_weighted_bce",
        "n_parts": 1,
        "static_mode": "androguard_required",
        "pins": {
            "hidden": HIDDEN,
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WD,
            "k_burst": K_BURST,
            "seed": SEED,
            "test_ratio": 0.2,
            "scorer": "deterministic_full_adjacency_weighted_bce",
            "adjacency": "22x22=484 including diagonal",
            "pos_weight": "n_neg/n_pos per graph",
        },
        "population": {
            "n_eligible_train_eval": len(bundle.eligible),
            "split": {
                "train": len(split["train"]),
                "test_benign": len(split["test_benign"]),
                "test_malware": len(split["test_malware"]),
            },
            "shared_corpus_cache": str(bundle.cache_dir),
        },
        "edge_weight_verify": edge_weight_verify,
        "feature_diff_L2_mean": bundle.feat_diff_mean,
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
            "higher_median_error_class": higher,
            "benign_malware_error_direction_inverted": inverted,
        },
        "density_by_partition": density,
        "densest_partition_by_median_edges": densest,
    }
    (out / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    torch.save(
        {
            "model_state": model.state_dict(),
            "hidden": HIDDEN,
            "in_channels": node_feature_dim(),
            "objective": "full_adjacency_weighted_bce",
        },
        out / "gae_androct_run3_model.pt",
    )
    (out / "training_curve.csv").write_text(
        "epoch,loss\n" + "\n".join(f"{i+1},{v}" for i, v in enumerate(losses)) + "\n"
    )

    lines = [
        "# AndroCT 2017 Run 3 — SUMMARY",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        "- axis: deterministic full-adjacency (22×22) weighted BCE (replaces stochastic recon_loss)",
        f"- pins: hidden={HIDDEN} epochs={EPOCHS} lr={LR} seed={SEED} (same split/features/N=1 as Run 2)",
        f"- edge_weight GCNConv is_none={edge_weight_verify['gcnconv_is_none']}",
        "",
        "## Population / split",
        f"- eligible: {len(bundle.eligible)} (train={len(split['train'])} "
        f"test_benign={len(split['test_benign'])} test_malware={len(split['test_malware'])})",
        f"- AUC n (finite): {auc_block['n']} / {len(test_apps)}",
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
    lines.append(f"- highest_floor={highest_floor:.6f}")
    if arm_below:
        lines.append(
            f"- **Arm AUC_floor={auc_block['auc_floor']:.6f} is below highest floor "
            f"{highest_floor:.6f}. Not a result.**"
        )
    else:
        lines.append(
            f"- Arm AUC_floor={auc_block['auc_floor']:.6f} ≥ highest floor {highest_floor:.6f}."
        )
    lines.extend(["", "## Leak Spearman ρ (score vs …)"])
    for k, v in leak.items():
        lines.append(f"- {k}: {v:.6f}" if math.isfinite(v) else f"- {k}: nan")
    lines.append(f"- largest |ρ|: {largest_rho[0]} = {largest_rho[1]:.6f}")
    lines.extend(["", "## Density (active nodes / edges)"])
    for part, d in density.items():
        lines.append(
            f"- {part}: active_nodes med={d['active_nodes']['median']:.3f} "
            f"IQR={d['active_nodes']['iqr']:.3f}; "
            f"edges med={d['edges']['median']:.3f} IQR={d['edges']['iqr']:.3f}"
        )
    lines.append(f"- densest partition (median edges): **{densest}**")
    lines.extend(
        [
            "",
            "## Recon error medians",
            f"- train_benign={d_train['median']:.6f} IQR={d_train['iqr']:.6f}",
            f"- test_benign={d_tben['median']:.6f} IQR={d_tben['iqr']:.6f}",
            f"- test_malware={d_tmal['median']:.6f} IQR={d_tmal['iqr']:.6f}",
            f"- higher median error: **{higher}**",
            f"- benign/malware error direction inverted vs malware-should-be-higher: **{inverted}**",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (out / "RUN.md").write_text(
        "\n".join(
            [
                "# RUN CARD — androct_2017 / run3",
                "",
                "AXIS: objective stochastic → deterministic full-adjacency weighted BCE (22×22)",
                "PINS: dataset=androct_2017 seed=42 scorer=deterministic_full_adj_weighted edge_weight=on N=1",
                "BASELINE: abrg/output/androct_2017/run2",
                f"RESULT: auc_floor={auc_block['auc_floor']:.6f} "
                f"CI_floor=[{auc_block['ci95_floor'][0]:.6f},{auc_block['ci95_floor'][1]:.6f}] "
                f"higher_err={higher} inverted={inverted}",
                f"VERDICT: {'below_floor' if arm_below else 'above_floor'}",
                "NOTES: same split/cache as Run 2; only recon objective changed.",
            ]
        )
        + "\n"
    )
    print("\n".join(lines), flush=True)
    print(f"[run3] done → {out}", flush=True)


if __name__ == "__main__":
    main()
