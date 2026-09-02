"""Finalize GLocalKD SUMMARY/explain/winner from completed run JSONs."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from abrg.glocalkd import (
    GLOCALKD_OUTPUT_ROOT,
    IMPLEMENTATION,
    OCPOOL_MEAN_RAW,
    REF_COMMIT,
    REF_ROWS,
    SCORE_VARIANTS,
    SIZE_FLOOR,
)
from abrg.glocalkd.explain import node_deviation_table
from abrg.glocalkd.run_experiment import _mean_std, write_summary
from abrg.kernels.load import load_bundle
from abrg.glocalkd.score import score_graphs
from abrg.glocalkd.data import make_loader
from abrg.glocalkd.train import train_glocalkd
from abrg.glocalkd import BATCH_SIZE
import torch


def main() -> int:
    out = GLOCALKD_OUTPUT_ROOT
    runs_dir = out / "runs"
    grid_rows: list[dict[str, Any]] = []
    ablation_rows: list[dict[str, Any]] = []
    deg_flags: list[dict[str, Any]] = []

    for f in sorted(runs_dir.glob("T*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        tag = d.get("tag", f.stem)
        deg = d.get("degeneracy", {})
        deg_flags.append(
            {
                "tag": tag,
                "DEGENERATE": bool(deg.get("DEGENERATE")),
                "flags": deg.get("flags", {}),
                "frac_near_zero": deg.get("train_s_graph", {}).get(
                    "frac_score_below_1e-6", float("nan")
                ),
            }
        )
        mode = d.get("loss_mode", "full")
        trained = bool(d.get("trained", True))
        for variant in SCORE_VARIANTS:
            sc = d["scores"][variant]
            row = {
                "kind": d["kind"],
                "pooling": d["pooling"],
                "loss_mode": mode,
                "trained": trained,
                "score_variant": variant,
                "seed": d["seed"],
                "auc": float(sc["auc"]["auc"]),
                "auc_floor": float(sc["auc"]["auc_floor"]),
                "direction": sc["auc"]["direction"],
                "ci95_floor": sc["auc"]["ci95_floor"],
                "gate": sc["gate"],
                "leak_spearman": sc["leak_spearman"],
                "DEGENERATE": bool(deg.get("DEGENERATE")),
                "inverted": sc.get("inverted"),
            }
            if mode == "full" and trained:
                grid_rows.append(row)
            else:
                ablation_rows.append(row)

    cand = [
        r
        for r in grid_rows
        if r["score_variant"] == "s_graph" and not r.get("DEGENERATE")
    ]
    if not cand:
        cand = [r for r in grid_rows if r["score_variant"] == "s_graph"]
    winner = max(cand, key=lambda r: float(r["auc_floor"])) if cand else None
    (runs_dir / "winner.json").write_text(
        json.dumps(winner, indent=2) + "\n", encoding="utf-8"
    )

    # explain: retrain winner once to get node scores
    explain = None
    nested = None
    nested_path = out / "bootstrap" / "winner_nested.json"
    if nested_path.is_file():
        nested = json.loads(nested_path.read_text(encoding="utf-8"))

    digest = "6129eb13d6a46457"
    if winner is not None:
        print(f"[finalize] winner {winner}", flush=True)
        bundle = load_bundle()
        digest = bundle["digest"]
        tensors = bundle["t22"] if winner["kind"] == "T22" else bundle["t1k"]
        train, test_b, test_m = (
            bundle["train"],
            bundle["test_benign"],
            bundle["test_malware"],
        )
        in_dim = int(tensors[train[0]]["x"].shape[1])
        device = torch.device("cpu")
        target, predictor, *_ = train_glocalkd(
            tensors=tensors,
            train_shas=train,
            in_dim=in_dim,
            pooling=winner["pooling"],
            seed=int(winner["seed"]),
            loss_mode="full",
            epochs=300,
            trained=True,
            device=device,
        )
        eval_ids = test_b + test_m
        eval_loader = make_loader(tensors, eval_ids, batch_size=BATCH_SIZE, shuffle=False)
        scored = score_graphs(
            target, predictor, eval_loader, device, shas_in_order=eval_ids
        )
        explain = node_deviation_table(
            node_scores_benign=scored["per_graph_node_scores"][: len(test_b)],
            node_scores_malware=scored["per_graph_node_scores"][len(test_b) :],
            kind=winner["kind"],
        )
        (out / "explain" / "winner_nodes.json").write_text(
            json.dumps(explain, indent=2) + "\n", encoding="utf-8"
        )

    write_summary(
        out / "SUMMARY.md",
        rows=grid_rows,
        deg_flags=deg_flags,
        winner=winner,
        ablation_rows=ablation_rows,
        explain=explain,
        nested=nested,
        digest=digest,
    )
    (runs_dir / "grid_rows.json").write_text(
        json.dumps(
            {"rows": grid_rows, "ablation_rows": ablation_rows, "winner": winner},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[finalize] wrote {out / 'SUMMARY.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
