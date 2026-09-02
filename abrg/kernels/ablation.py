"""Edge / feature ablation for the winning configuration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import numpy as np
import torch

from abrg.kernels._nx import LabelMode, prepare_graphs
from abrg.kernels.detectors import eval_row, run_embedding_detectors, run_kernel_detectors
from abrg.kernels.embeddings import (
    embed_fgsd,
    embed_gl2vec,
    embed_graph2vec,
    embed_netlsd,
)
from abrg.kernels.graph_kernels import fit_propagation, fit_shortest_path, fit_wl


def _strip_edges(tensors: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for sha, t in tensors.items():
        tt = dict(t)
        n = int(t["x"].shape[0])
        tt["edge_index"] = torch.zeros(2, 0, dtype=torch.long)
        tt["edge_weight"] = torch.zeros(0, dtype=torch.float32)
        tt["n_edges"] = 0
        tt["density"] = 0.0
        out[sha] = tt
    return out


def _constant_features(tensors: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for sha, t in tensors.items():
        tt = dict(t)
        x = t["x"]
        tt["x"] = torch.ones_like(x)
        out[sha] = tt
    return out


def _split_eval_emb(X_eval: np.ndarray, n_tb: int) -> tuple[np.ndarray, np.ndarray]:
    return X_eval[:n_tb], X_eval[n_tb:]


def run_ablation_for_winner(
    *,
    winner: dict[str, Any],
    tensors: dict[str, dict[str, Any]],
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    kind: str,
    cov: dict[str, list[float]],
    seeds: tuple[int, ...],
    score_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """
    Recompute winner representation on (1) edges removed (2) constant features.
    score_fn(tensors_variant) -> {auc_floor, full row}
    """
    variants = {
        "as_built": tensors,
        "edges_removed": _strip_edges(tensors),
        "features_constant": _constant_features(tensors),
    }
    results = {}
    for name, tens in variants.items():
        results[name] = score_fn(tens)
    full = float(results["as_built"]["auc_floor"])
    no_e = float(results["edges_removed"]["auc_floor"])
    no_f = float(results["features_constant"]["auc_floor"])
    return {
        "winner": winner,
        "as_built_auc_floor": full,
        "edges_removed_auc_floor": no_e,
        "features_constant_auc_floor": no_f,
        "delta_structure_minus_no_edges": full - no_e,
        "delta_structure_only_minus_full": no_f - full,
        "variants": results,
    }


def score_config_on_tensors(
    tensors: dict[str, dict[str, Any]],
    *,
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    kind: str,
    cov: dict[str, list[float]],
    seeds: tuple[int, ...],
    family: str,
    method: str,
    detector: str,
    label_mode: LabelMode,
) -> dict[str, Any]:
    """Re-fit representation + detector for one config on a tensor variant."""
    eval_ids = test_b + test_m
    forbidden = test_b + test_m
    n_tb = len(test_b)

    if family == "embedding":
        nx_tr, _, lab_tr, _ = prepare_graphs(tensors, train, kind=kind, label_mode=label_mode)
        nx_ev, _, lab_ev, _ = prepare_graphs(tensors, eval_ids, kind=kind, label_mode=label_mode)
        if method == "FGSD":
            emb = embed_fgsd(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            )
        elif method == "NetLSD":
            emb = embed_netlsd(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            )
        elif method == "Graph2Vec":
            emb = embed_graph2vec(
                nx_tr,
                nx_ev,
                lab_tr,
                lab_ev,
                train_ids=train,
                eval_ids=eval_ids,
                forbidden_ids=forbidden,
            )
        elif method == "GL2Vec":
            emb = embed_gl2vec(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            )
        else:
            raise SystemExit(f"unknown embedding {method}")
        X_tb, X_tm = _split_eval_emb(emb.X_eval, n_tb)
        det = run_embedding_detectors(emb.X_train, X_tb, X_tm, cov, seeds)
        block = det[detector]
        if block.get("stochastic"):
            # mean floor across seeds
            floor = float(block["auc_floor_mean"])
            # use seed 42 row for CI/direction
            row0 = next(r for r in block["per_seed"] if r["seed"] == seeds[0])
            return {
                "auc_floor": floor,
                "auc": row0["auc"],
                "detector_block": block,
                "dim": emb.dim,
            }
        return {
            "auc_floor": float(block["auc"]["auc_floor"]),
            "auc": block["auc"],
            "detector_block": block,
            "dim": emb.dim,
        }

    # kernel family
    _, gk_tr, _, _ = prepare_graphs(tensors, train, kind=kind, label_mode=label_mode)
    _, gk_ev, _, _ = prepare_graphs(tensors, eval_ids, kind=kind, label_mode=label_mode)
    if method.startswith("WL_h"):
        h = int(method.split("h")[1])
        kr = fit_wl(
            gk_tr, gk_ev, h=h, train_ids=train, forbidden=forbidden, label_mode=label_mode
        )
    elif method == "Propagation":
        kr = fit_propagation(
            gk_tr, gk_ev, train_ids=train, forbidden=forbidden, label_mode=label_mode
        )
    elif method == "ShortestPath":
        kr = fit_shortest_path(
            gk_tr,
            gk_ev,
            train_ids=train,
            forbidden=forbidden,
            label_mode=label_mode,
            kind=kind,
        )
        if kr.skipped:
            return {"auc_floor": float("nan"), "skipped": True, "reason": kr.skip_reason}
    else:
        raise SystemExit(f"unknown kernel {method}")
    K_et_b = kr.K_eval_train[:n_tb]
    K_et_m = kr.K_eval_train[n_tb:]
    det = run_kernel_detectors(kr.K_train, K_et_b, K_et_m, cov)
    block = det[detector]
    return {
        "auc_floor": float(block["auc"]["auc_floor"]),
        "auc": block["auc"],
        "detector_block": block,
    }
