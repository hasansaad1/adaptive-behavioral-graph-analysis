"""Orchestrate OCGTL experiment (additive)."""

from __future__ import annotations

import argparse
import csv
import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from sklearn.metrics import roc_auc_score

from abrg.androct.run_gae_run2 import TEST_RATIO, _auc_with_bootstrap, split_apps
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.apigraph.split import load_run3_split
from abrg.kernels.load import load_bundle
from abrg.ocgtl import (
    BATCH_SIZE,
    EPOCHS,
    EXPECTED_SPLIT_DIGEST_PREFIX,
    HIDDEN,
    IN_DIM,
    K_VALUES,
    LADDER_ASSIGNMENTS_PATH,
    LADDER_HOLDOUT_PATH,
    LR,
    N_LAYERS,
    OCGTL_OUTPUT_ROOT,
    OCPOOL_INCUMBENT,
    PRIMARY_K,
    REF_COMMIT,
    REF_REPO,
    REF_ROWS,
    REPRESENTATIONS,
    SEED,
    SEEDS,
    SIZE_FLOOR,
    TEMPERATURE,
    WEIGHT_DECAY,
)
from abrg.ocgtl.models import K1OCC, OCGTL, count_parameters
from abrg.ocgtl.score import degeneracy_report, evaluate_partitions, leak_spearman
from abrg.ocgtl.train import Mode, collect_embeddings, score_apps, train_ocgtl


def _population_floor(
    tensors: dict[str, dict[str, Any]],
    test_shas: list[str],
    labels: list[int],
) -> dict[str, Any]:
    """Mapped/in-vocab event floor; supports T22 (`n_mapped`) and T1K (`n_inv_events`)."""
    scores = []
    for s in test_shas:
        t = tensors[s]
        if "n_mapped" in t:
            scores.append(float(t["n_mapped"]))
        elif "n_inv_events" in t:
            scores.append(float(t["n_inv_events"]))
        else:
            raise KeyError(f"no mapped-event key in tensor for {s}")
    block = _auc_with_bootstrap(scores, labels)
    return {
        "metric": "mapped_or_inv_event_count",
        "auc_floor": block["auc_floor"],
        "direction": block["direction"],
        "ci95_floor": block["ci95_floor"],
        "n": block["n"],
    }


def _assert_digest(digest: str) -> None:
    if not digest.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(f"STOP: split digest {digest[:16]} != {EXPECTED_SPLIT_DIGEST_PREFIX}...")


def _load_ladder_assignments() -> dict[str, int]:
    if not LADDER_ASSIGNMENTS_PATH.is_file():
        raise SystemExit(f"STOP: missing {LADDER_ASSIGNMENTS_PATH}")
    payload = json.loads(LADDER_ASSIGNMENTS_PATH.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in payload["ward"]["assignments"].items()}


def _assert_ladder_folds(groups: dict[int, list[str]]) -> None:
    ladder = json.loads(LADDER_HOLDOUT_PATH.read_text(encoding="utf-8"))
    meta = {int(f["group_id"]): int(f["n_malware_holdout"]) for f in ladder["folds"]}
    if sorted(groups) != sorted(meta):
        raise SystemExit("STOP: split-B fold ids do not match ladder.")
    for gid, n_m in meta.items():
        if len(groups[gid]) != n_m:
            raise SystemExit(f"STOP: fold {gid} count {len(groups[gid])} != ladder {n_m}")


def _auc_fast(scores: list[float], labels: list[int]) -> dict[str, Any]:
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return {"auc": float("nan"), "auc_floor": float("nan"), "direction": "undefined"}
    auc = float(roc_auc_score(y, s))
    inv = float(roc_auc_score(y, -s))
    if inv > auc:
        return {"auc": inv, "auc_floor": inv, "direction": "benign_higher_score"}
    return {"auc": auc, "auc_floor": auc, "direction": "malware_higher_score"}


def _ckpt_path(artifacts: Path, *, rep: str, k: int, mode: str, split: str, seed: int, fold: int | None = None) -> Path:
    fold_tag = f"fold{fold}" if fold is not None else "all"
    return artifacts / "checkpoints" / f"{rep}__K{k}__{mode}__{split}__{fold_tag}__seed{seed}.pt"


def _result_path(ckpt: Path) -> Path:
    return ckpt.with_suffix(".json")


def _gate(auc_floor: float) -> dict[str, bool]:
    return {
        "clears_size_floor": auc_floor >= SIZE_FLOOR,
        "clears_ocpool": auc_floor >= OCPOOL_INCUMBENT,
    }


