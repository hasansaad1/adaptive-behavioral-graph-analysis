"""Orchestrate ocdev Part A then Part B."""

from __future__ import annotations

import argparse
import csv
import json
import platform
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.apigraph.split import load_run3_split
from abrg.ocdev import (
    EXPECTED_SPLIT_DIGEST_PREFIX,
    OCDEV_OUTPUT_ROOT,
    OCPOOL_INCUMBENT,
    REF_ROWS,
    SEED,
    SIZE_FLOOR,
)
from abrg.ocdev.detectors import score_with_fitted
from abrg.ocdev.part_a import load_profiles, run_part_a
from abrg.ocdev.part_b import run_part_b


def _assert_digest(digest: str) -> None:
    if not digest.startswith(EXPECTED_SPLIT_DIGEST_PREFIX):
        raise SystemExit(f"STOP: digest {digest[:16]} != {EXPECTED_SPLIT_DIGEST_PREFIX}...")


def _best_from_part_a(part_a: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    trained = part_a.get("splitA", {}).get("trained", {})
    for fset, reds in trained.items():
        for red, blk in reds.items():
            for det, val in blk.items():
                if det in ("feature_set", "reduction", "pca"):
                    continue
                if isinstance(val, dict) and "auc" in val:
                    af = float(val["auc"]["auc_floor"])
                    rows.append(
                        {
                            "feature_set": fset,
                            "reduction": red,
                            "detector": det,
                            "auc_floor": af,
                            "gate": val.get("gate"),
                            "path": None,
                        }
                    )
                elif isinstance(val, dict) and "auc_floor_mean" in val:
                    af = float(val["auc_floor_mean"])
                    rows.append(
                        {
                            "feature_set": fset,
                            "reduction": red,
                            "detector": det,
                            "auc_floor": af,
                            "gate": val.get("gate"),
                            "path": None,
                        }
                    )
    rows.sort(key=lambda r: -r["auc_floor"])
    return rows


def _write_summary(out: Path, part_a: dict | None, part_b: dict | None) -> None:
    lines = ["# ocdev — SUMMARY", "", "## GATE outcomes first", ""]
    winners = []
    if part_a:
        best = _best_from_part_a(part_a)
        lines.append("### Part A (trained profiles, Split-A)")
        lines.append("")
        lines.append("| feature | reduction | detector | auc_floor | size | ocpool |")
        lines.append("|---|---|---|---:|:---:|:---:|")
        for r in best[:40]:
            g = r.get("gate") or {}
            cs = "Y" if g.get("clears_size_floor") else "N"
            co = "Y" if g.get("clears_ocpool") else "N"
            lines.append(
                f"| {r['feature_set']} | {r['reduction']} | {r['detector']} | {r['auc_floor']:.4f} | {cs} | {co} |"
            )
            if g.get("clears_ocpool"):
                winners.append(r)
        sb = part_a.get("splitB", {}).get("trained", {})
        if sb:
            lines += ["", "### Part A Split-B (mahalanobis primary, weighted)", ""]
            lines.append("| feature | weighted | pooled | size | ocpool |")
            lines.append("|---|---:|---:|:---:|:---:|")
            for fset, blk in sb.items():
                g = blk.get("gate") or {}
                lines.append(
                    f"| {fset} | {blk['weighted_mean_auc_floor']:.4f} | "
                    f"{blk['pooled_oof_auc']['auc_floor']:.4f} | "
                    f"{'Y' if g.get('clears_size_floor') else 'N'} | "
                    f"{'Y' if g.get('clears_ocpool') else 'N'} |"
                )
        ctrl = part_a.get("controls", {})
        if ctrl.get("raw_tensor_splitA"):
            raw = ctrl["raw_tensor_splitA"]["RAW_full"]["none"]
            lines += ["", "### Raw-tensor control (Split-A)", ""]
            for det in ("centroid_euclidean", "mahalanobis", "ocsvm_rbf"):
                if det not in raw:
                    continue
                v = raw[det]
                af = v["auc"]["auc_floor"] if "auc" in v else v.get("auc_floor_mean")
                lines.append(f"- RAW_full / {det}: {af:.4f}")
        if ctrl.get("random_init_splitA") and isinstance(ctrl["random_init_splitA"], dict) and "D0" in ctrl["random_init_splitA"]:
            lines += ["", "### Random-init GAE profiles (best per D*, Split-A)", ""]
            for fset, reds in ctrl["random_init_splitA"].items():
                none = reds.get("none", {})
                best_af = -1.0
                best_d = ""
                for det, v in none.items():
                    if det in ("feature_set", "reduction", "pca"):
                        continue
                    if isinstance(v, dict) and "auc" in v:
                        af = float(v["auc"]["auc_floor"])
                    elif isinstance(v, dict) and "auc_floor_mean" in v:
                        af = float(v["auc_floor_mean"])
                    else:
                        continue
                    if af > best_af:
                        best_af, best_d = af, det
                lines.append(f"- {fset}: {best_d} {best_af:.4f}")

    if part_b:
        lines += ["", "### Part B support-novelty (primary scores, raw)", ""]
        lines.append("| family | score | auc_floor | size | ocpool |")
        lines.append("|---|---|---:|:---:|:---:|")
        for fam, blk in part_b.items():
            if not isinstance(blk, dict):
                continue
            for key in ("S1", "S2", "S3_one", "S4", "S1_norm", "S2_norm"):
                if key not in blk or not isinstance(blk[key], dict) or "auc" not in blk[key]:
                    continue
                af = float(blk[key]["auc"]["auc_floor"])
                g = blk[key].get("gate") or {}
                lines.append(
                    f"| {fam} | {key} | {af:.4f} | "
                    f"{'Y' if g.get('clears_size_floor') else 'N'} | "
                    f"{'Y' if g.get('clears_ocpool') else 'N'} |"
                )
                if g.get("clears_ocpool"):
                    winners.append({"part": "B", "family": fam, "score": key, "auc_floor": af})

    lines += ["", "## Reference rows", "", "| reference | auc_floor |", "|---|---:|"]
    for k, v in REF_ROWS.items():
        lines.append(f"| {k} | {v} |")

    lines += [
        "",
        f"## Nested bootstrap",
        "",
        (
            f"- winners clearing OCPool {OCPOOL_INCUMBENT}: {len(winners)}"
            if winners
            else f"- no configuration cleared OCPool {OCPOOL_INCUMBENT}; nested bootstrap not run"
        ),
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reload_verify(artifacts: Path, tensors: dict, split_bundle: Any) -> dict[str, Any]:
    """Reload one detector + profile and match AUC."""
    dets = list((artifacts / "detectors").glob("trained__D3__none__mahalanobis__splitA__foldNA.joblib"))
    if not dets:
        return {"available": False}
    path = dets[0]
    payload = joblib.load(path)
    arrays, shas = load_profiles("trained_t22")
    sha_to_i = {s: i for i, s in enumerate(shas)}
    corpus = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(corpus.eligible)
    te = split["test_benign"] + split["test_malware"]
    te_idx = np.asarray([sha_to_i[a.sha256] for a in te], dtype=np.int64)
    tr_idx = np.asarray([sha_to_i[a.sha256] for a in split["train"]], dtype=np.int64)
    X = arrays["D3"]
    # Need train fit object already saved — rescoring test with fitted
    fitted = payload["fitted"]
    scores = score_with_fitted(fitted, X[te_idx], "mahalanobis")
    labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
    reloaded = _auc_with_bootstrap(scores, labels)
    # original from json
    jpath = (
        OCDEV_OUTPUT_ROOT
        / "partA_profiles"
        / "splitA_trained"
        / "trained__D3__none__mahalanobis__splitA__foldNA.json"
    )
    stored = json.loads(jpath.read_text())["auc"]["auc"] if jpath.is_file() else float("nan")
    return {
        "detector": str(path),
        "stored_auc": stored,
        "reloaded_auc": reloaded["auc"],
        "match": abs(stored - reloaded["auc"]) < 1e-5 if jpath.is_file() else False,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ocdev: one-class on profiles + support novelty")
    ap.add_argument("--out", type=Path, default=OCDEV_OUTPUT_ROOT)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--skip-partA", action="store_true")
    ap.add_argument("--skip-partB", action="store_true")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    artifacts = out / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    split_bundle = load_run3_split()
    _assert_digest(split_bundle.sha_list_digest)
    corpus = load_corpus_cache(androct_run2_output_dir())
    tensors = corpus.tensors

    pred_path = artifacts / "predictions.csv"
    mode = "a" if args.resume and pred_path.is_file() else "w"
    pred_f = pred_path.open(mode, newline="", encoding="utf-8")
    pred_w = csv.writer(pred_f)
    if pred_f.tell() == 0:
        pred_w.writerow(
            [
                "app_id",
                "true_label",
                "score",
                "part",
                "feature_set",
                "detector",
                "reduction",
                "split",
                "fold",
                "seed",
                "model_tag",
            ]
        )

    part_a = None
    if not args.skip_partA:
        print("[ocdev] PART A …", flush=True)
        part_a = run_part_a(
            split_bundle=split_bundle,
            tensors=tensors,
            out=out,
            artifacts=artifacts,
            pred_writer=pred_w,
            resume=args.resume,
        )
    elif (out / "partA_profiles" / "partA_summary.json").is_file():
        part_a = json.loads((out / "partA_profiles" / "partA_summary.json").read_text())

    part_b = None
    if not args.skip_partB:
        print("[ocdev] PART B …", flush=True)
        part_b = run_part_b(
            split_bundle=split_bundle,
            tensors_t22=tensors,
            out=out,
            artifacts=artifacts,
            pred_writer=pred_w,
        )
    elif (out / "partB_support" / "partB_summary.json").is_file():
        part_b = json.loads((out / "partB_support" / "partB_summary.json").read_text())

    pred_f.close()

    reload_v = {"available": False}
    if part_a:
        reload_v = _reload_verify(artifacts, tensors, split_bundle)
        print(f"[ocdev] reload verify {reload_v}", flush=True)

    cfg = {
        "experiment": "ocdev",
        "library_versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "platform": platform.platform(),
        },
        "split_digest": split_bundle.sha_list_digest,
        "seeds": list(range(42, 47)),
        "source_profiles": str(OCDEV_OUTPUT_ROOT.parent / "devread" / "artifacts" / "profiles"),
        "ladder_assignments": str(
            OCDEV_OUTPUT_ROOT.parent / "ladder" / "grouping" / "route_b_behavioral.json"
        ),
        "eps": 1e-12,
        "reload_verification": reload_v,
        "reference_rows": REF_ROWS,
    }
    (artifacts / "reproduce_config.json").write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    (artifacts / "reproduce.md").write_text(
        "# Reproduce ocdev\n\n```bash\npython -m abrg.ocdev --resume\n```\n",
        encoding="utf-8",
    )

    _write_summary(out, part_a, part_b)
    print(f"[ocdev] done → {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
