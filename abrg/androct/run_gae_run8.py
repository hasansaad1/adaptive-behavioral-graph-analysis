"""
Run 8 — embedding-space scoring (no retrain). Load Run5 h=8 α=0.2 checkpoint.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
import torch
from scipy.stats import spearmanr
from sklearn.covariance import LedoitWolf
from sklearn.metrics.pairwise import cosine_distances, euclidean_distances
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from abrg.androct.paths import (
    androct_run2_output_dir,
    androct_run5_output_dir,
    androct_run8_output_dir,
)
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import SEED, _auc_with_bootstrap, floor_aucs, split_apps
from abrg.androct.run_gae_run3_5 import _vectorize
from abrg.autoencoder import build_gae, seed_rng
from abrg.features import node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

HIDDEN = 8
ALPHA = 0.2
N_NODES = len(GRAPH_CATEGORY_UNIVERSE)
assert N_NODES == 22

REF_INPUT_CENTROID = 0.776892
REF_GAE_RUN5 = 0.637893  # h=8 α=0.2
# Run 3 reconstruction-error leak rhos (stochastic scorer; reported for comparison)
RUN3_RECON_RHOS = {
    "mapped_event_count": -0.290534,
    "total_event_count": -0.319791,
    "active_nodes": -0.107458,
    "edge_count": -0.209223,
    "graph_density": -0.209223,
    "static_feature_norm": -0.107462,
}


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def _load_encoder(*, trained: bool, ckpt_path: Path):
    in_ch = node_feature_dim()
    if trained:
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        model = build_gae(in_ch, int(ckpt.get("hidden", HIDDEN)))
        model.encoder = EdgeWeightProbeEncoder(model.encoder)
        model.load_state_dict(ckpt["model_state"])
        source = f"loaded:{ckpt_path}"
    else:
        seed_rng(SEED)
        model = build_gae(in_ch, HIDDEN)
        model.encoder = EdgeWeightProbeEncoder(model.encoder)
        source = "random_init_seed42"
    model.eval()
    return model, source


@torch.no_grad()
def _node_embeddings(model, t: dict[str, Any]) -> np.ndarray:
    z = model.encode(t["x"], t["edge_index"], t["edge_weight"])
    return z.detach().cpu().numpy().astype(np.float64)  # (22, 8)


def _pool_all(Z: np.ndarray) -> dict[str, np.ndarray]:
    """Z: (22, H) -> graph-level vectors."""
    return {
        "flat": Z.reshape(-1),  # 176
        "mean": Z.mean(axis=0),  # 8
        "max": Z.max(axis=0),  # 8
        "sum": Z.sum(axis=0),  # 8
    }


def _embed_partition(model, tensors: dict, apps: list) -> dict[str, np.ndarray]:
    pools: dict[str, list[np.ndarray]] = {k: [] for k in ("flat", "mean", "max", "sum")}
    for a in apps:
        Z = _node_embeddings(model, tensors[a.sha256])
        assert Z.shape == (N_NODES, HIDDEN), Z.shape
        for k, v in _pool_all(Z).items():
            pools[k].append(v)
    return {k: np.stack(vs, axis=0) for k, vs in pools.items()}


def _score_auc(
    X_train: np.ndarray,
    X_test_ben: np.ndarray,
    X_test_mal: np.ndarray,
    *,
    method: str,
) -> tuple[dict[str, Any], np.ndarray]:
    """Return (auc_block, scores_test_concat). Higher score = more anomalous."""
    X_te = np.vstack([X_test_ben, X_test_mal])
    y = [0] * len(X_test_ben) + [1] * len(X_test_mal)

    if method == "centroid_euclidean":
        c = X_train.mean(axis=0, keepdims=True)
        scores = np.linalg.norm(X_te - c, axis=1)
    elif method == "centroid_cosine":
        c = X_train.mean(axis=0, keepdims=True)
        scores = cosine_distances(X_te, c).reshape(-1)
    elif method == "mahalanobis_ledoit_wolf":
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X_train)
        Xte = scaler.transform(X_te)
        lw = LedoitWolf().fit(Xtr)
        diff = Xte - lw.location_
        scores = np.einsum("ij,jk,ik->i", diff, lw.precision_, diff)
    elif method.startswith("knn_k"):
        k = int(method.split("knn_k")[1])
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X_train)
        Xte = scaler.transform(X_te)
        nn = NearestNeighbors(n_neighbors=k, metric="euclidean", n_jobs=-1)
        nn.fit(Xtr)
        dists, _ = nn.kneighbors(Xte)
        scores = dists.mean(axis=1)
    else:
        raise ValueError(method)

    auc = _auc_with_bootstrap(scores.tolist(), y)
    return auc, scores


def _input_centroid_auc(tensors, split) -> dict[str, Any]:
    X_tr, _, _, _ = _vectorize(tensors, split["train"], mode="full")
    X_tb, _, _, _ = _vectorize(tensors, split["test_benign"], mode="full")
    X_tm, _, _, _ = _vectorize(tensors, split["test_malware"], mode="full")
    X_tr = np.nan_to_num(X_tr)
    X_tb = np.nan_to_num(X_tb)
    X_tm = np.nan_to_num(X_tm)
    c = X_tr.mean(axis=0, keepdims=True)
    d_b = np.linalg.norm(X_tb - c, axis=1)
    d_m = np.linalg.norm(X_tm - c, axis=1)
    scores = d_b.tolist() + d_m.tolist()
    labels = [0] * len(d_b) + [1] * len(d_m)
    return _auc_with_bootstrap(scores, labels)


def main() -> None:
    parser = argparse.ArgumentParser(description="AndroCT Run 8 — embedding-space scoring")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    out = args.output_dir or androct_run8_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    ckpt_path = androct_run5_output_dir() / "gae_androct_run5_h8.pt"
    retrained = False
    if not ckpt_path.is_file():
        raise SystemExit(f"Run5 h=8 checkpoint missing: {ckpt_path}")

    bundle = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(bundle.eligible)
    tensors = bundle.tensors
    test_apps = split["test_benign"] + split["test_malware"]
    print(
        f"[run8] load ckpt={ckpt_path} split train={len(split['train'])} "
        f"test_b={len(split['test_benign'])} test_m={len(split['test_malware'])}",
        flush=True,
    )

    floors = floor_aucs(test_apps, tensors)
    highest_floor = max(floors[k]["auc_floor"] for k in floors)
    input_ref = _input_centroid_auc(tensors, split)

    reps = ("flat", "mean", "max", "sum")
    scorers = (
        "centroid_euclidean",
        "centroid_cosine",
        "mahalanobis_ledoit_wolf",
        "knn_k1",
        "knn_k5",
        "knn_k20",
    )

    results: dict[str, Any] = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "run": "run8",
        "retrained": retrained,
        "checkpoint": str(ckpt_path),
        "pins": {"hidden": HIDDEN, "alpha": ALPHA, "seed": SEED, "n_parts": 1},
        "representation_dims": {
            "flat": N_NODES * HIDDEN,
            "mean": HIDDEN,
            "max": HIDDEN,
            "sum": HIDDEN,
        },
        "controls": {
            "input_centroid_euclidean_704": {
                "auc_floor": input_ref["auc_floor"],
                "ci95_floor": input_ref["ci95_floor"],
                "direction": input_ref["direction"],
                "prior_reference": REF_INPUT_CENTROID,
            },
            "gae_run5_recon_error": {
                "auc_floor": REF_GAE_RUN5,
                "direction": "benign_higher_score",
                "inverted": True,
            },
        },
        "floors": {
            k: {
                "auc_floor": v["auc_floor"],
                "direction": v["direction"],
                "ci95_floor": v["ci95_floor"],
            }
            for k, v in floors.items()
        },
        "highest_floor": highest_floor,
        "by_encoder": {},
    }

    best: Optional[dict[str, Any]] = None

    for enc_name, trained in (("trained_run5", True), ("random_init", False)):
        print(f"[run8] encoder={enc_name}", flush=True)
        model, source = _load_encoder(trained=trained, ckpt_path=ckpt_path)
        emb_tr = _embed_partition(model, tensors, split["train"])
        emb_tb = _embed_partition(model, tensors, split["test_benign"])
        emb_tm = _embed_partition(model, tensors, split["test_malware"])

        enc_block: dict[str, Any] = {"source": source, "reps": {}}
        for rep in reps:
            enc_block["reps"][rep] = {"dim": int(emb_tr[rep].shape[1]), "scorers": {}}
            for scorer in scorers:
                auc, scores = _score_auc(
                    emb_tr[rep], emb_tb[rep], emb_tm[rep], method=scorer
                )
                row = {
                    "auc": auc["auc"],
                    "auc_floor": auc["auc_floor"],
                    "ci95_floor": auc["ci95_floor"],
                    "direction": auc["direction"],
                    "inverted": auc["direction"] == "benign_higher_score",
                    "below_input_centroid_0.777": auc["auc_floor"] < input_ref["auc_floor"],
                    "below_gae_recon_0.638": auc["auc_floor"] < REF_GAE_RUN5,
                    "below_highest_size_floor": auc["auc_floor"] < highest_floor,
                }
                enc_block["reps"][rep]["scorers"][scorer] = row
                print(
                    f"  {rep}/{scorer}: floor={auc['auc_floor']:.4f} dir={auc['direction']}",
                    flush=True,
                )
                if trained and (
                    best is None or auc["auc_floor"] > best["auc_floor"]
                ):
                    best = {
                        "encoder": enc_name,
                        "representation": rep,
                        "scorer": scorer,
                        "auc_floor": auc["auc_floor"],
                        "scores": scores,
                        "direction": auc["direction"],
                        "inverted": row["inverted"],
                        "ci95_floor": auc["ci95_floor"],
                    }
        results["by_encoder"][enc_name] = enc_block

    # Decoupling check for best trained scorer
    assert best is not None
    sc = best["scores"].tolist()
    leak = {
        "mapped_event_count": _rho(sc, [float(tensors[a.sha256]["n_mapped"]) for a in test_apps]),
        "total_event_count": _rho(sc, [float(tensors[a.sha256]["n_events"]) for a in test_apps]),
        "active_nodes": _rho(sc, [float(tensors[a.sha256]["n_active"]) for a in test_apps]),
        "edge_count": _rho(sc, [float(tensors[a.sha256]["n_edges"]) for a in test_apps]),
        "graph_density": _rho(sc, [float(tensors[a.sha256]["density"]) for a in test_apps]),
        "static_feature_norm": _rho(
            sc, [float(tensors[a.sha256]["static_norm"]) for a in test_apps]
        ),
    }
    # Compare |rho| to Run3 recon
    dens_keys = ("total_event_count", "edge_count", "graph_density", "mapped_event_count")
    mean_abs_emb = float(np.mean([abs(leak[k]) for k in dens_keys]))
    mean_abs_recon = float(np.mean([abs(RUN3_RECON_RHOS[k]) for k in dens_keys]))
    results["best_scorer"] = {
        "encoder": best["encoder"],
        "representation": best["representation"],
        "scorer": best["scorer"],
        "auc_floor": best["auc_floor"],
        "ci95_floor": best["ci95_floor"],
        "direction": best["direction"],
        "inverted": best["inverted"],
        "leak_spearman": leak,
        "run3_recon_leak_spearman": RUN3_RECON_RHOS,
        "mean_abs_rho_density_related_embedding": mean_abs_emb,
        "mean_abs_rho_density_related_run3_recon": mean_abs_recon,
        "embedding_less_coupled_to_density_than_run3_recon": mean_abs_emb < mean_abs_recon,
        "below_input_centroid": best["auc_floor"] < input_ref["auc_floor"],
    }

    # Drop non-serializable scores
    (out / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")

    # SUMMARY
    lines = [
        "# AndroCT Run 8 — embedding-space scoring (no retrain)",
        f"- UTC: {results['utc']}",
        f"- checkpoint: `{ckpt_path}` (retrained={retrained})",
        f"- dims: flat={N_NODES*HIDDEN}, mean=max=sum={HIDDEN}",
        f"- split: train_benign={len(split['train'])} test_benign={len(split['test_benign'])} "
        f"test_malware={len(split['test_malware'])}",
        "",
        "## Controls",
        f"- input-space centroid Euclidean 704-dim: AUC_floor="
        f"{input_ref['auc_floor']:.4f} CI={input_ref['ci95_floor']} "
        f"dir={input_ref['direction']} (prior ref {REF_INPUT_CENTROID})",
        f"- GAE Run5 recon-error ref: AUC_floor={REF_GAE_RUN5:.4f} inverted=True",
        f"- highest size floor: {highest_floor:.4f}",
        "",
        "## Size floors",
    ]
    for k, v in floors.items():
        lines.append(
            f"- {k}: floor={v['auc_floor']:.4f} dir={v['direction']} "
            f"CI=[{v['ci95_floor'][0]:.4f}, {v['ci95_floor'][1]:.4f}]"
        )

    lines.extend(
        [
            "",
            "## AUC_floor table (representation × scorer × encoder)",
            "| encoder | rep | scorer | AUC_floor | CI_floor | direction | inverted | "
            "< input 0.777 | < GAE 0.638 |",
            "|---|---|---|---:|---|---|---|---|---|",
        ]
    )
    for enc_name in ("trained_run5", "random_init"):
        for rep in reps:
            for scorer in scorers:
                r = results["by_encoder"][enc_name]["reps"][rep]["scorers"][scorer]
                lines.append(
                    f"| {enc_name} | {rep} | {scorer} | {r['auc_floor']:.4f} | "
                    f"[{r['ci95_floor'][0]:.4f}, {r['ci95_floor'][1]:.4f}] | "
                    f"{r['direction']} | {r['inverted']} | "
                    f"{r['below_input_centroid_0.777']} | {r['below_gae_recon_0.638']} |"
                )

    b = results["best_scorer"]
    lines.extend(
        [
            "",
            "## Best trained embedding scorer",
            f"- {b['representation']} / {b['scorer']}: AUC_floor={b['auc_floor']:.4f} "
            f"CI={b['ci95_floor']} dir={b['direction']} inverted={b['inverted']}",
            f"- below input centroid 0.777: {b['below_input_centroid']}",
            "",
            "## Decoupling — Spearman ρ (best scorer vs Run3 recon)",
            "| metric | embedding ρ | Run3 recon ρ |",
            "|---|---:|---:|",
        ]
    )
    for k in (
        "mapped_event_count",
        "total_event_count",
        "active_nodes",
        "edge_count",
        "graph_density",
        "static_feature_norm",
    ):
        lines.append(
            f"| {k} | {b['leak_spearman'][k]:.4f} | {RUN3_RECON_RHOS[k]:.4f} |"
        )
    lines.extend(
        [
            f"- mean |ρ| density-related (mapped/total/edges/density): "
            f"embedding={b['mean_abs_rho_density_related_embedding']:.4f} "
            f"run3_recon={b['mean_abs_rho_density_related_run3_recon']:.4f}",
            f"- embedding_less_coupled_to_density_than_run3_recon="
            f"{b['embedding_less_coupled_to_density_than_run3_recon']}",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    (out / "RUN.md").write_text(
        "\n".join(
            [
                "# RUN CARD — androct_2017 / run8",
                "AXIS: score Run5 latent embeddings (no retrain); vs input centroid & random-init",
                f"RESULT: best={b['representation']}/{b['scorer']} "
                f"auc_floor={b['auc_floor']:.4f} inverted={b['inverted']}",
            ]
        )
        + "\n"
    )
    print("\n".join(lines), flush=True)
    print(f"[run8] done → {out}", flush=True)


if __name__ == "__main__":
    main()
