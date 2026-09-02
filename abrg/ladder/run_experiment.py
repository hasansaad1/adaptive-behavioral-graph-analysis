"""Supervision ladder experiment orchestrator."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abrg.apigraph.split import load_run3_split
from abrg.kernels.load import assert_split_digest, load_t22
from abrg.ladder import (
    LADDER_OUTPUT_ROOT,
    MODES,
    MODELS,
    REF_ROWS,
    SEEDS,
    SIZE_FLOOR_REF,
)
from abrg.ladder.grouping import run_grouping
from abrg.ladder.rungs import run_rung1, run_rung2


def _fmt_ci(ci: list[float] | tuple[float, float] | None) -> str:
    if not ci:
        return "—"
    return f"[{ci[0]:.4f}, {ci[1]:.4f}]"


def _hgb_row(
    rung: str,
    assumption: str,
    mode: str,
    block: dict[str, Any],
    floor: float | None,
) -> str:
    auc = block["auc"]
    ms = block.get("multi_seed")
    if ms:
        mean_std = f"{ms['mean_auc_floor']:.4f} ± {ms['std_auc_floor']:.4f}"
    else:
        mean_std = f"{auc['auc_floor']:.4f}"
    ci = _fmt_ci(auc.get("ci95_floor"))
    floor_s = f"{floor:.4f}" if floor is not None else "—"
    return (
        f"| {rung} | {assumption} | hist_gradient_boosting | {mode} | "
        f"{mean_std} | {ci} | {floor_s} |"
    )


def write_summary(
    out: Path,
    *,
    grouping: dict[str, Any],
    rung1: dict[str, Any],
    rung2: dict[str, Any],
    digest: str,
    harness_stopped: bool,
) -> None:
    lines = [
        "# Supervision ladder — generalization to unseen malware groups",
        "",
        f"- UTC: {datetime.now(timezone.utc).isoformat()}",
        f"- split digest: `{digest[:16]}…`",
        f"- tensors: T22 run2 corpus cache (22×10 nodes + adjacency)",
        f"- grouping: {grouping['summary']['used_for_rung2']} "
        f"(Ward k={grouping['summary']['route_b_ward_k']})",
        f"- Route A VT: available={grouping['route_a']['available']}",
        "",
        "## Ladder table (HistGradientBoosting)",
        "",
        "| rung | assumption | model | mode | AUC (mean ± std) | CI | floor on that population |",
        "|---|---|---|---|---:|---|---:|",
    ]

    for mode in MODES:
        b = rung1["modes"][mode]["models"]["hist_gradient_boosting"]
        floor = rung1["modes"][mode]["mapped_event_floor"]["auc_floor"]
        lines.append(_hgb_row("1", "supervised_random_split", mode, b, floor))

    beh = rung2["behavioral"]
    for mode in MODES:
        agg = beh["aggregate"][mode]["hist_gradient_boosting"]
        mean_std = (
            f"{agg['mean_auc_floor']:.4f} ± {agg['std_auc_floor']:.4f} "
            f"(w={agg['weighted_mean_auc_floor']:.4f})"
        )
        pooled = beh["pooled_oof_hgb_full"] if mode == "full" else None
        ci = _fmt_ci(pooled.get("ci95_floor") if pooled else None)
        # representative floor: mean of per-fold mapped-event floors
        fold_floors = [
            f["mapped_event_floor"]["auc_floor"]
            for f in beh["folds"]
            if mode == "full"
        ]
        mf = float(sum(fold_floors) / len(fold_floors)) if fold_floors else None
        floor_s = f"{mf:.4f}" if mf is not None else "—"
        lines.append(
            f"| 2 | group_holdout_behavioral | hist_gradient_boosting | {mode} | "
            f"{mean_std} | {ci} | {floor_s} |"
        )

    rand = rung2["random"]
    for mode in MODES:
        agg = rand["aggregate"][mode]["hist_gradient_boosting"]
        mean_std = (
            f"{agg['mean_auc_floor']:.4f} ± {agg['std_auc_floor']:.4f} "
            f"(w={agg['weighted_mean_auc_floor']:.4f})"
        )
        fold_floors = [
            f["mapped_event_floor"]["auc_floor"]
            for f in rand["folds"]
            if mode == "full"
        ]
        mf = float(sum(fold_floors) / len(fold_floors)) if fold_floors else None
        floor_s = f"{mf:.4f}" if mf is not None else "—"
        lines.append(
            f"| 2-control | random_group_holdout | hist_gradient_boosting | {mode} | "
            f"{mean_std} | — | {floor_s} |"
        )

    lines.extend(
        [
            "",
            "## Rung 3 reference (one-class, not re-run)",
            "",
            "| rung | assumption | model | mode | AUC | CI | floor |",
            "|---|---|---|---|---:|---|---:|",
            f"| 3 | benign_only_one_class | OCPool_mean | pooled | "
            f"{REF_ROWS['OCPool_mean_raw']:.4f} raw / {REF_ROWS['OCPool_mean_R2']:.4f} R2 | "
            f"{_fmt_ci(REF_ROWS['OCPool_mean_R2_nested_CI'])} | {SIZE_FLOOR_REF:.4f} |",
            "",
            "## Harness (rung 1 vs Run 3.5)",
            "",
        ]
    )
    if rung1.get("harness"):
        for c in rung1["harness"]["checks"]:
            lines.append(
                f"- {c['mode']}: ref={c['reference_auc_floor']:.4f} "
                f"got={c['got_auc_floor']:.4f} delta={c['delta']:.4f} "
                f"ok={c['within_tolerance']}"
            )
    if harness_stopped:
        lines.append("- **STOP:** harness tolerance exceeded; rung 2 numbers may be invalid.")

    lines.extend(["", "## GATE", ""])
    r1_full = rung1["modes"]["full"]["models"]["hist_gradient_boosting"]["auc"]["auc_floor"]
    r2_full = beh["aggregate"]["full"]["hist_gradient_boosting"]["mean_auc_floor"]
    rand_full = rand["aggregate"]["full"]["hist_gradient_boosting"]["mean_auc_floor"]
    clears = [
        f["modes"]["full"]["hist_gradient_boosting"]["auc"]["auc_floor"]
        >= f["mapped_event_floor"]["auc_floor"]
        for f in beh["folds"]
    ]
    n_clear = sum(clears)
    lines.append(
        f"- Rung 2 behavioral folds clearing own mapped-event floor (HGB full): "
        f"{n_clear}/{len(clears)}"
    )
    lines.append(f"- Rung 1 HGB full auc_floor: {r1_full:.4f}")
    lines.append(f"- Rung 2 behavioral mean fold auc_floor (HGB full): {r2_full:.4f}")
    lines.append(f"- Gap rung1 − rung2: {r1_full - r2_full:.4f}")
    lines.append(
        f"- Rung 2 random-group mean fold auc_floor (HGB full): {rand_full:.4f}"
    )
    lines.append(
        f"- Gap rung2 − rung3 reference R2: {r2_full - REF_ROWS['OCPool_mean_R2']:.4f}"
    )
    lines.append(
        f"- Leakage–AUC correlation (behavioral, HGB full): "
        f"{beh.get('leakage_auc_correlation_hgb_full', float('nan')):.4f}"
    )

    lines.extend(["", "## Per-fold detail (behavioral group holdout, HGB full)", ""])
    lines.append(
        "| fold | n_malware | auc_floor | mapped_floor | mean_pairwise_cosine | clears_floor |"
    )
    lines.append("|---:|---:|---:|---:|---:|---|")
    for f in beh["folds"]:
        auc_f = f["modes"]["full"]["hist_gradient_boosting"]["auc"]["auc_floor"]
        mf = f["mapped_event_floor"]["auc_floor"]
        sim = f["leakage"]["mean_pairwise_cosine"]
        lines.append(
            f"| {f['group_id']} | {f['n_malware_holdout']} | {auc_f:.4f} | {mf:.4f} | "
            f"{sim:.4f} | {auc_f >= mf} |"
        )

    lines.extend(["", "## Random-group control per-fold (HGB full)", ""])
    lines.append("| fold | n_malware | auc_floor | mapped_floor |")
    lines.append("|---:|---:|---:|---:|")
    for f in rand["folds"]:
        auc_f = f["modes"]["full"]["hist_gradient_boosting"]["auc"]["auc_floor"]
        mf = f["mapped_event_floor"]["auc_floor"]
        lines.append(
            f"| {f['group_id']} | {f['n_malware_holdout']} | {auc_f:.4f} | {mf:.4f} |"
        )

    lines.extend(["", "## Grouping (Route B Ward cluster profiles)", ""])
    ward_profiles = grouping["route_b"]["ward"]["profiles"]
    for cid, prof in sorted(ward_profiles.items(), key=lambda x: int(x[0])):
        lines.append(
            f"- cluster {cid}: n={prof['n']} median_mapped={prof['median_mapped_events']:.1f}"
        )

    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Supervision ladder experiment")
    ap.add_argument("--out", type=Path, default=LADDER_OUTPUT_ROOT)
    ap.add_argument("--skip-rung2", action="store_true", help="Only grouping + rung1")
    ap.add_argument("--skip-rung1", action="store_true", help="Skip rung1 harness")
    ap.add_argument("--skip-grouping", action="store_true", help="Reuse grouping/*.json")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    split_b = load_run3_split()
    assert_split_digest(split_b.sha_list_digest)
    t22, _ = load_t22()
    tensors = t22
    malware_shas = [a.sha256 for a in split_b.test_malware]

    print("[ladder] Stage 1 — malware grouping", flush=True)
    grouping_path = out / "grouping" / "grouping_summary.json"
    if args.skip_grouping and grouping_path.is_file():
        route_b = json.loads(
            (out / "grouping" / "route_b_behavioral.json").read_text(encoding="utf-8")
        )
        route_a = json.loads(
            (out / "grouping" / "route_a_vt_check.json").read_text(encoding="utf-8")
        )
        grouping = {
            "route_a": route_a,
            "route_b": route_b,
            "summary": json.loads(grouping_path.read_text(encoding="utf-8")),
        }
    else:
        grouping = run_grouping(
            tensors, malware_shas, split_b.by_sha, out / "grouping"
        )

    rung1: dict[str, Any] = {}
    harness_stopped = False
    if not args.skip_rung1:
        print("[ladder] Rung 1 — supervised random split (harness)", flush=True)
        rung1 = run_rung1(tensors, split_b, out / "rung1")
        harness_stopped = bool(rung1.get("harness", {}).get("stop"))
        if harness_stopped:
            print(
                "[ladder] STOP: rung1 harness check failed — see rung1/HARNESS_FAIL.json",
                flush=True,
            )
    else:
        rung1_path = out / "rung1" / "rung1.json"
        if rung1_path.is_file():
            rung1 = json.loads(rung1_path.read_text(encoding="utf-8"))

    rung2_result: dict[str, Any] = {}
    if not args.skip_rung2 and not harness_stopped:
        print("[ladder] Rung 2 — group holdout + random control", flush=True)
        rung2_result = run_rung2(
            tensors,
            split_b,
            grouping["route_b"],
            out / "rung2",
            out / "control",
        )
    elif harness_stopped:
        print("[ladder] skipping rung2 due to harness failure", flush=True)

    meta = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "split_digest": split_b.sha_list_digest,
        "n_malware": len(malware_shas),
        "seeds_hgb": list(SEEDS),
        "grouping_route": grouping["summary"]["used_for_rung2"],
        "harness_stopped": harness_stopped,
    }
    (out / "reproduce_config.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    write_summary(
        out,
        grouping=grouping,
        rung1=rung1,
        rung2=rung2_result,
        digest=split_b.sha_list_digest,
        harness_stopped=harness_stopped,
    )

    print(f"[ladder] done → {out}", flush=True)
    return 1 if harness_stopped else 0


if __name__ == "__main__":
    raise SystemExit(main())
