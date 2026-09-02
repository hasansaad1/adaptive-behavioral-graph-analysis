"""Assemble Run 6 top-level SUMMARY from part1–3 outputs."""

from __future__ import annotations

import json
from pathlib import Path

from abrg.androct.paths import androct_run6_output_dir


def main() -> None:
    root = androct_run6_output_dir()
    p1 = json.loads((root / "part1_ablation" / "comparison.json").read_text())
    p2 = json.loads((root / "part2_geometry" / "comparison.json").read_text())
    p3 = json.loads((root / "part3_armB" / "comparison.json").read_text())

    lines = [
        "# AndroCT Run 6 — SUMMARY (three independent parts)",
        "",
        "Numbers only. Parts are independent; do not merge.",
        "",
        "## Part 1 — supervised ablation (HGB full AUC_floor)",
        "| condition | HGB full | Δ | LR full | Δ |",
        "|---|---:|---:|---:|---:|",
    ]
    order = [
        "a_baseline",
        "b_crypto_zeroed",
        "b2_crypto_features_only",
        "c_file_io_zeroed",
        "d_crypto_and_file_io_zeroed",
        "e_control_notifications_zeroed",
        "f_control_process_zeroed",
    ]
    for c in order:
        h = p1["conditions"][c]["modes"]["full"]["models"]["hist_gradient_boosting"]
        lr = p1["conditions"][c]["modes"]["full"]["models"]["logistic_regression"]
        lines.append(
            f"| {c} | {h['auc_floor']:.4f} | {h['delta_auc_floor_vs_baseline']:+.4f} | "
            f"{lr['auc_floor']:.4f} | {lr['delta_auc_floor_vs_baseline']:+.4f} |"
        )
    ca = p1["crypto_act_v_frac"]
    lines.extend(
        [
            "",
            f"- crypto:act_v_frac benign med/IQR="
            f"{ca['benign']['median']:.4f}/{ca['benign']['iqr']:.4f}; "
            f"malware={ca['malware']['median']:.4f}/{ca['malware']['iqr']:.4f}",
            f"- Spearman(crypto:act_v_frac, TLS share)="
            f"{p1['spearman_crypto_act_v_frac_vs_tls_caller_share']['rho']:.4f}",
            "",
            "## Part 2 — geometry",
        ]
    )
    rr = p2["ratio_test_benign_over_test_malware"]
    lines.append(
        f"- pairwise cosine ratio test_ben/test_mal: raw_mean={rr['raw_mean']:.4f} "
        f"raw_med={rr['raw_median']:.4f} | l2_mean={rr['l2norm_mean']:.4f} "
        f"l2_med={rr['l2norm_median']:.4f}"
    )
    for tag, block in p2["centroid_distance"].items():
        ab = block["auc_distance_as_score"]
        lines.append(
            f"- centroid ({tag}): ben_med={block['test_benign']['median']:.4f} "
            f"mal_med={block['test_malware']['median']:.4f} "
            f"higher={block['higher_median_distance_class']} "
            f"AUC_floor={ab['auc_floor']:.4f}"
        )
    for name, p in p2["pca"].items():
        lines.append(f"- PCA 90% {name}: {p['n_components_90pct_variance']} comps")

    lines.extend(["", "## Part 3 — Arm B N=8 (primary, no floor)"])
    prim = p3["primary"]
    for how, ag in prim["aggregation"].items():
        ab = ag["auc"]
        lines.append(
            f"- agg={how}: AUC_floor={ab['auc_floor']:.4f} "
            f"CI=[{ab['ci95_floor'][0]:.4f},{ab['ci95_floor'][1]:.4f}] "
            f"inverted={ag['recon_error']['benign_malware_error_direction_inverted']} "
            f"below_floor={ag['arm_below_highest_floor']}"
        )
    sens = p3["sensitivity_floor_320"]
    ex = sens["exclusion"]
    lines.extend(
        [
            "",
            "## Part 3 — SENSITIVITY (mapped≥320, not primary)",
            f"- exclusion B={ex['benign_exclusion_rate']:.4f} M={ex['malware_exclusion_rate']:.4f}",
        ]
    )
    for how, ag in sens["aggregation"].items():
        ab = ag["auc"]
        lines.append(
            f"- agg={how}: AUC_floor={ab['auc_floor']:.4f} "
            f"inverted={ag['recon_error']['benign_malware_error_direction_inverted']}"
        )
    lines.extend(
        [
            "",
            "Per-part detail: `part1_ablation/SUMMARY.md`, `part2_geometry/SUMMARY.md`, "
            "`part3_armB/SUMMARY.md`.",
        ]
    )
    (root / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
