"""Orchestrate ocdev headline validation checks 1–4."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.paths import androct_run2_output_dir
from abrg.ocdev_validate import NESTED_B, VALIDATE_OUTPUT_ROOT
from abrg.ocdev_validate.check1 import run_check1
from abrg.ocdev_validate.check2 import run_check2
from abrg.ocdev_validate.check3 import run_check3
from abrg.ocdev_validate.check4 import run_check4
from abrg.ocdev_validate.util import assert_digest, write_json


def _fmt_ci(lo: float, hi: float) -> str:
    return f"[{lo:.4f}, {hi:.4f}]"


def write_summary(
    *,
    out: Path,
    digest: str,
    c1: dict[str, Any] | None,
    c2: dict[str, Any] | None,
    c3: dict[str, Any] | None,
    c4: dict[str, Any] | None,
) -> None:
    lines: list[str] = []
    lines.append("# ocdev headline validation — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_sha_digest: `{digest}`")
    lines.append("- nested B=200, seed=42")
    lines.append("")
    lines.append("## Thesis numbers")
    lines.append("")
    lines.append("| headline | form carried | value | interval | interval kind |")
    lines.append("|---|---|---:|---|---|")
    if c1:
        for key in ("partA_D1_centroid", "partB_T1K_S1_norm"):
            blk = c1[key]
            t = blk["thesis_carries"]
            lo, hi = t["interval"]
            lines.append(
                f"| `{blk['config']}` | {t['carries']} | {t['value']:.4f} | "
                f"{_fmt_ci(lo, hi)} | {t['interval_kind']} |"
            )
    lines.append("")
    if c1:
        lines.append("### Check 1 — nested-bootstrap bias")
        lines.append("")
        lines.append(
            "| config | full-sample | boot mean | boot median | boot std | "
            "p2.5 | p25 | p50 | p75 | p97.5 | bias | bias-corrected | "
            "nested CI | basic CI | point in nested CI |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|")
        for key in ("partA_D1_centroid", "partB_T1K_S1_norm"):
            blk = c1[key]
            d = blk["bootstrap"]
            nci = blk["nested_percentile_ci95"]
            bci = blk["basic_reverse_percentile_ci95"]
            lines.append(
                f"| `{blk['config']}` | {blk['full_sample_point']:.4f} | "
                f"{d['mean']:.4f} | {d['median']:.4f} | {d['std']:.4f} | "
                f"{d['p2.5']:.4f} | {d['p25']:.4f} | {d['p50']:.4f} | {d['p75']:.4f} | {d['p97.5']:.4f} | "
                f"{blk['bias_mean_minus_point']:+.4f} | {blk['bias_corrected_2point_minus_mean']:.4f} | "
                f"{_fmt_ci(*nci)} | {_fmt_ci(*bci)} | {blk['point_inside_nested_percentile_ci']} |"
            )
        lines.append("")
        lines.append("| BCa | feasible |")
        lines.append("|---|---|")
        lines.append("| nested train-resample / fixed eval | no |")
        lines.append("")
        bc = c1["bias_comparison"]
        lines.append("| | D1 centroid | T1K S1_norm |")
        lines.append("|---|---:|---:|")
        lines.append(f"| bias | {bc['D1_bias']:+.4f} | {bc['S1_norm_bias']:+.4f} |")
        lines.append(
            f"| bias / nested width | {bc['D1_bias_over_width']:+.3f} | {bc['S1_norm_bias_over_width']:+.3f} |"
        )
        lines.append(f"| bias sign consistent | {bc['bias_sign_consistent']} | {bc['bias_sign_consistent']} |")
        lines.append("")
        for key in ("partA_D1_centroid", "partB_T1K_S1_norm"):
            t = c1[key]["thesis_carries"]
            lines.append(f"- `{c1[key]['config']}` carries **{t['carries']}** = {t['value']:.4f}. {t['reason']}.")
        lines.append("")

    if c2:
        lines.append("### Check 2 — random-init vs trained")
        lines.append("")
        lines.append(c2["random_init_encoder_note"])
        lines.append("")
        lines.append("| feature | centroid_eucl trained | centroid_eucl rand | ocsvm trained mean±std | ocsvm rand mean±std |")
        lines.append("|---|---:|---:|---:|---:|")
        for r in c2["ocdev_grid"]["table_rows"]:
            lines.append(
                f"| {r['feature_set']} | {r['centroid_euclidean_trained']:.4f} | "
                f"{r['centroid_euclidean_random_init']:.4f} | "
                f"{r['ocsvm_rbf_trained_mean']:.4f} ± {r['ocsvm_rbf_trained_std']:.4f} | "
                f"{r['ocsvm_rbf_random_init_mean']:.4f} ± {r['ocsvm_rbf_random_init_std']:.4f} |"
            )
        lines.append("")
        lines.append("#### Paired deltas (trained − random-init), not pooled across profile types")
        lines.append("")
        lines.append("| feature / detector | n | per-seed Δ | median Δ | IQR Δ | win rate untrained | Wilcoxon p |")
        lines.append("|---|---:|---|---:|---:|---:|---:|")
        for fset, blk in c2["ocdev_grid"]["per_feature_set"].items():
            for det in ("centroid_euclidean", "ocsvm_rbf"):
                p = blk[det]["paired"]
                deltas = ", ".join(f"{x:+.4f}" for x in p["per_seed_delta_trained_minus_untrained"])
                wp = p.get("wilcoxon") or {}
                pval = f"{wp['pvalue']:.4g}" if wp.get("pvalue") is not None else wp.get("reason", "NA")
                lines.append(
                    f"| {fset} / {det} | {p['n']} | {deltas} | {p['median_delta']:+.4f} | "
                    f"{p['iqr_delta']:.4f} | {p['win_rate_untrained_higher']:.2f} | {pval} |"
                )
        lines.append("")
        d1b = c2["d1_centroid_eval_paired_bootstrap"]
        lines.append(
            f"- D1 centroid eval-paired bootstrap Δ (trained−rand): {d1b['delta_t_minus_r']:+.4f}; "
            f"mean {d1b['delta_mean']:+.4f}; CI95 {_fmt_ci(*d1b['delta_ci95'])}; "
            f"CI includes 0 = {d1b['ci_includes_zero']}"
        )
        lines.append(f"- D1 centroid claim: `{c2['claims']['deviation_profiles_D1_centroid']}`")
        lines.append(f"- D1 centroid basis: {c2['claims']['deviation_profiles_D1_centroid_basis']}")
        lines.append("")
        lines.append("#### Cross-family paired table")
        lines.append("")
        lines.append("| family | pairing | n | trained mean | untrained mean | median Δ | Wilcoxon p | claim |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---|")
        name_map = [
            ("GAE_reconstruction", "GAE reconstruction"),
            ("GAE_embedding_distance", "GAE embedding distance"),
            ("OCGIN", "OCGIN"),
            ("GLocalKD", "GLocalKD"),
            ("OCGTL", "OCGTL"),
            ("deviation_profiles_D1_centroid", "deviation profiles D1 centroid"),
            ("deviation_profiles_D1_ocsvm", "deviation profiles D1 ocsvm"),
        ]
        for key, label in name_map:
            fam = c2["families"][key]
            p = fam.get("paired") or {}
            n = p.get("n", 1)
            tm = fam.get("trained_mean", fam.get("trained"))
            um = fam.get("random_init_mean", fam.get("random_init"))
            med = p.get("median_delta", float("nan"))
            wp = (p.get("wilcoxon") or {}).get("pvalue")
            pval = f"{wp:.4g}" if wp is not None else "NA"

            def _fs(x: Any) -> str:
                try:
                    xf = float(x)
                except (TypeError, ValueError):
                    return "nan"
                if xf != xf:
                    return "nan"
                return f"{xf:.4f}"

            def _fs_signed(x: Any) -> str:
                try:
                    xf = float(x)
                except (TypeError, ValueError):
                    return "nan"
                if xf != xf:
                    return "nan"
                return f"{xf:+.4f}"

            lines.append(
                f"| {label} | {fam.get('pairing','')} | {n} | {_fs(tm)} | {_fs(um)} | "
                f"{_fs_signed(med)} | {pval} | `{c2['claims'][key]}` |"
            )
        lines.append("")

    if c3:
        lines.append("### Check 3 — Split-B pooled / weighted")
        lines.append("")
        lines.append(f"- config: {c3['config']['feature_set']} / {c3['config']['detector']}")
        lines.append(f"- train-benign fixed across folds: {c3['config']['train_benign_fixed_across_folds']}")
        lines.append(
            f"- benign replication in pooled: {c3['benign_replication_factor']:.1f}× "
            f"({c3['n_benign_rows_in_pooled']} rows / {c3['n_test_benign_unique']} unique)"
        )
        lines.append("")
        lines.append("| figure | auc_floor |")
        lines.append("|---|---:|")
        lines.append(f"| weighted mean | {c3['weighted_mean_auc_floor']:.4f} |")
        lines.append(f"| unweighted mean ± std | {c3['mean_auc_floor']:.4f} ± {c3['std_auc_floor']:.4f} |")
        lines.append(f"| pooled OOF raw | {c3['pooled_oof_raw']['auc_floor']:.4f} |")
        lines.append(f"| pooled OOF z-scored (train-benign μ,σ) | {c3['pooled_oof_zscored']['auc_floor']:.4f} |")
        lines.append(f"| deduplicated pooled raw | {c3['deduplicated_pooled_raw']['auc_floor']:.4f} |")
        lines.append(f"| deduplicated pooled z-scored | {c3['deduplicated_pooled_zscored']['auc_floor']:.4f} |")
        lines.append("")
        bv = c3["between_vs_within"]
        lines.append("| variance | value |")
        lines.append("|---|---:|")
        lines.append(f"| between-fold var of fold-median (all test) | {bv['var_fold_median_all']:.6g} |")
        lines.append(f"| between-fold var of fold-median (malware) | {bv['var_fold_median_malware']:.6g} |")
        lines.append(f"| between-fold var of fold-median (benign) | {bv['var_fold_median_benign']:.6g} |")
        lines.append(f"| mean within-fold variance | {bv['mean_within_fold_variance']:.6g} |")
        lines.append(f"| ratio between-median / mean-within | {bv['ratio_between_median_over_mean_within']:.6g} |")
        lines.append(f"| benign medians identical across folds | {bv['benign_medians_identical_across_folds']} |")
        lines.append("")
        sh = c3["scale_hypothesis"]
        lines.append(
            f"- |weighted − raw pooled| = {sh['abs_weighted_minus_raw_pooled']:.4f}; "
            f"|weighted − z pooled| = {sh['abs_weighted_minus_z_pooled']:.4f}; "
            f"z moves toward weighted = {sh['z_moves_toward_weighted']}"
        )
        sp = c3["spearman"]
        lines.append(
            f"- Spearman AUC vs n_malware: ρ={sp['auc_vs_n_malware']['rho']:.4f} "
            f"(p={sp['auc_vs_n_malware']['pvalue']:.4g})"
        )
        lines.append(
            f"- Spearman AUC vs trivial floor (mapped_event_count): "
            f"ρ={sp['auc_vs_trivial_floor']['rho']:.4f} "
            f"(p={sp['auc_vs_trivial_floor']['pvalue']:.4g})"
        )
        t = c3["thesis_carries"]
        lines.append(f"- Split-B figure carried: **{t['figure']}** = {t['value']:.4f}. {t['reason']}")
        lines.append("")
        lines.append("| fold | n_mal | auc_floor | trivial_floor | tb median/IQR | tm median/IQR | tm min | tm max | ranges overlap |")
        lines.append("|---:|---:|---:|---:|---|---|---:|---:|---|")
        ov = {r["fold"]: r for r in c3["range_overlap"]}
        for r in c3["folds"]:
            tb = r["score_test_benign"]
            tm = r["score_test_malware"]
            lines.append(
                f"| {r['fold']} | {r['n_malware']} | {r['auc_floor']:.4f} | "
                f"{r['trivial_floor_mapped_event_count']:.4f} | "
                f"{tb['median']:.4g} / {tb['iqr']:.4g} | {tm['median']:.4g} / {tm['iqr']:.4g} | "
                f"{tm['min']:.4g} | {tm['max']:.4g} | {ov[r['fold']]['ranges_overlap']} |"
            )
        lines.append("")

    if c4:
        lines.append("### Check 4 — S1_norm volume / OOV / shuffle")
        lines.append("")
        lines.append("| quantity | auc_floor | direction | CI95_floor |")
        lines.append("|---|---:|---|---|")
        raw = c4["raw"]
        res = c4["residualisation"]["residualised"]
        lines.append(
            f"| S1_norm raw | {raw['auc_floor']:.4f} | {raw['direction']} | {_fmt_ci(*raw['ci95_floor'])} |"
        )
        lines.append(
            f"| S1_norm residualised vs OOV (R2 train-benign OLS) | {res['auc_floor']:.4f} | "
            f"{res['direction']} | {_fmt_ci(*res['ci95_floor'])} |"
        )
        lines.append("")
        lines.append("| covariate | Spearman ρ vs S1_norm (eval) |")
        lines.append("|---|---:|")
        for k, v in c4["spearman_eval"].items():
            lines.append(f"| {k} | {v:.4f} |")
        ols = c4["residualisation"]["ols"]
        lines.append("")
        rz = ols.get("r2")
        rz_s = "NA" if rz is None else f"{rz:.4f}"
        lines.append(
            f"- train-benign S1_norm identically 0: {c4['residualisation']['train_benign_S1_norm_identically_zero']} "
            f"(n_nonzero={c4['residualisation']['train_benign_n_nonzero']}); "
            f"residual equals raw: {c4['residualisation']['residual_equals_raw']}"
        )
        if ols.get("degenerate"):
            lines.append(f"- OLS: degenerate. {ols.get('reason')}")
        else:
            lines.append(
                f"- OLS (train-benign): intercept={ols['coef_intercept']:.6g} "
                f"coef_oov={ols['coef_oov']:.6g} R²={rz_s} n={ols['n_fit']}"
            )
        sh = c4["shuffled_support"]
        lines.append(f"- shuffle permutation: {sh['what_was_permuted']}")
        lines.append(
            f"- shuffle S1_norm auc_floor: mean={sh['auc_floor_mean']:.4f} ± {sh['auc_floor_std']:.4f} "
            f"(min={sh['auc_floor_min']:.4f}, max={sh['auc_floor_max']:.4f}); "
            f"n(>0.55)={sh['n_seeds_auc_floor_gt_0.55']}/20; "
            f"n(>0.50)={sh['n_seeds_auc_floor_gt_0.50']}/20"
        )
        lines.append("")
        if sh.get("seed42_spearman_vs_volume"):
            lines.append("| shuffled S1_norm seed42 vs volume | Spearman ρ |")
            lines.append("|---|---:|")
            for k, v in sh["seed42_spearman_vs_volume"].items():
                lines.append(f"| {k} | {v:.4f} |")
            lines.append("")
        shr = c4.get("shuffled_support_S1_raw") or {}
        if shr:
            lines.append(
                f"- shuffle S1 raw auc_floor: mean={shr['auc_floor_mean']:.4f} ± {shr['auc_floor_std']:.4f} "
                f"(min={shr['auc_floor_min']:.4f}, max={shr['auc_floor_max']:.4f}); "
                f"n(>0.55)={shr['n_seeds_auc_floor_gt_0.55']}/20; "
                f"seed42={next(r['auc_floor'] for r in shr['per_seed'] if r['seed']==42):.4f}; "
                f"matches recorded 0.5689: {shr.get('seed42_matches_recorded')}"
            )
        lines.append("")
        lines.append("| shuffle seed | S1_norm auc_floor | S1 raw auc_floor |")
        lines.append("|---:|---:|---:|")
        raw_by = {r["seed"]: r["auc_floor"] for r in (shr.get("per_seed") or [])}
        for r in sh["per_seed"]:
            lines.append(
                f"| {r['seed']} | {r['auc_floor']:.4f} | {raw_by.get(r['seed'], float('nan')):.4f} |"
            )
        lines.append("")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Validate ocdev headline numbers")
    ap.add_argument("--out", type=Path, default=VALIDATE_OUTPUT_ROOT)
    ap.add_argument("--skip-check1", action="store_true")
    ap.add_argument("--skip-check2", action="store_true")
    ap.add_argument("--skip-check3", action="store_true")
    ap.add_argument("--skip-check4", action="store_true")
    ap.add_argument("--nested-B", type=int, default=NESTED_B)
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    split_bundle = assert_digest()
    corpus = load_corpus_cache(androct_run2_output_dir())

    c1 = c2 = c3 = c4 = None
    if not args.skip_check1:
        print("[ocdev_validate] CHECK 1 …", flush=True)
        c1 = run_check1(out=out / "check1_bias", split_bundle=split_bundle, B=args.nested_B)
    else:
        p = out / "check1_bias" / "bias_stats.json"
        if p.is_file():
            import json

            c1 = json.loads(p.read_text())

    if not args.skip_check2:
        print("[ocdev_validate] CHECK 2 …", flush=True)
        c2 = run_check2(out=out / "check2_randominit")
    else:
        p = out / "check2_randominit" / "check2.json"
        if p.is_file():
            import json

            c2 = json.loads(p.read_text())

    if not args.skip_check3:
        print("[ocdev_validate] CHECK 3 …", flush=True)
        c3 = run_check3(
            out=out / "check3_splitB",
            split_bundle=split_bundle,
            tensors=corpus.tensors,
        )
    else:
        p = out / "check3_splitB" / "check3.json"
        if p.is_file():
            import json

            c3 = json.loads(p.read_text())

    if not args.skip_check4:
        print("[ocdev_validate] CHECK 4 …", flush=True)
        c4 = run_check4(out=out / "check4_s1norm", split_bundle=split_bundle)
    else:
        p = out / "check4_s1norm" / "check4.json"
        if p.is_file():
            import json

            c4 = json.loads(p.read_text())

    write_summary(out=out, digest=split_bundle.sha_list_digest, c1=c1, c2=c2, c3=c3, c4=c4)
    write_json(
        out / "run_meta.json",
        {"digest": split_bundle.sha_list_digest, "nested_B": args.nested_B},
    )
    print(f"[ocdev_validate] done → {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
