"""Orchestrate validation Checks 1–3."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abrg.apigraph.extract import extract_sequences
from abrg.validate import (
    EXPECTED_R0,
    EXPECTED_R1,
    HEADLINE_K,
    HEADLINE_VOCAB,
    NAIVE_CI,
    VALIDATE_OUTPUT_ROOT,
)
from abrg.validate.check2 import run_check2
from abrg.validate.check3 import run_check3
from abrg.validate.features import build_many
from abrg.validate.residual import check1_residualization
from abrg.validate.split import load_split_or_stop
from abrg.validate.vocab import assert_train_benign_only, rank_vocab


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def write_summary(
    *,
    out: Path,
    digest: str,
    check1: dict[str, Any],
    check2: dict[str, Any],
    check3: dict[str, Any],
) -> None:
    lines: list[str] = []
    lines.append("# Validation of OCPool residual 0.8141 — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_sha_digest: `{digest}`")
    lines.append("- cell: B_docfreq K=1000 · OCPool_mean")
    lines.append("")

    lines.append("## Thesis number")
    lines.append("")
    tc = check1["thesis_carries"]
    lines.append("| quantity | value |")
    lines.append("|---|---|")
    lines.append(f"| variant carried | `{tc['variant']}` |")
    lines.append(f"| AUC_floor | {tc['auc_floor']:.4f} |")
    lines.append(f"| direction | {tc['direction']} |")
    lines.append(
        f"| score-resample CI95_floor | "
        f"[{tc['ci95_floor'][0]:.4f}, {tc['ci95_floor'][1]:.4f}] |"
    )
    lines.append(
        f"| nested-bootstrap CI95_floor (B={check3['B']}) | "
        f"[{check3['auc_floor']['p2.5']:.4f}, {check3['auc_floor']['p97.5']:.4f}] |"
    )
    lines.append(f"| nested-bootstrap mean±std | "
                 f"{check3['auc_floor']['mean']:.4f} ± {check3['auc_floor']['std']:.4f} |")
    lines.append(f"| reason | {tc['reason']} |")
    lines.append("")
    lines.append(
        f"| delta R2−R1 | {check1['delta_R2_minus_R1']:.4f} |"
    )
    lines.append("")

    lines.append("## Check 1 — residualization")
    lines.append("")
    lines.append(
        "| variant | AUC_floor | direction | CI95_floor | R² | coef_oov | intercept |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for key in ("R0", "R1", "R2"):
        r = check1[key]
        coef = r.get("coef_oov", float("nan"))
        inter = r.get("coef_intercept", float("nan"))
        r2 = r.get("r2", float("nan"))
        lines.append(
            f"| {r['name']} | {r['auc']['auc_floor']:.4f} | {r['auc']['direction']} | "
            f"[{r['auc']['ci95_floor'][0]:.4f},{r['auc']['ci95_floor'][1]:.4f}] | "
            f"{r2 if r2==r2 else float('nan'):.4f} | "
            f"{coef if coef==coef else float('nan'):.4f} | "
            f"{inter if inter==inter else float('nan'):.4f} |"
        )
    r3 = check1["R3"]
    lines.append("")
    lines.append(
        f"- R3 train residual med (IQR): {r3['train_residual_dist']['median']:.4f} "
        f"({r3['train_residual_dist']['iqr']:.4f})"
    )
    lines.append(
        f"- R3 eval residual med (IQR): {r3['eval_residual_dist']['median']:.4f} "
        f"({r3['eval_residual_dist']['iqr']:.4f})"
    )
    lines.append(f"- R3 QQ train: {r3['qq_train']}")
    lines.append(f"- R3 QQ eval: {r3['qq_eval']}")
    ex = check1["oov_extrapolation"]
    lines.append(
        f"- oov train range: [{ex['train_benign_oov_range'][0]:.4f}, "
        f"{ex['train_benign_oov_range'][1]:.4f}]"
    )
    lines.append(
        f"- oov eval range: [{ex['eval_oov_range'][0]:.4f}, {ex['eval_oov_range'][1]:.4f}]"
    )
    lines.append(
        f"- eval extrapolation below/above: "
        f"{ex['eval_requires_extrapolation_below']}/"
        f"{ex['eval_requires_extrapolation_above']} "
        f"(frac below={ex['frac_eval_below_train_min']:.4f}, "
        f"above={ex['frac_eval_above_train_max']:.4f})"
    )
    lines.append(f"- expected R0≈{EXPECTED_R0} R1≈{EXPECTED_R1}")
    lines.append("")

    lines.append("## Check 2 — 3×3 grid (OCPool_mean R2_train_fit AUC_floor)")
    lines.append("")
    lines.append("| | K=300 | K=500 | K=1000 |")
    lines.append("|---|---|---|---|")
    for method in ("A_tfidf", "B_docfreq", "C_rawfreq"):
        cells = []
        for k in (300, 500, 1000):
            tag = f"{method}_K{k}"
            v = check2["headline_values_by_cell"][tag]
            cells.append(f"{v:.4f}")
        lines.append(f"| {method} | " + " | ".join(cells) + " |")
    ac = check2["across_cells"]
    lines.append("")
    lines.append(
        f"- across 9 cells: min={ac['min']:.4f} median={ac['median']:.4f} max={ac['max']:.4f}"
    )
    lines.append(
        f"- B_docfreq_K1000={check2['B_docfreq_K1000']:.4f} "
        f"is_max={check2['B_docfreq_K1000_is_max']} is_min={check2['B_docfreq_K1000_is_min']}"
    )
    lines.append("")
    lines.append("### Per-cell detail (coverage / oov floor / raw / R2)")
    lines.append("")
    lines.append(
        "| cell | cov_tr | cov_tb | cov_tm | oov_floor | mean_raw | mean_R2 | max_raw | max_R2 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for tag, cell in sorted(check2["cells"].items()):
        cov = cell["coverage"]
        fl = cell["floors"]
        lines.append(
            f"| {tag} | {cov['train_benign']['coverage_frac']:.4f} | "
            f"{cov['test_benign']['coverage_frac']:.4f} | "
            f"{cov['test_malware']['coverage_frac']:.4f} | "
            f"{fl['oov_rate']['auc_floor']:.4f} | "
            f"{cell['OCPool_mean']['raw']['auc']['auc_floor']:.4f} | "
            f"{cell['OCPool_mean']['R2_train_fit']['auc']['auc_floor']:.4f} | "
            f"{cell['OCPool_max']['raw']['auc']['auc_floor']:.4f} | "
            f"{cell['OCPool_max']['R2_train_fit']['auc']['auc_floor']:.4f} |"
        )
    lines.append("")

    lines.append("## Check 3 — nested bootstrap")
    lines.append("")
    lines.append(f"- B={check3['B']} (requested {check3['B_requested']})")
    lines.append(f"- runtime_sec={check3['runtime_sec']:.1f}")
    lines.append(
        f"- AUC_floor mean±std={check3['auc_floor']['mean']:.4f}±{check3['auc_floor']['std']:.4f}"
    )
    lines.append(
        f"- AUC_floor p2.5–p97.5=[{check3['auc_floor']['p2.5']:.4f}, "
        f"{check3['auc_floor']['p97.5']:.4f}]"
    )
    lines.append(
        f"- naive score-resample CI95={list(NAIVE_CI)}"
    )
    vs = check3["vocab_stability"]
    lines.append(
        f"- mean pairwise Jaccard={vs['mean_pairwise_jaccard']:.4f}"
    )
    lines.append(
        f"- callees in >90% bootstraps={vs['n_callees_in_gt90pct_bootstraps']} "
        f"(frac of K={vs['frac_vocab_stable_gt90pct']:.4f})"
    )
    lines.append("")

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[validate] wrote {out / 'SUMMARY.md'}", flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Validate OCPool residual 0.8141")
    p.add_argument("--output-dir", type=Path, default=VALIDATE_OUTPUT_ROOT)
    p.add_argument("--skip-check3", action="store_true")
    p.add_argument("--bootstrap-B", type=int, default=None)
    args = p.parse_args(argv)

    out = args.output_dir
    c1_dir = out / "check1_residualization"
    c2_dir = out / "check2_grid"
    c3_dir = out / "check3_bootstrap"
    for d in (c1_dir, c2_dir, c3_dir):
        d.mkdir(parents=True, exist_ok=True)

    bundle = load_split_or_stop()
    train_shas = [a.sha256 for a in bundle.train]
    test_b = [a.sha256 for a in bundle.test_benign]
    test_m = [a.sha256 for a in bundle.test_malware]
    all_apps = bundle.train + bundle.test_benign + bundle.test_malware

    assert_train_benign_only(
        train_shas, malware_shas=set(test_m), heldout_benign_shas=set(test_b)
    )

    print("[validate] load sequences (cache)", flush=True)
    sequences = extract_sequences(all_apps)

    # --- Check 1: headline B_docfreq K=1000 ---
    print("[validate] === CHECK 1 ===", flush=True)
    train_seqs = {s: sequences[s] for s in train_shas}
    vocab = rank_vocab(train_seqs, train_shas, method=HEADLINE_VOCAB, k=HEADLINE_K)
    tensors = build_many(
        sequences, vocab, bundle.by_sha, train_shas + test_b + test_m
    )
    check1 = check1_residualization(tensors, train_shas, test_b, test_m, pool="mean")
    _write_json(c1_dir / "check1_summary.json", check1)
    print(
        f"[validate/C1] R0={check1['R0']['auc']['auc_floor']:.4f} "
        f"R1={check1['R1']['auc']['auc_floor']:.4f} "
        f"R2={check1['R2']['auc']['auc_floor']:.4f} "
        f"delta(R2-R1)={check1['delta_R2_minus_R1']:.4f}",
        flush=True,
    )

    # --- Check 2 ---
    print("[validate] === CHECK 2 ===", flush=True)
    check2 = run_check2(
        sequences=sequences,
        by_sha=bundle.by_sha,
        train_shas=train_shas,
        test_b=test_b,
        test_m=test_m,
        out_dir=c2_dir,
    )

    # --- Check 3 ---
    if args.skip_check3:
        check3 = json.loads((c3_dir / "check3_summary.json").read_text(encoding="utf-8"))
    else:
        print("[validate] === CHECK 3 ===", flush=True)
        check3 = run_check3(
            sequences=sequences,
            by_sha=bundle.by_sha,
            train_shas=train_shas,
            test_b=test_b,
            test_m=test_m,
            out_dir=c3_dir,
            B=args.bootstrap_B,
        )

    write_summary(
        out=out,
        digest=bundle.sha_list_digest,
        check1=check1,
        check2=check2,
        check3=check3,
    )
    _write_json(
        out / "run_meta.json",
        {
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "sha_list_digest": bundle.sha_list_digest,
            "thesis_carries": check1["thesis_carries"],
        },
    )


if __name__ == "__main__":
    main()
