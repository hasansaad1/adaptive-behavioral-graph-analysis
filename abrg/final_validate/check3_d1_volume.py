"""Check 3 — is D1 a volume detector?"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
from scipy.stats import spearmanr

from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.final_validate.util import write_json
from abrg.ocdev.detectors import fit_score_centroid_euclidean
from abrg.ocdev.part_a import load_profiles
from abrg.registry import GRAPH_CATEGORY_UNIVERSE
from abrg.validate.residual import apply_residual, ols_fit


def _covariates(tensors: dict[str, dict], shas: list[str]) -> dict[str, np.ndarray]:
    rows = []
    for s in shas:
        t = tensors[s]
        mapped = float(t.get("n_mapped", t.get("n_inv_events", 0)))
        total = float(t.get("n_events", t.get("n_total_events", 0)))
        static = t.get("static_global")
        if static is not None and hasattr(static, "norm"):
            sn = float(static.norm().item())
        else:
            sn = t.get("static_norm", t.get("static_slice_norm", 0.0))
            if hasattr(sn, "item"):
                sn = float(sn)
            else:
                sn = float(sn) if sn is not None else 0.0
        rows.append(
            {
                "mapped_events": mapped,
                "total_events": total,
                "active_nodes": float(t["n_active"]),
                "edge_count": float(t["n_edges"]),
                "density": float(t["density"]),
                "static_feature_norm": sn,
            }
        )
    keys = list(rows[0].keys())
    return {k: np.asarray([r[k] for r in rows], dtype=np.float64) for k in keys}


def run_check3(*, out: Path, split_bundle: Any, tensors: dict[str, dict]) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    X = arrays["D1"]
    assert X.shape[1] == 22, X.shape

    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    train_b = [a.sha256 for a in split["train"]]
    test_b = [a.sha256 for a in split["test_benign"]]
    test_m = [a.sha256 for a in split["test_malware"]]
    te_shas = test_b + test_m
    labels = np.asarray([0] * len(test_b) + [1] * len(test_m), dtype=np.int32)
    tr_idx = np.asarray([sha_to_i[s] for s in train_b], dtype=np.int64)
    te_idx = np.asarray([sha_to_i[s] for s in te_shas], dtype=np.int64)

    sc, _ = fit_score_centroid_euclidean(X[tr_idx], X[te_idx])
    sc = np.asarray(sc, dtype=np.float64)
    raw_auc = _auc_with_bootstrap(sc.tolist(), labels.tolist())

    cov = _covariates(tensors, te_shas)
    rhos = {}
    for k, v in cov.items():
        r, p = spearmanr(sc, v)
        rhos[k] = {"rho": float(r), "p": float(p)}

    # per-node ablation: zero dim i, recompute centroid on train
    base_floor = float(raw_auc["auc_floor"])
    ablations = []
    for i, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        Xz = X.copy()
        Xz[:, i] = 0.0
        sc_z, _ = fit_score_centroid_euclidean(Xz[tr_idx], Xz[te_idx])
        auc_z = _auc_with_bootstrap(sc_z, labels.tolist())
        # univariate: 1-d centroid distance on this node
        sc_u, _ = fit_score_centroid_euclidean(X[tr_idx][:, [i]], X[te_idx][:, [i]])
        auc_u = _auc_with_bootstrap(sc_u, labels.tolist())
        # raw dim as score
        auc_raw_dim = _auc_with_bootstrap(X[te_idx][:, i].tolist(), labels.tolist())
        drop = base_floor - float(auc_z["auc_floor"])
        ablations.append(
            {
                "node": cat,
                "dim": i,
                "auc_zeroed": float(auc_z["auc"]),
                "auc_floor_zeroed": float(auc_z["auc_floor"]),
                "delta_auc_floor": drop,
                "univariate_centroid_auc": float(auc_u["auc"]),
                "univariate_centroid_auc_floor": float(auc_u["auc_floor"]),
                "univariate_raw_dim_auc": float(auc_raw_dim["auc"]),
                "univariate_raw_dim_auc_floor": float(auc_raw_dim["auc_floor"]),
            }
        )
    ablations.sort(key=lambda r: -r["delta_auc_floor"])
    dominant = ablations[0]

    # residualise vs mapped-event count, OLS on train-benign only
    sc_tr, _ = fit_score_centroid_euclidean(X[tr_idx], X[tr_idx])
    mapped_tr = _covariates(tensors, train_b)["mapped_events"].tolist()
    mapped_te = cov["mapped_events"].tolist()
    reg, ols_meta = ols_fit(list(sc_tr), mapped_tr)
    resid = apply_residual(reg, sc.tolist(), mapped_te)
    resid_auc = _auc_with_bootstrap(resid, labels.tolist())

    # volume-stratified terciles on TEST mapped-event count
    mapped = cov["mapped_events"]
    qs = np.quantile(mapped, [1 / 3, 2 / 3])
    tercile_rows = []
    for t_i, (lo, hi, lab) in enumerate(
        [
            (-np.inf, qs[0], "T1_low"),
            (qs[0], qs[1], "T2_mid"),
            (qs[1], np.inf, "T3_high"),
        ]
    ):
        if t_i == 0:
            mask = mapped <= hi
        elif t_i == 2:
            mask = mapped > lo
        else:
            mask = (mapped > lo) & (mapped <= hi)
        y_t = labels[mask]
        s_t = sc[mask]
        n0, n1 = int((y_t == 0).sum()), int((y_t == 1).sum())
        if n0 == 0 or n1 == 0:
            auc_t = {
                "auc": float("nan"),
                "auc_floor": float("nan"),
                "ci95": [float("nan"), float("nan")],
                "ci95_floor": [float("nan"), float("nan")],
                "direction": "undefined",
            }
        else:
            auc_t = _auc_with_bootstrap(s_t.tolist(), y_t.tolist())
        tercile_rows.append(
            {
                "tercile": lab,
                "mapped_lo": float(mapped[mask].min()) if mask.any() else float("nan"),
                "mapped_hi": float(mapped[mask].max()) if mask.any() else float("nan"),
                "n": int(mask.sum()),
                "n_benign": n0,
                "n_malware": n1,
                "auc": auc_t["auc"],
                "auc_floor": auc_t["auc_floor"],
                "ci95": auc_t.get("ci95"),
                "ci95_floor": auc_t.get("ci95_floor"),
                "direction": auc_t.get("direction"),
            }
        )

    csv_path = out / "per_node_ablation.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "rank",
                "node",
                "dim",
                "auc_floor_zeroed",
                "delta_auc_floor",
                "univariate_centroid_auc_floor",
                "univariate_raw_dim_auc_floor",
            ]
        )
        for rank, r in enumerate(ablations, 1):
            w.writerow(
                [
                    rank,
                    r["node"],
                    r["dim"],
                    f"{r['auc_floor_zeroed']:.10f}",
                    f"{r['delta_auc_floor']:.10f}",
                    f"{r['univariate_centroid_auc_floor']:.10f}",
                    f"{r['univariate_raw_dim_auc_floor']:.10f}",
                ]
            )

    payload = {
        "d1_shape": list(X.shape),
        "nodes": list(GRAPH_CATEGORY_UNIVERSE),
        "raw_centroid": raw_auc,
        "spearman_vs_d1_centroid_eval": rhos,
        "per_node_ablation_ranked": ablations,
        "dominant_node": {
            "node": dominant["node"],
            "delta_auc_floor": dominant["delta_auc_floor"],
            "univariate_centroid_auc": dominant["univariate_centroid_auc"],
            "univariate_centroid_auc_floor": dominant["univariate_centroid_auc_floor"],
            "univariate_raw_dim_auc": dominant["univariate_raw_dim_auc"],
            "univariate_raw_dim_auc_floor": dominant["univariate_raw_dim_auc_floor"],
        },
        "residualisation_mapped_events_R2_train_benign": {
            "ols": ols_meta,
            "raw_auc": raw_auc,
            "residualised_auc": resid_auc,
        },
        "volume_stratified_terciles_test_mapped_events": {
            "cuts": [float(qs[0]), float(qs[1])],
            "terciles": tercile_rows,
        },
    }
    write_json(out / "check3.json", payload)
    return payload