def _run_one(
    *,
    tensors: dict[str, dict],
    train_apps: list,
    test_benign: list,
    test_malware: list,
    in_dim: int,
    rep: str,
    k: int,
    mode: Mode,
    seed: int,
    device: torch.device,
    artifacts: Path,
    split_name: str,
    fold: int | None,
    pred_writer: csv.writer | None,
    resume: bool,
    degeneracy_dir: Path,
) -> dict[str, Any]:
    ckpt = _ckpt_path(artifacts, rep=rep, k=k, mode=mode, split=split_name, seed=seed, fold=fold)
    rpath = _result_path(ckpt)
    if resume and rpath.is_file():
        return json.loads(rpath.read_text(encoding="utf-8"))

    fit = train_ocgtl(
        tensors=tensors,
        train_apps=train_apps,
        in_dim=in_dim,
        k=k,
        seed=seed,
        mode=mode,
        device=device,
    )
    model = fit["model"]
    sc_tr, _ = score_apps(model, tensors, train_apps, mode=mode, device=device)
    sc_tb, _ = score_apps(model, tensors, test_benign, mode=mode, device=device)
    sc_tm, _ = score_apps(model, tensors, test_malware, mode=mode, device=device)

    emb = collect_embeddings(model, tensors, train_apps, mode=mode, device=device)
    degen = degeneracy_report(
        emb=emb, scores_train=sc_tr, train_losses=fit["train_losses"], mode=mode
    )
    degen_path = degeneracy_dir / f"{rep}__K{k}__{mode}__{split_name}__fold{fold if fold is not None else 'all'}__seed{seed}.json"
    degen_path.parent.mkdir(parents=True, exist_ok=True)
    degen_path.write_text(json.dumps(degen, indent=2) + "\n", encoding="utf-8")

    eval_block = evaluate_partitions(sc_tr, sc_tb, sc_tm)
    test_apps = test_benign + test_malware
    test_scores = sc_tb + sc_tm
    leak = leak_spearman(test_scores, test_apps, tensors)
    floor = _population_floor(
        tensors,
        [a.sha256 for a in test_apps],
        [0] * len(test_benign) + [1] * len(test_malware),
    )

    ckpt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": fit["state_dict"],
            "meta": {
                "rep": rep,
                "k": k,
                "mode": mode,
                "split": split_name,
                "fold": fold,
                "seed": seed,
                "in_dim": in_dim,
                "n_parameters": fit["n_parameters"],
            },
        },
        ckpt,
    )

    if pred_writer is not None:
        fold_str = "NA" if fold is None else str(fold)
        for a, sc in zip(test_benign, sc_tb):
            pred_writer.writerow([a.sha256, 0, sc, rep, k, mode, split_name, fold_str, seed])
        for a, sc in zip(test_malware, sc_tm):
            pred_writer.writerow([a.sha256, 1, sc, rep, k, mode, split_name, fold_str, seed])

    out: dict[str, Any] = {
        "rep": rep,
        "k": k,
        "mode": mode,
        "split": split_name,
        "fold": fold,
        "seed": seed,
        "n_parameters": fit["n_parameters"],
        "epochs_run": fit["epochs_run"],
        "degeneracy": {
            "COLLAPSE_DETECTED": degen["COLLAPSE_DETECTED"],
            "collapse_flags": degen["collapse_flags"],
            "frac_train_score_lt_1e-6": degen["frac_train_score_lt_1e-6"],
            "encoder_agreement": degen["encoder_agreement"],
            "mean_var_across_encoders": degen["mean_var_across_encoders"],
            "final_to_initial_loss_ratio": degen["final_to_initial_loss_ratio"],
            "path": str(degen_path),
        },
        "checkpoint": str(ckpt),
        "population_floor": floor,
        "leak_spearman": leak,
    }
    if degen["COLLAPSE_DETECTED"]:
        out["auc"] = None
        out["gate"] = None
        out["note"] = "COLLAPSE DETECTED — AUC not presented"
    else:
        out["auc"] = eval_block["auc"]
        out["direction_inverted"] = eval_block["direction_inverted"]
        out["score_distributions"] = eval_block["score_distributions"]
        out["gate"] = _gate(float(eval_block["auc"]["auc_floor"]))

    rpath.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    tag = f"{rep}/K{k}/{mode}/{split_name}"
    if fold is not None:
        tag += f"/fold{fold}"
    af = out["auc"]["auc_floor"] if out.get("auc") else float("nan")
    print(
        f"[ocgtl] {tag} seed={seed} collapse={degen['COLLAPSE_DETECTED']} auc_floor={af:.4f}",
        flush=True,
    )
    return out


