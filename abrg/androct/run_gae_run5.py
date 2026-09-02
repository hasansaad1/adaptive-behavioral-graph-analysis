"""AndroCT Run 5 — bottleneck sweep at best Run-4 alpha. One axis: hidden."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from scipy.stats import spearmanr

from abrg.androct.paths import (
    androct_run2_output_dir,
    androct_run4_output_dir,
    androct_run5_output_dir,
)
from abrg.androct.run2_corpus import prepare_corpus
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import EPOCHS, LR, SEED, WD, _auc_with_bootstrap, _dist, floor_aucs
from abrg.androct.run_gae_run4 import _eval_arm
from abrg.autoencoder import (
    FeatureDecoder,
    build_gae,
    seed_rng,
    train_gae_multi_dual,
)
from abrg.config import K_BURST
from abrg.features import node_feature_dim

HIDDENS = (2, 4, 8, 16, 64)


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT Run 5 — hidden bottleneck sweep")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    run2 = androct_run2_output_dir()
    run4 = androct_run4_output_dir()
    out = args.output_dir or androct_run5_output_dir()
    out.mkdir(parents=True, exist_ok=True)

    best_path = run4 / "best_alpha.json"
    if not best_path.is_file():
        raise SystemExit("Run 4 best_alpha.json missing — run Run 4 first")
    best_alpha = float(json.loads(best_path.read_text(encoding="utf-8"))["best_alpha"])

    print(f"[run5] bottleneck sweep at alpha={best_alpha} hiddens={list(HIDDENS)}", flush=True)
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
    highest_floor = max(floors[k]["auc_floor"] for k in floors)

    results: dict[str, Any] = {
        "run": "run5",
        "axis": f"hidden bottleneck sweep at dual-recon alpha={best_alpha}",
        "best_alpha_from_run4": best_alpha,
        "pins": {
            "epochs": EPOCHS,
            "lr": LR,
            "weight_decay": WD,
            "k_burst": K_BURST,
            "seed": SEED,
            "alpha": best_alpha,
            "hiddens": list(HIDDENS),
        },
        "floors": floors,
        "by_hidden": {},
    }

    lines = [
        "# AndroCT 2017 Run 5 — SUMMARY (bottleneck sweep)",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- axis: hidden ∈ {list(HIDDENS)} at Run-4 best alpha={best_alpha}",
        f"- pins: epochs={EPOCHS} lr={LR} seed={SEED} dual-recon",
        f"- highest size floor={highest_floor:.6f}",
        "",
    ]

    for hidden in HIDDENS:
        print(f"[run5] hidden={hidden} …", flush=True)
        seed_rng(SEED)
        model = build_gae(in_ch, hidden)
        model.encoder = EdgeWeightProbeEncoder(model.encoder)
        feature_decoder = FeatureDecoder(hidden, in_ch)
        losses, final_loss = train_gae_multi_dual(
            model,
            feature_decoder,
            train_graphs,
            EPOCHS,
            LR,
            alpha=best_alpha,
            weight_decay=WD,
        )
        arm = _eval_arm(
            model=model,
            feature_decoder=feature_decoder,
            alpha=best_alpha,
            split=split,
            tensors=tensors,
            floors=floors,
        )
        arm["hidden"] = hidden
        arm["final_train_loss"] = final_loss
        results["by_hidden"][str(hidden)] = arm
        torch.save(
            {
                "model_state": model.state_dict(),
                "feature_decoder_state": feature_decoder.state_dict(),
                "alpha": best_alpha,
                "hidden": hidden,
                "in_channels": in_ch,
            },
            out / f"gae_androct_run5_h{hidden}.pt",
        )

        ab = arm["auc"]
        inv = arm["recon_error"]["benign_malware_error_direction_inverted"]
        lines.extend(
            [
                f"## hidden={hidden}",
                f"- auc={ab['auc']:.6f} auc_floor={ab['auc_floor']:.6f} direction={ab['direction']}",
                f"- CI_floor=[{ab['ci95_floor'][0]:.6f}, {ab['ci95_floor'][1]:.6f}]",
                f"- below_floor={arm['arm_below_highest_floor']} inverted={inv}",
                f"- higher_err={arm['recon_error']['higher_median_error_class']}",
                f"- largest |ρ|={arm['largest_abs_rho']['metric']}={arm['largest_abs_rho']['rho']:.6f}",
                "",
            ]
        )
        print(
            f"  h={hidden} auc_floor={ab['auc_floor']:.4f} inverted={inv} "
            f"below={arm['arm_below_highest_floor']}",
            flush=True,
        )

    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (out / "RUN.md").write_text(
        "\n".join(
            [
                "# RUN CARD — androct_2017 / run5",
                "",
                f"AXIS: hidden sweep {list(HIDDENS)} at alpha={best_alpha}",
                "PINS: seed=42 dual-recon same split as Run 3/4",
                "BASELINE: run4 best alpha",
            ]
        )
        + "\n"
    )
    print("\n".join(lines), flush=True)
    print(f"[run5] done → {out}", flush=True)


if __name__ == "__main__":
    main()
