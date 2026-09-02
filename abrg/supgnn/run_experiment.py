"""Orchestrate Experiment S1: supervised GIN end-to-end on graphs."""

from __future__ import annotations

import argparse
import csv
import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import roc_auc_score

from abrg.androct.run_gae_run2 import TEST_RATIO, _auc_with_bootstrap
from abrg.androct.run_gae_run3_5 import _stratified_split
from abrg.apigraph.split import load_run3_split
from abrg.kernels.load import load_bundle
from abrg.ladder.floors import mapped_event_floor
from abrg.supgnn import (
    BATCH_SIZE,
    DROPOUT,
    EARLY_STOP_PATIENCE,
    EPOCHS,
    EXPECTED_SPLIT_DIGEST_PREFIX,
    HIDDEN,
    LADDER_ASSIGNMENTS_PATH,
    LADDER_HOLDOUT_PATH,
    LR,
    MODES,
    N_LAYERS,
    POOLINGS,
    REF_ROWS,
    REPRESENTATIONS,
    SEED,
    SEEDS,
    SUPGNN_OUTPUT_ROOT,
    VAL_FRAC,
    WEIGHT_DECAY,
)
from abrg.supgnn.data import Mode
from abrg.supgnn.models import Pooling, build_supervised_gin, count_parameters
from abrg.supgnn.train import evaluate_apps, train_supervised_gin


def _assert_split_digest(digest: str) -> None:
    if not digest.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {digest[:16]} != {EXPECTED_SPLIT_DIGEST_PREFIX}..."
        )


def _assert_ladder_folds(groups: dict[int, list[str]], ladder_holdout_path: Path) -> None:
    ladder = json.loads(ladder_holdout_path.read_text(encoding="utf-8"))
    ladder_meta = {int(f["group_id"]): int(f["n_malware_holdout"]) for f in ladder["folds"]}
    if sorted(groups) != sorted(ladder_meta):
        raise SystemExit("STOP: split-B fold ids do not match ladder behavioral holdout.")
    for gid, n_m in ladder_meta.items():
        if len(groups[gid]) != n_m:
            raise SystemExit(
                f"STOP: fold {gid} malware count {len(groups[gid])} != ladder {n_m}"
            )


def _load_ladder_assignments() -> dict[str, int]:
    if not LADDER_ASSIGNMENTS_PATH.is_file():
        raise SystemExit(f"STOP: missing ladder assignments {LADDER_ASSIGNMENTS_PATH}")
    payload = json.loads(LADDER_ASSIGNMENTS_PATH.read_text(encoding="utf-8"))
    assignments = payload["ward"]["assignments"]
    return {str(k): int(v) for k, v in assignments.items()}


def _auc_fast(scores: list[float], labels: list[int]) -> dict[str, Any]:
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return {
            "auc": float("nan"),
            "auc_floor": float("nan"),
            "direction": "undefined",
            "ci95": [float("nan"), float("nan")],
            "ci95_floor": [float("nan"), float("nan")],
            "n": int(len(y)),
        }
    auc = float(roc_auc_score(y, s))
    inv = float(roc_auc_score(y, -s))
    if inv > auc:
        return {
            "auc": inv,
            "auc_floor": inv,
            "direction": "benign_higher_score",
            "ci95": [float("nan"), float("nan")],
            "ci95_floor": [float("nan"), float("nan")],
            "n": int(len(y)),
        }
    return {
        "auc": auc,
        "auc_floor": auc,
        "direction": "malware_higher_score",
        "ci95": [float("nan"), float("nan")],
        "ci95_floor": [float("nan"), float("nan")],
        "n": int(len(y)),
    }


def _population_floor(
    tensors: dict[str, dict[str, Any]],
    test_shas: list[str],
    labels: list[int],
) -> dict[str, Any]:
    return mapped_event_floor(tensors, test_shas, labels)


def _ckpt_path(artifacts: Path, rep: str, pooling: str, mode: str, split: str, seed: int, fold: int | None = None) -> Path:
    fold_tag = f"fold{fold}" if fold is not None else "all"
    return artifacts / "checkpoints" / f"{rep}__{pooling}__{mode}__{split}__{fold_tag}__seed{seed}.pt"


