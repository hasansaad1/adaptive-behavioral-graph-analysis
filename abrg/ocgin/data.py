"""Load AndroCT corpus tensors (read-only) and assert identity with Run 3 population."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch

from abrg.androct.paths import androct_run2_output_dir, androct_run3_output_dir
from abrg.androct.run2_corpus import CorpusBundle, load_corpus_cache
from abrg.androct.run_gae_run2 import SEED, TEST_RATIO, split_apps
from abrg.features import node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE


@dataclass
class OCGINCorpus:
    bundle: CorpusBundle
    split: dict[str, list]
    tensors: dict[str, dict[str, Any]]
    fingerprint: str


def _tensor_fingerprint(tensors: dict[str, dict[str, Any]], shas: list[str]) -> str:
    h = hashlib.sha256()
    for sha in sorted(shas):
        t = tensors[sha]
        h.update(sha.encode())
        h.update(t["x"].detach().cpu().contiguous().numpy().tobytes())
        h.update(t["edge_index"].detach().cpu().contiguous().numpy().tobytes())
        h.update(t["edge_weight"].detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def assert_run3_tensor_identity(bundle: CorpusBundle, split: dict[str, list]) -> str:
    """
    Assert tensors match the Run-3 shared cache population.
    STOP if counts / node dim / fingerprint vs run2 cache meta disagree.
    """
    run3 = androct_run3_output_dir()
    cmp_path = run3 / "comparison.json"
    if not cmp_path.is_file():
        raise SystemExit(f"STOP: Run3 comparison.json missing at {cmp_path}")

    run3_cmp = json.loads(cmp_path.read_text(encoding="utf-8"))
    pop = run3_cmp.get("population") or {}
    expected_split = (pop.get("split") or {})
    n_train = len(split["train"])
    n_tb = len(split["test_benign"])
    n_tm = len(split["test_malware"])

    errors: list[str] = []
    if expected_split.get("train") is not None and int(expected_split["train"]) != n_train:
        errors.append(f"train size {n_train} != run3 {expected_split['train']}")
    if expected_split.get("test_benign") is not None and int(expected_split["test_benign"]) != n_tb:
        errors.append(f"test_benign {n_tb} != run3 {expected_split['test_benign']}")
    if expected_split.get("test_malware") is not None and int(expected_split["test_malware"]) != n_tm:
        errors.append(f"test_malware {n_tm} != run3 {expected_split['test_malware']}")

    n_nodes = len(GRAPH_CATEGORY_UNIVERSE)
    feat_dim = node_feature_dim()
    if n_nodes != 22 or feat_dim != 10:
        errors.append(f"expected 22x10 nodes/feats, got {n_nodes}x{feat_dim}")

    # Sample identity: every eligible tensor must be 22x10 and match cache file
    cache_tensors = torch.load(
        androct_run2_output_dir() / "corpus_cache" / "tensors.pt",
        map_location="cpu",
        weights_only=False,
    )
    for sha, t in bundle.tensors.items():
        if sha not in cache_tensors:
            errors.append(f"sha {sha} missing from on-disk tensors.pt")
            break
        c = cache_tensors[sha]
        if not torch.equal(t["x"], c["x"]):
            errors.append(f"tensor x mismatch for {sha}")
            break
        if not torch.equal(t["edge_index"], c["edge_index"]):
            errors.append(f"edge_index mismatch for {sha}")
            break
        if not torch.equal(t["edge_weight"], c["edge_weight"]):
            errors.append(f"edge_weight mismatch for {sha}")
            break
        if tuple(t["x"].shape) != (22, 10):
            errors.append(f"x.shape {tuple(t['x'].shape)} != (22, 10) for {sha}")
            break

    all_shas = list(bundle.tensors.keys())
    fp = _tensor_fingerprint(bundle.tensors, all_shas)
    fp_disk = _tensor_fingerprint(cache_tensors, all_shas)
    if fp != fp_disk:
        errors.append(f"fingerprint mismatch loaded={fp[:16]}… disk={fp_disk[:16]}…")

    shared = pop.get("shared_corpus_cache")
    if shared:
        expected_cache = Path(shared).resolve()
        actual_cache = (androct_run2_output_dir() / "corpus_cache").resolve()
        if expected_cache != actual_cache and expected_cache.name == "corpus_cache":
            # path string may differ if absolute; compare resolved run2 corpus_cache
            if actual_cache != androct_run2_output_dir().resolve() / "corpus_cache":
                errors.append(f"cache path drift: run3={expected_cache} actual={actual_cache}")

    if errors:
        raise SystemExit("STOP: tensor equality vs Run3 failed:\n  - " + "\n  - ".join(errors))

    print(
        f"[ocgin] tensor identity OK fingerprint={fp[:16]}… "
        f"split train={n_train} test_b={n_tb} test_m={n_tm} "
        f"n_nodes={n_nodes} feat_dim={feat_dim}",
        flush=True,
    )
    return fp


def load_ocgin_corpus() -> OCGINCorpus:
    bundle = load_corpus_cache(androct_run2_output_dir())
    # Prefer frozen split from cache meta (same as Run3 prepare_corpus); fall back to re-split
    split = bundle.split
    if not split or not split.get("train"):
        split = split_apps(bundle.eligible)
    # Verify seed pins
    assert SEED == 42 and TEST_RATIO == 0.2
    fp = assert_run3_tensor_identity(bundle, split)
    return OCGINCorpus(bundle=bundle, split=split, tensors=bundle.tensors, fingerprint=fp)


def malware_train_split(eligible: list, *, n_train: int = 562, seed: int = 42) -> dict[str, list]:
    """Diagnostic flip: malware-only train of matched size; remainder + all benign for test."""
    import random

    rng = random.Random(seed)
    malware = [a for a in eligible if a.label == "malware"]
    benign = [a for a in eligible if a.label == "benign"]
    rng.shuffle(malware)
    train = malware[:n_train]
    test_malware = malware[n_train:]
    return {
        "train": train,
        "test_benign": benign,  # anomaly class under Variant B
        "test_malware": test_malware,  # "normal" under Variant B
    }
