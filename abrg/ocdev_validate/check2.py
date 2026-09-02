"""Check 2 — trained vs random-init, paired, existing artifacts only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.metrics import roc_auc_score

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT, androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import split_apps
from abrg.ocdev import FEATURE_SETS, OCDEV_OUTPUT_ROOT, SEEDS
from abrg.ocdev.detectors import fit_score_centroid_euclidean
from abrg.ocdev.part_a import load_profiles
from abrg.ocdev_validate.util import paired_delta_block, write_json


def _auc_floor_of(obj: dict[str, Any]) -> float:
    if "auc" in obj and isinstance(obj["auc"], dict):
        return float(obj["auc"]["auc_floor"])
    if "auc_floor" in obj:
        return float(obj["auc_floor"])
    raise KeyError("no auc_floor")


def _load_ocdev_json(model_tag: str, fset: str, det: str, seed: int | None) -> dict[str, Any]:
    if model_tag == "trained":
        root = OCDEV_OUTPUT_ROOT / "partA_profiles" / "splitA_trained"
    else:
        root = OCDEV_OUTPUT_ROOT / "controls" / "random_init_splitA"
    if seed is None:
        p = root / f"{model_tag}__{fset}__none__{det}__splitA__foldNA.json"
    else:
        p = root / f"{model_tag}__{fset}__none__{det}__splitA__foldNA__seed{seed}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _ocdev_grid() -> dict[str, Any]:
    rows = []
    per_fset: dict[str, Any] = {}
    for fset in FEATURE_SETS:
        cent_t = _auc_floor_of(_load_ocdev_json("trained", fset, "centroid_euclidean", None))
        cent_r = _auc_floor_of(_load_ocdev_json("random_init", fset, "centroid_euclidean", None))
        ocsvm_t, ocsvm_r = [], []
        ocsvm_seeds = []
        for seed in SEEDS:
            t = _auc_floor_of(_load_ocdev_json("trained", fset, "ocsvm_rbf", seed))
            r = _auc_floor_of(_load_ocdev_json("random_init", fset, "ocsvm_rbf", seed))
            ocsvm_t.append(t)
            ocsvm_r.append(r)
            ocsvm_seeds.append({"seed": seed, "trained": t, "random_init": r, "delta_t_minus_r": t - r})
        per_fset[fset] = {
            "centroid_euclidean": {
                "stochastic": False,
                "note": (
                    "random-init GAE profiles are a single saved encoder; "
                    "centroid_euclidean is deterministic — n=1, not 5 encoder seeds"
                ),
                "trained": cent_t,
                "random_init": cent_r,
                "delta_t_minus_r": cent_t - cent_r,
                "paired": paired_delta_block([cent_t], [cent_r]),
            },
            "ocsvm_rbf": {
                "stochastic": True,
                "seeds": list(SEEDS),
                "trained_mean": float(np.mean(ocsvm_t)),
                "trained_std": float(np.std(ocsvm_t, ddof=1)),
                "random_init_mean": float(np.mean(ocsvm_r)),
                "random_init_std": float(np.std(ocsvm_r, ddof=1)),
                "per_seed": ocsvm_seeds,
                "paired": paired_delta_block(ocsvm_t, ocsvm_r),
            },
        }
        rows.append(
            {
                "feature_set": fset,
                "centroid_euclidean_trained": cent_t,
                "centroid_euclidean_random_init": cent_r,
                "ocsvm_rbf_trained_mean": float(np.mean(ocsvm_t)),
                "ocsvm_rbf_trained_std": float(np.std(ocsvm_t, ddof=1)),
                "ocsvm_rbf_random_init_mean": float(np.mean(ocsvm_r)),
                "ocsvm_rbf_random_init_std": float(np.std(ocsvm_r, ddof=1)),
            }
        )
    return {"per_feature_set": per_fset, "table_rows": rows}


def _headline_d1_eval_paired_bootstrap(n_boot: int = 2000, seed: int = 42) -> dict[str, Any]:
    """Paired eval-set bootstrap of AUC_floor(trained) − AUC_floor(random-init) for D1 centroid."""
    arrays_t, shas = load_profiles("trained_t22")
    arrays_r, shas_r = load_profiles("random_init_t22")
    if shas != shas_r:
        raise SystemExit("STOP: random-init profile index != trained")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    tr = np.asarray([sha_to_i[a.sha256] for a in split["train"]], dtype=np.int64)
    te = np.asarray(
        [sha_to_i[a.sha256] for a in (split["test_benign"] + split["test_malware"])],
        dtype=np.int64,
    )
    y = np.asarray([0] * len(split["test_benign"]) + [1] * len(split["test_malware"]))
    sc_t, _ = fit_score_centroid_euclidean(arrays_t["D1"][tr], arrays_t["D1"][te])
    sc_r, _ = fit_score_centroid_euclidean(arrays_r["D1"][tr], arrays_r["D1"][te])
    sc_t = np.asarray(sc_t)
    sc_r = np.asarray(sc_r)
    a_t = max(float(roc_auc_score(y, sc_t)), 1.0 - float(roc_auc_score(y, sc_t)))
    a_r = max(float(roc_auc_score(y, sc_r)), 1.0 - float(roc_auc_score(y, sc_r)))
    rng = np.random.default_rng(seed)
    pos = np.where(y == 1)[0]
    neg = np.where(y == 0)[0]
    deltas = []
    for _ in range(n_boot):
        pi = rng.choice(pos, size=len(pos), replace=True)
        ni = rng.choice(neg, size=len(neg), replace=True)
        idx = np.concatenate([pi, ni])
        yy = y[idx]
        at = float(roc_auc_score(yy, sc_t[idx]))
        ar = float(roc_auc_score(yy, sc_r[idx]))
        deltas.append(max(at, 1.0 - at) - max(ar, 1.0 - ar))
    d = np.asarray(deltas)
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {
        "trained_auc_floor": a_t,
        "random_init_auc_floor": a_r,
        "delta_t_minus_r": a_t - a_r,
        "paired_eval_bootstrap_B": n_boot,
        "delta_mean": float(np.mean(d)),
        "delta_ci95": [float(lo), float(hi)],
        "ci_includes_zero": bool(lo <= 0.0 <= hi),
        "frac_boot_untrained_higher": float(np.mean(d < 0)),
    }


def _family_gae_recon() -> dict[str, Any]:
    root = ANDROCT_OUTPUT_ROOT / "invgraph" / "models" / "V2_invocation"
    t, u = [], []
    per = []
    for seed in SEEDS:
        jt = json.loads((root / f"gae_seed{seed}.json").read_text())
        ju = json.loads((root / f"gae_rand_seed{seed}.json").read_text())
        at, au = _auc_floor_of(jt), _auc_floor_of(ju)
        t.append(at)
        u.append(au)
        per.append({"seed": seed, "trained": at, "random_init": au, "delta_t_minus_r": at - au})
    return {
        "source": str(root / "gae_seed*.json + gae_rand_seed*.json"),
        "pairing": "invgraph V2_invocation GAE recon, 5 seeds",
        "per_seed": per,
        "trained_mean": float(np.mean(t)),
        "trained_std": float(np.std(t, ddof=1)),
        "random_init_mean": float(np.mean(u)),
        "random_init_std": float(np.std(u, ddof=1)),
        "paired": paired_delta_block(t, u),
    }


def _family_gae_embedding() -> dict[str, Any]:
    # Run8 SUMMARY table — deterministic scorers, single encoder each. n=1.
    trained = 0.6691  # trained_run5 / mean / centroid_euclidean
    rand = 0.7591  # random_init / mean / centroid_euclidean
    return {
        "source": str(ANDROCT_OUTPUT_ROOT / "run8" / "SUMMARY.md"),
        "pairing": "Run8 mean / centroid_euclidean (deterministic; n=1 encoder)",
        "trained": trained,
        "random_init": rand,
        "delta_t_minus_r": trained - rand,
        "paired": paired_delta_block([trained], [rand]),
    }


def _family_ocgin() -> dict[str, Any]:
    def _per(path: Path) -> list[float]:
        blob = json.loads(path.read_text())
        # preserve seed order
        items = sorted(blob["per_seed"], key=lambda r: int(r["seed"]))
        return [_auc_floor_of(r) for r in items]

    root = ANDROCT_OUTPUT_ROOT / "ocgin" / "per_seed"
    t = _per(root / "OCGIN_plus_A.json")
    u = _per(root / "OCGIN_plus_rand_A.json")
    per = [
        {"seed": s, "trained": tt, "random_init": uu, "delta_t_minus_r": tt - uu}
        for s, tt, uu in zip(SEEDS, t, u)
    ]
    return {
        "source": str(root),
        "pairing": "OCGIN_plus Variant A vs RANDOM-INIT OCGIN_plus, 5 seeds",
        "per_seed": per,
        "trained_mean": float(np.mean(t)),
        "trained_std": float(np.std(t, ddof=1)),
        "random_init_mean": float(np.mean(u)),
        "random_init_std": float(np.std(u, ddof=1)),
        "paired": paired_delta_block(t, u),
    }


def _family_glocalkd() -> dict[str, Any]:
    blob = json.loads((ANDROCT_OUTPUT_ROOT / "glocalkd" / "runs" / "grid_rows.json").read_text())
    rows = list(blob.get("rows") or []) + list(blob.get("ablation_rows") or [])
    def pick(trained: bool) -> dict[int, float]:
        want_loss = "full" if trained else "untrained"
        out = {}
        for r in rows:
            if (
                r.get("kind") == "T22"
                and r.get("pooling") == "mean"
                and r.get("score_variant") == "s_graph"
                and bool(r.get("trained")) is trained
                and r.get("loss_mode") == want_loss
            ):
                out[int(r["seed"])] = float(r["auc_floor"])
        return out

    tmap, umap = pick(True), pick(False)
    seeds = [s for s in SEEDS if s in tmap and s in umap]
    if not seeds:
        raise SystemExit(
            f"STOP: GLocalKD T22 mean/s_graph pairing empty trained={sorted(tmap)} untrained={sorted(umap)}"
        )
    t = [tmap[s] for s in seeds]
    u = [umap[s] for s in seeds]
    per = [
        {"seed": s, "trained": tt, "random_init": uu, "delta_t_minus_r": tt - uu}
        for s, tt, uu in zip(seeds, t, u)
    ]
    return {
        "source": str(ANDROCT_OUTPUT_ROOT / "glocalkd" / "runs" / "grid_rows.json"),
        "pairing": "T22 / pool=mean / s_graph / loss=full, trained vs untrained, 5 seeds",
        "per_seed": per,
        "trained_mean": float(np.mean(t)),
        "trained_std": float(np.std(t, ddof=1)),
        "random_init_mean": float(np.mean(u)),
        "random_init_std": float(np.std(u, ddof=1)),
        "paired": paired_delta_block(t, u),
    }


def _family_ocgtl() -> dict[str, Any]:
    ckpt = ANDROCT_OUTPUT_ROOT / "ocgtl" / "artifacts" / "checkpoints"

    def load(mode: str) -> tuple[list[float], list[bool]]:
        vals, coll = [], []
        for seed in SEEDS:
            p = ckpt / f"T1K__K4__{mode}__splitA__all__seed{seed}.json"
            blob = json.loads(p.read_text())
            collapsed = bool(blob.get("degeneracy", {}).get("COLLAPSE_DETECTED"))
            coll.append(collapsed)
            if collapsed or blob.get("auc") is None:
                vals.append(float("nan"))
            else:
                vals.append(_auc_floor_of(blob))
        return vals, coll

    t, t_c = load("ocgtl")
    u, u_c = load("untrained")
    # T22 trained collapsed 5/5 — record that
    t22_note = "T22 ocgtl_K4/K6 COLLAPSE 5/5; pairing uses T1K K4"
    per = []
    t_ok, u_ok = [], []
    for s, tt, uu, tc, uc in zip(SEEDS, t, u, t_c, u_c):
        per.append(
            {
                "seed": s,
                "trained": tt,
                "random_init": uu,
                "delta_t_minus_r": (tt - uu) if np.isfinite(tt) and np.isfinite(uu) else float("nan"),
                "trained_collapsed": tc,
                "untrained_collapsed": uc,
            }
        )
        if np.isfinite(tt) and np.isfinite(uu):
            t_ok.append(tt)
            u_ok.append(uu)
    return {
        "source": str(ckpt),
        "pairing": "T1K OCGTL K=4 vs untrained K=4, 5 seeds",
        "t22_note": t22_note,
        "per_seed": per,
        "n_paired_noncollapsed": len(t_ok),
        "trained_mean": float(np.mean(t_ok)) if t_ok else float("nan"),
        "trained_std": float(np.std(t_ok, ddof=1)) if len(t_ok) > 1 else float("nan"),
        "random_init_mean": float(np.mean(u_ok)) if u_ok else float("nan"),
        "random_init_std": float(np.std(u_ok, ddof=1)) if len(u_ok) > 1 else float("nan"),
        "paired": paired_delta_block(t_ok, u_ok) if t_ok else {"n": 0},
    }


def _distinguishable(paired: dict[str, Any]) -> str:
    w = paired.get("wilcoxon") or {}
    if not w.get("pvalue") and w.get("available") is False:
        return "wilcoxon_not_applicable"
    p = w.get("pvalue")
    if p is None:
        return "wilcoxon_not_applicable"
    if p < 0.05:
        med = paired.get("median_delta", 0.0)
        if med < 0:
            return "random_init_advantage_distinguishable_from_zero"
        return "trained_advantage_distinguishable_from_zero"
    return "trained_and_untrained_indistinguishable"


def run_check2(*, out: Path) -> dict[str, Any]:
    print("[ocdev_validate/C2] ocdev random-init grid …", flush=True)
    ocdev = _ocdev_grid()
    print("[ocdev_validate/C2] D1 centroid paired eval bootstrap …", flush=True)
    d1_boot = _headline_d1_eval_paired_bootstrap()
    families = {
        "GAE_reconstruction": _family_gae_recon(),
        "GAE_embedding_distance": _family_gae_embedding(),
        "OCGIN": _family_ocgin(),
        "GLocalKD": _family_glocalkd(),
        "OCGTL": _family_ocgtl(),
        "deviation_profiles_D1_centroid": {
            "source": "ocdev saved profiles + centroid_euclidean",
            "pairing": "D1 centroid_euclidean trained vs random-init (n=1 encoder)",
            "trained": ocdev["per_feature_set"]["D1"]["centroid_euclidean"]["trained"],
            "random_init": ocdev["per_feature_set"]["D1"]["centroid_euclidean"]["random_init"],
            "paired": ocdev["per_feature_set"]["D1"]["centroid_euclidean"]["paired"],
            "eval_paired_bootstrap": d1_boot,
        },
        "deviation_profiles_D1_ocsvm": {
            "source": "ocdev saved OCSVM seeds",
            "pairing": "D1 ocsvm_rbf 5 detector seeds, same profiles",
            "trained_mean": ocdev["per_feature_set"]["D1"]["ocsvm_rbf"]["trained_mean"],
            "random_init_mean": ocdev["per_feature_set"]["D1"]["ocsvm_rbf"]["random_init_mean"],
            "paired": ocdev["per_feature_set"]["D1"]["ocsvm_rbf"]["paired"],
            "per_seed": ocdev["per_feature_set"]["D1"]["ocsvm_rbf"]["per_seed"],
        },
    }
    claims = {}
    for name, blk in families.items():
        paired = blk.get("paired") or {}
        claims[name] = _distinguishable(paired)
    # headline D1 centroid: Wilcoxon n=1 N/A; use eval-set paired bootstrap CI
    claims["deviation_profiles_D1_centroid"] = (
        "trained_and_untrained_indistinguishable"
        if d1_boot["ci_includes_zero"]
        else (
            "random_init_advantage_distinguishable_from_zero"
            if d1_boot["delta_t_minus_r"] < 0
            else "trained_advantage_distinguishable_from_zero"
        )
    )
    claims["deviation_profiles_D1_centroid_basis"] = (
        "paired eval-set bootstrap CI of AUC_floor delta (Wilcoxon n=1 not applicable); "
        f"CI includes 0 = {d1_boot['ci_includes_zero']}"
    )

    payload = {
        "random_init_encoder_note": (
            "devread random-init GAE profiles exist for a single untrained encoder; "
            "centroid_euclidean is deterministic; ocsvm_rbf uses detector seeds {42..46}"
        ),
        "ocdev_grid": ocdev,
        "d1_centroid_eval_paired_bootstrap": d1_boot,
        "families": families,
        "claims": claims,
    }
    write_json(out / "check2.json", payload)
    return payload
