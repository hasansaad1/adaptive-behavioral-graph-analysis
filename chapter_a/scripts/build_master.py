"""Stage 2 — promote/extend final_validation MASTER_RESULTS.csv from saved artifacts only."""
from __future__ import annotations

import csv
from pathlib import Path

from lib import (
    ANDROCT,
    CHAPTER_A,
    FV,
    abs_artifact,
    auc_fields,
    load_json,
    load_ocpool_raw,
    load_size_floor,
    map_ci_type,
    rel_to_repo,
    summary_for,
    write_csv,
)

FIELDS = [
    "experiment",
    "module",
    "representation",
    "method",
    "detector",
    "split",
    "seed",
    "raw_auc",
    "auc_floor",
    "direction",
    "ci_low",
    "ci_high",
    "ci_type",
    "clears_size_floor",
    "clears_ocpool",
    "is_headline",
    "is_superseded",
    "artifact_path",
    "summary_path",
    "trace_flag",
]


def _bool(v) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"true", "1", "yes"}


def _gates(floor, size_floor, ocpool):
    try:
        f = float(floor)
        return f > size_floor, f > ocpool
    except (TypeError, ValueError):
        return False, False


def _row(**kw):
    out = {k: kw.get(k, "") for k in FIELDS}
    art = kw.get("artifact_path", "")
    p = abs_artifact(art) if art else None
    if not art:
        out["trace_flag"] = "NO_ARTIFACT"
    elif p is None or not p.exists():
        out["trace_flag"] = "MISSING_ARTIFACT"
        out["artifact_path"] = rel_to_repo(p) if p else art
    else:
        out["trace_flag"] = ""
        out["artifact_path"] = rel_to_repo(p)
    if out.get("summary_path"):
        sp = abs_artifact(out["summary_path"])
        out["summary_path"] = rel_to_repo(sp) if sp.exists() else out["summary_path"]
    cs, co = _gates(out.get("auc_floor"), kw.get("_size", 0), kw.get("_ocpool", 0))
    if "clears_size_floor" not in kw or kw.get("clears_size_floor") in ("", None):
        out["clears_size_floor"] = cs
    if "clears_ocpool" not in kw or kw.get("clears_ocpool") in ("", None):
        out["clears_ocpool"] = co
    out["ci_type"] = map_ci_type(out.get("ci_type"))
    out["is_headline"] = bool(kw.get("is_headline", False))
    out["is_superseded"] = bool(kw.get("is_superseded", False))
    return out


