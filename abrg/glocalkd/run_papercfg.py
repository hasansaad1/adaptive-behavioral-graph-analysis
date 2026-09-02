"""Paper-configuration validation arm for GLocalKD (family-sweep pairing).

Runs T22 / pool=mean / loss=full / score=s_graph with Ma et al. reference
training hypers (512/256, lr=1e-4, 150 epochs, dropout 0.3, BN, StepLR).
Trained and untrained predictor arms, 5 seeds. Does not replace Table A.7
primary scores; reports alongside brief-profile numbers from grid_rows.json.
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
from abrg.glocalkd import IMPLEMENTATION, REF_COMMIT, SCORE_VARIANTS, SEEDS
from abrg.glocalkd.config import BRIEF, PAPERCFG, TrainProfile
from abrg.glocalkd.data import covariates_for, make_loader
from abrg.glocalkd.degeneracy import diagnose
from abrg.glocalkd.score import eval_scores, score_graphs
from abrg.glocalkd.train import train_glocalkd
from abrg.kernels.load import load_bundle

GLOCALKD_PAPERCFG_ROOT = ANDROCT_OUTPUT_ROOT / "glocalkd_papercfg"
BRIEF_GRID = ANDROCT_OUTPUT_ROOT / "glocalkd" / "runs" / "grid_rows.json"

PRIMARY_VARIANTS = ("s_graph", "s_graph_plus_mean_node")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _mean_std(vals: list[float]) -> dict[str, float]:
    arr = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.mean(arr)),
        "std": float(np.std(arr, ddof=0)),
    }


def _resolve_batch_size(profile: TrainProfile, *, device: torch.device) -> tuple[int, list[int]]:
    """Try profile batch; halve on OOM until 1 or success (one-epoch probe)."""
    from dataclasses import replace

    tried: list[int] = []
    bs = profile.batch_size
    probe = replace(profile, epochs=1)
    while bs >= 1:
        tried.append(bs)
        try:
            bundle = load_bundle()
            tensors = bundle["t22"]
            train = bundle["train"]
            in_dim = int(tensors[train[0]]["x"].shape[1])
            train_glocalkd(
                tensors=tensors,
                train_shas=train,
                in_dim=in_dim,
                pooling="mean",
                seed=42,
                profile=probe,
                trained=True,
                device=device,
                batch_size=bs,
            )
            return bs, tried
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "out of memory" not in msg and "mps" not in msg:
                raise
            if device.type == "cuda":
                torch.cuda.empty_cache()
            bs = bs // 2
    raise RuntimeError(f"batch probe failed after tries {tried}")


def run_one(
    *,
    tensors: dict,
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    seed: int,
    trained: bool,
    profile: TrainProfile,
    batch_size: int,
    out_dir: Path,
    device: torch.device,
) -> dict[str, Any]:
    in_dim = int(tensors[train[0]]["x"].shape[1])
    eval_ids = test_b + test_m
    labels = [0] * len(test_b) + [1] * len(test_m)
    cov = covariates_for(tensors, eval_ids, kind="T22")
    tag = f"T22__pool-mean__{'full' if trained else 'untrained'}__seed{seed}"

    t0 = time.perf_counter()
    target, predictor, tot_c, _, _ = train_glocalkd(
        tensors=tensors,
        train_shas=train,
        in_dim=in_dim,
        pooling="mean",
        seed=seed,
        loss_mode="full",
        profile=profile,
        trained=trained,
        device=device,
        batch_size=batch_size,
    )
    train_time = time.perf_counter() - t0

    train_loader = make_loader(tensors, train, batch_size=batch_size, shuffle=False)
    eval_loader = make_loader(tensors, eval_ids, batch_size=batch_size, shuffle=False)
    deg = diagnose(
        target=target,
        predictor=predictor,
        train_loader=train_loader,
        loss_curve=tot_c if trained else [],
        device=device,
    )
    scored = score_graphs(target, predictor, eval_loader, device, shas_in_order=eval_ids)

    score_results: dict[str, Any] = {}
    for variant in SCORE_VARIANTS:
        row = eval_scores(scored[variant], labels, cov)
        if deg["DEGENERATE"] and trained:
            row["auc_suppressed"] = True
        score_results[variant] = row

    payload = {
        "tag": tag,
        "kind": "T22",
        "pooling": "mean",
        "loss_mode": "full" if trained else "untrained",
        "trained": trained,
        "seed": seed,
        "profile": profile.name,
        "train_profile": profile.summary_line(),
        "batch_size_used": batch_size,
        "train_wall_sec": train_time,
        "degeneracy": deg,
        "scores": score_results,
    }
    _write_json(out_dir / "runs" / f"{tag}.json", payload)
    return payload


def _load_brief_pairing() -> dict[str, Any]:
    if not BRIEF_GRID.is_file():
        return {"available": False, "note": f"missing {BRIEF_GRID}"}
    blob = json.loads(BRIEF_GRID.read_text())
    rows = list(blob.get("rows") or []) + list(blob.get("ablation_rows") or [])

    def pick(trained: bool) -> dict[int, dict[str, float]]:
        want_loss = "full" if trained else "untrained"
        out: dict[int, dict[str, float]] = {}
        for r in rows:
            if (
                r.get("kind") == "T22"
                and r.get("pooling") == "mean"
                and bool(r.get("trained")) is trained
                and r.get("loss_mode") == want_loss
            ):
                seed = int(r["seed"])
                variant = r.get("score_variant")
                if variant not in PRIMARY_VARIANTS:
                    continue
                out.setdefault(seed, {})[variant] = float(r["auc_floor"])
        return out

    tmap, umap = pick(True), pick(False)
    seeds = [s for s in SEEDS if s in tmap and s in umap]
    per_seed = []
    for s in seeds:
        per_seed.append(
            {
                "seed": s,
                "trained": tmap[s],
                "untrained": umap[s],
            }
        )
    brief_summary: dict[str, Any] = {"pairing": BRIEF.summary_line(), "per_seed": per_seed}
    for variant in PRIMARY_VARIANTS:
        t_vals = [tmap[s][variant] for s in seeds if variant in tmap[s]]
        u_vals = [umap[s][variant] for s in seeds if variant in umap[s]]
        if t_vals and u_vals:
            brief_summary[variant] = {
                "trained": {**_mean_std(t_vals), "values": t_vals},
                "untrained": {**_mean_std(u_vals), "values": u_vals},
                "delta_trained_minus_untrained_mean": float(np.mean(t_vals) - np.mean(u_vals)),
            }
    return {"available": True, "source": str(BRIEF_GRID), **brief_summary}


def _summarize_papercfg(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_arm: dict[str, dict[int, dict[str, float]]] = {"trained": {}, "untrained": {}}
    for r in runs:
        arm = "trained" if r["trained"] else "untrained"
        seed = int(r["seed"])
        by_arm[arm][seed] = {
            v: float(r["scores"][v]["auc"]["auc_floor"])
            for v in PRIMARY_VARIANTS
            if v in r["scores"]
        }

    out: dict[str, Any] = {"per_seed": []}
    for s in SEEDS:
        if s in by_arm["trained"] and s in by_arm["untrained"]:
            out["per_seed"].append(
                {
                    "seed": s,
                    "trained": by_arm["trained"][s],
                    "untrained": by_arm["untrained"][s],
                }
            )

    for variant in PRIMARY_VARIANTS:
        t_vals = [by_arm["trained"][s][variant] for s in SEEDS if variant in by_arm["trained"].get(s, {})]
        u_vals = [by_arm["untrained"][s][variant] for s in SEEDS if variant in by_arm["untrained"].get(s, {})]
        if t_vals and u_vals:
            out[variant] = {
                "trained": {**_mean_std(t_vals), "values": t_vals},
                "untrained": {**_mean_std(u_vals), "values": u_vals},
                "delta_trained_minus_untrained_mean": float(np.mean(t_vals) - np.mean(u_vals)),
                "untrained_wins_seed_count": sum(1 for t, u in zip(t_vals, u_vals) if u > t),
            }
    return out


def write_summary_md(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# GLocalKD paper-configuration validation",
        "",
        f"- generated_utc: {datetime.now(timezone.utc).isoformat()}",
        f"- axis: training configuration only (reference Ma et al. App B vs brief profile)",
        f"- pairing: T22 / pool=mean / loss=full / seeds {list(SEEDS)}",
        f"- implementation: {IMPLEMENTATION}",
        f"- reference_commit: `{REF_COMMIT}`",
        f"- note: reimplementation comparison on AndroCT tensors; not a reproduction of Ma et al. published benchmark numbers",
        "",
        "## Paper profile used",
        "",
        f"- {report['papercfg_profile']['summary_line']}",
        f"- batch_size_requested: {report['papercfg_profile']['batch_size']}",
        f"- batch_size_used: {report['batch_size_used']}",
        f"- batch_probe_tried: {report.get('batch_probe_tried', [])}",
        "",
        "## Brief profile (existing grid — Table A.7 pairing)",
        "",
    ]
    brief = report.get("brief_baseline") or {}
    if brief.get("available"):
        for v in PRIMARY_VARIANTS:
            block = brief.get(v) or {}
            if block:
                tm = block["trained"]["mean"]
                um = block["untrained"]["mean"]
                lines.append(
                    f"- **{v}**: trained {tm:.4f} · untrained {um:.4f} · "
                    f"Δ(tr−un) {block['delta_trained_minus_untrained_mean']:+.4f}"
                )
    else:
        lines.append(f"- {brief.get('note', 'n/a')}")

    lines.extend(["", "## Paper profile results", ""])
    pap = report.get("papercfg_results") or {}
    for v in PRIMARY_VARIANTS:
        block = pap.get(v) or {}
        if block:
            tm = block["trained"]["mean"]
            um = block["untrained"]["mean"]
            wins = block.get("untrained_wins_seed_count", "?")
            lines.append(
                f"- **{v}**: trained {tm:.4f} · untrained {um:.4f} · "
                f"Δ(tr−un) {block['delta_trained_minus_untrained_mean']:+.4f} · "
                f"untrained wins {wins}/5 seeds"
            )

    lines.extend(["", "## Per-seed (s_graph)", ""])
    lines.append("| seed | brief trained | brief untrained | paper trained | paper untrained |")
    lines.append("|---:|---:|---:|---:|---:|")
    brief_ps = {r["seed"]: r for r in (brief.get("per_seed") or [])}
    paper_ps = {r["seed"]: r for r in (pap.get("per_seed") or [])}
    for s in SEEDS:
        bt = brief_ps.get(s, {}).get("trained", {}).get("s_graph", float("nan"))
        bu = brief_ps.get(s, {}).get("untrained", {}).get("s_graph", float("nan"))
        pt = paper_ps.get(s, {}).get("trained", {}).get("s_graph", float("nan"))
        pu = paper_ps.get(s, {}).get("untrained", {}).get("s_graph", float("nan"))
        lines.append(f"| {s} | {bt:.4f} | {bu:.4f} | {pt:.4f} | {pu:.4f} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="GLocalKD paper-configuration validation")
    ap.add_argument("--out", type=Path, default=GLOCALKD_PAPERCFG_ROOT)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--batch-size", type=int, default=None, help="Override; else probe from 300")
    ap.add_argument("--skip-batch-probe", action="store_true")
    ap.add_argument("--seeds", default=",".join(str(s) for s in SEEDS))
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "runs").mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)
    seeds = tuple(int(s.strip()) for s in args.seeds.split(",") if s.strip())

    profile = PAPERCFG
    if args.batch_size is not None:
        batch_used = args.batch_size
        probe_tried = [batch_used]
    elif args.skip_batch_probe:
        batch_used = profile.batch_size
        probe_tried = [batch_used]
    else:
        print("[glocalkd_papercfg] probing batch size …", flush=True)
        batch_used, probe_tried = _resolve_batch_size(profile, device=device)
        print(f"[glocalkd_papercfg] using batch_size={batch_used} (tried {probe_tried})", flush=True)

    if batch_used != profile.batch_size:
        profile = replace(profile, batch_size=batch_used)

    bundle = load_bundle()
    tensors = bundle["t22"]
    train, test_b, test_m = bundle["train"], bundle["test_benign"], bundle["test_malware"]

    _write_json(
        out / "reproduce_config.json",
        {
            "arm": "glocalkd_papercfg",
            "split_digest": bundle["digest"],
            "implementation": IMPLEMENTATION,
            "reference_commit": REF_COMMIT,
            "pairing": "T22 / pool=mean / loss=full / trained vs untrained",
            "seeds": list(seeds),
            "profile": asdict(profile),
            "batch_size_requested": PAPERCFG.batch_size,
            "batch_size_used": batch_used,
            "batch_probe_tried": probe_tried,
            "score_variants_reported": list(PRIMARY_VARIANTS),
            "note": "Reimplementation on AndroCT tensors; not Ma et al. benchmark reproduction",
        },
    )

    runs: list[dict[str, Any]] = []
    t_all = time.perf_counter()
    for trained in (True, False):
        for seed in seeds:
            tag = f"T22 mean {'full' if trained else 'untrained'} seed{seed}"
            print(f"[glocalkd_papercfg] {tag}", flush=True)
            runs.append(
                run_one(
                    tensors=tensors,
                    train=train,
                    test_b=test_b,
                    test_m=test_m,
                    seed=seed,
                    trained=trained,
                    profile=profile,
                    batch_size=batch_used,
                    out_dir=out,
                    device=device,
                )
            )

    brief_baseline = _load_brief_pairing()
    papercfg_results = _summarize_papercfg(runs)
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "wall_sec": time.perf_counter() - t_all,
        "papercfg_profile": {
            "name": profile.name,
            "summary_line": profile.summary_line(),
            "batch_size": PAPERCFG.batch_size,
            **asdict(profile),
        },
        "batch_size_used": batch_used,
        "batch_probe_tried": probe_tried,
        "brief_baseline": brief_baseline,
        "papercfg_results": papercfg_results,
        "runs": runs,
    }
    _write_json(out / "comparison.json", report)
    write_summary_md(out / "SUMMARY.md", report)
    print(f"[glocalkd_papercfg] done → {out / 'SUMMARY.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
