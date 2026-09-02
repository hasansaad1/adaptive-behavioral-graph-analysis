"""Load T22 (run2 corpus cache) and T1K (B_docfreq K=1000) tensors; assert split."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import torch

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.apigraph.construct import NODE_FEAT_DIM, build_graph_tensors
from abrg.apigraph.extract import extract_sequences
from abrg.apigraph.split import load_run3_split
from abrg.invgraph.extract import load_b_docfreq_vocab
from abrg.kernels import (
    EXPECTED_SPLIT_DIGEST_PREFIX,
    KERNELS_OUTPUT_ROOT,
    T1K_EXPECTED_X,
    T22_EXPECTED_X,
)
from abrg.apigraph import APIGRAPH_OUTPUT_ROOT

B_DOCFREQ_VOCAB = (
    APIGRAPH_OUTPUT_ROOT / "vocab_control" / "vocab_B_docfreq_K1000.csv"
)


def assert_split_digest(digest: str) -> None:
    if not digest.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {digest[:16]}… != {EXPECTED_SPLIT_DIGEST_PREFIX}…"
        )
    print(f"[kernels] split OK {digest[:12]}… (562/141/1700)", flush=True)


def _assert_x_shape(tensors: dict[str, dict[str, Any]], expected: tuple[int, int], name: str) -> None:
    bad = []
    for sha, t in tensors.items():
        sh = tuple(t["x"].shape)
        if sh != expected:
            bad.append((sha, sh))
            if len(bad) >= 5:
                break
    if bad:
        raise SystemExit(f"STOP: {name} x shape != {expected}; examples={bad}")
    print(f"[kernels] {name} load OK n={len(tensors)} x={expected}", flush=True)


def load_t22() -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    bundle = load_corpus_cache(androct_run2_output_dir())
    tensors = bundle.tensors
    _assert_x_shape(tensors, T22_EXPECTED_X, "T22")
    split = {
        "train": [a.sha256 for a in bundle.split["train"]],
        "test_benign": [a.sha256 for a in bundle.split["test_benign"]],
        "test_malware": [a.sha256 for a in bundle.split["test_malware"]],
    }
    return tensors, split


def _covariates_t22(t: dict[str, Any]) -> dict[str, float]:
    return {
        "mapped_events": float(t["n_mapped"]),
        "total_events": float(t["n_events"]),
        "active_nodes": float(t["n_active"]),
        "edge_count": float(t["n_edges"]),
        "density": float(t["density"]),
        "static_norm": float(t["static_norm"]),
    }


def _covariates_t1k(t: dict[str, Any]) -> dict[str, float]:
    sg = t["static_global"]
    sn = float(sg.norm().item()) if hasattr(sg, "norm") else float(np_static(sg))
    return {
        "mapped_events": float(t["n_inv_events"]),
        "total_events": float(t["n_total_events"]),
        "active_nodes": float(t["n_active"]),
        "edge_count": float(t["n_edges"]),
        "density": float(t["density"]),
        "static_norm": sn,
    }


def np_static(sg: Any) -> float:
    import numpy as np

    return float(np.linalg.norm(np.asarray(sg, dtype=float)))


def load_t1k(
    *,
    by_sha: dict[str, Any],
    all_shas: list[str],
    cache_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Materialize B_docfreq K=1000 tensors from cached sequences + frozen vocab CSV.
    Does not re-rank vocabulary. Caches under kernels/embeddings/.
    """
    cache_path = cache_path or (KERNELS_OUTPUT_ROOT / "embeddings" / "t1k_tensors.pt")
    if cache_path.is_file():
        payload = torch.load(cache_path, map_location="cpu", weights_only=False)
        tensors = payload["tensors"]
        _assert_x_shape(tensors, T1K_EXPECTED_X, "T1K")
        if int(payload.get("node_feat_dim", NODE_FEAT_DIM)) != NODE_FEAT_DIM:
            raise SystemExit("STOP: T1K cache node_feat_dim mismatch")
        return tensors

    vocab = load_b_docfreq_vocab(B_DOCFREQ_VOCAB)
    if len(vocab) != 1000:
        raise SystemExit(f"STOP: B_docfreq vocab len {len(vocab)} != 1000")
    apps = [by_sha[s] for s in all_shas]
    print("[kernels] T1K: loading sequences (apigraph cache)", flush=True)
    sequences = extract_sequences(apps)
    print("[kernels] T1K: constructing tensors from vocab_B_docfreq_K1000.csv", flush=True)
    tensors: dict[str, dict[str, Any]] = {}
    for i, sha in enumerate(all_shas):
        tensors[sha] = build_graph_tensors(sequences[sha], vocab, app=by_sha[sha])
        if (i + 1) % 500 == 0:
            print(f"  … {i+1}/{len(all_shas)}", flush=True)
    _assert_x_shape(tensors, T1K_EXPECTED_X, "T1K")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "tensors": tensors,
            "node_feat_dim": NODE_FEAT_DIM,
            "K": 1000,
            "vocab_csv": str(B_DOCFREQ_VOCAB),
        },
        cache_path,
    )
    print(f"[kernels] wrote {cache_path}", flush=True)
    return tensors


def covariates_for(
    tensors: dict[str, dict[str, Any]], shas: list[str], *, kind: str
) -> dict[str, list[float]]:
    rows = []
    for s in shas:
        if kind == "T22":
            rows.append(_covariates_t22(tensors[s]))
        else:
            rows.append(_covariates_t1k(tensors[s]))
    keys = rows[0].keys()
    return {k: [r[k] for r in rows] for k in keys}


def load_bundle() -> dict[str, Any]:
    split_b = load_run3_split()
    assert_split_digest(split_b.sha_list_digest)
    t22, split = load_t22()
    # align SHA lists with split_b
    for key in ("train", "test_benign", "test_malware"):
        a = [x.sha256 for x in getattr(split_b, key if key != "train" else "train")]
        # SplitBundle uses .train / .test_benign / .test_malware
    train = [a.sha256 for a in split_b.train]
    test_b = [a.sha256 for a in split_b.test_benign]
    test_m = [a.sha256 for a in split_b.test_malware]
    if (
        train != split["train"]
        or test_b != split["test_benign"]
        or test_m != split["test_malware"]
    ):
        raise SystemExit("STOP: T22 split SHA lists != Run3 split bundle")
    all_shas = train + test_b + test_m
    t1k = load_t1k(by_sha=split_b.by_sha, all_shas=all_shas)
    meta = {
        "sha_list_digest": split_b.sha_list_digest,
        "n_train": len(train),
        "n_test_benign": len(test_b),
        "n_test_malware": len(test_m),
        "T22_x": list(T22_EXPECTED_X),
        "T1K_x": list(T1K_EXPECTED_X),
    }
    (KERNELS_OUTPUT_ROOT / "embeddings").mkdir(parents=True, exist_ok=True)
    (KERNELS_OUTPUT_ROOT / "embeddings" / "load_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "t22": t22,
        "t1k": t1k,
        "train": train,
        "test_benign": test_b,
        "test_malware": test_m,
        "digest": split_b.sha_list_digest,
        "by_sha": split_b.by_sha,
    }