def _split_a_apps(split_bundle: Any) -> tuple[list, list, list]:
    """Benign-only train from app-level 80/20 (GAE split); test = held-out benign + all malware."""
    corpus = load_corpus_cache(Path("abrg/output/androct_2017/run2"))
    split = split_apps(corpus.eligible)
    if any(a.label != "benign" for a in split["train"]):
        raise SystemExit("STOP: train partition contains non-benign apps.")
    # Align with split_bundle SHA lists
    by_sha = split_bundle.by_sha
    train = [by_sha[a.sha256] for a in split["train"]]
    test_b = [by_sha[a.sha256] for a in split["test_benign"]]
    test_m = [by_sha[a.sha256] for a in split["test_malware"]]
    return train, test_b, test_m


def _run_split_a(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    out_dir: Path,
    artifacts: Path,
    degeneracy_dir: Path,
    pred_writer: csv.writer,
    device: torch.device,
    resume: bool,
    reps: tuple[str, ...],
    modes: tuple[Mode, ...],
    k_values: tuple[int, ...],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    train, test_b, test_m = _split_a_apps(split_bundle)
    (artifacts / "indices").mkdir(parents=True, exist_ok=True)
    (artifacts / "indices" / "splitA__shas.json").write_text(
        json.dumps(
            {
                "train_shas": [a.sha256 for a in train],
                "test_benign_shas": [a.sha256 for a in test_b],
                "test_malware_shas": [a.sha256 for a in test_m],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    results: dict[str, Any] = {}
    for rep in reps:
        tensors = bundle["t22"] if rep == "T22" else bundle["t1k"]
        in_dim = IN_DIM[rep]
        results[rep] = {}
        for mode in modes:
            ks = (1,) if mode == "k1_occ" else k_values
            for k in ks:
                key = f"{mode}_K{k}"
                per_seed = []
                for seed in SEEDS:
                    r = _run_one(
                        tensors=tensors,
                        train_apps=train,
                        test_benign=test_b,
                        test_malware=test_m,
                        in_dim=in_dim,
                        rep=rep,
                        k=k,
                        mode=mode,
                        seed=seed,
                        device=device,
                        artifacts=artifacts,
                        split_name="splitA",
                        fold=None,
                        pred_writer=pred_writer,
                        resume=resume,
                        degeneracy_dir=degeneracy_dir,
                    )
                    per_seed.append(r)
                floors = [
                    float(x["auc"]["auc_floor"])
                    for x in per_seed
                    if x.get("auc") is not None
                ]
                results[rep][key] = {
                    "per_seed": per_seed,
                    "auc_floor_mean": float(np.mean(floors)) if floors else float("nan"),
                    "auc_floor_std": float(np.std(floors)) if floors else float("nan"),
                    "n_noncollapsed": len(floors),
                    "n_collapsed": sum(1 for x in per_seed if x["degeneracy"]["COLLAPSE_DETECTED"]),
                }
    # Merge with any existing Split-A results so --reps T1K does not wipe T22 (and vice versa).
    out_json = out_dir / "splitA_results.json"
    if out_json.is_file():
        prev = json.loads(out_json.read_text(encoding="utf-8"))
        for rep, blk in results.items():
            prev.setdefault(rep, {}).update(blk)
        results = prev
    out_json.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _run_split_b(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    assignments: dict[str, int],
    out_dir: Path,
    artifacts: Path,
    degeneracy_dir: Path,
    pred_writer: csv.writer,
    device: torch.device,
    resume: bool,
    reps: tuple[str, ...],
    k_values: tuple[int, ...],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    if assignments != _load_ladder_assignments():
        raise SystemExit("STOP: assignments != ladder artifact")
    groups: dict[int, list[str]] = {}
    for sha, gid in assignments.items():
        groups.setdefault(int(gid), []).append(sha)
    _assert_ladder_folds(groups)

    train_b = list(split_bundle.train)
    test_ben = list(split_bundle.test_benign)
    all_m = list(split_bundle.test_malware)
    by_sha = split_bundle.by_sha

    results: dict[str, Any] = {}
    for rep in reps:
        tensors = bundle["t22"] if rep == "T22" else bundle["t1k"]
        in_dim = IN_DIM[rep]
        results[rep] = {}
        for k in k_values:
            fold_rows = []
            pooled_s: list[float] = []
            pooled_y: list[int] = []
            for gid in sorted(groups):
                hold_m = [by_sha[s] for s in groups[gid]]
                train_m = [a for a in all_m if a.sha256 not in groups[gid]]
                tr = train_b + train_m
                te_b = test_ben
                te_m = hold_m
                per_seed = []
                primary_scores = None
                primary_labels = None
                for seed in SEEDS:
                    r = _run_one(
                        tensors=tensors,
                        train_apps=tr,
                        test_benign=te_b,
                        test_malware=te_m,
                        in_dim=in_dim,
                        rep=rep,
                        k=k,
                        mode="ocgtl",
                        seed=seed,
                        device=device,
                        artifacts=artifacts,
                        split_name="splitB",
                        fold=gid,
                        pred_writer=pred_writer,
                        resume=resume,
                        degeneracy_dir=degeneracy_dir,
                    )
                    per_seed.append(r)
                    if seed == SEED and r.get("auc") is not None:
                        # re-score for pooled from checkpoint
                        payload = torch.load(r["checkpoint"], map_location="cpu", weights_only=False)
                        model = OCGTL(in_dim=in_dim, k=k, hidden=HIDDEN, n_layers=N_LAYERS)
                        model.load_state_dict(payload["state_dict"])
                        model.eval()
                        sc_tb, _ = score_apps(model, tensors, te_b, mode="ocgtl", device=torch.device("cpu"))
                        sc_tm, _ = score_apps(model, tensors, te_m, mode="ocgtl", device=torch.device("cpu"))
                        primary_scores = sc_tb + sc_tm
                        primary_labels = [0] * len(sc_tb) + [1] * len(sc_tm)
                if primary_scores is not None:
                    pooled_s.extend(primary_scores)
                    pooled_y.extend(primary_labels)
                    fold_auc = _auc_fast(primary_scores, primary_labels)
                else:
                    fold_auc = {"auc": float("nan"), "auc_floor": float("nan"), "direction": "collapsed"}
                fold_rows.append(
                    {
                        "fold": gid,
                        "n_malware": len(hold_m),
                        "n_test": len(te_b) + len(te_m),
                        "primary_auc": fold_auc,
                        "per_seed": [{kk: vv for kk, vv in p.items() if kk != "score_distributions"} for p in per_seed],
                    }
                )
            fold_aucs = [float(f["primary_auc"]["auc_floor"]) for f in fold_rows if np.isfinite(f["primary_auc"]["auc_floor"])]
            w = [f["n_test"] for f in fold_rows if np.isfinite(f["primary_auc"]["auc_floor"])]
            pooled = _auc_with_bootstrap(pooled_s, pooled_y) if pooled_s else {"auc_floor": float("nan")}
            results[rep][f"ocgtl_K{k}"] = {
                "folds": fold_rows,
                "mean_auc_floor": float(np.mean(fold_aucs)) if fold_aucs else float("nan"),
                "std_auc_floor": float(np.std(fold_aucs)) if fold_aucs else float("nan"),
                "weighted_mean_auc_floor": float(np.average(fold_aucs, weights=w)) if fold_aucs else float("nan"),
                "pooled_oof_auc": pooled,
            }
    (out_dir / "splitB_results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _flip_diagnostic(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    out_dir: Path,
    artifacts: Path,
    degeneracy_dir: Path,
    device: torch.device,
    resume: bool,
    reps: tuple[str, ...],
) -> dict[str, Any]:
    """Train on 562 malware (seed=42); score benign as anomalous (diagnostic)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    malware = list(split_bundle.test_malware)
    idx = rng.choice(len(malware), size=562, replace=False)
    train_m = [malware[i] for i in idx]
    # test: remaining malware as "normal" for this diagnostic? Spec: score benign as anomalous.
    # Train malware-only; test uses benign vs held malware with labels swapped in AUC.
    train_a, test_b, test_m = _split_a_apps(split_bundle)
    # Use same test partitions; train on malware sample instead of benign.
    results: dict[str, Any] = {}
    for rep in reps:
        tensors = bundle["t22"] if rep == "T22" else bundle["t1k"]
        in_dim = IN_DIM[rep]
        # Variant A (already in splitA) — load primary seed result if present
        a_path = _result_path(
            _ckpt_path(artifacts, rep=rep, k=PRIMARY_K, mode="ocgtl", split="splitA", seed=SEED)
        )
        var_a = json.loads(a_path.read_text(encoding="utf-8")) if a_path.is_file() else None
        # Variant B
        r_b = _run_one(
            tensors=tensors,
            train_apps=train_m,
            test_benign=test_b,
            test_malware=test_m,
            in_dim=in_dim,
            rep=rep,
            k=PRIMARY_K,
            mode="ocgtl",
            seed=SEED,
            device=device,
            artifacts=artifacts,
            split_name="flipB",
            fold=None,
            pred_writer=None,
            resume=resume,
            degeneracy_dir=degeneracy_dir,
        )
        # For flip: recompute AUC with benign as positive (anomalous)
        if r_b.get("auc") is not None:
            payload = torch.load(r_b["checkpoint"], map_location="cpu", weights_only=False)
            model = OCGTL(in_dim=in_dim, k=PRIMARY_K)
            model.load_state_dict(payload["state_dict"])
            sc_tb, _ = score_apps(model, tensors, test_b, mode="ocgtl", device=torch.device("cpu"))
            sc_tm, _ = score_apps(model, tensors, test_m, mode="ocgtl", device=torch.device("cpu"))
            # benign = anomaly (label 1), malware = normal (label 0)
            scores = sc_tm + sc_tb
            labels = [0] * len(sc_tm) + [1] * len(sc_tb)
            auc_b = _auc_with_bootstrap(scores, labels)
        else:
            auc_b = None
        auc_a = var_a["auc"] if var_a and var_a.get("auc") else None
        results[rep] = {
            "variant_A_benign_train": auc_a,
            "variant_B_malware_train_diagnostic": auc_b,
            "sum_raw_auc": (
                float(auc_a["auc"]) + float(auc_b["auc"])
                if auc_a and auc_b
                else float("nan")
            ),
            "note": "variant_B violates benign-only premise; diagnostic only",
            "ocgin_compare": {"orig_A_plus_B": 1.083, "plus_A_plus_B": 1.335},
        }
    (out_dir / "flip.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _shuffled_graph_control(
    *,
    bundle: dict[str, Any],
    split_bundle: Any,
    artifacts: Path,
    out_dir: Path,
    device: torch.device,
    reps: tuple[str, ...],
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    train, test_b, test_m = _split_a_apps(split_bundle)
    results = {}
    for rep in reps:
        tensors = bundle["t22"] if rep == "T22" else bundle["t1k"]
        in_dim = IN_DIM[rep]
        ckpt = _ckpt_path(artifacts, rep=rep, k=PRIMARY_K, mode="ocgtl", split="splitA", seed=SEED)
        if not ckpt.is_file():
            results[rep] = {"available": False}
            continue
        payload = torch.load(ckpt, map_location="cpu", weights_only=False)
        model = OCGTL(in_dim=in_dim, k=PRIMARY_K)
        model.load_state_dict(payload["state_dict"])
        model.eval()
        # Permute node features across test graphs
        test_apps = test_b + test_m
        xs = [tensors[a.sha256]["x"].float().clone() for a in test_apps]
        rng = np.random.default_rng(SEED)
        order = rng.permutation(len(xs))
        shuffled = {a.sha256: xs[order[i]] for i, a in enumerate(test_apps)}
        sc_tb, _ = score_apps(model, tensors, test_b, mode="ocgtl", device=device, shuffled_x=shuffled)
        sc_tm, _ = score_apps(model, tensors, test_m, mode="ocgtl", device=device, shuffled_x=shuffled)
        auc = _auc_with_bootstrap(sc_tb + sc_tm, [0] * len(sc_tb) + [1] * len(sc_tm))
        results[rep] = {"auc": auc, "expected_near": 0.5}
    (out_dir / "shuffled_graph.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def _pilot(device: torch.device, out: Path) -> dict[str, Any]:
    print("[ocgtl] PILOT: T22 K=4 seed=42 Split-A …", flush=True)
    split_bundle = load_run3_split()
    _assert_digest(split_bundle.sha_list_digest)
    bundle = load_bundle()
    train, test_b, test_m = _split_a_apps(split_bundle)
    t0 = time.perf_counter()
    fit = train_ocgtl(
        tensors=bundle["t22"],
        train_apps=train,
        in_dim=10,
        k=PRIMARY_K,
        seed=SEED,
        mode="ocgtl",
        device=device,
    )
    model = fit["model"]
    sc_tb, _ = score_apps(model, bundle["t22"], test_b, mode="ocgtl", device=device)
    sc_tm, _ = score_apps(model, bundle["t22"], test_m, mode="ocgtl", device=device)
    elapsed = time.perf_counter() - t0
    # Projection: Split-A primary = 2 reps × 2 K × 5 seeds = 20
    # + untrained 20 + k1 10 + gtl 20 + flip ~2 + shuffle ~2 ≈ 74 Split-A-ish
    # Split-B: 2 × 2 × 30 × 5 = 600
    n_split_a_equiv = 74
    n_split_b = 600
    proj_a = elapsed * n_split_a_equiv
    proj_b = elapsed * n_split_b
    proj = {
        "pilot_seconds": elapsed,
        "pilot_hours": elapsed / 3600.0,
        "projected_splitA_hours": proj_a / 3600.0,
        "projected_splitB_hours": proj_b / 3600.0,
        "projected_full_hours": (proj_a + proj_b) / 3600.0,
        "exceeds_8h_full": (proj_a + proj_b) / 3600.0 > 8.0,
        "recommendation": (
            "run Split-A first; defer Split-B"
            if (proj_a + proj_b) / 3600.0 > 8.0
            else "full grid feasible"
        ),
        "n_parameters": fit["n_parameters"],
        "graph_embedding_dim": 128,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "pilot_timing.json").write_text(json.dumps(proj, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proj, indent=2), flush=True)
    return proj


def _write_summary(
    out: Path,
    *,
    split_a: dict[str, Any],
    split_b: dict[str, Any] | None,
    flip: dict[str, Any] | None,
    shuffle: dict[str, Any] | None,
    pilot: dict[str, Any] | None,
) -> None:
    lines = [
        "# OCGTL — SUMMARY",
        "",
        "## Degeneracy flags FIRST",
        "",
    ]
    for rep, blk in split_a.items():
        for key, conf in blk.items():
            n_c = conf.get("n_collapsed", 0)
            lines.append(
                f"- {rep}/{key}: collapsed {n_c}/{len(conf['per_seed'])} seeds; "
                f"mean auc_floor={conf['auc_floor_mean']:.4f} (n_noncollapsed={conf['n_noncollapsed']})"
            )
    lines += ["", "## GATE (non-collapsed only)", ""]
    for rep, blk in split_a.items():
        for key, conf in blk.items():
            if conf["n_noncollapsed"] == 0:
                lines.append(f"- {rep}/{key}: COLLAPSE DETECTED — no gate")
                continue
            m = conf["auc_floor_mean"]
            g_size = "clears" if m >= SIZE_FLOOR else "does not clear"
            g_oc = "clears" if m >= OCPOOL_INCUMBENT else "does not clear"
            lines.append(
                f"- {rep}/{key}: {m:.4f} — {g_size} size floor ({SIZE_FLOOR}); {g_oc} OCPool ({OCPOOL_INCUMBENT})"
            )
    if split_b:
        lines += ["", "## Split-B (weighted mean)", ""]
        for rep, blk in split_b.items():
            for key, conf in blk.items():
                lines.append(
                    f"- {rep}/{key}: weighted={conf['weighted_mean_auc_floor']:.4f} "
                    f"± {conf['std_auc_floor']:.4f}; pooled={conf['pooled_oof_auc'].get('auc_floor', float('nan')):.4f}"
                )
    lines += ["", "## Reference rows", "", "| reference | auc_floor |", "|---|---:|"]
    for k, v in REF_ROWS.items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Split-A grid", "", "| rep | config | mean | std | n_ok | n_collapse |", "|---|---|---:|---:|---:|---:|"]
    for rep, blk in split_a.items():
        for key, conf in blk.items():
            lines.append(
                f"| {rep} | {key} | {conf['auc_floor_mean']:.4f} | {conf['auc_floor_std']:.4f} | "
                f"{conf['n_noncollapsed']} | {conf['n_collapsed']} |"
            )
    if flip:
        lines += ["", "## Performance-flip diagnostic", ""]
        for rep, blk in flip.items():
            a = blk.get("variant_A_benign_train")
            b = blk.get("variant_B_malware_train_diagnostic")
            lines.append(
                f"- {rep}: A_auc={a['auc'] if a else None}; B_auc={b['auc'] if b else None}; "
                f"sum={blk.get('sum_raw_auc')}"
            )
    if shuffle:
        lines += ["", "## Shuffled-graph control", ""]
        for rep, blk in shuffle.items():
            if blk.get("auc"):
                lines.append(f"- {rep}: auc_floor={blk['auc']['auc_floor']:.4f}")
    if pilot:
        lines += [
            "",
            "## Runtime pilot",
            "",
            f"- pilot_seconds: {pilot['pilot_seconds']:.1f}",
            f"- projected_full_hours: {pilot['projected_full_hours']:.2f}",
            f"- recommendation: {pilot['recommendation']}",
        ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_reproduce(artifacts: Path, digest: str, n_params: int) -> None:
    cfg = {
        "experiment": "OCGTL",
        "implementation": "reimplemented_from_paper",
        "reference_repo": REF_REPO,
        "reference_commit": REF_COMMIT,
        "reference_license": "AGPL-3.0_not_vendored",
        "library_versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "hyperparameters": {
            "hidden": HIDDEN,
            "n_layers": N_LAYERS,
            "graph_embedding_dim": HIDDEN * N_LAYERS,
            "k_values": list(K_VALUES),
            "epochs": EPOCHS,
            "lr": LR,
            "lr_source": "paper_config_default_0.001",
            "weight_decay": WEIGHT_DECAY,
            "batch_size": BATCH_SIZE,
            "temperature": TEMPERATURE,
            "seeds": list(SEEDS),
            "n_parameters_K4": n_params,
            "bias": False,
            "pooling": "add",
            "norm": "GraphNorm",
            "center": "trainable_normal_init",
            "loss": "L_OCC + L_GTL equal weight (paper Eqn 1)",
        },
        "split_digest": digest,
        "cluster_assignments_path": str(LADDER_ASSIGNMENTS_PATH),
        "reference_rows": REF_ROWS,
    }
    (artifacts / "reproduce_config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (artifacts / "reproduce.md").write_text(
        "# Reproduce OCGTL\n\n```bash\npython -m abrg.ocgtl --resume\n```\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="OCGTL on AndroCT 2017")
    ap.add_argument("--out", type=Path, default=OCGTL_OUTPUT_ROOT)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-split-a", action="store_true")
    ap.add_argument("--skip-split-b", action="store_true")
    ap.add_argument("--reps", type=str, default="T22,T1K")
    ap.add_argument("--pilot", action="store_true", help="Time one run and exit")
    ap.add_argument("--device", type=str, default="auto", choices=("auto", "cpu", "cuda"))
    ap.add_argument("--primary-only", action="store_true", help="Only OCGTL primary (no ablations)")
    args = ap.parse_args(argv)

    device = (
        torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if args.device == "auto"
        else torch.device(args.device)
    )
    print(f"[ocgtl] device={device}", flush=True)
    reps = tuple(r.strip() for r in args.reps.split(",") if r.strip())

    if args.pilot:
        _pilot(device, args.out)
        return 0

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    degeneracy_dir = out / "degeneracy"
    degeneracy_dir.mkdir(parents=True, exist_ok=True)

    split_bundle = load_run3_split()
    _assert_digest(split_bundle.sha_list_digest)
    bundle = load_bundle()
    assignments = _load_ladder_assignments()

    probe = OCGTL(in_dim=10, k=PRIMARY_K)
    n_params = count_parameters(probe)
    print(f"[ocgtl] n_parameters(K={PRIMARY_K})={n_params} emb_dim={probe.graph_embedding_dim}", flush=True)

    # Runtime guard: if no pilot file, run a quick estimate note from existing or skip
    pilot_path = out / "pilot_timing.json"
    pilot = json.loads(pilot_path.read_text(encoding="utf-8")) if pilot_path.is_file() else None

    pred_path = artifacts / "predictions.csv"
    pred_f = pred_path.open("a" if args.resume and pred_path.is_file() else "w", newline="", encoding="utf-8")
    pred_w = csv.writer(pred_f)
    if pred_f.tell() == 0:
        pred_w.writerow(["app_id", "true_label", "score", "representation", "K", "mode", "split", "fold", "seed"])

    if args.primary_only:
        modes: tuple[Mode, ...] = ("ocgtl",)
    else:
        modes = ("ocgtl", "untrained", "gtl_only", "k1_occ")

    split_a: dict[str, Any] = {}
    if not args.skip_split_a:
        print("[ocgtl] Split-A …", flush=True)
        split_a = _run_split_a(
            bundle=bundle,
            split_bundle=split_bundle,
            out_dir=out / "splitA",
            artifacts=artifacts,
            degeneracy_dir=degeneracy_dir,
            pred_writer=pred_w,
            device=device,
            resume=args.resume,
            reps=reps,
            modes=modes,
            k_values=K_VALUES,
        )
    elif (out / "splitA" / "splitA_results.json").is_file():
        split_a = json.loads((out / "splitA" / "splitA_results.json").read_text(encoding="utf-8"))

    # Ablations folder pointer
    (out / "ablation").mkdir(parents=True, exist_ok=True)
    if split_a:
        (out / "ablation" / "splitA_ablations.json").write_text(
            json.dumps({r: {k: v for k, v in blk.items() if not k.startswith("ocgtl")} for r, blk in split_a.items()}, indent=2)
            + "\n",
            encoding="utf-8",
        )

    flip = None
    shuffle = None
    if split_a and not args.primary_only:
        flip = _flip_diagnostic(
            bundle=bundle,
            split_bundle=split_bundle,
            out_dir=out / "flip",
            artifacts=artifacts,
            degeneracy_dir=degeneracy_dir,
            device=device,
            resume=args.resume,
            reps=reps,
        )
        shuffle = _shuffled_graph_control(
            bundle=bundle,
            split_bundle=split_bundle,
            artifacts=artifacts,
            out_dir=out / "ablation",
            device=device,
            reps=reps,
        )

    split_b = None
    run_b = not args.skip_split_b
    # Runtime guard: when launching both stages and projection > 8h, finish Split-A first.
    # Stage-2: `python -m abrg.ocgtl --skip-split-a --resume` still runs Split-B.
    if (
        pilot
        and pilot.get("exceeds_8h_full")
        and not args.skip_split_b
        and not args.skip_split_a
    ):
        print(
            f"[ocgtl] runtime guard: projected_full={pilot['projected_full_hours']:.1f}h > 8h; "
            "deferring Split-B to stage 2 (--skip-split-a --resume)",
            flush=True,
        )
        run_b = False

    if run_b:
        print("[ocgtl] Split-B …", flush=True)
        split_b = _run_split_b(
            bundle=bundle,
            split_bundle=split_bundle,
            assignments=assignments,
            out_dir=out / "splitB",
            artifacts=artifacts,
            degeneracy_dir=degeneracy_dir,
            pred_writer=pred_w,
            device=device,
            resume=args.resume,
            reps=reps,
            k_values=K_VALUES,
        )
    elif (out / "splitB" / "splitB_results.json").is_file():
        split_b = json.loads((out / "splitB" / "splitB_results.json").read_text(encoding="utf-8"))

    pred_f.close()

    # Reload verification
    reload_v = {"available": False}
    ckpt = _ckpt_path(artifacts, rep="T22", k=PRIMARY_K, mode="ocgtl", split="splitA", seed=SEED)
    if ckpt.is_file() and "T22" in split_a:
        stored = None
        for conf in split_a["T22"].values():
            if conf["per_seed"] and conf["per_seed"][0].get("checkpoint") == str(ckpt):
                stored = conf["per_seed"][0]
                break
        if stored and stored.get("auc"):
            train, test_b, test_m = _split_a_apps(split_bundle)
            payload = torch.load(ckpt, map_location="cpu", weights_only=False)
            model = OCGTL(in_dim=10, k=PRIMARY_K)
            model.load_state_dict(payload["state_dict"])
            sc_tb, _ = score_apps(model, bundle["t22"], test_b, mode="ocgtl", device=torch.device("cpu"))
            sc_tm, _ = score_apps(model, bundle["t22"], test_m, mode="ocgtl", device=torch.device("cpu"))
            reloaded = _auc_with_bootstrap(sc_tb + sc_tm, [0] * len(sc_tb) + [1] * len(sc_tm))
            reload_v = {
                "checkpoint": str(ckpt),
                "stored_auc": stored["auc"]["auc"],
                "reloaded_auc": reloaded["auc"],
                "match": abs(stored["auc"]["auc"] - reloaded["auc"]) < 1e-5,
            }
            print(
                f"[ocgtl] reload stored={reload_v['stored_auc']:.6f} "
                f"reloaded={reload_v['reloaded_auc']:.6f} match={reload_v['match']}",
                flush=True,
            )

    _write_reproduce(artifacts, split_bundle.sha_list_digest, n_params)
    if split_a:
        _write_summary(out, split_a=split_a, split_b=split_b, flip=flip, shuffle=shuffle, pilot=pilot)
        # attach reload to reproduce
        cfg_path = artifacts / "reproduce_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        cfg["reload_verification"] = reload_v
        cfg_path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")

    print(f"[ocgtl] done → {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
