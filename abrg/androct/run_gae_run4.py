"""AndroCT Run 4 — dual reconstruction (structure + features). One axis: alpha."""

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

from abrg.androct.paths import androct_run2_output_dir, androct_run4_output_dir
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
    FeatureDecoder,
    build_gae,
    graph_reconstruction_error_dual,
    seed_rng,
    train_gae_multi_dual,
)
from abrg.config import K_BURST
from abrg.features import node_feature_dim

ALPHAS = (0.8, 0.5, 0.2)


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def _eval_arm(
    *,
    model,
    feature_decoder,
    alpha: float,
    split: dict,
    tensors: dict,
    floors: dict,
) -> dict[str, Any]:
    def score_app(a) -> float:
        t = tensors[a.sha256]
        return graph_reconstruction_error_dual(
            model,
            feature_decoder,
            t["x"],
            t["edge_index"],
            t["edge_weight"],
            alpha=alpha,
        )

    train_scores = {a.sha256: score_app(a) for a in split["train"]}
    test_ben_scores = {a.sha256: score_app(a) for a in split["test_benign"]}
    test_mal_scores = {a.sha256: score_app(a) for a in split["test_malware"]}
    test_apps = split["test_benign"] + split["test_malware"]

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

    highest_floor = max(floors[k]["auc_floor"] for k in floors)
    arm_below = auc_block["auc_floor"] < highest_floor

    return {
        "alpha": alpha,
        "auc": auc_block,
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
        "highest_floor": highest_floor,
        "arm_below_highest_floor": arm_below,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT Run 4 — dual reconstruction alpha sweep")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    run2 = androct_run2_output_dir()
    out = args.output_dir or androct_run4_output_dir()
    out.mkdir(parents=True, exist_ok=True)

    print("[run4] load corpus cache (same as Run 3) …", flush=True)
    bundle = prepare_corpus(force_rebuild=False, out=run2)
    split = bundle.split
    tensors = bundle.tensors
    test_apps = split["test_benign"] + split["test_malware"]
    floors = floor_aucs(test_apps, tensors)
    (out / "floors.json").write_text(json.dumps(floors, indent=2) + "\n")

    train_graphs = [
        (tensors[a.sha256]["x"], tensors[a.sha256]["edge_index"], tensors[a.sha256]["edge_weight"])
        for a in split["train"]
        if tensors[a.sha256]["edge_index"].numel() > 0
    ]
    in_ch = node_feature_dim()
    results: dict[str, Any] = {
        "run": "run4",
        "axis": "dual_recon alpha * structure + (1-alpha) * feature_mse; structure=Run3 full-adj weighted BCE",
        "pins": {
            "hidden": HIDDEN,
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WD,
            "k_burst": K_BURST,
            "seed": SEED,
            "test_ratio": 0.2,
            "scorer": "dual_recon_deterministic",
            "alphas": list(ALPHAS),
        },
        "population": {
            "n_eligible": len(bundle.eligible),
            "split": {
                "train": len(split["train"]),
                "test_benign": len(split["test_benign"]),
                "test_malware": len(split["test_malware"]),
            },
        },
        "floors": floors,
        "by_alpha": {},
    }

    lines = [
        "# AndroCT 2017 Run 4 — SUMMARY (dual reconstruction)",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        "- axis: α·structure + (1−α)·feature_MSE; structure = Run-3 full-adjacency weighted BCE",
        f"- pins: hidden={HIDDEN} epochs={EPOCHS} lr={LR} seed={SEED} N=1 (same split as Run 3)",
        f"- eligible: {len(bundle.eligible)} train={len(split['train'])} "
        f"test_benign={len(split['test_benign'])} test_malware={len(split['test_malware'])}",
        "",
        "## Size floors (same population)",
    ]
    for k, b in floors.items():
        lines.append(
            f"- {k}: floor={b['auc_floor']:.6f} dir={b['direction']} "
            f"CI_floor=[{b['ci95_floor'][0]:.6f}, {b['ci95_floor'][1]:.6f}]"
        )
    highest_floor = max(floors[k]["auc_floor"] for k in floors)
    lines.append(f"- highest_floor={highest_floor:.6f}")
    lines.append("")

    best_alpha = None
    best_floor = -1.0

    for alpha in ALPHAS:
        print(f"[run4] alpha={alpha} train …", flush=True)
        seed_rng(SEED)
        model = build_gae(in_ch, HIDDEN)
        probe = EdgeWeightProbeEncoder(model.encoder)
        model.encoder = probe
        feature_decoder = FeatureDecoder(HIDDEN, in_ch)
        losses, final_loss = train_gae_multi_dual(
            model, feature_decoder, train_graphs, EPOCHS, LR, alpha=alpha, weight_decay=WD
        )
        arm = _eval_arm(
            model=model,
            feature_decoder=feature_decoder,
            alpha=alpha,
            split=split,
            tensors=tensors,
            floors=floors,
        )
        arm["final_train_loss"] = final_loss
        results["by_alpha"][str(alpha)] = arm
        torch.save(
            {
                "model_state": model.state_dict(),
                "feature_decoder_state": feature_decoder.state_dict(),
                "alpha": alpha,
                "hidden": HIDDEN,
                "in_channels": in_ch,
            },
            out / f"gae_androct_run4_alpha{alpha}.pt",
        )
        (out / f"training_curve_alpha{alpha}.csv").write_text(
            "epoch,loss\n" + "\n".join(f"{i+1},{v}" for i, v in enumerate(losses)) + "\n"
        )

        ab = arm["auc"]
        inv = arm["recon_error"]["benign_malware_error_direction_inverted"]
        lines.extend(
            [
                f"## alpha={alpha}",
                f"- auc={ab['auc']:.6f} auc_floor={ab['auc_floor']:.6f} direction={ab['direction']}",
                f"- bootstrap 95% CI auc=[{ab['ci95'][0]:.6f}, {ab['ci95'][1]:.6f}]",
                f"- bootstrap 95% CI auc_floor=[{ab['ci95_floor'][0]:.6f}, {ab['ci95_floor'][1]:.6f}]",
                f"- arm_below_highest_floor={arm['arm_below_highest_floor']} "
                f"(highest_floor={highest_floor:.6f})",
                f"- higher median error: **{arm['recon_error']['higher_median_error_class']}** "
                f"(inverted={inv})",
                f"- densest partition: {arm['densest_partition_by_median_edges']}",
                "- Spearman ρ:",
            ]
        )
        for k, v in arm["leak_spearman"].items():
            lines.append(f"  - {k}: {v:.6f}" if math.isfinite(v) else f"  - {k}: nan")
        lines.append(
            f"- largest |ρ|: {arm['largest_abs_rho']['metric']} = {arm['largest_abs_rho']['rho']:.6f}"
        )
        for part, d in arm["density_by_partition"].items():
            lines.append(
                f"- density {part}: active med={d['active_nodes']['median']:.3f} "
                f"IQR={d['active_nodes']['iqr']:.3f}; "
                f"edges med={d['edges']['median']:.3f} IQR={d['edges']['iqr']:.3f}"
            )
        re_ = arm["recon_error"]
        lines.append(
            f"- recon medians train={re_['train_benign']['median']:.6f} "
            f"test_ben={re_['test_benign']['median']:.6f} "
            f"test_mal={re_['test_malware']['median']:.6f}"
        )
        lines.append("")

        if ab["auc_floor"] > best_floor:
            best_floor = ab["auc_floor"]
            best_alpha = alpha
        print(
            f"  alpha={alpha} auc_floor={ab['auc_floor']:.4f} inverted={inv} "
            f"below_floor={arm['arm_below_highest_floor']}",
            flush=True,
        )

    results["best_alpha_by_auc_floor"] = best_alpha
    results["best_auc_floor"] = best_floor
    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    lines.extend(
        [
            "## Best alpha (by AUC_floor)",
            f"- **alpha={best_alpha}** auc_floor={best_floor:.6f}",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (out / "RUN.md").write_text(
        "\n".join(
            [
                "# RUN CARD — androct_2017 / run4",
                "",
                "AXIS: dual recon α·structure+(1-α)·feature_MSE (structure=Run3 full-adj)",
                f"PINS: hidden=64 epochs=300 seed=42 alphas={list(ALPHAS)}",
                "BASELINE: run3",
                f"RESULT: best_alpha={best_alpha} auc_floor={best_floor:.6f}",
                "NOTES: same GAE split/tensors as Run 3; FeatureDecoder Linear(hidden→F).",
            ]
        )
        + "\n"
    )
    (out / "best_alpha.json").write_text(
        json.dumps({"best_alpha": best_alpha, "auc_floor": best_floor}, indent=2) + "\n"
    )
    print("\n".join(lines), flush=True)
    print(f"[run4] done → {out} best_alpha={best_alpha}", flush=True)


if __name__ == "__main__":
    main()