def _from_existing(size_floor, ocpool) -> list[dict]:
    src = FV / "MASTER_RESULTS.csv"
    rows = []
    with src.open() as f:
        for r in csv.DictReader(f):
            exp = r["experiment"]
            det = r["detector"]
            # headline / superseded policy (final defensible set)
            headline = False
            superseded = False
            if det == "centroid_euclidean_nested_form":
                headline = True
            elif det == "centroid_euclidean" and exp == "ocdev":
                headline = False  # same point as nested; nested CI is the carried interval
            elif det == "OCPool_mean_raw":
                headline = True
            elif det == "OCPool_mean_R2":
                headline = True
            elif det == "S1_norm":
                superseded = True
            elif det == "S1_norm_nested_bootstrap_mean":
                headline = True
            elif det == "HGB" and exp == "devread":
                headline = True  # seed-42 ROC / operating-point artifact
            elif det == "HGB_mean_seeds_42_46":
                headline = True
            elif det == "HGB" and exp == "ladder":
                headline = True
            elif det == "mapped_event_count":
                headline = True
            elif det == "HGB_mean_auc_floor" and "random" not in r["method"]:
                superseded = True
            elif det == "HGB_weighted_mean_auc_floor":
                superseded = True
            elif det == "HGB_pooled_oof_raw":
                headline = True
            elif det == "HGB_mean_raw_auc":
                headline = False
            elif det == "HGB_mean_auc_floor" and "random" in r["method"]:
                headline = True
            elif exp == "final_validate" and det == "centroid_euclidean":
                headline = True
            elif exp == "final_validate" and det == "mahalanobis":
                headline = False

            art = r.get("artifact_path", "")
            summ = summary_for(ANDROCT / exp) if (ANDROCT / exp).is_dir() else None
            if exp == "ocdev_validate":
                summ = ANDROCT / "ocdev" / "validation" / "SUMMARY.md"
            elif exp == "final_validate":
                summ = FV / "SUMMARY.md"
            elif exp == "validation":
                summ = ANDROCT / "validation" / "SUMMARY.md"
            elif exp == "run3":
                summ = ANDROCT / "run3" / "SUMMARY.md"
            elif exp == "ladder":
                summ = ANDROCT / "ladder" / "SUMMARY.md"
            elif exp == "devread":
                summ = ANDROCT / "devread" / "SUMMARY.md"
            elif exp == "ocdev":
                summ = ANDROCT / "ocdev" / "SUMMARY.md"

            ci_type = map_ci_type(r.get("ci_type"))
            if det == "HGB_mean_auc_floor":
                ci_type = "per_fold_std" if "random" not in r["method"] else "per_fold_std"
            if det == "HGB_mean_seeds_42_46":
                ci_type = "none"
            if det == "HGB_weighted_mean_auc_floor":
                ci_type = "none"
            if det == "HGB_mean_raw_auc":
                ci_type = "per_fold_std"

            rows.append(
                _row(
                    experiment=exp,
                    module=r["module"],
                    representation=r["representation"],
                    method=r["method"],
                    detector=det,
                    split=r["split"],
                    seed=r["seed"],
                    raw_auc=r["raw_auc"],
                    auc_floor=r["auc_floor"],
                    direction=r["direction"],
                    ci_low=r.get("ci_low", ""),
                    ci_high=r.get("ci_high", ""),
                    ci_type=ci_type,
                    clears_size_floor=_bool(r.get("clears_size_floor")),
                    clears_ocpool=_bool(r.get("clears_ocpool")),
                    is_headline=headline,
                    is_superseded=superseded,
                    artifact_path=art,
                    summary_path=str(summ) if summ else "",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )
    return rows


def _append_check1_r1(rows, size_floor, ocpool):
    p = ANDROCT / "validation" / "check1_residualization" / "check1_summary.json"
    d = load_json(p)
    r1 = d["R1"]["auc"]
    rows.append(
        _row(
            experiment="validation",
            module="validate",
            representation="T1K_B_docfreq_K1000_pool_mean",
            method="benign_only",
            detector="OCPool_mean_R1_ols_fit_eval",
            split="splitA_GAE",
            seed="42",
            raw_auc=r1["auc"],
            auc_floor=r1["auc_floor"],
            direction=r1["direction"],
            ci_low=r1["ci95_floor"][0],
            ci_high=r1["ci95_floor"][1],
            ci_type="score_bootstrap",
            is_headline=False,
            is_superseded=True,
            artifact_path=p,
            summary_path=ANDROCT / "validation" / "SUMMARY.md",
            _size=size_floor,
            _ocpool=ocpool,
        )
    )


def _append_splitb_d4(rows, size_floor, ocpool):
    p = ANDROCT / "ocdev" / "validation" / "check3_splitB" / "check3.json"
    d = load_json(p)
    rows.append(
        _row(
            experiment="ocdev_validate",
            module="ocdev_validate",
            representation="D4_trained_t22",
            method="benign_only_group_holdout",
            detector="mahalanobis_weighted_mean_auc_floor",
            split="splitB_ward30",
            seed="42",
            raw_auc=d["weighted_mean_auc_floor"],
            auc_floor=d["weighted_mean_auc_floor"],
            direction="see_per_fold",
            ci_type="none",
            is_headline=False,
            is_superseded=True,
            artifact_path=p,
            summary_path=ANDROCT / "ocdev" / "validation" / "SUMMARY.md",
            _size=size_floor,
            _ocpool=ocpool,
        )
    )
    po = d["pooled_oof_raw"]
    rows.append(
        _row(
            experiment="ocdev_validate",
            module="ocdev_validate",
            representation="D4_trained_t22",
            method="benign_only_group_holdout",
            detector="mahalanobis_pooled_oof",
            split="splitB_ward30",
            seed="42",
            raw_auc=po["auc"],
            auc_floor=po["auc_floor"],
            direction=po["direction"],
            ci_low=po["ci95_floor"][0],
            ci_high=po["ci95_floor"][1],
            ci_type="score_bootstrap",
            is_headline=False,
            is_superseded=False,
            artifact_path=p,
            summary_path=ANDROCT / "ocdev" / "validation" / "SUMMARY.md",
            _size=size_floor,
            _ocpool=ocpool,
        )
    )


def _append_families(rows, size_floor, ocpool):
    p = ANDROCT / "ocdev" / "validation" / "check2_randominit" / "check2.json"
    d = load_json(p)["families"]
    fam_map = {
        "GAE_reconstruction": ("invgraph", "invgraph", "V2_invocation", "gae_recon"),
        "GAE_embedding_distance": ("run8", "androct", "T22_gae_h8", "gae_embedding_centroid_mean"),
        "OCGIN": ("ocgin", "ocgin", "T22", "OCGIN_plus"),
        "GLocalKD": ("glocalkd", "glocalkd", "T22_pool_mean", "s_graph_full"),
        "OCGTL": ("ocgtl", "ocgtl", "T1K", "ocgtl_K4"),
    }
    for fam, meta in fam_map.items():
        exp, mod, rep, det = meta
        rec = d[fam]
        src = rec.get("source", p)
        # trained
        if "trained_mean" in rec:
            t, u = rec["trained_mean"], rec["random_init_mean"]
            tstd = rec.get("trained_std", "")
            rows.append(
                _row(
                    experiment=exp,
                    module=mod,
                    representation=rep,
                    method="trained",
                    detector=det,
                    split="splitA_GAE",
                    seed="42-46",
                    raw_auc=t,
                    auc_floor=t,
                    direction="malware_higher_score",
                    ci_type="per_fold_std" if tstd != "" else "none",
                    is_headline=False,
                    artifact_path=p if not str(src).endswith(".md") else p,
                    summary_path=summary_for(ANDROCT / exp) or "",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )
            rows.append(
                _row(
                    experiment=exp,
                    module=mod,
                    representation=rep,
                    method="untrained",
                    detector=det,
                    split="splitA_GAE",
                    seed="42-46",
                    raw_auc=u,
                    auc_floor=u,
                    direction="malware_higher_score",
                    ci_type="per_fold_std",
                    is_headline=False,
                    artifact_path=p,
                    summary_path=summary_for(ANDROCT / exp) or "",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )
        else:
            t, u = rec["trained"], rec["random_init"]
            # prefer run8 comparison.json for 6dp
            if fam == "GAE_embedding_distance":
                c8 = load_json(ANDROCT / "run8" / "comparison.json")
                t = c8["by_encoder"]["trained_run5"]["reps"]["mean"]["scorers"]["centroid_euclidean"]["auc_floor"]
                u = c8["by_encoder"]["random_init"]["reps"]["mean"]["scorers"]["centroid_euclidean"]["auc_floor"]
                src = ANDROCT / "run8" / "comparison.json"
            rows.append(
                _row(
                    experiment=exp,
                    module=mod,
                    representation=rep,
                    method="trained",
                    detector=det,
                    split="splitA_GAE",
                    seed="42",
                    raw_auc=t,
                    auc_floor=t,
                    direction="malware_higher_score",
                    ci_type="none",
                    is_headline=False,
                    artifact_path=src,
                    summary_path=summary_for(ANDROCT / exp) or "",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )
            rows.append(
                _row(
                    experiment=exp,
                    module=mod,
                    representation=rep,
                    method="untrained",
                    detector=det,
                    split="splitA_GAE",
                    seed="42",
                    raw_auc=u,
                    auc_floor=u,
                    direction="malware_higher_score",
                    ci_type="none",
                    is_headline=False,
                    artifact_path=src,
                    summary_path=summary_for(ANDROCT / exp) or "",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )


def _append_kernels(rows, size_floor, ocpool):
    grid = load_json(ANDROCT / "kernels" / "detectors" / "grid_rows.json")
    if isinstance(grid, dict):
        grid = grid.get("rows", grid)
    best = None
    for r in grid:
        if r.get("method") == "WL_h3" and r.get("kind") == "T1K" and r.get("detector") == "ocsvm_precomputed":
            if best is None or float(r["auc_floor"]) > float(best["auc_floor"]):
                best = r
    if best:
        rows.append(
            _row(
                experiment="kernels",
                module="kernels",
                representation="T1K",
                method="graph_kernel",
                detector="WL_h3_ocsvm_precomputed",
                split="splitA_GAE",
                seed="42",
                raw_auc=best["auc"],
                auc_floor=best["auc_floor"],
                direction=best["direction"],
                ci_type="none",
                is_headline=False,
                artifact_path=ANDROCT / "kernels" / "detectors" / "grid_rows.json",
                summary_path=ANDROCT / "kernels" / "SUMMARY.md",
                _size=size_floor,
                _ocpool=ocpool,
            )
        )
    ab = load_json(ANDROCT / "kernels" / "ablation" / "winner_ablation.json")
    for det, key in (
        ("WL_structure_only_features_constant", "features_constant_auc_floor"),
        ("WL_edges_removed", "edges_removed_auc_floor"),
    ):
        rows.append(
            _row(
                experiment="kernels",
                module="kernels",
                representation="T1K",
                method="graph_kernel_ablation",
                detector=det,
                split="splitA_GAE",
                seed="42",
                raw_auc=ab[key],
                auc_floor=ab[key],
                direction="malware_higher_score" if float(ab[key]) >= 0.5 else "benign_higher_score",
                ci_type="none",
                is_headline=False,
                artifact_path=ANDROCT / "kernels" / "ablation" / "winner_ablation.json",
                summary_path=ANDROCT / "kernels" / "SUMMARY.md",
                _size=size_floor,
                _ocpool=ocpool,
            )
        )


def _append_floors(rows, size_floor, ocpool):
    specs = [
        ("run3", "androct", "T22", ANDROCT / "run3" / "floors.json"),
        ("apigraph", "apigraph", "API_1000", ANDROCT / "apigraph" / "floors" / "K1000_floors.json"),
        ("invgraph", "invgraph", "invocation_V2", ANDROCT / "invgraph" / "floors" / "V2_invocation_floors.json"),
    ]
    want = {"mapped_event_count", "total_event_count", "active_nodes", "edge_count", "graph_density", "in_vocab_event_count", "in_vocab_events", "distinct_active_categories"}
    for exp, mod, rep, path in specs:
        d = load_json(path)
        for k, rec in d.items():
            if not isinstance(rec, dict) or "auc_floor" not in rec:
                continue
            metric = rec.get("metric", k)
            if metric not in want and k not in want:
                continue
            f = auc_fields(rec)
            rows.append(
                _row(
                    experiment=exp,
                    module=mod,
                    representation=rep,
                    method="trivial_floor",
                    detector=metric,
                    split="splitA_GAE",
                    seed="42",
                    **f,
                    is_headline=False,
                    is_superseded=False,
                    artifact_path=path,
                    summary_path=summary_for(ANDROCT / exp) or "",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )


def _walk_detectors(node: dict):
    """Yield (detector_name, blob) for leaves that contain an auc dict."""
    if not isinstance(node, dict):
        return
    if "auc" in node and isinstance(node["auc"], dict) and "auc_floor" in node["auc"]:
        yield None, node
        return
    for k, v in node.items():
        if isinstance(v, dict):
            if "auc" in v and isinstance(v["auc"], dict) and "auc_floor" in v["auc"]:
                yield k, v
            else:
                yield from _walk_detectors(v)


def _append_ocdev_dsets(rows, size_floor, ocpool):
    p = ANDROCT / "ocdev" / "partA_profiles" / "partA_summary.json"
    d = load_json(p)
    for split_name, split_blob in (("splitA", d["splitA"]), ("splitB", d["splitB"])):
        trained = split_blob.get("trained", {})
        for fs, reds in trained.items():
            if not isinstance(reds, dict):
                continue
            art_path = p
            f = None
            if split_name == "splitA":
                none = reds.get("none") or reds
                blob = none.get("centroid_euclidean") if isinstance(none, dict) else None
                if blob is None:
                    continue
                f = auc_fields(blob)
                cand = (
                    ANDROCT
                    / "ocdev"
                    / "partA_profiles"
                    / "splitA_trained"
                    / f"trained__{fs}__none__centroid_euclidean__splitA__foldNA.json"
                )
                if cand.exists():
                    art_path = cand
            else:
                po = reds.get("pooled_oof_auc")
                if not isinstance(po, dict):
                    continue
                f = auc_fields({"auc": po} if "auc_floor" in po else po)
            if f is None or f["auc_floor"] in ("", None):
                continue
            rows.append(
                _row(
                    experiment="ocdev",
                    module="ocdev",
                    representation=f"{fs}_trained_t22",
                    method="benign_only",
                    detector="centroid_euclidean" if split_name == "splitA" else "centroid_euclidean_pooled_oof",
                    split="splitA_GAE" if split_name == "splitA" else "splitB_ward30",
                    seed="42",
                    **f,
                    is_headline=False,
                    artifact_path=art_path,
                    summary_path=ANDROCT / "ocdev" / "SUMMARY.md",
                    _size=size_floor,
                    _ocpool=ocpool,
                )
            )
    # raw-input control
    raw = ANDROCT / "ocdev" / "controls" / "raw_tensor" / "raw__RAW_full__none__centroid_euclidean__splitA__foldNA.json"
    if raw.exists():
        rec = load_json(raw)
        f = auc_fields(rec)
        rows.append(
            _row(
                experiment="ocdev",
                module="ocdev",
                representation="RAW_full",
                method="raw_input_control",
                detector="centroid_euclidean",
                split="splitA_GAE",
                seed="42",
                **f,
                is_headline=False,
                artifact_path=raw,
                summary_path=ANDROCT / "ocdev" / "SUMMARY.md",
                _size=size_floor,
                _ocpool=ocpool,
            )
        )


def _mean_floor(per_seed: list) -> tuple[float, float]:
    floors = []
    for s in per_seed:
        a = s.get("auc", s)
        floors.append(float(a["auc_floor"] if isinstance(a, dict) else a))
    n = len(floors)
    mean = sum(floors) / n
    var = sum((x - mean) ** 2 for x in floors) / n
    return mean, var ** 0.5


def _append_devread(rows, size_floor, ocpool):
    for split, fname in (("splitA", "results_trained.json"), ("splitB", "results_trained.json")):
        p = ANDROCT / "devread" / split / fname
        if not p.exists():
            continue
        d = load_json(p)
        for fs, dets in d.items():
            if not isinstance(dets, dict):
                continue
            if "HGB" not in dets:
                continue
            rec = dets["HGB"]
            if "per_seed" in rec:
                mean, std = _mean_floor(rec["per_seed"])
                seed0 = rec["per_seed"][0]
                a0 = seed0["auc"]
                # seed 42 row
                rows.append(
                    _row(
                        experiment="devread",
                        module="devread",
                        representation=f"{fs}_trained_t22",
                        method="supervised",
                        detector="HGB",
                        split="splitA_stratified" if split == "splitA" else "splitB_ward30",
                        seed=str(seed0.get("seed", 42)),
                        raw_auc=a0["auc"],
                        auc_floor=a0["auc_floor"],
                        direction=a0["direction"],
                        ci_low=a0.get("ci95_floor", ["", ""])[0],
                        ci_high=a0.get("ci95_floor", ["", ""])[1],
                        ci_type="score_bootstrap",
                        is_headline=False,
                        artifact_path=p,
                        summary_path=ANDROCT / "devread" / "SUMMARY.md",
                        _size=size_floor,
                        _ocpool=ocpool,
                    )
                )
                rows.append(
                    _row(
                        experiment="devread",
                        module="devread",
                        representation=f"{fs}_trained_t22",
                        method="supervised",
                        detector="HGB_mean_seeds_42_46",
                        split="splitA_stratified" if split == "splitA" else "splitB_ward30",
                        seed="42-46",
                        raw_auc=mean,
                        auc_floor=mean,
                        direction="malware_higher_score",
                        ci_type="per_fold_std",
                        is_headline=False,
                        artifact_path=p,
                        summary_path=ANDROCT / "devread" / "SUMMARY.md",
                        _size=size_floor,
                        _ocpool=ocpool,
                    )
                )


def _append_supgnn(rows, size_floor, ocpool):
    sa = load_json(ANDROCT / "supgnn" / "splitA" / "splitA_results.json")
    for rep, pools in sa.items():
        if not isinstance(pools, dict):
            continue
        for pool, modes in pools.items():
            if not isinstance(modes, dict):
                continue
            for mode, rec in modes.items():
                if not isinstance(rec, dict) or "per_seed" not in rec:
                    continue
                mean, std = _mean_floor(rec["per_seed"])
                rows.append(
                    _row(
                        experiment="supgnn",
                        module="supgnn",
                        representation=f"{rep}_{pool}",
                        method=mode,
                        detector="GIN_mean_seeds",
                        split="splitA_stratified",
                        seed="42-46",
                        raw_auc=mean,
                        auc_floor=mean,
                        direction="malware_higher_score",
                        ci_type="per_fold_std",
                        is_headline=False,
                        artifact_path=ANDROCT / "supgnn" / "splitA" / "splitA_results.json",
                        summary_path=ANDROCT / "supgnn" / "SUMMARY.md",
                        _size=size_floor,
                        _ocpool=ocpool,
                    )
                )
    sb = ANDROCT / "supgnn" / "splitB"
    # splitB_results.json if present
    for cand in sb.glob("*results*.json"):
        d = load_json(cand)
        for rep, pools in d.items() if isinstance(d, dict) else []:
            if not isinstance(pools, dict):
                continue
            for pool, modes in pools.items():
                if not isinstance(modes, dict):
                    continue
                for mode, rec in modes.items():
                    if not isinstance(rec, dict):
                        continue
                    wm = rec.get("weighted_mean_auc_floor") or rec.get("weighted_mean")
                    po = rec.get("pooled_oof_auc") or rec.get("pooled_oof") or rec.get("pooled_oof_raw")
                    if isinstance(po, dict):
                        po = po.get("auc_floor", po.get("auc"))
                    if wm is not None:
                        rows.append(
                            _row(
                                experiment="supgnn",
                                module="supgnn",
                                representation=f"{rep}_{pool}",
                                method=mode,
                                detector="GIN_weighted_mean_auc_floor",
                                split="splitB_ward30",
                                seed="42",
                                raw_auc=wm,
                                auc_floor=wm,
                                direction="see_per_fold",
                                ci_type="per_fold_std",
                                is_headline=False,
                                artifact_path=cand,
                                summary_path=ANDROCT / "supgnn" / "SUMMARY.md",
                                _size=size_floor,
                                _ocpool=ocpool,
                            )
                        )
                    if po is not None:
                        rows.append(
                            _row(
                                experiment="supgnn",
                                module="supgnn",
                                representation=f"{rep}_{pool}",
                                method=mode,
                                detector="GIN_pooled_oof",
                                split="splitB_ward30",
                                seed="42",
                                raw_auc=po,
                                auc_floor=po,
                                direction="malware_higher_score",
                                ci_type="none",
                                is_headline=False,
                                artifact_path=cand,
                                summary_path=ANDROCT / "supgnn" / "SUMMARY.md",
                                _size=size_floor,
                                _ocpool=ocpool,
                            )
                        )


def _dedupe(rows: list[dict]) -> list[dict]:
    seen = {}
    out = []
    for r in rows:
        key = (
            r["experiment"],
            r["representation"],
            r["method"],
            r["detector"],
            r["split"],
            str(r["seed"]),
        )
        if key in seen:
            # keep first (existing MASTER takes priority)
            continue
        seen[key] = True
        out.append(r)
    return out


def build_master() -> list[dict]:
    size_floor = load_size_floor()
    ocpool = load_ocpool_raw()
    rows = _from_existing(size_floor, ocpool)
    _append_check1_r1(rows, size_floor, ocpool)
    _append_splitb_d4(rows, size_floor, ocpool)
    _append_families(rows, size_floor, ocpool)
    _append_kernels(rows, size_floor, ocpool)
    _append_floors(rows, size_floor, ocpool)
    _append_ocdev_dsets(rows, size_floor, ocpool)
    _append_devread(rows, size_floor, ocpool)
    _append_supgnn(rows, size_floor, ocpool)
    rows = _dedupe(rows)
    write_csv(CHAPTER_A / "MASTER_RESULTS.csv", rows, FIELDS)
    just = CHAPTER_A / "HEADLINE_JUSTIFICATION.txt"
    lines = [
        "is_headline=True rows and justification (no new numbers):",
        "",
        "1. ocdev_validate / centroid_euclidean_nested_form — D1 full-sample point 0.80042553 with nested percentile CI; thesis-carried interval.",
        "2. validation / OCPool_mean_raw — pooling incumbent; not residualized; operating-point curve.",
        "3. validation / OCPool_mean_R2 — train-fit residual correction replacing eval-fit 0.8141.",
        "4. ocdev_validate / S1_norm_nested_bootstrap_mean — replaces full-sample point 0.8226.",
        "5. devread / D3 HGB seed 42 — ROC and TPR@FPR artifact (do not conflate with seed-mean).",
        "6. devread / D3 HGB_mean_seeds_42_46 — reported seed-mean AUC.",
        "7. ladder / HGB rung1 full — supervised random-split ceiling.",
        "8. run3 / mapped_event_count — size floor used as the trivial bar.",
        "9. ladder / HGB_pooled_oof_raw — rung-2 generalization number; replaces per-fold floor mean 0.8492.",
        "10. ladder / random-group HGB_mean_auc_floor — matched-size control.",
        "11. final_validate / D1 centroid benign-group holdout pooled OOF — one-class holdout check.",
        "",
        "is_superseded=True:",
        "- S1_norm point 0.8226 → nested bootstrap mean 0.7867",
        "- HGB_mean_auc_floor 0.8492 → pooled OOF 0.848861",
        "- HGB_weighted_mean_auc_floor 0.8606 (not the carried generalization number)",
        "- OCPool R1 eval-fit 0.8141 → R2 0.7544",
        "- D4 mahalanobis Split-B weighted 0.8083 → pooled OOF 0.5178",
    ]
    just.write_text("\n".join(lines) + "\n")
    return rows


if __name__ == "__main__":
    rows = build_master()
    n_h = sum(1 for r in rows if r["is_headline"] in (True, "True"))
    n_s = sum(1 for r in rows if r["is_superseded"] in (True, "True"))
    n_m = sum(1 for r in rows if r["trace_flag"])
    print(f"MASTER n={len(rows)} headline={n_h} superseded={n_s} flags={n_m}")
