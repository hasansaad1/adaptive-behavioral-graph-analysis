"""Orchestrate final validation checks 1–5. Additive; does not write existing run dirs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.final_validate import FINAL_OUTPUT_ROOT, WILD_BASE_RATE_NOTE
from abrg.final_validate.check1_ladder import run_check1
from abrg.final_validate.check2_operating import run_check2
from abrg.final_validate.check3_d1_volume import run_check3
from abrg.final_validate.check4_benign_holdout import run_check4
from abrg.final_validate.check5_integrity import run_check5
from abrg.final_validate.util import assert_digest, write_json


def _fmt(x: Any, nd: int = 4) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v != v:  # nan
        return "—"
    return f"{v:.{nd}f}"


def _ci(lo: Any, hi: Any, nd: int = 4) -> str:
    try:
        return f"[{float(lo):.{nd}f}, {float(hi):.{nd}f}]"
    except (TypeError, ValueError):
        return "—"


def write_summary(
    *,
    out: Path,
    digest: str,
    c1: dict[str, Any] | None,
    c2: dict[str, Any] | None,
    c3: dict[str, Any] | None,
    c4: dict[str, Any] | None,
    c5: dict[str, Any] | None,
) -> None:
    lines: list[str] = []
    lines.append("# Final validation — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_sha_digest: `{digest}`")
    lines.append("- additive only; existing run outputs not modified")
    lines.append("")

    lines.append("## Headline table")
    lines.append("")
    lines.append(
        "| config | form | value | interval | TPR@FPR=0.01 | survived |"
    )
    lines.append("|---|---|---:|---|---:|---|")

    tpr01 = (c2 or {}).get("tpr_at_fpr_0.01") or {}

    def tpr(name: str) -> str:
        v = tpr01.get(name)
        return _fmt(v) if v is not None else "—"

    if c1:
        t = c1["thesis_carries"]
        h = c1["behavioral"]["from_saved_json"]["full"]["hist_gradient_boosting"]
        pooled = c1["behavioral"].get("saved_pooled_oof_hgb_full") or {}
        lines.append(
            f"| ladder rung2 HGB full | {t['carries']} | {_fmt(t['value'])} | "
            f"{_ci(*(pooled.get('ci95') or [None, None]))} | — | "
            f"raw<0.5 in {t['n_folds_raw_auc_lt_0.5']}/30 folds; "
            f"mean_raw={_fmt(t['mean_raw_auc'])}; mean_floor={_fmt(t['mean_auc_floor'])}; "
            f"weighted_floor={_fmt(t['weighted_mean_auc_floor'])} |"
        )
    if c2:
        d1n = next(
            (c for c in c2["configurations"] if c["name"] == "D1_centroid_euclidean_benign_only"),
            None,
        )
        if d1n:
            ci = d1n.get("artifact_auc")
            lines.append(
                f"| D1 centroid_euclidean | full-sample AUC | {_fmt(d1n['artifact_auc'])} | "
                f"see ocdev nested [0.7572, 0.8154] | {tpr(d1n['name'])} | "
                f"volume check 3; benign-holdout check 4 |"
            )
        for c in c2["configurations"]:
            if c["name"] == "D1_centroid_euclidean_benign_only":
                continue
            lines.append(
                f"| {c['name']} | artifact AUC | {_fmt(c['artifact_auc'])} | — | "
                f"{tpr(c['name'])} | operating points check 2 |"
            )
            if c["name"] == "S1_norm_T1K_B_docfreq":
                lines.append(
                    f"| S1_norm_T1K_B_docfreq | nested bootstrap mean | 0.7867 | "
                    f"[0.7553, 0.8175] | {tpr(c['name'])} | "
                    f"operating points from full-sample ROC (point {_fmt(c['artifact_auc'])}) |"
                )
            if c["name"] == "D3_profile_HGB_supervised_readout":
                lines.append(
                    "| D3_profile_HGB_mean_seeds_42_46 | seed-mean AUC floor | 0.9624 | — | "
                    f"{tpr(c['name'])} | seed-42 ROC used for TPR@FPR (seed42 AUC {_fmt(c['artifact_auc'])}) |"
                )
    lines.append("")

    # ---- Check 1 ----
    lines.append("## Check 1 — ladder rung-2 direction")
    lines.append("")
    if c1:
        t = c1["thesis_carries"]
        lines.append(f"- thesis carries: `{t['carries']}` = {_fmt(t['value'], 6)}")
        lines.append(f"- {t['reason']}")
        lines.append("")
        lines.append(
            "| grouping | mode | model | n raw<0.5 | mean raw | mean floor | inflation | "
            "weighted raw | weighted floor | pooled OOF raw |"
        )
        lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for gname, g in (("behavioral", c1["behavioral"]), ("random_group", c1["random_group"])):
            tables = g["from_saved_json"]
            pooled_s = ""
            if gname == "behavioral":
                po = g.get("saved_pooled_oof_hgb_full") or {}
                pooled_hgb = _fmt(po.get("auc"), 6) if po else "—"
            else:
                po = g.get("saved_pooled_oof_hgb_full") or {}
                pooled_hgb = _fmt(po.get("auc"), 6) if po else "—"
            for mode, models in tables.items():
                for model, blk in models.items():
                    pooled_cell = pooled_hgb if (mode == "full" and model == "hist_gradient_boosting") else "—"
                    lines.append(
                        f"| {gname} | {mode} | {model} | {blk['n_folds_raw_auc_lt_0.5']}/30 | "
                        f"{_fmt(blk['mean_raw_auc'], 6)} | {_fmt(blk['mean_auc_floor'], 6)} | "
                        f"{_fmt(blk['inflation_floor_minus_raw'], 6)} | "
                        f"{_fmt(blk['weighted_mean_raw_auc'], 6)} | "
                        f"{_fmt(blk['weighted_mean_auc_floor'], 6)} | {pooled_cell} |"
                    )
        lines.append("")
        lines.append("### Per-fold raw AUC (behavioral, HGB full)")
        lines.append("")
        lines.append("| fold | n_malware | raw AUC | floor AUC | inverted |")
        lines.append("|---:|---:|---:|---:|---|")
        for r in c1["behavioral"]["from_saved_json"]["full"]["hist_gradient_boosting"]["folds"]:
            lines.append(
                f"| {r['fold']} | {r['n_malware']} | {_fmt(r['raw_auc'], 6)} | "
                f"{_fmt(r['auc_floor'], 6)} | {r['inverted']} |"
            )
        lines.append("")
        lines.append("### Per-fold raw AUC (random-group, HGB full)")
        lines.append("")
        lines.append("| fold | n_malware | raw AUC | floor AUC | inverted |")
        lines.append("|---:|---:|---:|---:|---|")
        for r in c1["random_group"]["from_saved_json"]["full"]["hist_gradient_boosting"]["folds"]:
            lines.append(
                f"| {r['fold']} | {r['n_malware']} | {_fmt(r['raw_auc'], 6)} | "
                f"{_fmt(r['auc_floor'], 6)} | {r['inverted']} |"
            )
        lines.append("")
        if c1.get("retrained_available"):
            lines.append("### Retrain score-scale (seed=42, GAE not retrained; models retrain per fold)")
            lines.append("")
            lines.append(
                "| grouping | mean raw | weighted raw | pooled OOF raw | pooled OOF z(train) | "
                "var median benign | var median malware | median benign range | median malware range |"
            )
            lines.append("|---|---:|---:|---:|---:|---:|---:|---|---|")
            for gname, key in (
                ("behavioral", "retrained_behavioral_HGB_full"),
                ("random_group", "retrained_random_HGB_full"),
            ):
                b = c1[key]
                po = b["pooled_oof_raw"]
                pz = b["pooled_oof_zscored_train_scores"]
                lines.append(
                    f"| {gname} | {_fmt(b['mean_raw_auc'], 6)} | {_fmt(b['weighted_mean_raw_auc'], 6)} | "
                    f"{_fmt(po['auc'], 6)} | {_fmt(pz['auc'], 6)} | "
                    f"{_fmt(b['between_fold_var_median_benign'], 6)} | "
                    f"{_fmt(b['between_fold_var_median_malware'], 6)} | "
                    f"{b['fold_median_benign_range']} | {b['fold_median_malware_range']} |"
                )
            lines.append("")
        else:
            lines.append("- retrain for score-scale: not run")
            lines.append("")

    # ---- Check 2 ----
    lines.append("## Check 2 — operating points")
    lines.append("")
    lines.append(f"- {WILD_BASE_RATE_NOTE}")
    if c2:
        lines.append(f"- {c2['test_class_balance_note']}")
        lines.append("")
        lines.append(
            "| config | n_neg | n_pos | FPR target | FPR achieved | TPR | threshold | "
            "precision (test balance) | precision (wild π=0.01) |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for c in c2["configurations"]:
            for r in c["operating_points"]:
                lines.append(
                    f"| {c['name']} | {c['n_neg']} | {c['n_pos']} | {r['fpr_target']} | "
                    f"{_fmt(r['fpr_achieved'], 6)} | {_fmt(r['tpr'], 6)} | "
                    f"{_fmt(r['threshold'], 6)} | {_fmt(r['precision_test_balance_141_1700'], 6)} | "
                    f"{_fmt(r['precision_wild_base_rate'], 6)} |"
                )
        lines.append("")
        lines.append("| config | TPR@FPR=0.01 |")
        lines.append("|---|---:|")
        for name, v in c2["tpr_at_fpr_0.01"].items():
            lines.append(f"| {name} | {_fmt(v, 6)} |")
        lines.append("")

    # ---- Check 3 ----
    lines.append("## Check 3 — D1 volume")
    lines.append("")
    if c3:
        raw = c3["raw_centroid"]
        lines.append(
            f"- D1 centroid raw AUC={_fmt(raw['auc'], 6)} floor={_fmt(raw['auc_floor'], 6)} "
            f"CI={_ci(*raw.get('ci95', [None, None]), 4)}"
        )
        lines.append("")
        lines.append("| covariate | Spearman ρ vs D1 centroid (eval) | p |")
        lines.append("|---|---:|---:|")
        for k, v in c3["spearman_vs_d1_centroid_eval"].items():
            lines.append(f"| {k} | {_fmt(v['rho'], 6)} | {_fmt(v['p'], 6)} |")
        lines.append("")
        lines.append("### Per-node ablation (22 D1 dims zeroed in turn)")
        lines.append("")
        lines.append(
            "| rank | node | AUC floor zeroed | Δ floor | univariate centroid floor | univariate raw-dim floor |"
        )
        lines.append("|---:|---|---:|---:|---:|---:|")
        for i, r in enumerate(c3["per_node_ablation_ranked"], 1):
            lines.append(
                f"| {i} | {r['node']} | {_fmt(r['auc_floor_zeroed'], 6)} | "
                f"{_fmt(r['delta_auc_floor'], 6)} | {_fmt(r['univariate_centroid_auc_floor'], 6)} | "
                f"{_fmt(r['univariate_raw_dim_auc_floor'], 6)} |"
            )
        d = c3["dominant_node"]
        lines.append("")
        lines.append(
            f"- rank-1 drop node: `{d['node']}` Δfloor={_fmt(d['delta_auc_floor'], 6)}; "
            f"univariate centroid AUC={_fmt(d['univariate_centroid_auc'], 6)} "
            f"floor={_fmt(d['univariate_centroid_auc_floor'], 6)}"
        )
        res = c3["residualisation_mapped_events_R2_train_benign"]
        ra, rb = res["raw_auc"], res["residualised_auc"]
        lines.append("")
        lines.append("| score | AUC | AUC floor | CI95 | CI95 floor | OLS R² |")
        lines.append("|---|---:|---:|---|---|---:|")
        lines.append(
            f"| raw D1 centroid | {_fmt(ra['auc'], 6)} | {_fmt(ra['auc_floor'], 6)} | "
            f"{_ci(*ra.get('ci95', [None, None]))} | {_ci(*ra.get('ci95_floor', [None, None]))} | — |"
        )
        lines.append(
            f"| residualised vs mapped (R2 train-benign OLS) | {_fmt(rb['auc'], 6)} | "
            f"{_fmt(rb['auc_floor'], 6)} | {_ci(*rb.get('ci95', [None, None]))} | "
            f"{_ci(*rb.get('ci95_floor', [None, None]))} | {_fmt(res['ols']['r2'], 6)} |"
        )
        lines.append("")
        st = c3["volume_stratified_terciles_test_mapped_events"]
        lines.append(f"- tercile cuts (mapped events): {st['cuts']}")
        lines.append("")
        lines.append("| tercile | n | n_benign | n_malware | AUC | AUC floor | CI95 |")
        lines.append("|---|---:|---:|---:|---:|---:|---|")
        for r in st["terciles"]:
            lines.append(
                f"| {r['tercile']} | {r['n']} | {r['n_benign']} | {r['n_malware']} | "
                f"{_fmt(r['auc'], 6)} | {_fmt(r['auc_floor'], 6)} | {_ci(*(r.get('ci95') or [None, None]))} |"
            )
        lines.append("")

    # ---- Check 4 ----
    lines.append("## Check 4 — D1 benign-group holdout")
    lines.append("")
    if c4:
        cl = c4["clustering"]
        lines.append(f"- GAE retrained per fold: {c4['gae_retrained_per_fold']}")
        lines.append(f"- reference recomputed per fold: {c4['reference_recomputed_per_fold']}")
        lines.append(f"- clustering population: {cl['population']}; malware in clustering: {cl['malware_used_in_clustering']}")
        lines.append(f"- method: {cl['method']}; k grid: {cl['k_grid']}; chosen k: {cl['chosen_k']}")
        lines.append("")
        lines.append("| k | silhouette |")
        lines.append("|---:|---:|")
        for row in cl["silhouette"]["curve"]:
            lines.append(f"| {row['k']} | {_fmt(row['silhouette'], 6)} |")
        lines.append("")
        lines.append(f"- cluster sizes: {cl['cluster_sizes']}")
        lines.append("")
        lines.append(
            "| detector | n folds | n raw<0.5 | mean raw | mean floor | weighted raw | "
            "weighted floor | pooled OOF raw | pooled CI |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for det in ("centroid_euclidean", "mahalanobis"):
            b = c4[det]
            po = b["pooled_oof_raw"]
            lines.append(
                f"| {det} | {b['n_folds']} | {b['n_folds_raw_auc_lt_0.5']} | "
                f"{_fmt(b['mean_raw_auc'], 6)} | {_fmt(b['mean_auc_floor'], 6)} | "
                f"{_fmt(b['weighted_mean_raw_auc'], 6)} | {_fmt(b['weighted_mean_auc_floor'], 6)} | "
                f"{_fmt(po['auc'], 6)} | {_ci(*po.get('ci95', [None, None]))} |"
            )
        lines.append("")
        for det in ("centroid_euclidean", "mahalanobis"):
            lines.append(f"### {det} per-fold")
            lines.append("")
            lines.append("| fold | n_holdout_benign | raw AUC | floor AUC | inverted |")
            lines.append("|---:|---:|---:|---:|---|")
            for r in c4[det]["folds"]:
                lines.append(
                    f"| {r['fold']} | {r['n_holdout_benign']} | {_fmt(r['raw_auc'], 6)} | "
                    f"{_fmt(r['auc_floor'], 6)} | {r['inverted']} |"
                )
            lines.append("")

    # ---- Check 5 ----
    lines.append("## Check 5 — artifact integrity")
    lines.append("")
    if c5:
        lines.append("| name | original | reproduced | match 6 dp | how |")
        lines.append("|---|---:|---:|---|---|")
        for r in c5["reload_verification"]:
            orig = r.get("original", r.get("original_mean_auc_floor"))
            got = r.get("reproduced", r.get("reproduced_mean_auc_floor"))
            match = r.get("match_6dp", r.get("match_6dp_mean_floor"))
            lines.append(
                f"| {r['name']} | {_fmt(orig, 6)} | {_fmt(got, 6)} | {match} | {r.get('how', '')} |"
            )
        lines.append("")
        lines.append(f"- n reload mismatch (6 dp): {c5['n_reload_mismatch_6dp']}")
        lines.append(f"- n reproduce.md: {c5['n_reproduce_md']}; help fail: {c5['n_reproduce_help_fail']}")
        lines.append("- full `reproduce.md` execute: skipped (would write existing run dirs)")
        miss = c5.get("summary_dirs_without_reproduce_md") or []
        lines.append(f"- experiment dirs with SUMMARY.md and no reproduce.md: {len(miss)}")
        if miss:
            for m in miss:
                lines.append(f"  - `{m}`")
        lines.append("")
        lines.append("| reproduce.md | command | `--help` exit 0 |")
        lines.append("|---|---|---|")
        for r in c5["reproduce_md"]:
            lines.append(f"| `{r['path']}` | `{r['command']}` | {r['help_exit_0']} |")
        lines.append("")
        if c5.get("untraceable"):
            lines.append("| untraceable SUMMARY number | where | status |")
            lines.append("|---|---|---|")
            for r in c5["untraceable"]:
                lines.append(f"| {r.get('summary_number')} | {r.get('where_reported')} | {r.get('status')} |")
            lines.append("")
        else:
            lines.append("- untraceable SUMMARY numbers: none flagged")
            lines.append("")
        lines.append(f"- MASTER_RESULTS.csv rows: {c5['n_master_rows']} → `{c5['master_results_csv']}`")
        lines.append("")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Final validation sweep (additive)")
    ap.add_argument("--out", type=Path, default=FINAL_OUTPUT_ROOT)
    ap.add_argument("--skip-check1", action="store_true")
    ap.add_argument("--skip-check2", action="store_true")
    ap.add_argument("--skip-check3", action="store_true")
    ap.add_argument("--skip-check4", action="store_true")
    ap.add_argument("--skip-check5", action="store_true")
    ap.add_argument("--skip-retrain", action="store_true", help="Check 1: JSON-only, no per-fold refit")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    split_bundle = assert_digest()
    corpus = load_corpus_cache(androct_run2_output_dir())
    tensors = corpus.tensors

    c1 = c2 = c3 = c4 = c5 = None

    def _load(p: Path) -> dict | None:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    if not args.skip_check1:
        print("[final_validate] CHECK 1 …", flush=True)
        c1 = run_check1(
            out=out / "check1_ladder",
            split_bundle=split_bundle,
            tensors=tensors,
            skip_retrain=args.skip_retrain,
        )
    else:
        c1 = _load(out / "check1_ladder" / "check1.json")

    if not args.skip_check2:
        print("[final_validate] CHECK 2 …", flush=True)
        c2 = run_check2(out=out / "check2_operating")
    else:
        c2 = _load(out / "check2_operating" / "check2.json")

    if not args.skip_check3:
        print("[final_validate] CHECK 3 …", flush=True)
        c3 = run_check3(out=out / "check3_d1_volume", split_bundle=split_bundle, tensors=tensors)
    else:
        c3 = _load(out / "check3_d1_volume" / "check3.json")

    if not args.skip_check4:
        print("[final_validate] CHECK 4 …", flush=True)
        c4 = run_check4(out=out / "check4_benign_holdout", split_bundle=split_bundle, tensors=tensors)
    else:
        c4 = _load(out / "check4_benign_holdout" / "check4.json")

    if not args.skip_check5:
        print("[final_validate] CHECK 5 …", flush=True)
        c5 = run_check5(
            out=out / "check5_integrity",
            split_bundle=split_bundle,
            tensors=tensors,
            c1=c1,
            c2=c2,
            c4=c4,
        )
    else:
        c5 = _load(out / "check5_integrity" / "check5.json")

    write_summary(out=out, digest=split_bundle.sha_list_digest, c1=c1, c2=c2, c3=c3, c4=c4, c5=c5)
    write_json(
        out / "run_meta.json",
        {
            "digest": split_bundle.sha_list_digest,
            "skip_retrain": args.skip_retrain,
            "utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    print(f"[final_validate] done → {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