def _indices_path(artifacts: Path, split: str, fold: int | None = None) -> Path:
    fold_tag = f"fold{fold}" if fold is not None else "all"
    return artifacts / "indices" / f"{split}__{fold_tag}__indices.npz"


def _save_indices(
    path: Path,
    *,
    train_idx: np.ndarray,
    val_idx: np.ndarray | None,
    test_idx: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"train_idx": train_idx, "test_idx": test_idx}
    if val_idx is not None:
        payload["val_idx"] = val_idx
    np.savez(path, **payload)


def _train_and_eval(
    *,
    tensors: dict[str, dict[str, Any]],
    train_apps: list[Any],
    test_apps: list[Any],
    in_dim: int,
    rep: str,
    pooling: Pooling,
    mode: Mode,
    seed: int,
    device: torch.device,
    artifacts: Path,
    split_name: str,
    fold: int | None,
    pred_writer: csv.writer,
    resume: bool,
) -> dict[str, Any]:
    ckpt = _ckpt_path(artifacts, rep, pooling, mode, split_name, seed, fold)
    result_json = ckpt.with_suffix(".json")
    curve_path = ckpt.with_name(ckpt.stem + "_curves.json")
    if resume and result_json.is_file():
        return json.loads(result_json.read_text(encoding="utf-8"))

    fit = train_supervised_gin(
        tensors=tensors,
        train_apps=train_apps,
        in_dim=in_dim,
        mode=mode,
        pooling=pooling,
        seed=seed,
        device=device,
    )
    model = fit["model"]
    scores, labels, shas = evaluate_apps(model, tensors, test_apps, mode=mode, device=device)
    auc = _auc_with_bootstrap(scores, labels)
    test_floor = _population_floor(tensors, shas, labels)

    ckpt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": fit["state_dict"],
            "meta": {
                "rep": rep,
                "pooling": pooling,
                "mode": mode,
                "split": split_name,
                "fold": fold,
                "seed": seed,
                "in_dim": in_dim,
                "n_parameters": fit["n_parameters"],
                "class_weights": fit["class_weights"],
            },
        },
        ckpt,
    )

    fold_str = "NA" if fold is None else str(fold)
    for sha, lab, sc in zip(shas, labels, scores):
        pred_writer.writerow([sha, lab, sc, rep, pooling, mode, split_name, fold_str, seed])

    curve_path.write_text(
        json.dumps({"train_losses": fit["train_losses"], "val_losses": fit["val_losses"]}, indent=2) + "\n",
        encoding="utf-8",
    )

    out = {
        "rep": rep,
        "pooling": pooling,
        "mode": mode,
        "split": split_name,
        "fold": fold,
        "seed": seed,
        "auc": auc,
        "population_floor": test_floor,
        "n_parameters": fit["n_parameters"],
        "class_weights": fit["class_weights"],
        "train_losses": fit["train_losses"],
        "val_losses": fit["val_losses"],
        "best_val_loss": fit["best_val_loss"],
        "epochs_run": fit["epochs_run"],
        "val_loss_diverged": fit["val_loss_diverged"],
        "checkpoint": str(ckpt),
    }
    result_json.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    tag = f"{rep}/{pooling}/{mode}/{split_name}"
    if fold is not None:
        tag += f"/fold{fold}"
    print(f"[supgnn] {tag} seed={seed} auc_floor={auc['auc_floor']:.4f}", flush=True)
    return out


