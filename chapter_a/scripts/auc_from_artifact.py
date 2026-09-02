"""Reload auc_floor from Chapter A artifact paths (shared by verify + reproduce)."""
from __future__ import annotations

from lib import ANDROCT, abs_artifact, load_json


def as_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def close6(a, b) -> bool:
    if a is None or b is None:
        return False
    return round(float(a), 6) == round(float(b), 6)


def extract_auc(row: dict) -> tuple[float | None, str]:
    """Return (auc_floor from artifact, mode). mode in {scores, catalog, missing, unparseable}."""
    path = row.get("artifact_path") or ""
    if not path:
        return None, "missing"
    p = abs_artifact(path)
    if not p.exists():
        return None, "missing"
    det = row["detector"]
    method = row["method"]
    if p.suffix == ".joblib":
        companion = ANDROCT / "devread" / "splitA" / "results_trained.json"
        if companion.exists() and det in {"HGB", "HGB_mean_seeds_42_46"}:
            d = load_json(companion)
            fs = row["representation"].split("_")[0]
            rec = d.get(fs, {}).get("HGB", {})
            if det == "HGB" and rec.get("per_seed"):
                return float(rec["per_seed"][0]["auc"]["auc_floor"]), "catalog"
            if det == "HGB_mean_seeds_42_46" and rec.get("per_seed"):
                vals = [float(s["auc"]["auc_floor"]) for s in rec["per_seed"]]
                return sum(vals) / len(vals), "catalog"
        return None, "unparseable"
    if p.suffix != ".json":
        return None, "unparseable"
    d = load_json(p)

    def from_auc_blob(blob):
        if isinstance(blob, dict) and "auc_floor" in blob:
            return float(blob["auc_floor"])
        if isinstance(blob, dict) and "auc" in blob and isinstance(blob["auc"], dict):
            return float(blob["auc"]["auc_floor"])
        return None

    if det == "mapped_event_count" and "mapped_event_count" in d:
        return from_auc_blob(d["mapped_event_count"]), "catalog"
    if row["method"] == "trivial_floor":
        rec = d.get(det) or next(
            (v for k, v in d.items() if isinstance(v, dict) and v.get("metric") == det),
            None,
        )
        if rec:
            return from_auc_blob(rec), "catalog"
    if det == "OCPool_mean_raw" and "R0" in d:
        return from_auc_blob(d["R0"]["auc"]), "catalog"
    if det == "OCPool_mean_R2" and "R2" in d:
        return from_auc_blob(d["R2"]["auc"]), "catalog"
    if det == "OCPool_mean_R1_ols_fit_eval" and "R1" in d:
        return from_auc_blob(d["R1"]["auc"]), "catalog"
    if det == "centroid_euclidean_nested_form":
        return float(d["partA_D1_centroid"]["full_sample_point"]), "catalog"
    if det == "S1_norm_nested_bootstrap_mean":
        return float(d["partB_T1K_S1_norm"]["bootstrap"]["mean"]), "catalog"
    if det == "S1_norm" and "S1_norm" in d:
        return from_auc_blob(d["S1_norm"]["auc"]), "catalog"
    if det == "HGB_pooled_oof_raw" and "pooled_oof_hgb_full" in d:
        return from_auc_blob(d["pooled_oof_hgb_full"]), "catalog"
    if det == "HGB_mean_auc_floor" and "aggregate" in d:
        h = d["aggregate"]["full"]["hist_gradient_boosting"]
        if "mean_auc_floor" in h:
            return float(h["mean_auc_floor"]), "catalog"
    if det == "HGB_weighted_mean_auc_floor" and "aggregate" in d:
        h = d["aggregate"]["full"]["hist_gradient_boosting"]
        if "weighted_mean_auc_floor" in h:
            return float(h["weighted_mean_auc_floor"]), "catalog"
    if det == "HGB_mean_raw_auc" and "folds" in d:
        vals = [
            float(f["modes"]["full"]["hist_gradient_boosting"]["auc"]["auc"])
            for f in d["folds"]
        ]
        return sum(vals) / len(vals), "catalog"
    if det == "HGB" and row["experiment"] == "ladder":
        return from_auc_blob(d["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]), "catalog"
    if det == "mahalanobis_weighted_mean_auc_floor":
        return float(d["weighted_mean_auc_floor"]), "catalog"
    if det == "mahalanobis_pooled_oof":
        return from_auc_blob(d["pooled_oof_raw"]), "catalog"
    if row["experiment"] == "final_validate" and det == "centroid_euclidean":
        return from_auc_blob(d["centroid_euclidean"]["pooled_oof_raw"]), "catalog"
    if row["experiment"] == "final_validate" and det == "mahalanobis":
        return from_auc_blob(d["mahalanobis"]["pooled_oof_raw"]), "catalog"
    if "families" in d:
        fam = {
            "gae_recon": "GAE_reconstruction",
            "gae_embedding_centroid_mean": "GAE_embedding_distance",
            "OCGIN_plus": "OCGIN",
            "s_graph_full": "GLocalKD",
            "ocgtl_K4": "OCGTL",
        }.get(det)
        if fam and fam in d["families"]:
            rec = d["families"][fam]
            key = "trained_mean" if method == "trained" else "random_init_mean"
            if key in rec:
                return float(rec[key]), "catalog"
            key2 = "trained" if method == "trained" else "random_init"
            if key2 in rec:
                return float(rec[key2]), "catalog"
    if "by_encoder" in d and det == "gae_embedding_centroid_mean":
        enc = "trained_run5" if method == "trained" else "random_init"
        return float(
            d["by_encoder"][enc]["reps"]["mean"]["scorers"]["centroid_euclidean"][
                "auc_floor"
            ]
        ), "catalog"
    if det == "WL_h3_ocsvm_precomputed" and isinstance(d, (list, dict)):
        rows = d if isinstance(d, list) else d.get("rows", [])
        best = None
        for r in rows:
            if (
                r.get("method") == "WL_h3"
                and r.get("kind") == "T1K"
                and r.get("detector") == "ocsvm_precomputed"
            ):
                if best is None or float(r["auc_floor"]) > float(best["auc_floor"]):
                    best = r
        if best:
            return float(best["auc_floor"]), "catalog"
    if det == "WL_structure_only_features_constant":
        return float(d["features_constant_auc_floor"]), "catalog"
    if det == "WL_edges_removed":
        return float(d["edges_removed_auc_floor"]), "catalog"
    if det.startswith("GIN_"):
        rep, pool = (
            row["representation"].rsplit("_", 1)
            if "_" in row["representation"]
            else (row["representation"], "")
        )
        node = d.get(rep, {}).get(pool, {}).get(row["method"], {})
        if det == "GIN_mean_seeds" and node.get("per_seed"):
            vals = [float(s["auc"]["auc_floor"]) for s in node["per_seed"]]
            return sum(vals) / len(vals), "catalog"
        if det == "GIN_weighted_mean_auc_floor":
            v = node.get("weighted_mean_auc_floor") or node.get("weighted_mean")
            if v is not None:
                return float(v), "catalog"
        if det == "GIN_pooled_oof":
            po = node.get("pooled_oof_auc") or node.get("pooled_oof") or node.get("pooled_oof_raw")
            if isinstance(po, dict):
                return float(po.get("auc_floor", po.get("auc"))), "catalog"
            if po is not None:
                return float(po), "catalog"
    if det in {"HGB_mean_seeds_42_46", "HGB"} and row["experiment"] == "devread":
        rep = row["representation"]
        fs = (
            rep[: -len("_trained_t22")]
            if rep.endswith("_trained_t22")
            else rep.split("_")[0]
        )
        rec = d.get(fs, {}).get("HGB", {})
        if rec.get("per_seed"):
            if det == "HGB":
                return float(rec["per_seed"][0]["auc"]["auc_floor"]), "catalog"
            vals = [float(s["auc"]["auc_floor"]) for s in rec["per_seed"]]
            return sum(vals) / len(vals), "catalog"
    if det == "centroid_euclidean_pooled_oof":
        fs = row["representation"].split("_")[0]
        rec = d.get("splitB", {}).get("trained", {}).get(fs, {})
        if rec.get("pooled_oof_auc"):
            return from_auc_blob(rec["pooled_oof_auc"]), "catalog"
    got = from_auc_blob(d)
    if got is not None:
        return got, "catalog"
    if "auc" in d and isinstance(d["auc"], dict):
        return from_auc_blob(d["auc"]), "catalog"
    return None, "unparseable"


def verify_master_rows(rows: list[dict]) -> dict:
    verified, failed, untraceable = [], [], []
    for i, r in enumerate(rows):
        art_auc, mode = extract_auc(r)
        master_auc = as_float(r["auc_floor"])
        if r["detector"] == "HGB_mean_raw_auc":
            master_auc = as_float(r["raw_auc"])
        rec = {
            "i": i,
            "experiment": r["experiment"],
            "detector": r["detector"],
            "method": r["method"],
            "split": r["split"],
            "master_auc_floor": master_auc,
            "artifact_auc_floor": art_auc,
            "mode": mode,
            "artifact_path": r["artifact_path"],
            "trace_flag": r.get("trace_flag", ""),
        }
        if r.get("trace_flag") or mode == "missing":
            untraceable.append(rec)
            continue
        if art_auc is None or not close6(master_auc, art_auc):
            rec["error"] = (
                f"mismatch or unparseable mode={mode} master={master_auc} artifact={art_auc}"
            )
            failed.append(rec)
            continue
        verified.append(rec)
    return {"verified": verified, "failed": failed, "untraceable": untraceable}
