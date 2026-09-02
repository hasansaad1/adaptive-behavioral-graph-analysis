"""Shared helpers for ocdev headline validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr, wilcoxon
from sklearn.metrics import roc_auc_score

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.apigraph.split import load_run3_split
from abrg.ocdev_validate import EXPECTED_SPLIT_DIGEST_PREFIX


def assert_digest() -> Any:
    bundle = load_run3_split()
    dig = bundle.sha_list_digest
    if not dig.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(
            f"STOP: split digest {dig[:16]}… != {EXPECTED_SPLIT_DIGEST_PREFIX}…"
        )
    print(f"[ocdev_validate] split OK {dig[:12]}…", flush=True)
    return bundle


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _json_default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def auc_floor(scores: list[float] | np.ndarray, labels: list[int] | np.ndarray) -> float:
    y = np.asarray(labels, dtype=np.int32)
    s = np.asarray(scores, dtype=np.float64)
    a = float(roc_auc_score(y, s))
    return max(a, 1.0 - a)


def dist_summary(x: np.ndarray) -> dict[str, float]:
    x = np.asarray(x, dtype=np.float64)
    q = np.percentile(x, [2.5, 25, 50, 75, 97.5])
    return {
        "n": int(x.size),
        "mean": float(np.mean(x)),
        "median": float(np.median(x)),
        "std": float(np.std(x, ddof=1)) if x.size > 1 else 0.0,
        "p2.5": float(q[0]),
        "p25": float(q[1]),
        "p50": float(q[2]),
        "p75": float(q[3]),
        "p97.5": float(q[4]),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
    }


def score_dist_block(scores: np.ndarray) -> dict[str, float]:
    s = np.asarray(scores, dtype=np.float64)
    if s.size == 0:
        return {"n": 0, "median": float("nan"), "iqr": float("nan"), "min": float("nan"), "max": float("nan")}
    q25, q50, q75 = np.percentile(s, [25, 50, 75])
    return {
        "n": int(s.size),
        "median": float(q50),
        "iqr": float(q75 - q25),
        "min": float(np.min(s)),
        "max": float(np.max(s)),
        "mean": float(np.mean(s)),
        "std": float(np.std(s, ddof=1)) if s.size > 1 else 0.0,
    }


def paired_delta_block(trained: list[float], untrained: list[float]) -> dict[str, Any]:
    t = np.asarray(trained, dtype=np.float64)
    u = np.asarray(untrained, dtype=np.float64)
    if t.shape != u.shape:
        raise ValueError("paired lengths differ")
    d = t - u  # trained minus random-init
    n = int(d.size)
    out: dict[str, Any] = {
        "n": n,
        "per_seed_delta_trained_minus_untrained": [float(x) for x in d],
        "median_delta": float(np.median(d)) if n else float("nan"),
        "iqr_delta": float(np.subtract(*np.percentile(d, [75, 25]))) if n else float("nan"),
        "mean_delta": float(np.mean(d)) if n else float("nan"),
        "win_rate_untrained_higher": float(np.mean(d < 0)) if n else float("nan"),
        "win_rate_trained_higher": float(np.mean(d > 0)) if n else float("nan"),
        "n_ties": int(np.sum(d == 0)),
    }
    if n >= 6 or (n >= 3 and np.any(d != 0)):
        try:
            # Wilcoxon on deltas vs 0. n<6 uses exact; zero diffs dropped.
            res = wilcoxon(d, zero_method="wilcox", alternative="two-sided")
            out["wilcoxon"] = {
                "statistic": float(res.statistic),
                "pvalue": float(res.pvalue),
                "n_used": n,
            }
        except ValueError as e:
            out["wilcoxon"] = {"available": False, "reason": str(e), "n_used": n}
    else:
        out["wilcoxon"] = {
            "available": False,
            "reason": f"n={n} too small for Wilcoxon signed-rank",
            "n_used": n,
        }
    return out


def leak_rho(scores: list[float], cov: dict[str, list[float]]) -> dict[str, float]:
    out = {}
    for k, v in cov.items():
        if len(scores) < 3:
            out[k] = float("nan")
        else:
            r, _ = spearmanr(scores, v)
            out[k] = float(r)
    return out


def eval_auc_block(scores: list[float], labels: list[int]) -> dict[str, Any]:
    return _auc_with_bootstrap(scores, labels)
