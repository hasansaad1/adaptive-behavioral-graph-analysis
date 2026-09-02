"""Stage 3 — thesis tables from MASTER_RESULTS.csv and saved artifacts. No hardcoded numbers."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from lib import ANDROCT, CHAPTER_A, booktabs_table, fmt_num, load_json, load_size_floor, load_ocpool_raw

TABLES = CHAPTER_A / "tables"
MASTER = CHAPTER_A / "MASTER_RESULTS.csv"


def read_master() -> list[dict]:
    with MASTER.open() as f:
        return list(csv.DictReader(f))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _tf(v) -> bool:
    return str(v).strip() in {"True", "true", "1"}


def write_pair(stem: str, columns: list[str], rows: list[list], caption: str, label: str, csv_rows: list[dict], csv_fields: list[str]):
    TABLES.mkdir(parents=True, exist_ok=True)
    with (TABLES / f"{stem}.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields)
        w.writeheader()
        for r in csv_rows:
            w.writerow(r)
    booktabs_table(TABLES / f"{stem}.tex", columns, rows, caption, label)


def t1_corpus():
    """AndroCT 2017 population inventory (post-_CALL_RE), not the graph-eligible split cache.

    Reads:
      datasets/androct_2017/inventory/inventory_summary.json  (scored_at_utc in file)
      abrg/output/androct_2017/run2/corpus_cache/meta.json     (eligible + split counts only)
      abrg/output/androct_2017/run2/FINAL_POPULATION_STATS.json
      abrg/output/androct_2017/run2/POSTMORTEM.json            (eligibility attrition)
    """
    from lib import REPO

    inv_path = REPO / "datasets" / "androct_2017" / "inventory" / "inventory_summary.json"
    inv = load_json(inv_path)
    meta = load_json(ANDROCT / "run2" / "corpus_cache" / "meta.json")
    final_pop = load_json(ANDROCT / "run2" / "FINAL_POPULATION_STATS.json")
    elig = load_json(ANDROCT / "run2" / "POSTMORTEM.json")["eligibility"]

    fields = [
        "stage",
        "class",
        "n_files",
        "n_header_only",
        "n_effective",
        "n_events",
        "n_mapped",
        "mapped_rate",
        "categories_firing",
        "median_trace_length",
        "median_active_categories",
        "artifact_path",
        "artifact_scored_at_utc",
    ]
    csv_rows = []
    tex_rows = []
    art_rel = "datasets/androct_2017/inventory/inventory_summary.json"
    scored = inv.get("scored_at_utc", "")

    # Population = post-_CALL_RE parse inventory (pre-graph, pre-eligibility).
    pop_classes = []
    for lab in ("benign", "malware"):
        c = inv["classes"][lab]
        rec = {
            "stage": "population",
            "class": lab,
            "n_files": c["n_files"],
            "n_header_only": c["n_header_only"],
            "n_effective": c["n_effective"],
            "n_events": c["total_events"],
            "n_mapped": c["total_mapped_events"],
            "mapped_rate": c["mapped_event_rate"],
            "categories_firing": c["n_universe_cats_active"],
            "median_trace_length": c["dist_n_events"]["p50"],
            "median_active_categories": c["dist_n_active_cats"]["p50"],
            "artifact_path": art_rel,
            "artifact_scored_at_utc": scored,
        }
        pop_classes.append(rec)
        csv_rows.append(rec)
    all_rec = {
        "stage": "population",
        "class": "all",
        "n_files": sum(r["n_files"] for r in pop_classes),
        "n_header_only": sum(r["n_header_only"] for r in pop_classes),
        "n_effective": sum(r["n_effective"] for r in pop_classes),
        "n_events": sum(r["n_events"] for r in pop_classes),
        "n_mapped": sum(r["n_mapped"] for r in pop_classes),
        "mapped_rate": "",
        "categories_firing": "",
        "median_trace_length": "",
        "median_active_categories": "",
        "artifact_path": art_rel,
        "artifact_scored_at_utc": scored,
    }
    tot_e, tot_m = all_rec["n_events"], all_rec["n_mapped"]
    all_rec["mapped_rate"] = tot_m / tot_e if tot_e else ""
    csv_rows.insert(0, all_rec)

    # Fetch / final experiment population (pre-eligibility).
    # Pre-dedupe benign = hex_vt0 + pkg = 592 + 172 = 764.
    pre_dedupe_b = int(final_pop["n_hex_clean_vt0"]) + int(final_pop["n_pkg_resolved"])
    fetch_b = elig["fetch_by_label"]["benign"]
    fetch_m = elig["fetch_by_label"]["malware"]
    pm_utc = load_json(ANDROCT / "run2" / "POSTMORTEM.json").get("utc", "")
    for lab, n_files, n_eff in (
        ("benign", pre_dedupe_b, fetch_b),
        ("malware", fetch_m, fetch_m),
        ("all", pre_dedupe_b + fetch_m, fetch_b + fetch_m),
    ):
        csv_rows.append(
            {
                "stage": "fetch",
                "class": lab,
                "n_files": n_files,
                "n_header_only": "",
                "n_effective": n_eff,
                "n_events": "",
                "n_mapped": "",
                "mapped_rate": "",
                "categories_firing": "",
                "median_trace_length": "",
                "median_active_categories": "",
                "artifact_path": "abrg/output/androct_2017/run2/POSTMORTEM.json#eligibility",
                "artifact_scored_at_utc": pm_utc,
            }
        )

    # Graph-eligible (corpus_cache), not population.
    for lab in ("benign", "malware", "all"):
        if lab == "all":
            n = elig["eligible"]["n"]
        else:
            n = elig["eligible"]["by_label"][lab]
        csv_rows.append(
            {
                "stage": "graph_eligible",
                "class": lab,
                "n_files": "",
                "n_header_only": "",
                "n_effective": n,
                "n_events": "",
                "n_mapped": "",
                "mapped_rate": "",
                "categories_firing": "",
                "median_trace_length": "",
                "median_active_categories": "",
                "artifact_path": "abrg/output/androct_2017/run2/corpus_cache/meta.json",
                "artifact_scored_at_utc": "",
            }
        )

    # Split counts (post-eligibility).
    split = meta["split"]
    for name, key in (
        ("train_benign", "train"),
        ("test_benign", "test_benign"),
        ("test_malware", "test_malware"),
    ):
        csv_rows.append(
            {
                "stage": "split",
                "class": name,
                "n_files": "",
                "n_header_only": "",
                "n_effective": len(split[key]),
                "n_events": "",
                "n_mapped": "",
                "mapped_rate": "",
                "categories_firing": "",
                "median_trace_length": "",
                "median_active_categories": "",
                "artifact_path": "abrg/output/androct_2017/run2/corpus_cache/meta.json#split",
                "artifact_scored_at_utc": "",
            }
        )

    # LaTeX: population rows only (thesis table).
    for rec in csv_rows:
        if rec["stage"] != "population":
            continue
        tex_rows.append(
            [
                rec["class"],
                rec["n_files"],
                rec["n_header_only"],
                rec["n_effective"],
                rec["n_events"],
                rec["n_mapped"],
                fmt_num(rec["mapped_rate"], 4) if rec["mapped_rate"] != "" else "",
                rec["categories_firing"],
                rec["median_trace_length"],
                rec["median_active_categories"],
            ]
        )
    write_pair(
        "T1_corpus",
        [
            "class",
            "files",
            "header-only",
            "effective n",
            "events",
            "mapped",
            "mapped rate",
            "cats firing",
            "med. length",
            "med. active cats",
        ],
        tex_rows,
        "AndroCT 2017 corpus population (post-\\_CALL\\_RE inventory; pre-graph, pre-eligibility).",
        "tab:t1-corpus",
        csv_rows,
        fields,
    )

    # Attrition companion (numbers only).
    attr_fields = [
        "stage",
        "benign",
        "malware",
        "total",
        "delta_benign",
        "delta_malware",
        "note",
        "artifact_path",
    ]
    # Archive → parsed non-empty (inventory).
    b, m = inv["classes"]["benign"], inv["classes"]["malware"]
    attr = [
        {
            "stage": "archive_files",
            "benign": b["n_files"],
            "malware": m["n_files"],
            "total": b["n_files"] + m["n_files"],
            "delta_benign": "",
            "delta_malware": "",
            "note": "Zenodo archives",
            "artifact_path": art_rel,
        },
        {
            "stage": "parsed_nonempty",
            "benign": b["n_effective"],
            "malware": m["n_effective"],
            "total": b["n_effective"] + m["n_effective"],
            "delta_benign": -(b["n_header_only"]),
            "delta_malware": -(m["n_header_only"]),
            "note": "drop header-only",
            "artifact_path": art_rel,
        },
        {
            "stage": "fetch_pre_dedupe",
            "benign": pre_dedupe_b,
            "malware": fetch_m,
            "total": pre_dedupe_b + fetch_m,
            "delta_benign": "",
            "delta_malware": "",
            "note": "hex_vt0+pkg=592+172=764 benign; malware all 1742",
            "artifact_path": "abrg/output/androct_2017/run2/FINAL_POPULATION_STATS.json",
        },
        {
            "stage": "fetch",
            "benign": fetch_b,
            "malware": fetch_m,
            "total": fetch_b + fetch_m,
            "delta_benign": -(int(final_pop["n_sha_dedupe_collisions"])),
            "delta_malware": 0,
            "note": "sha256 dedupe -1 benign → 763",
            "artifact_path": "abrg/output/androct_2017/run2/POSTMORTEM.json#eligibility",
        },
        {
            "stage": "nonempty_mapped_ge1",
            "benign": elig["ge1_static_ok"]["by_label"]["benign"],
            "malware": elig["ge1_static_ok"]["by_label"]["malware"],
            "total": elig["ge1_static_ok"]["n"],
            "delta_benign": -elig["drop_n_mapped_0"]["by_label"]["benign"],
            "delta_malware": -elig["drop_n_mapped_0"]["by_label"]["malware"],
            "note": "drop n_mapped==0",
            "artifact_path": "abrg/output/androct_2017/run2/POSTMORTEM.json#eligibility",
        },
        {
            "stage": "graph_eligible",
            "benign": elig["eligible"]["by_label"]["benign"],
            "malware": elig["eligible"]["by_label"]["malware"],
            "total": elig["eligible"]["n"],
            "delta_benign": -elig["drop_empty_categories"]["by_label"]["benign"],
            "delta_malware": -elig["drop_empty_categories"]["by_label"]["malware"],
            "note": "drop empty categories after re-parse",
            "artifact_path": "abrg/output/androct_2017/run2/POSTMORTEM.json#eligibility",
        },
        {
            "stage": "split_train_benign",
            "benign": len(split["train"]),
            "malware": 0,
            "total": len(split["train"]),
            "delta_benign": "",
            "delta_malware": "",
            "note": "seed=42 test_ratio=0.2; malware all held in test",
            "artifact_path": "abrg/output/androct_2017/run2/corpus_cache/meta.json#split",
        },
        {
            "stage": "split_test_benign",
            "benign": len(split["test_benign"]),
            "malware": 0,
            "total": len(split["test_benign"]),
            "delta_benign": "",
            "delta_malware": "",
            "note": "562+141=703",
            "artifact_path": "abrg/output/androct_2017/run2/corpus_cache/meta.json#split",
        },
        {
            "stage": "split_test_malware",
            "benign": 0,
            "malware": len(split["test_malware"]),
            "total": len(split["test_malware"]),
            "delta_benign": "",
            "delta_malware": "",
            "note": "1700 graph-eligible malware",
            "artifact_path": "abrg/output/androct_2017/run2/corpus_cache/meta.json#split",
        },
    ]
    TABLES.mkdir(parents=True, exist_ok=True)
    with (TABLES / "T1_attrition.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=attr_fields)
        w.writeheader()
        for r in attr:
            w.writerow(r)


def t2_floors(master):
    csv_rows = []
    tex_rows = []
    fields = ["representation", "metric", "raw_auc", "auc_floor", "direction", "ci_low", "ci_high", "artifact_path"]
    for r in master:
        if r["method"] != "trivial_floor":
            continue
        csv_rows.append({k: r.get(k, "") for k in fields})
        tex_rows.append(
            [
                r["representation"],
                r["detector"],
                fmt_num(r["raw_auc"], 4),
                fmt_num(r["auc_floor"], 4),
                r["direction"].replace("_", "\\_"),
                fmt_num(r["ci_low"], 4),
                fmt_num(r["ci_high"], 4),
            ]
        )
    write_pair(
        "T2_floors",
        ["rep", "metric", "raw", "floor", "direction", "CI low", "CI high"],
        tex_rows,
        "Trivial floors across T22, API-1000, and invocation representations.",
        "tab:t2-floors",
        csv_rows,
        fields,
    )


def t3_method_sweep(master):
    size_floor = load_size_floor()
    # families from MASTER trained/untrained pairs + kernels + OCPool
    families = [
        ("GAE reconstruction", "gae_recon"),
        ("GAE embedding distance", "gae_embedding_centroid_mean"),
        ("OCGIN", "OCGIN_plus"),
        ("GLocalKD", "s_graph_full"),
        ("OCGTL", "ocgtl_K4"),
        ("graph kernels", "WL_h3_ocsvm_precomputed"),
        ("pooling / one-class", "OCPool_mean_raw"),
    ]
    by = {(r["detector"], r["method"]): r for r in master}
    csv_rows = []
    tex_rows = []
    fields = [
        "family",
        "trained_auc_floor",
        "untrained_auc_floor",
        "ci_low",
        "ci_high",
        "ci_type",
        "clears_size_floor",
        "artifact_path",
    ]
    for fam, det in families:
        tr = by.get((det, "trained"))
        un = by.get((det, "untrained"))
        if det == "WL_h3_ocsvm_precomputed":
            tr = next((r for r in master if r["detector"] == det), None)
            un = None
        if det == "OCPool_mean_raw":
            tr = next((r for r in master if r["detector"] == "OCPool_mean_raw"), None)
            un = None
        rec = {
            "family": fam,
            "trained_auc_floor": tr["auc_floor"] if tr else "",
            "untrained_auc_floor": un["auc_floor"] if un else "",
            "ci_low": tr["ci_low"] if tr else "",
            "ci_high": tr["ci_high"] if tr else "",
            "ci_type": tr["ci_type"] if tr else "",
            "clears_size_floor": tr["clears_size_floor"] if tr else "",
            "artifact_path": tr["artifact_path"] if tr else "",
        }
        csv_rows.append(rec)
        tex_rows.append(
            [
                fam,
                fmt_num(rec["trained_auc_floor"], 4),
                fmt_num(rec["untrained_auc_floor"], 4) if rec["untrained_auc_floor"] != "" else "---",
                fmt_num(rec["ci_low"], 4),
                fmt_num(rec["ci_high"], 4),
                rec["ci_type"].replace("_", "\\_"),
                rec["clears_size_floor"],
            ]
        )
    write_pair(
        "T3_method_sweep",
        ["family", "trained", "untrained", "CI low", "CI high", "CI type", "clears floor"],
        tex_rows,
        "Seven method families, trained vs untrained, against the mapped-event size floor.",
        "tab:t3-sweep",
        csv_rows,
        fields,
    )
    _ = size_floor


def t4_ladder(master):
    want = [
        ("rung1_HGB_full", lambda r: r["experiment"] == "ladder" and r["detector"] == "HGB" and r["method"] == "supervised"),
        ("rung2_mean_auc_floor_superseded", lambda r: r["detector"] == "HGB_mean_auc_floor" and "random" not in r["method"]),
        ("rung2_pooled_oof", lambda r: r["detector"] == "HGB_pooled_oof_raw"),
        ("rung2_mean_raw", lambda r: r["detector"] == "HGB_mean_raw_auc"),
        ("random_group_control", lambda r: "random_group" in r["method"] and r["detector"] == "HGB_mean_auc_floor"),
        ("rung3_OCPool_raw", lambda r: r["detector"] == "OCPool_mean_raw"),
        ("rung3_OCPool_R2", lambda r: r["detector"] == "OCPool_mean_R2"),
    ]
    # per-fold inflation from ladder JSON
    b = load_json(ANDROCT / "ladder" / "rung2" / "behavioral_group_holdout.json")
    csv_rows = []
    tex_rows = []
    fields = ["row", "raw_auc", "auc_floor", "ci_low", "ci_high", "ci_type", "is_superseded", "artifact_path"]
    for name, pred in want:
        r = next((x for x in master if pred(x)), None)
        if r is None:
            continue
        rec = {"row": name, **{k: r[k] for k in fields if k != "row"}}
        csv_rows.append(rec)
        tex_rows.append(
            [
                name.replace("_", "\\_"),
                fmt_num(r["raw_auc"], 6),
                fmt_num(r["auc_floor"], 6),
                fmt_num(r["ci_low"], 4),
                fmt_num(r["ci_high"], 4),
                r["ci_type"].replace("_", "\\_"),
                r["is_superseded"],
            ]
        )
    n_inv = 0
    for f in b.get("folds", []):
        h = f["modes"]["full"]["hist_gradient_boosting"]["auc"]
        if float(h["auc"]) < 0.5:
            n_inv += 1
    csv_rows.append(
        {
            "row": "rung2_n_folds_raw_lt_0.5",
            "raw_auc": n_inv,
            "auc_floor": "",
            "ci_low": "",
            "ci_high": "",
            "ci_type": "none",
            "is_superseded": "False",
            "artifact_path": "abrg/output/androct_2017/ladder/rung2/behavioral_group_holdout.json",
        }
    )
    write_pair(
        "T4_supervision_ladder",
        ["row", "raw", "floor", "CI low", "CI high", "CI type", "superseded"],
        tex_rows,
        "Supervision ladder: rung 1 / rung 2 / random-group control / rung 3 one-class reference.",
        "tab:t4-ladder",
        csv_rows,
        fields,
    )


def t5_message_passing(master):
    csv_rows = []
    tex_rows = []
    fields = ["representation", "method", "split", "detector", "auc_floor", "ci_type", "artifact_path"]
    for r in master:
        if r["experiment"] != "supgnn" and r["detector"] not in {"WL_structure_only_features_constant", "WL_edges_removed", "WL_h3_ocsvm_precomputed"}:
            continue
        if r["experiment"] == "supgnn" or r["detector"].startswith("WL"):
            csv_rows.append({k: r.get(k, "") for k in fields})
            tex_rows.append(
                [
                    r["representation"].replace("_", "\\_"),
                    r["method"].replace("_", "\\_"),
                    r["split"].replace("_", "\\_"),
                    r["detector"].replace("_", "\\_"),
                    fmt_num(r["auc_floor"], 4),
                    r["ci_type"].replace("_", "\\_"),
                ]
            )
    write_pair(
        "T5_message_passing",
        ["rep", "mode", "split", "detector", "AUC floor", "CI type"],
        tex_rows,
        "M1/M2/M3 across poolings and splits, plus WL structure-only and edges-removed.",
        "tab:t5-mp",
        csv_rows,
        fields,
    )


def t6_devread(master):
    csv_rows = []
    tex_rows = []
    fields = ["representation", "method", "detector", "split", "auc_floor", "direction", "artifact_path"]
    for r in master:
        fs = r["representation"]
        keep = False
        if any(fs.startswith(f"D{i}") for i in range(6)) and r["experiment"] in {"ocdev", "devread"}:
            keep = True
        if r["method"] == "raw_input_control":
            keep = True
        if not keep:
            continue
        if r["detector"] not in {"centroid_euclidean", "centroid_euclidean_pooled_oof", "HGB", "HGB_mean_seeds_42_46"} and r["method"] != "raw_input_control":
            continue
        csv_rows.append({k: r.get(k, "") for k in fields})
        tex_rows.append(
            [
                r["representation"].replace("_", "\\_"),
                r["method"].replace("_", "\\_"),
                r["detector"].replace("_", "\\_"),
                r["split"].replace("_", "\\_"),
                fmt_num(r["auc_floor"], 4),
                r["direction"].replace("_", "\\_"),
            ]
        )
    write_pair(
        "T6_deviation_readout",
        ["rep", "method", "detector", "split", "AUC floor", "direction"],
        tex_rows,
        "D0--D5 one-class and supervised detectors on both splits, plus raw-input control.",
        "tab:t6-dev",
        csv_rows,
        fields,
    )


def t7_operating():
    d = load_json(ANDROCT / "final_validation" / "check2_operating" / "check2.json")
    csv_rows = []
    tex_rows = []
    fields = ["config", "fpr_target", "fpr_achieved", "tpr", "threshold", "precision_wild", "artifact_path"]
    art = "abrg/output/androct_2017/final_validation/check2_operating/check2.json"
    for cfg in d["configurations"]:
        for op in cfg["operating_points"]:
            rec = {
                "config": cfg["name"],
                "fpr_target": op["fpr_target"],
                "fpr_achieved": op["fpr_achieved"],
                "tpr": op["tpr"],
                "threshold": op["threshold"],
                "precision_wild": op["precision_wild_base_rate"],
                "artifact_path": art,
            }
            csv_rows.append(rec)
            tex_rows.append(
                [
                    cfg["name"].replace("_", "\\_"),
                    fmt_num(op["fpr_target"], 3),
                    fmt_num(op["fpr_achieved"], 4),
                    fmt_num(op["tpr"], 4),
                    fmt_num(op["threshold"], 4),
                    fmt_num(op["precision_wild_base_rate"], 4),
                ]
            )
    write_pair(
        "T7_operating_points",
        ["config", "FPR$^\\star$", "FPR", "TPR", "threshold", "prec.\\ wild"],
        tex_rows,
        "TPR at FPR in $\\{0.001,0.01,0.05,0.10\\}$ with wild-base-rate precision $\\pi=0.01$.",
        "tab:t7-op",
        csv_rows,
        fields,
    )


def t8_validation(master):
    """What each headline number survived, from saved check JSONs (boolean presence, not new AUCs)."""
    bias = load_json(ANDROCT / "ocdev" / "validation" / "check1_bias" / "bias_stats.json")
    nested_d1 = bias["partA_D1_centroid"]["point_inside_nested_percentile_ci"]
    nested_s1 = bias["partB_T1K_S1_norm"]["point_inside_nested_percentile_ci"]
    vol = load_json(ANDROCT / "final_validation" / "check3_d1_volume" / "check3.json")
    hold = load_json(ANDROCT / "final_validation" / "check4_benign_holdout" / "check4.json")
    shuf = load_json(ANDROCT / "ocdev" / "validation" / "check4_s1norm" / "check4.json")
    headlines = [r for r in master if _tf(r["is_headline"])]
    csv_rows = []
    tex_rows = []
    fields = [
        "detector",
        "auc_floor",
        "bias_check",
        "nested_ci",
        "volume_ablation",
        "benign_group_holdout",
        "shuffle_control",
        "artifact_path",
    ]
    for r in headlines:
        det = r["detector"]
        rec = {
            "detector": det,
            "auc_floor": r["auc_floor"],
            "bias_check": "",
            "nested_ci": "",
            "volume_ablation": "",
            "benign_group_holdout": "",
            "shuffle_control": "",
            "artifact_path": r["artifact_path"],
        }
        if "centroid_euclidean_nested_form" in det or (det == "centroid_euclidean" and r["experiment"] == "ocdev_validate"):
            rec["bias_check"] = str(bias["partA_D1_centroid"].get("bias_mean_minus_point", ""))
            rec["nested_ci"] = str(nested_d1)
            rec["volume_ablation"] = str(vol["dominant_node"]["node"])
            rec["benign_group_holdout"] = str(hold.get("chosen_k", ""))
        if "S1_norm_nested" in det:
            rec["bias_check"] = str(bias["partB_T1K_S1_norm"].get("bias_mean_minus_point", ""))
            rec["nested_ci"] = str(nested_s1)
            rec["shuffle_control"] = "check4_s1norm" if shuf else ""
        if det == "centroid_euclidean" and r["experiment"] == "final_validate":
            rec["benign_group_holdout"] = "pooled_oof"
        csv_rows.append(rec)
        tex_rows.append(
            [
                det.replace("_", "\\_"),
                fmt_num(r["auc_floor"], 4),
                fmt_num(rec["bias_check"], 4) if rec["bias_check"] not in ("", "True", "False") else rec["bias_check"],
                rec["nested_ci"],
                rec["volume_ablation"].replace("_", "\\_"),
                rec["benign_group_holdout"].replace("_", "\\_"),
                rec["shuffle_control"].replace("_", "\\_"),
            ]
        )
    write_pair(
        "T8_validation",
        ["detector", "AUC floor", "bias", "nested CI", "volume", "holdout", "shuffle"],
        tex_rows,
        "Checks each headline number survived (bias, nested CI, volume, holdout, shuffle).",
        "tab:t8-val",
        csv_rows,
        fields,
    )


def make_tables():
    master = read_master()
    t1_corpus()
    t2_floors(master)
    t3_method_sweep(master)
    t4_ladder(master)
    t5_message_passing(master)
    t6_devread(master)
    t7_operating()
    t8_validation(master)


if __name__ == "__main__":
    make_tables()
    print("tables written to", TABLES)
