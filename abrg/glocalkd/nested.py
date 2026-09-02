"""Run nested bootstrap for saved winner only: python -m abrg.glocalkd.nested"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from abrg.glocalkd import BATCH_SIZE, GLOCALKD_OUTPUT_ROOT, NESTED_B
from abrg.glocalkd.bootstrap import nested_bootstrap
from abrg.glocalkd.finalize import main as finalize_main
from abrg.kernels.load import load_bundle


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--B", type=int, default=NESTED_B)
    ap.add_argument("--epochs", type=int, default=300)
    args = ap.parse_args(argv)

    out = GLOCALKD_OUTPUT_ROOT
    winner = json.loads((out / "runs" / "winner.json").read_text(encoding="utf-8"))
    print(f"[nested] winner={winner}", flush=True)
    bundle = load_bundle()
    tensors = bundle["t22"] if winner["kind"] == "T22" else bundle["t1k"]
    train, test_b, test_m = bundle["train"], bundle["test_benign"], bundle["test_malware"]
    in_dim = int(tensors[train[0]]["x"].shape[1])
    nested = nested_bootstrap(
        tensors=tensors,
        train=train,
        test_b=test_b,
        test_m=test_m,
        in_dim=in_dim,
        pooling=winner["pooling"],
        loss_mode="full",
        score_variant=winner["score_variant"],
        naive_ci=list(winner.get("ci95_floor") or [float("nan"), float("nan")]),
        B=args.B,
        epochs=args.epochs,
        seed=int(winner["seed"]),
        device=torch.device("cpu"),
    )
    nested["runtime_note"] = (
        f"B={args.B} full retrain epochs={args.epochs}; "
        f"wall_sec={nested.get('wall_sec')}; "
        "B=100 infeasible on T1K (~22 min/replicate ≈ 37h wall); "
        "B=200 not attempted."
    )
    (out / "bootstrap").mkdir(parents=True, exist_ok=True)
    (out / "bootstrap" / "winner_nested.json").write_text(
        json.dumps(nested, indent=2) + "\n", encoding="utf-8"
    )
    print("[nested] refreshing SUMMARY", flush=True)
    finalize_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
