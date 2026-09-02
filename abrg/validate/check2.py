"""Check 2 — 3×3 vocab method × K grid."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from abrg.validate import GRID_KS, VOCAB_METHODS
from abrg.validate.features import build_many
from abrg.validate.floors import coverage_frac, size_floors
from abrg.validate.residual import (
    apply_residual,
    fit_ocpool,
    ols_fit,
    residual_block,
    score_apps,
)
from abrg.validate.vocab import assert_train_benign_only, rank_vocab


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _cell_ocpool_residual(
    tensors: dict[str, dict[str, Any]],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    *,
    pool: str,
) -> dict[str, Any]:
    clf = fit_ocpool(tensors, train_shas, pool=pool)  # type: ignore[arg-type]
    sc_tr = score_apps(clf, tensors, train_shas, pool=pool)  # type: ignore[arg-type]
    sc_te = score_apps(clf, tensors, test_b, pool=pool) + score_apps(  # type: ignore[arg-type]
        clf, tensors, test_m, pool=pool
    )
    labels = [0] * len(test_b) + [1] * len(test_m)
    oov_tr = [float(tensors[s]["oov_rate"]) for s in train_shas]
    oov_te = [float(tensors[s]["oov_rate"]) for s in test_b + test_m]
    raw = residual_block(sc_te, labels, name=f"OCPool_{pool}_raw")
    reg, meta = ols_fit(sc_tr, oov_tr)
    resid = apply_residual(reg, sc_te, oov_te)
    r2 = residual_block(resid, labels, name=f"OCPool_{pool}_R2_train_fit", ols_meta=meta)
    return {"raw": raw, "R2_train_fit": r2}


def run_check2(
    *,
    sequences: dict[str, list[str]],
    by_sha: dict[str, Any],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    malware = set(test_m)  # eval malware; train is benign-only so all malware is held out
    # held-out benign = test_b
    heldout_b = set(test_b)
    assert_train_benign_only(train_shas, malware_shas=malware, heldout_benign_shas=heldout_b)

    train_seqs = {s: sequences[s] for s in train_shas}
    assert set(train_seqs) == set(train_shas)
    # integrity: no malware keys in ranking input
    assert not (set(train_seqs) & malware)
    assert not (set(train_seqs) & heldout_b)

    cells: dict[str, Any] = {}
    headline_r2_mean: list[float] = []

    for method in VOCAB_METHODS:
        for k in GRID_KS:
            tag = f"{method}_K{k}"
            print(f"[validate/C2] {tag}", flush=True)
            vocab = rank_vocab(train_seqs, train_shas, method=method, k=k)
            assert len(vocab) == k
            # rebuild integrity: vocab from train_seqs keys only
            all_shas = train_shas + test_b + test_m
            tensors = build_many(sequences, vocab, by_sha, all_shas)
            cov = {
                "train_benign": coverage_frac(sequences, vocab, train_shas),
                "test_benign": coverage_frac(sequences, vocab, test_b),
                "test_malware": coverage_frac(sequences, vocab, test_m),
            }
            floors = size_floors(tensors, test_b, test_m)
            mean_res = _cell_ocpool_residual(tensors, train_shas, test_b, test_m, pool="mean")
            max_res = _cell_ocpool_residual(tensors, train_shas, test_b, test_m, pool="max")
            cell = {
                "method": method,
                "K": k,
                "vocab_integrity": "train_benign_only",
                "n_vocab": len(vocab),
                "coverage": cov,
                "floors": floors,
                "OCPool_mean": mean_res,
                "OCPool_max": max_res,
            }
            cells[tag] = cell
            _write_json(out_dir / f"{tag}.json", cell)
            headline_r2_mean.append(float(mean_res["R2_train_fit"]["auc"]["auc_floor"]))
            print(
                f"  mean raw={mean_res['raw']['auc']['auc_floor']:.4f} "
                f"R2={mean_res['R2_train_fit']['auc']['auc_floor']:.4f} "
                f"oov_floor={floors['oov_rate']['auc_floor']:.4f}",
                flush=True,
            )

    arr = np.asarray(headline_r2_mean, dtype=float)
    summary = {
        "cells": cells,
        "headline_metric": "OCPool_mean R2_train_fit auc_floor",
        "headline_values_by_cell": {
            tag: float(cells[tag]["OCPool_mean"]["R2_train_fit"]["auc"]["auc_floor"])
            for tag in cells
        },
        "across_cells": {
            "min": float(arr.min()),
            "median": float(np.median(arr)),
            "max": float(arr.max()),
            "n": int(len(arr)),
        },
        "B_docfreq_K1000": float(
            cells["B_docfreq_K1000"]["OCPool_mean"]["R2_train_fit"]["auc"]["auc_floor"]
        ),
        "B_docfreq_K1000_is_max": bool(
            abs(
                float(cells["B_docfreq_K1000"]["OCPool_mean"]["R2_train_fit"]["auc"]["auc_floor"])
                - float(arr.max())
            )
            < 1e-12
        ),
        "B_docfreq_K1000_is_min": bool(
            abs(
                float(cells["B_docfreq_K1000"]["OCPool_mean"]["R2_train_fit"]["auc"]["auc_floor"])
                - float(arr.min())
            )
            < 1e-12
        ),
    }
    _write_json(out_dir / "check2_summary.json", summary)
    return summary
