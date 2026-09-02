"""Check 3 — nested bootstrap: resample train apps → rebuild vocab → refit → score fixed eval."""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.svm import OneClassSVM

from abrg.validate import BOOTSTRAP_B, BOOTSTRAP_B_FALLBACK, HEADLINE_K, HEADLINE_VOCAB, SEED
from abrg.validate.features import build_many
from abrg.validate.residual import apply_residual, ols_fit, pool_x, score_apps
from abrg.validate.vocab import rank_vocab


def _auc_floor_fast(scores: list[float], labels: list[int]) -> tuple[float, float]:
    """Point AUC + floor only (no inner bootstrap) — for nested outer bootstrap."""
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    mask = np.isfinite(s)
    y, s = y[mask], s[mask]
    if len(np.unique(y)) < 2:
        return float("nan"), float("nan")
    auc = float(roc_auc_score(y, s))
    return auc, max(auc, 1.0 - auc)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def _one_bootstrap_iter(
    *,
    rng: np.random.Generator,
    train_shas_arr: np.ndarray,
    n_tr: int,
    sequences: dict[str, list[str]],
    by_sha: dict[str, Any],
    eval_shas: list[str],
    labels: list[int],
    method: str,
    k: int,
) -> tuple[float, float, list[str]]:
    idx = rng.integers(0, n_tr, size=n_tr)
    boot_shas = train_shas_arr[idx].tolist()
    boot_seqs = {f"{sha}__{i}": sequences[sha] for i, sha in enumerate(boot_shas)}
    boot_keys = list(boot_seqs.keys())
    vocab = rank_vocab(boot_seqs, boot_keys, method=method, k=k)  # type: ignore[arg-type]
    unique_train = list(dict.fromkeys(boot_shas))
    need = list(dict.fromkeys(unique_train + eval_shas))
    tensors = build_many(sequences, vocab, by_sha, need)
    X_tr = np.stack([pool_x(tensors[s], "mean") for s in boot_shas])
    clf = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale").fit(X_tr)
    sc_tr = (-clf.decision_function(X_tr)).tolist()
    oov_tr = [float(tensors[s]["oov_rate"]) for s in boot_shas]
    reg, _ = ols_fit(sc_tr, oov_tr)
    sc_te = score_apps(clf, tensors, eval_shas, pool="mean")
    oov_te = [float(tensors[s]["oov_rate"]) for s in eval_shas]
    resid = apply_residual(reg, sc_te, oov_te)
    auc, floor = _auc_floor_fast(resid, labels)
    return auc, floor, vocab


def run_check3(
    *,
    sequences: dict[str, list[str]],
    by_sha: dict[str, Any],
    train_shas: list[str],
    test_b: list[str],
    test_m: list[str],
    out_dir: Path,
    B: int | None = None,
    method: str = HEADLINE_VOCAB,
    k: int = HEADLINE_K,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    B_requested = B or BOOTSTRAP_B
    train_shas_arr = np.asarray(train_shas)
    n_tr = len(train_shas)
    assert n_tr == 562
    eval_shas = test_b + test_m
    labels = [0] * len(test_b) + [1] * len(test_m)

    rng = np.random.default_rng(SEED)

    # Timing probe
    B_run = B_requested
    if B is None:
        print(f"[validate/C3] timing probe (3 iters) before B={B_requested}", flush=True)
        probe = []
        for _ in range(3):
            tp = time.time()
            _one_bootstrap_iter(
                rng=rng,
                train_shas_arr=train_shas_arr,
                n_tr=n_tr,
                sequences=sequences,
                by_sha=by_sha,
                eval_shas=eval_shas,
                labels=labels,
                method=method,
                k=k,
            )
            probe.append(time.time() - tp)
        per = float(np.median(probe))
        est = per * B_requested
        print(
            f"[validate/C3] ~{per:.1f}s/iter → est {est/60:.1f} min for B={B_requested}",
            flush=True,
        )
        if est > 7200:
            B_run = BOOTSTRAP_B_FALLBACK
            print(f"[validate/C3] reducing to B={B_run}", flush=True)
        rng = np.random.default_rng(SEED)

    print(f"[validate/C3] nested bootstrap B={B_run} method={method} K={k}", flush=True)
    t0 = time.time()
    aucs: list[float] = []
    auc_floors: list[float] = []
    vocabs: list[list[str]] = []
    for b in range(B_run):
        auc, floor, vocab = _one_bootstrap_iter(
            rng=rng,
            train_shas_arr=train_shas_arr,
            n_tr=n_tr,
            sequences=sequences,
            by_sha=by_sha,
            eval_shas=eval_shas,
            labels=labels,
            method=method,
            k=k,
        )
        aucs.append(auc)
        auc_floors.append(floor)
        vocabs.append(vocab)
        if (b + 1) % 10 == 0 or b == 0:
            elapsed = time.time() - t0
            eta = elapsed / (b + 1) * (B_run - b - 1)
            print(
                f"  … b={b+1}/{B_run} floor={floor:.4f} "
                f"elapsed={elapsed:.0f}s eta={eta:.0f}s",
                flush=True,
            )

    elapsed = time.time() - t0
    floors = np.asarray(auc_floors, dtype=float)
    raws = np.asarray(aucs, dtype=float)

    sets = [set(v) for v in vocabs]
    pairs = [
        _jaccard(sets[i], sets[j])
        for i in range(len(sets))
        for j in range(i + 1, len(sets))
    ]
    mean_jaccard = float(np.mean(pairs)) if pairs else float("nan")

    cnt: Counter[str] = Counter()
    for v in vocabs:
        cnt.update(set(v))
    thresh = 0.9 * len(vocabs)
    stable = [c for c, n in cnt.items() if n >= thresh]

    result = {
        "method": method,
        "K": k,
        "B": len(auc_floors),
        "B_requested": B_requested,
        "runtime_sec": elapsed,
        "auc_floor": {
            "mean": float(floors.mean()),
            "std": float(floors.std(ddof=0)),
            "p2.5": float(np.percentile(floors, 2.5)),
            "p97.5": float(np.percentile(floors, 97.5)),
            "values": [float(x) for x in floors],
        },
        "auc_raw": {
            "mean": float(raws.mean()),
            "std": float(raws.std(ddof=0)),
            "p2.5": float(np.percentile(raws, 2.5)),
            "p97.5": float(np.percentile(raws, 97.5)),
        },
        "naive_score_resample_ci95_floor": [0.771, 0.851],
        "vocab_stability": {
            "mean_pairwise_jaccard": mean_jaccard,
            "n_callees_in_gt90pct_bootstraps": len(stable),
            "frac_vocab_stable_gt90pct": len(stable) / k,
            "stable_callee_count": len(stable),
        },
        "scoring": (
            "OCPool_mean + OLS residual score~oov fit on bootstrap train, "
            "apply to fixed eval"
        ),
    }
    _write_json(out_dir / "check3_summary.json", result)
    _write_json(
        out_dir / "auc_floor_distribution.json",
        {"auc_floor": result["auc_floor"]["values"]},
    )
    print(
        f"[validate/C3] done B={result['B']} mean_floor={result['auc_floor']['mean']:.4f} "
        f"CI=[{result['auc_floor']['p2.5']:.4f},{result['auc_floor']['p97.5']:.4f}] "
        f"jaccard={mean_jaccard:.3f} runtime={elapsed:.0f}s",
        flush=True,
    )
    return result
