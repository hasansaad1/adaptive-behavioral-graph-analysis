"""One-seed T1K GLocalKD node-gap table under Ma et al. reference hypers.

Pairing matches the brief-profile T1K winner: add pool, loss=full, s_graph,
seed 46, trained arm only. Writes a new directory; does not touch
glocalkd/explain/winner_nodes.json.

CLI: python -m abrg.glocalkd.run_t1k_papercfg_node
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT
from abrg.glocalkd import IMPLEMENTATION, REF_COMMIT, SCORE_VARIANTS
from abrg.glocalkd.config import PAPERCFG, TrainProfile
from abrg.glocalkd.data import covariates_for, make_loader
from abrg.glocalkd.degeneracy import diagnose
from abrg.glocalkd.explain import node_deviation_table
from abrg.glocalkd.score import eval_scores, score_graphs
from abrg.glocalkd.train import train_glocalkd
from abrg.kernels.load import load_bundle

OUT_DEFAULT = ANDROCT_OUTPUT_ROOT / "glocalkd_papercfg_t1k_node"
BRIEF_WINNER_AUC_FLOOR = 0.6896078431372549
BRIEF_LARGEST_POS = 0.0009610038250684738
BRIEF_LARGEST_NEG = -0.0009215950267389417
KIND = "T1K"
POOLING = "add"
LOSS_MODE = "full"
SEED = 46


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _resolve_device(name: str) -> torch.device:
    if name != "auto":
        return torch.device(name)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _resolve_batch_size(
    profile: TrainProfile,
    *,
    tensors: dict,
    train_shas: list[str],
    in_dim: int,
    device: torch.device,
) -> tuple[int, list[int], float]:
    tried: list[int] = []
    bs = profile.batch_size
    probe = replace(profile, epochs=1)
    while bs >= 1:
        tried.append(bs)
        t0 = time.perf_counter()
        try:
            train_glocalkd(
                tensors=tensors,
                train_shas=train_shas,
                in_dim=in_dim,
                pooling=POOLING,
                seed=SEED,
                profile=probe,
                trained=True,
                device=device,
                batch_size=bs,
            )
            return bs, tried, time.perf_counter() - t0
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "out of memory" not in msg and "mps" not in msg:
                raise
            if device.type == "cuda":
                torch.cuda.empty_cache()
            bs = bs // 2
    raise RuntimeError(f"batch probe failed after tries {tried}")


def _sign_stats(deltas: list[float]) -> dict[str, Any]:
    signs = [1 if d > 0 else (-1 if d < 0 else 0) for d in deltas]
    flips = sum(1 for a, b in zip(signs, signs[1:]) if a != 0 and b != 0 and a != b)
    n_pairs = max(len(signs) - 1, 1)
    n_pos = sum(1 for s in signs if s > 0)
    n_neg = sum(1 for s in signs if s < 0)
    n_zero = sum(1 for s in signs if s == 0)
    return {
        "n": len(signs),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_zero": n_zero,
        "consecutive_sign_flips": flips,
        "flip_rate": flips / n_pairs,
        "strict_alternating": bool(
            len(signs) >= 2
            and all(a != 0 and b != 0 and a != b for a, b in zip(signs, signs[1:]))
        ),
        "both_signs_present": bool(n_pos > 0 and n_neg > 0),
    }


def write_summary_md(path: Path, report: dict[str, Any]) -> None:
    expl = report["explain"]
    ranked = expl["all_nodes_ranked"]
    pos = max(ranked, key=lambda r: r["delta_malware_minus_benign"])
    neg = min(ranked, key=lambda r: r["delta_malware_minus_benign"])
    sg = report["scores"]["s_graph"]["auc"]
    lines = [
        "# GLocalKD T1K node null under paper configuration (one seed)",
        "",
        f"- generated_utc: {report['generated_utc']}",
        f"- pairing: {KIND} / pool={POOLING} / loss={LOSS_MODE} / score=s_graph / seed={SEED} / trained only",
        f"- profile: {report['train_profile']}",
        f"- device: {report['device']}",
        f"- batch_size_requested: {report['batch_size_requested']}",
        f"- batch_size_used: {report['batch_size_used']}",
        f"- batch_probe_tried: {report['batch_probe_tried']}",
        f"- probe_one_epoch_sec: {report['probe_one_epoch_sec']:.3f}",
        f"- train_wall_sec: {report['train_wall_sec']:.3f}",
        f"- eval_wall_sec: {report['eval_wall_sec']:.3f}",
        f"- wall_sec: {report['wall_sec']:.3f}",
        f"- implementation: {IMPLEMENTATION}",
        f"- reference_commit: `{REF_COMMIT}`",
        "",
        "## Graph-level AUC (s_graph)",
        "",
        f"- auc: {sg['auc']:.6f}",
        f"- auc_floor: {sg['auc_floor']:.6f}",
        f"- direction: {sg['direction']}",
        f"- brief-profile winner auc_floor (same pairing): {BRIEF_WINNER_AUC_FLOOR:.6f}",
        "",
        "## Per-node class-mean gaps (malware mean − benign mean)",
        "",
        f"- n_nodes: {expl['n_nodes']}",
        f"- largest positive: {pos['delta_malware_minus_benign']:+.9f} (`{pos['name']}`)",
        f"- largest negative: {neg['delta_malware_minus_benign']:+.9f} (`{neg['name']}`)",
        f"- brief-profile comparison: {BRIEF_LARGEST_POS:+.9f} / {BRIEF_LARGEST_NEG:+.9f}",
        f"- top-20 sign stats: {json.dumps(report['sign_stats_top20'])}",
        f"- all-nodes sign stats: {json.dumps(report['sign_stats_all'])}",
        "",
        "## Top 20 by |Δ|",
        "",
        "| rank | node | mean_benign | mean_malware | Δ (m−b) |",
        "|---:|---|---:|---:|---:|",
    ]
    for i, row in enumerate(expl["top_k"], 1):
        lines.append(
            f"| {i} | {row['name']} | {row['mean_test_benign']:.9f} | "
            f"{row['mean_test_malware']:.9f} | {row['delta_malware_minus_benign']:+.9f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="T1K GLocalKD paper-config node-gap (one seed)")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--skip-batch-probe", action="store_true")
    args = ap.parse_args(argv)

    out: Path = args.out
    if out.resolve() == (ANDROCT_OUTPUT_ROOT / "glocalkd").resolve():
        raise SystemExit("refusing to write into brief-profile glocalkd/")
    out.mkdir(parents=True, exist_ok=True)
    (out / "runs").mkdir(exist_ok=True)
    (out / "explain").mkdir(exist_ok=True)
    device = _resolve_device(args.device)
    t_all = time.perf_counter()

    print(f"[glocalkd_t1k_papercfg] device={device}", flush=True)
    bundle = load_bundle()
    tensors = bundle["t1k"]
    train, test_b, test_m = bundle["train"], bundle["test_benign"], bundle["test_malware"]
    in_dim = int(tensors[train[0]]["x"].shape[1])

    profile = PAPERCFG
    probe_sec = float("nan")
    if args.batch_size is not None:
        batch_used = args.batch_size
        probe_tried = [batch_used]
    elif args.skip_batch_probe:
        batch_used = profile.batch_size
        probe_tried = [batch_used]
    else:
        print("[glocalkd_t1k_papercfg] probing batch size on T1K add …", flush=True)
        batch_used, probe_tried, probe_sec = _resolve_batch_size(
            profile,
            tensors=tensors,
            train_shas=train,
            in_dim=in_dim,
            device=device,
        )
        print(
            f"[glocalkd_t1k_papercfg] batch_size={batch_used} "
            f"(tried {probe_tried}; one-epoch {probe_sec:.1f}s)",
            flush=True,
        )

    if batch_used != profile.batch_size:
        profile = replace(profile, batch_size=batch_used)

    _write_json(
        out / "reproduce_config.json",
        {
            "arm": "glocalkd_papercfg_t1k_node",
            "split_digest": bundle["digest"],
            "implementation": IMPLEMENTATION,
            "reference_commit": REF_COMMIT,
            "pairing": f"{KIND} / pool={POOLING} / loss={LOSS_MODE} / s_graph / seed={SEED} / trained",
            "seeds": [SEED],
            "profile": asdict(profile),
            "batch_size_requested": PAPERCFG.batch_size,
            "batch_size_used": batch_used,
            "batch_probe_tried": probe_tried,
            "device": str(device),
            "note": "One-seed node-gap replica of brief T1K winner under Ma et al. reference hypers. Not a five-seed campaign.",
        },
    )

    eval_ids = test_b + test_m
    labels = [0] * len(test_b) + [1] * len(test_m)
    cov = covariates_for(tensors, eval_ids, kind=KIND)

    print("[glocalkd_t1k_papercfg] training …", flush=True)
    t0 = time.perf_counter()
    target, predictor, tot_c, _, _ = train_glocalkd(
        tensors=tensors,
        train_shas=train,
        in_dim=in_dim,
        pooling=POOLING,
        seed=SEED,
        loss_mode=LOSS_MODE,
        profile=profile,
        trained=True,
        device=device,
        batch_size=batch_used,
    )
    train_time = time.perf_counter() - t0
    print(f"[glocalkd_t1k_papercfg] train_wall_sec={train_time:.1f}", flush=True)

    train_loader = make_loader(tensors, train, batch_size=batch_used, shuffle=False)
    eval_loader = make_loader(tensors, eval_ids, batch_size=batch_used, shuffle=False)
    deg = diagnose(
        target=target,
        predictor=predictor,
        train_loader=train_loader,
        loss_curve=tot_c,
        device=device,
    )
    t1 = time.perf_counter()
    scored = score_graphs(target, predictor, eval_loader, device, shas_in_order=eval_ids)
    eval_time = time.perf_counter() - t1

    score_results: dict[str, Any] = {}
    for variant in SCORE_VARIANTS:
        row = eval_scores(scored[variant], labels, cov)
        if deg["DEGENERATE"]:
            row["auc_suppressed"] = True
        score_results[variant] = row

    node_tb = scored["per_graph_node_scores"][: len(test_b)]
    node_tm = scored["per_graph_node_scores"][len(test_b) :]
    explain = node_deviation_table(
        node_scores_benign=node_tb,
        node_scores_malware=node_tm,
        kind=KIND,
    )
    ranked = explain["all_nodes_ranked"]
    pos = max(ranked, key=lambda r: r["delta_malware_minus_benign"])
    neg = min(ranked, key=lambda r: r["delta_malware_minus_benign"])
    sign_top20 = _sign_stats([r["delta_malware_minus_benign"] for r in explain["top_k"]])
    sign_all = _sign_stats([r["delta_malware_minus_benign"] for r in ranked])

    tag = f"{KIND}__pool-{POOLING}__{LOSS_MODE}__seed{SEED}"
    run_payload = {
        "tag": tag,
        "kind": KIND,
        "pooling": POOLING,
        "loss_mode": LOSS_MODE,
        "trained": True,
        "seed": SEED,
        "profile": profile.name,
        "train_profile": profile.summary_line(),
        "batch_size_used": batch_used,
        "device": str(device),
        "train_wall_sec": train_time,
        "eval_wall_sec": eval_time,
        "degeneracy": {
            k: v
            for k, v in deg.items()
            if not (k == "loss" and isinstance(v, dict) and "curve" in v)
        },
        "scores": {
            v: {
                k: score_results[v][k]
                for k in score_results[v]
                if not (k == "auc" and "roc_points" in score_results[v].get("auc", {}))
            }
            for v in SCORE_VARIANTS
        },
    }
    # keep auc scalars, drop roc_points from run json
    for v in SCORE_VARIANTS:
        auc = dict(score_results[v]["auc"])
        auc.pop("roc_points", None)
        run_payload["scores"][v]["auc"] = auc

    _write_json(out / "runs" / f"{tag}.json", run_payload)
    _write_json(out / "explain" / "winner_nodes.json", explain)

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "wall_sec": time.perf_counter() - t_all,
        "device": str(device),
        "train_profile": profile.summary_line(),
        "batch_size_requested": PAPERCFG.batch_size,
        "batch_size_used": batch_used,
        "batch_probe_tried": probe_tried,
        "probe_one_epoch_sec": probe_sec,
        "train_wall_sec": train_time,
        "eval_wall_sec": eval_time,
        "scores": score_results,
        "explain": explain,
        "largest_positive": pos,
        "largest_negative": neg,
        "sign_stats_top20": sign_top20,
        "sign_stats_all": sign_all,
        "brief_winner_auc_floor": BRIEF_WINNER_AUC_FLOOR,
        "brief_largest_pos": BRIEF_LARGEST_POS,
        "brief_largest_neg": BRIEF_LARGEST_NEG,
        "DEGENERATE": bool(deg.get("DEGENERATE")),
    }
    # comparison.json without full 1000-row table duplication of roc
    comparison = dict(report)
    comparison["explain"] = {
        "kind": explain["kind"],
        "n_nodes": explain["n_nodes"],
        "n_test_benign": explain["n_test_benign"],
        "n_test_malware": explain["n_test_malware"],
        "top_k": explain["top_k"],
        "largest_positive": pos,
        "largest_negative": neg,
    }
    for v in SCORE_VARIANTS:
        comparison["scores"][v] = dict(score_results[v])
        auc = dict(comparison["scores"][v]["auc"])
        auc.pop("roc_points", None)
        comparison["scores"][v]["auc"] = auc
    _write_json(out / "comparison.json", comparison)
    write_summary_md(out / "SUMMARY.md", report)
    print(f"[glocalkd_t1k_papercfg] done → {out / 'SUMMARY.md'}", flush=True)
    print(
        f"[glocalkd_t1k_papercfg] s_graph auc_floor="
        f"{score_results['s_graph']['auc']['auc_floor']:.4f} "
        f"max+={pos['delta_malware_minus_benign']:+.6g} "
        f"max-={neg['delta_malware_minus_benign']:+.6g}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