def _run_split_a(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    out_dir: Path,
    artifacts: Path,
    pred_writer: csv.writer,
    device: torch.device,
    resume: bool,
    reps: tuple[str, ...],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    apps = list(split_bundle.eligible)
    split = _stratified_split(apps, seed=SEED, test_ratio=TEST_RATIO)
    train_apps = split["train"]
    test_apps = split["test_benign"] + split["test_malware"]
    sha_to_idx = {a.sha256: i for i, a in enumerate(apps)}
    tr_idx = np.asarray([sha_to_idx[a.sha256] for a in train_apps], dtype=np.int64)
    te_idx = np.asarray([sha_to_idx[a.sha256] for a in test_apps], dtype=np.int64)
    _save_indices(_indices_path(artifacts, "splitA"), train_idx=tr_idx, val_idx=None, test_idx=te_idx)
    sha_idx_path = artifacts / "indices" / "splitA__shas.json"
    sha_idx_path.write_text(
        json.dumps(
            {
                "train_shas": [a.sha256 for a in train_apps],
                "test_shas": [a.sha256 for a in test_apps],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    results: dict[str, Any] = {}
    for rep in reps:
        tensors = bundle["t22"] if rep == "T22" else bundle["t1k"]
        in_dim = 10 if rep == "T22" else 25
        results[rep] = {}
        for pooling in POOLINGS:
            results[rep][pooling] = {}
            for mode in MODES:
                per_seed = []
                for seed in SEEDS:
                    r = _train_and_eval(
                        tensors=tensors,
                        train_apps=train_apps,
                        test_apps=test_apps,
                        in_dim=in_dim,
                        rep=rep,
                        pooling=pooling,  # type: ignore[arg-type]
                        mode=mode,  # type: ignore[arg-type]
                        seed=seed,
                        device=device,
                        artifacts=artifacts,
                        split_name="splitA",
                        fold=None,
                        pred_writer=pred_writer,
                        resume=resume,
                    )
                    per_seed.append({k: v for k, v in r.items() if k not in ("train_losses", "val_losses")})
                floors = [float(x["auc"]["auc_floor"]) for x in per_seed]
                results[rep][pooling][mode] = {
                    "per_seed": per_seed,
                    "auc_floor_mean": float(np.mean(floors)),
                    "auc_floor_std": float(np.std(floors)),
                }
    (out_dir / "splitA_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _run_split_b(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    assignments: dict[str, int],
    out_dir: Path,
    artifacts: Path,
    pred_writer: csv.writer,
    device: torch.device,
    resume: bool,
    reps: tuple[str, ...],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    ladder_assign = _load_ladder_assignments()
    if assignments != ladder_assign:
        raise SystemExit("STOP: cluster assignments != ladder artifact route_b_behavioral.json")

    groups: dict[int, list[str]] = {}
    for sha, gid in assignments.items():
        groups.setdefault(int(gid), []).append(sha)
    _assert_ladder_folds(groups, LADDER_HOLDOUT_PATH)

    train_b_shas = [a.sha256 for a in split_bundle.train]
    test_ben_shas = [a.sha256 for a in split_bundle.test_benign]
    all_m_shas = [a.sha256 for a in split_bundle.test_malware]
    by_sha = split_bundle.by_sha

    results: dict[str, Any] = {}
    for rep in reps:
        tensors = bundle["t22"] if rep == "T22" else bundle["t1k"]
        in_dim = 10 if rep == "T22" else 25
        results[rep] = {}
        for pooling in POOLINGS:
            results[rep][pooling] = {}
            for mode in MODES:
                fold_rows = []
                pooled_scores: list[float] = []
                pooled_labels: list[int] = []
                for gid in sorted(groups):
                    hold_m = groups[gid]
                    train_m = [s for s in all_m_shas if s not in hold_m]
                    tr_shas = train_b_shas + train_m
                    te_shas = test_ben_shas + hold_m
                    tr_apps = [by_sha[s] for s in tr_shas]
                    te_apps = [by_sha[s] for s in te_shas]
                    idx_path = artifacts / "indices" / f"splitB__fold{gid}__shas.json"
                    idx_path.parent.mkdir(parents=True, exist_ok=True)
                    if not idx_path.is_file():
                        idx_path.write_text(
                            json.dumps({"train_shas": tr_shas, "test_shas": te_shas}, indent=2) + "\n",
                            encoding="utf-8",
                        )
                    per_seed = []
                    primary_scores: list[float] | None = None
                    primary_labels: list[int] | None = None
                    for seed in SEEDS:
                        r = _train_and_eval(
                            tensors=tensors,
                            train_apps=tr_apps,
                            test_apps=te_apps,
                            in_dim=in_dim,
                            rep=rep,
                            pooling=pooling,  # type: ignore[arg-type]
                            mode=mode,  # type: ignore[arg-type]
                            seed=seed,
                            device=device,
                            artifacts=artifacts,
                            split_name="splitB",
                            fold=gid,
                            pred_writer=pred_writer,
                            resume=resume,
                        )
                        per_seed.append({k: v for k, v in r.items() if k not in ("train_losses", "val_losses")})
                        if seed == SEED:
                            # reload scores from checkpoint eval stored in result
                            ckpt = Path(r["checkpoint"])
                            payload = torch.load(ckpt, map_location="cpu", weights_only=False)
                            model = build_supervised_gin(in_dim=in_dim, pooling=pooling)  # type: ignore[arg-type]
                            model.load_state_dict(payload["state_dict"])
                            model.eval()
                            primary_scores, primary_labels, _ = evaluate_apps(
                                model, tensors, te_apps, mode=mode, device=torch.device("cpu")
                            )
                    assert primary_scores is not None and primary_labels is not None
                    pooled_scores.extend(primary_scores)
                    pooled_labels.extend(primary_labels)
                    fold_auc = _auc_fast(primary_scores, primary_labels)
                    fold_floor = _population_floor(tensors, te_shas, primary_labels)
                    fold_rows.append(
                        {
                            "fold": gid,
                            "n_test": len(te_apps),
                            "n_malware": len(hold_m),
                            "primary_auc": fold_auc,
                            "population_floor": fold_floor,
                            "per_seed": per_seed,
                        }
                    )
                fold_aucs = [float(f["primary_auc"]["auc_floor"]) for f in fold_rows]
                w = [f["n_test"] for f in fold_rows]
                pooled_auc = _auc_with_bootstrap(pooled_scores, pooled_labels)
                results[rep][pooling][mode] = {
                    "folds": fold_rows,
                    "mean_auc_floor": float(np.mean(fold_aucs)),
                    "std_auc_floor": float(np.std(fold_aucs)),
                    "weighted_mean_auc_floor": float(np.average(fold_aucs, weights=w)),
                    "pooled_oof_auc": pooled_auc,
                }
    (out_dir / "splitB_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _ablation_table(split_a: dict[str, Any], split_b: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for rep in REPRESENTATIONS:
        if rep not in split_a:
            continue
        for pooling in POOLINGS:
            if pooling not in split_a[rep]:
                continue
            m1_a = float(split_a[rep][pooling]["M1_full"]["auc_floor_mean"])
            m2_a = float(split_a[rep][pooling]["M2_no_edges"]["auc_floor_mean"])
            m3_a = float(split_a[rep][pooling]["M3_const_feats"]["auc_floor_mean"])
            mp_delta_a = m1_a - m2_a
            m1_b = float(split_b[rep][pooling]["M1_full"]["weighted_mean_auc_floor"])
            m2_b = float(split_b[rep][pooling]["M2_no_edges"]["weighted_mean_auc_floor"])
            m3_b = float(split_b[rep][pooling]["M3_const_feats"]["weighted_mean_auc_floor"])
            mp_delta_b = m1_b - m2_b
            rows.append(
                {
                    "rep": rep,
                    "pooling": pooling,
                    "splitA_M1": m1_a,
                    "splitA_M2": m2_a,
                    "splitA_M3": m3_a,
                    "splitA_M1_minus_M2": mp_delta_a,
                    "splitB_M1_weighted": m1_b,
                    "splitB_M2_weighted": m2_b,
                    "splitB_M3_weighted": m3_b,
                    "splitB_M1_minus_M2": mp_delta_b,
                }
            )
    return {"rows": rows}


def _best_m1(split_results: dict[str, Any]) -> tuple[float, str, str]:
    best = (-1.0, "", "")
    for rep in split_results:
        for pooling in split_results[rep]:
            v = float(split_results[rep][pooling]["M1_full"]["auc_floor_mean"])
            if v > best[0]:
                best = (v, rep, pooling)
    return best


def _best_m1_split_b(split_results: dict[str, Any]) -> tuple[float, str, str]:
    best = (-1.0, "", "")
    for rep in split_results:
        for pooling in split_results[rep]:
            v = float(split_results[rep][pooling]["M1_full"]["weighted_mean_auc_floor"])
            if v > best[0]:
                best = (v, rep, pooling)
    return best


def _write_summary(
    out: Path,
    *,
    split_a: dict[str, Any],
    split_b: dict[str, Any],
    ablation: dict[str, Any],
    reload_verification: dict[str, Any],
    n_parameters: int,
) -> None:
    best_a_val, best_a_rep, best_a_pool = _best_m1(split_a)
    best_b_val, best_b_rep, best_b_pool = _best_m1_split_b(split_b)

    gate_a = "clears" if best_a_val >= REF_ROWS["HGB_full_random"] else "does not clear"
    gate_b = "clears" if best_b_val >= REF_ROWS["HGB_full_behavioral_weighted"] else "does not clear"

    mp_rows = [r for r in ablation["rows"] if r["rep"] == "T22" and r["pooling"] == "mean"]
    mp_a = mp_rows[0]["splitA_M1_minus_M2"] if mp_rows else float("nan")
    mp_b = mp_rows[0]["splitB_M1_minus_M2"] if mp_rows else float("nan")

    lines = [
        "# Experiment S1 — supervised GIN (supgnn)",
        "",
        "## GATE",
        "",
        f"- Split-A best M1: **{best_a_val:.4f}** ({best_a_rep}/{best_a_pool}) — supervised GIN {gate_a} HGB full random ({REF_ROWS['HGB_full_random']:.4f}).",
        f"- Split-B best M1 weighted: **{best_b_val:.4f}** ({best_b_rep}/{best_b_pool}) — supervised GIN {gate_b} HGB behavioral weighted ({REF_ROWS['HGB_full_behavioral_weighted']:.4f}).",
        "",
        "## Message-passing contribution (M1 − M2)",
        "",
        f"- Split-A (T22/mean): **{mp_a:+.4f}**",
        f"- Split-B weighted (T22/mean): **{mp_b:+.4f}**",
        "",
        f"- Model parameters (per config): **{n_parameters}**",
        "",
        "## Reference rows",
        "",
        "| reference | auc_floor |",
        "|---|---:|",
        f"| HGB full random | {REF_ROWS['HGB_full_random']:.4f} |",
        f"| HGB adj_only random | {REF_ROWS['HGB_adj_only_random']:.4f} |",
        f"| HGB full behavioral | {REF_ROWS['HGB_full_behavioral']:.4f} |",
        f"| HGB full behavioral weighted | {REF_ROWS['HGB_full_behavioral_weighted']:.4f} |",
        f"| OCPool_mean raw | {REF_ROWS['OCPool_mean_raw']:.4f} |",
        f"| OCPool_mean R2 | {REF_ROWS['OCPool_mean_R2']:.4f} |",
        f"| GAE | {REF_ROWS['GAE']:.4f} |",
        f"| OCGIN_plus | {REF_ROWS['OCGIN_plus']:.4f} |",
        f"| WL_h3 | {REF_ROWS['WL_h3']:.4f} |",
        f"| WL structure-only | {REF_ROWS['WL_structure_only']:.4f} |",
        f"| size floor | {REF_ROWS['size_floor']:.4f} |",
        "",
        "## Split-A (random stratified, mean ± std auc_floor over seeds)",
        "",
        "| rep | pooling | mode | mean | std |",
        "|---|---|---|---:|---:|",
    ]
    for rep in REPRESENTATIONS:
        if rep not in split_a:
            continue
        for pooling in POOLINGS:
            for mode in MODES:
                blk = split_a[rep][pooling][mode]
                lines.append(
                    f"| {rep} | {pooling} | {mode} | {blk['auc_floor_mean']:.4f} | {blk['auc_floor_std']:.4f} |"
                )

    lines += [
        "",
        "## Split-B (behavioral holdout, weighted mean auc_floor)",
        "",
        "| rep | pooling | mode | weighted_mean | std_fold | pooled_oof |",
        "|---|---|---|---:|---:|---:|",
    ]
    for rep in REPRESENTATIONS:
        if rep not in split_b:
            continue
        for pooling in POOLINGS:
            for mode in MODES:
                blk = split_b[rep][pooling][mode]
                lines.append(
                    f"| {rep} | {pooling} | {mode} | {blk['weighted_mean_auc_floor']:.4f} | "
                    f"{blk['std_auc_floor']:.4f} | {blk['pooled_oof_auc']['auc_floor']:.4f} |"
                )

    lines += [
        "",
        "## Ablation (M1 vs M2 vs M3)",
        "",
        "| rep | pooling | splitA M1 | M2 | M3 | M1−M2 | splitB M1 | M2 | M3 | M1−M2 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in ablation["rows"]:
        lines.append(
            f"| {row['rep']} | {row['pooling']} | {row['splitA_M1']:.4f} | {row['splitA_M2']:.4f} | "
            f"{row['splitA_M3']:.4f} | {row['splitA_M1_minus_M2']:+.4f} | "
            f"{row['splitB_M1_weighted']:.4f} | {row['splitB_M2_weighted']:.4f} | "
            f"{row['splitB_M3_weighted']:.4f} | {row['splitB_M1_minus_M2']:+.4f} |"
        )

    if reload_verification.get("checkpoint"):
        lines += [
            "",
            "## Reload verification",
            "",
            f"- checkpoint: `{reload_verification['checkpoint']}`",
            f"- stored auc_floor: {reload_verification['stored_auc_floor']:.6f}",
            f"- reloaded auc_floor: {reload_verification['reloaded_auc_floor']:.6f}",
            f"- match: {reload_verification['match']}",
        ]

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_summary_split_a_only(
    out: Path,
    *,
    split_a: dict[str, Any],
    reload_verification: dict[str, Any],
    n_parameters: int,
) -> None:
    best_a_val, best_a_rep, best_a_pool = _best_m1(split_a)
    gate_a = "clears" if best_a_val >= REF_ROWS["HGB_full_random"] else "does not clear"

    mp_rows = []
    for rep in split_a:
        for pooling in split_a[rep]:
            m1 = float(split_a[rep][pooling]["M1_full"]["auc_floor_mean"])
            m2 = float(split_a[rep][pooling]["M2_no_edges"]["auc_floor_mean"])
            mp_rows.append((rep, pooling, m1 - m2))
    mp_rows.sort(key=lambda x: -abs(x[2]))

    lines = [
        "# Experiment S1 — supervised GIN (supgnn) [partial: Split-A only]",
        "",
        "## GATE (Split-A)",
        "",
        f"- Split-A best M1: **{best_a_val:.4f}** ({best_a_rep}/{best_a_pool}) — supervised GIN {gate_a} HGB full random ({REF_ROWS['HGB_full_random']:.4f}).",
        "",
        "## Message-passing contribution (M1 − M2, Split-A)",
        "",
    ]
    for rep, pooling, delta in mp_rows:
        lines.append(f"- {rep}/{pooling}: **{delta:+.4f}**")
    lines += [
        "",
        f"- Model parameters (per config): **{n_parameters}**",
        "",
        "## Reference rows",
        "",
        "| reference | auc_floor |",
        "|---|---:|",
        f"| HGB full random | {REF_ROWS['HGB_full_random']:.4f} |",
        f"| HGB adj_only random | {REF_ROWS['HGB_adj_only_random']:.4f} |",
        f"| HGB full behavioral | {REF_ROWS['HGB_full_behavioral']:.4f} |",
        f"| HGB full behavioral weighted | {REF_ROWS['HGB_full_behavioral_weighted']:.4f} |",
        f"| OCPool_mean raw | {REF_ROWS['OCPool_mean_raw']:.4f} |",
        f"| OCPool_mean R2 | {REF_ROWS['OCPool_mean_R2']:.4f} |",
        f"| GAE | {REF_ROWS['GAE']:.4f} |",
        f"| OCGIN_plus | {REF_ROWS['OCGIN_plus']:.4f} |",
        f"| WL_h3 | {REF_ROWS['WL_h3']:.4f} |",
        f"| WL structure-only | {REF_ROWS['WL_structure_only']:.4f} |",
        f"| size floor | {REF_ROWS['size_floor']:.4f} |",
        "",
        "## Split-A (random stratified, mean ± std auc_floor over seeds)",
        "",
        "| rep | pooling | mode | mean | std |",
        "|---|---|---|---:|---:|",
    ]
    for rep in split_a:
        for pooling in split_a[rep]:
            for mode in MODES:
                blk = split_a[rep][pooling][mode]
                lines.append(
                    f"| {rep} | {pooling} | {mode} | {blk['auc_floor_mean']:.4f} | {blk['auc_floor_std']:.4f} |"
                )
    if reload_verification.get("checkpoint"):
        lines += [
            "",
            "## Reload verification",
            "",
            f"- checkpoint: `{reload_verification['checkpoint']}`",
            f"- stored auc: {reload_verification['stored_auc']:.6f}",
            f"- reloaded auc: {reload_verification['reloaded_auc']:.6f}",
            f"- match: {reload_verification['match']}",
        ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_reproduce_config(
    artifacts: Path,
    *,
    digest: str,
    n_parameters: int,
    reload_verification: dict[str, Any],
) -> None:
    cfg = {
        "experiment": "S1_supgnn",
        "library_versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "platform": platform.platform(),
        },
        "hyperparameters": {
            "hidden": HIDDEN,
            "n_layers": N_LAYERS,
            "poolings": list(POOLINGS),
            "modes": list(MODES),
            "representations": list(REPRESENTATIONS),
            "lr": LR,
            "weight_decay": WEIGHT_DECAY,
            "epochs": EPOCHS,
            "batch_size": BATCH_SIZE,
            "dropout": DROPOUT,
            "early_stop_patience": EARLY_STOP_PATIENCE,
            "val_frac_train_only": VAL_FRAC,
            "seeds": list(SEEDS),
            "split_digest_prefix": EXPECTED_SPLIT_DIGEST_PREFIX,
            "n_parameters": n_parameters,
        },
        "split_digest": digest,
        "cluster_assignments_path": str(LADDER_ASSIGNMENTS_PATH),
        "ladder_holdout_path": str(LADDER_HOLDOUT_PATH),
        "reload_verification": reload_verification,
        "reference_rows": REF_ROWS,
    }
    (artifacts / "reproduce_config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (artifacts / "reproduce.md").write_text(
        "# Reproduce Experiment S1 (supgnn)\n\n"
        "```bash\n"
        "python -m abrg.supgnn --resume\n"
        "```\n\n"
        "Requires existing T22/T1K tensors and ladder Ward k=30 artifacts.\n",
        encoding="utf-8",
    )


def _reload_verify_one(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    split_a: dict[str, Any],
) -> dict[str, Any]:
    rep = "T22"
    pooling = "mean"
    blk = split_a[rep][pooling]["M1_full"]["per_seed"][0]
    ckpt = Path(blk["checkpoint"])
    stored_auc = float(blk["auc"]["auc"])
    stored_floor = float(blk["auc"]["auc_floor"])
    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    in_dim = int(payload["meta"]["in_dim"])
    mode = payload["meta"]["mode"]
    model = build_supervised_gin(in_dim=in_dim, pooling=pooling)  # type: ignore[arg-type]
    model.load_state_dict(payload["state_dict"])
    apps = list(split_bundle.eligible)
    split = _stratified_split(apps, seed=SEED, test_ratio=TEST_RATIO)
    test_apps = split["test_benign"] + split["test_malware"]
    scores, labels, _ = evaluate_apps(
        model, bundle["t22"], test_apps, mode=mode, device=torch.device("cpu")
    )
    reloaded = _auc_with_bootstrap(scores, labels)
    match = abs(reloaded["auc"] - stored_auc) < 1e-5
    return {
        "checkpoint": str(ckpt),
        "stored_auc": stored_auc,
        "stored_auc_floor": stored_floor,
        "reloaded_auc": reloaded["auc"],
        "reloaded_auc_floor": reloaded["auc_floor"],
        "match": match,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Experiment S1: supervised GIN (supgnn)")
    ap.add_argument("--out", type=Path, default=SUPGNN_OUTPUT_ROOT)
    ap.add_argument("--resume", action="store_true", help="Skip completed runs")
    ap.add_argument("--skip-split-a", action="store_true")
    ap.add_argument("--skip-split-b", action="store_true")
    ap.add_argument("--reps", type=str, default="T22,T1K", help="Comma-separated T22 and/or T1K")
    ap.add_argument("--device", type=str, default="auto", choices=("auto", "cpu", "cuda"))
    args = ap.parse_args(argv)

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    print(f"[supgnn] device={device}", flush=True)

    reps = tuple(r.strip() for r in args.reps.split(",") if r.strip())
    for r in reps:
        if r not in REPRESENTATIONS:
            raise SystemExit(f"unknown rep {r!r}")

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    split_bundle = load_run3_split()
    _assert_split_digest(split_bundle.sha_list_digest)
    bundle = load_bundle()
    assignments = _load_ladder_assignments()

    # Parameter count (T22 mean M1)
    probe = build_supervised_gin(in_dim=10, pooling="mean")
    n_parameters = count_parameters(probe)
    print(f"[supgnn] n_parameters={n_parameters}", flush=True)

    pred_path = artifacts / "predictions.csv"
    pred_f = pred_path.open("a" if args.resume and pred_path.is_file() else "w", newline="", encoding="utf-8")
    pred_writer = csv.writer(pred_f)
    if pred_f.tell() == 0:
        pred_writer.writerow(
            ["app_id", "true_label", "score", "rep", "pooling", "mode", "split", "fold", "seed"]
        )

    split_a: dict[str, Any] = {}
    if not args.skip_split_a:
        print("[supgnn] Split-A …", flush=True)
        split_a = _run_split_a(
            bundle=bundle,
            split_bundle=split_bundle,
            out_dir=out / "splitA",
            artifacts=artifacts,
            pred_writer=pred_writer,
            device=device,
            resume=args.resume,
            reps=reps,
        )
    elif (out / "splitA" / "splitA_results.json").is_file():
        split_a = json.loads((out / "splitA" / "splitA_results.json").read_text(encoding="utf-8"))

    split_b: dict[str, Any] = {}
    if not args.skip_split_b:
        print("[supgnn] Split-B …", flush=True)
        split_b = _run_split_b(
            bundle=bundle,
            split_bundle=split_bundle,
            assignments=assignments,
            out_dir=out / "splitB",
            artifacts=artifacts,
            pred_writer=pred_writer,
            device=device,
            resume=args.resume,
            reps=reps,
        )
    elif (out / "splitB" / "splitB_results.json").is_file():
        split_b = json.loads((out / "splitB" / "splitB_results.json").read_text(encoding="utf-8"))

    pred_f.close()

    ablation: dict[str, Any] = {"rows": []}
    if split_a and split_b:
        ablation = _ablation_table(split_a, split_b)
        (out / "ablation" / "M1_M2_M3.json").parent.mkdir(parents=True, exist_ok=True)
        (out / "ablation" / "M1_M2_M3.json").write_text(
            json.dumps(ablation, indent=2) + "\n", encoding="utf-8"
        )

    reload_verification: dict[str, Any] = {"available": False}
    if split_a:
        reload_verification = _reload_verify_one(
            bundle=bundle, split_bundle=split_bundle, split_a=split_a
        )
        print(
            f"[supgnn] reload verify stored={reload_verification['stored_auc']:.6f} "
            f"reloaded={reload_verification['reloaded_auc']:.6f} match={reload_verification['match']}",
            flush=True,
        )

    _write_reproduce_config(
        artifacts,
        digest=split_bundle.sha_list_digest,
        n_parameters=n_parameters,
        reload_verification=reload_verification,
    )
    if split_a and split_b:
        _write_summary(
            out,
            split_a=split_a,
            split_b=split_b,
            ablation=ablation,
            reload_verification=reload_verification,
            n_parameters=n_parameters,
        )
    elif split_a:
        _write_summary_split_a_only(
            out,
            split_a=split_a,
            reload_verification=reload_verification,
            n_parameters=n_parameters,
        )
    print(f"[supgnn] done → {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
