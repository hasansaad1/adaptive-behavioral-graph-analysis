"""K=1000 vocabulary controls A/B/C — coverage, oov floors, OCPool residual."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LinearRegression

from abrg.androct.run_gae_run2 import _auc_with_bootstrap
from abrg.apigraph import APIGRAPH_OUTPUT_ROOT
from abrg.apigraph.construct import (
    NODE_FEAT_DIM,
    STATIC_GLOBAL_DIM,
    build_graph_tensors,
    construction_stats,
)
from abrg.apigraph.extract import category_for_callee, extract_sequences
from abrg.apigraph.floors import compute_floors
from abrg.apigraph.models_stage4 import ocpool
from abrg.apigraph.split import load_run3_split
from abrg.apigraph.vocab import VOCAB_SOURCE_ASSERTION, coverage_table

K = 1000
CONTROL_DIRNAME = "vocab_control"


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def _write_vocab_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["rank", "callee", "document_frequency", "raw_frequency", "score", "category"],
        )
        w.writeheader()
        w.writerows(rows)


def _train_benign_stats(
    train_benign_seqs: dict[str, list[str]],
    train_benign_shas: list[str],
) -> tuple[Counter[str], Counter[str], dict[str, float]]:
    """df, raw corpus frequency, and TF-IDF scores — train-benign only."""
    assert set(train_benign_seqs.keys()) == set(train_benign_shas)
    N = len(train_benign_shas)
    assert N == 562
    df: Counter[str] = Counter()
    raw: Counter[str] = Counter()
    app_tf: dict[str, dict[str, float]] = {}
    for sha in train_benign_shas:
        seq = train_benign_seqs[sha]
        if not seq:
            app_tf[sha] = {}
            continue
        counts = Counter(seq)
        L = float(len(seq))
        app_tf[sha] = {c: cnt / L for c, cnt in counts.items()}
        for c, cnt in counts.items():
            df[c] += 1
            raw[c] += cnt

    tfidf_scores: dict[str, float] = {}
    for c, dfc in df.items():
        idf = math.log(N / dfc)
        tfidfs = [app_tf[sha][c] * idf for sha in train_benign_shas if c in app_tf[sha]]
        tfidf_scores[c] = (sum(tfidfs) / len(tfidfs)) * dfc
    return df, raw, tfidf_scores


def build_control_vocabs(
    train_benign_seqs: dict[str, list[str]],
    train_benign_shas: list[str],
    *,
    out_dir: Path,
    k: int = K,
) -> dict[str, Any]:
    """
    Vocab A: TF-IDF score (current) top-K train-benign
    Vocab B: document frequency top-K train-benign (no TF-IDF)
    Vocab C: raw corpus frequency top-K train-benign (no app-level labels in ranking;
             frequency pooled over the train-benign partition as a bag of calls)
    """
    df, raw, tfidf_scores = _train_benign_stats(train_benign_seqs, train_benign_shas)

    defs = {
        "A_tfidf": {
            "description": "train-benign TF-IDF score (current): mean_tfidf * df",
            "ranked": sorted(tfidf_scores.items(), key=lambda kv: (-kv[1], kv[0])),
            "score_key": "tfidf",
        },
        "B_docfreq": {
            "description": "train-benign document frequency only (no TF-IDF)",
            "ranked": sorted(df.items(), key=lambda kv: (-kv[1], kv[0])),
            "score_key": "df",
        },
        "C_rawfreq": {
            "description": (
                "train-benign raw corpus frequency (sum of call counts); "
                "no app-level labels; no per-app weighting"
            ),
            "ranked": sorted(raw.items(), key=lambda kv: (-kv[1], kv[0])),
            "score_key": "raw",
        },
    }

    vocabs: dict[str, list[str]] = {}
    meta: dict[str, Any] = {"integrity": VOCAB_SOURCE_ASSERTION, "K": k, "variants": {}}
    for name, spec in defs.items():
        rows = []
        for rank, (callee, score) in enumerate(spec["ranked"][:k], start=1):
            rows.append(
                {
                    "rank": rank,
                    "callee": callee,
                    "document_frequency": int(df[callee]),
                    "raw_frequency": int(raw[callee]),
                    "score": float(score),
                    "category": category_for_callee(callee),
                }
            )
        vocabs[name] = [r["callee"] for r in rows]
        _write_vocab_csv(out_dir / f"vocab_{name}_K{k}.csv", rows)
        overlap_a = (
            len(set(vocabs[name]) & set(vocabs["A_tfidf"])) / k
            if "A_tfidf" in vocabs
            else float("nan")
        )
        meta["variants"][name] = {
            "description": spec["description"],
            "score_key": spec["score_key"],
            "n": len(rows),
            "overlap_with_A": overlap_a if name != "A_tfidf" else 1.0,
        }
        print(f"[vocab_control] wrote {name} n={len(rows)}", flush=True)

    # pairwise overlaps
    names = list(vocabs.keys())
    overlaps = {}
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            overlaps[f"{a}_vs_{b}"] = len(set(vocabs[a]) & set(vocabs[b])) / k
    meta["pairwise_overlap_frac"] = overlaps
    _write_json(out_dir / "vocab_meta.json", meta)
    return {"vocabs": vocabs, "meta": meta}


def _build_tensors(
    vocab: list[str],
    sequences: dict[str, list[str]],
    by_sha: dict[str, Any],
    shas: list[str],
) -> dict[str, dict[str, Any]]:
    tensors: dict[str, dict[str, Any]] = {}
    for i, sha in enumerate(shas):
        tensors[sha] = build_graph_tensors(sequences[sha], vocab, app=by_sha[sha])
        if (i + 1) % 500 == 0:
            print(f"  … graphs {i+1}/{len(shas)}", flush=True)
    return tensors


def residualize_scores_vs_oov(
    scores: list[float],
    oov_rates: list[float],
    labels: list[int],
) -> dict[str, Any]:
    """
    OLS on the evaluation set: score ~ 1 + oov_rate; AUC on residuals.
    Reports whether class separation survives after removing linear oov effect.
    """
    y = np.asarray(scores, dtype=np.float64)
    x = np.asarray(oov_rates, dtype=np.float64).reshape(-1, 1)
    mask = np.isfinite(y) & np.isfinite(x.ravel())
    y_m, x_m = y[mask], x[mask]
    labels_m = [labels[i] for i, m in enumerate(mask) if m]
    if len(y_m) < 3 or len(set(labels_m)) < 2:
        return {"auc": {"auc_floor": float("nan")}, "coef": None}

    reg = LinearRegression().fit(x_m, y_m)
    resid = (y_m - reg.predict(x_m)).tolist()
    auc = _auc_with_bootstrap(resid, labels_m)
    # also raw for comparison on same mask
    auc_raw = _auc_with_bootstrap(y_m.tolist(), labels_m)
    return {
        "method": "OLS residual: score ~ 1 + oov_rate (fit on eval set)",
        "coef_intercept": float(reg.intercept_),
        "coef_oov": float(reg.coef_[0]),
        "r2": float(reg.score(x_m, y_m)),
        "n": int(mask.sum()),
        "auc_raw_same_mask": auc_raw,
        "auc_residual": auc,
    }


def main() -> None:
    out = APIGRAPH_OUTPUT_ROOT / CONTROL_DIRNAME
    out.mkdir(parents=True, exist_ok=True)

    print("[vocab_control] split assert", flush=True)
    bundle = load_run3_split()
    train_shas = [a.sha256 for a in bundle.train]
    test_b = [a.sha256 for a in bundle.test_benign]
    test_m = [a.sha256 for a in bundle.test_malware]
    all_apps = bundle.train + bundle.test_benign + bundle.test_malware
    all_shas = train_shas + test_b + test_m

    print("[vocab_control] sequences (cache)", flush=True)
    sequences = extract_sequences(all_apps)
    train_benign_seqs = {s: sequences[s] for s in train_shas}

    print("[vocab_control] build A/B/C", flush=True)
    built = build_control_vocabs(train_benign_seqs, train_shas, out_dir=out, k=K)
    partitions = {
        "train_benign": train_shas,
        "test_benign": test_b,
        "test_malware": test_m,
    }
    coverage = coverage_table(built["vocabs"], sequences, partitions)
    _write_json(out / "coverage.json", coverage)

    per_variant: dict[str, Any] = {}
    tensors_by_var: dict[str, dict[str, dict[str, Any]]] = {}

    for name, vocab in built["vocabs"].items():
        print(f"[vocab_control] construct + floors {name}", flush=True)
        tensors = _build_tensors(vocab, sequences, bundle.by_sha, all_shas)
        tensors_by_var[name] = tensors
        floors = compute_floors(tensors, test_b, test_m)
        stats = construction_stats(
            tensors,
            {
                "train_benign": train_shas,
                "test_benign": test_b,
                "test_malware": test_m,
            },
        )
        per_variant[name] = {
            "coverage": coverage[name],
            "floors": floors,
            "oov_rate_floor": floors["oov_rate"]["auc_floor"],
            "oov_rate_direction": floors["oov_rate"]["direction"],
            "graph_stats": stats,
            "node_feat_dim": NODE_FEAT_DIM,
            "static_global_dim": STATIC_GLOBAL_DIM,
        }
        _write_json(out / f"{name}_floors.json", floors)
        _write_json(out / f"{name}_stats.json", stats)
        print(
            f"  oov_rate floor={floors['oov_rate']['auc_floor']:.4f} "
            f"({floors['oov_rate']['direction']})",
            flush=True,
        )

    # pick closest oov_rate floor to 0.5
    pick = min(
        per_variant.keys(),
        key=lambda n: abs(float(per_variant[n]["oov_rate_floor"]) - 0.5),
    )
    print(
        f"[vocab_control] selected={pick} "
        f"|oov_floor-0.5|={abs(per_variant[pick]['oov_rate_floor'] - 0.5):.4f}",
        flush=True,
    )

    tensors = tensors_by_var[pick]
    print(f"[vocab_control] OCPool on {pick}", flush=True)
    ocpool_results = {}
    for pool in ("add", "mean", "max"):
        row = ocpool(tensors, train_shas, test_b, test_m, pool)
        ocpool_results[pool] = row
        _write_json(out / f"{pick}_ocpool_{pool}.json", row)
        print(
            f"  OCPool_{pool} auc_floor={row['auc']['auc_floor']:.4f} "
            f"({row['auc']['direction']})",
            flush=True,
        )

    # residual: OCPool_mean after regressing out oov_rate
    print("[vocab_control] OCPool_mean residual vs oov_rate", flush=True)
    mean_row = ocpool_results["mean"]
    # rebuild scores
    from sklearn.svm import OneClassSVM

    def pool_mean(sha: str) -> np.ndarray:
        x = tensors[sha]["x"].detach().cpu().numpy()
        return np.concatenate([x.mean(axis=0), tensors[sha]["static_global"].detach().cpu().numpy()])

    clf = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale").fit(
        np.stack([pool_mean(s) for s in train_shas])
    )
    sc_tb = (-clf.decision_function(np.stack([pool_mean(s) for s in test_b]))).tolist()
    sc_tm = (-clf.decision_function(np.stack([pool_mean(s) for s in test_m]))).tolist()
    scores = sc_tb + sc_tm
    oovs = [float(tensors[s]["oov_rate"]) for s in test_b + test_m]
    labels = [0] * len(test_b) + [1] * len(test_m)
    residual = residualize_scores_vs_oov(scores, oovs, labels)
    _write_json(out / f"{pick}_ocpool_mean_residual_oov.json", residual)
    print(
        f"  residual auc_floor={residual['auc_residual']['auc_floor']:.4f} "
        f"r2={residual['r2']:.4f} coef_oov={residual['coef_oov']:.4f}",
        flush=True,
    )

    summary = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "K": K,
        "integrity": VOCAB_SOURCE_ASSERTION,
        "variants": {
            n: {
                "description": built["meta"]["variants"][n]["description"],
                "overlap_with_A": built["meta"]["variants"][n]["overlap_with_A"],
                "coverage": {
                    p: {
                        "coverage_frac": per_variant[n]["coverage"][p]["coverage_frac"],
                        "oov_frac": per_variant[n]["coverage"][p]["oov_frac"],
                    }
                    for p in ("train_benign", "test_benign", "test_malware")
                },
                "oov_rate_floor": per_variant[n]["oov_rate_floor"],
                "oov_rate_direction": per_variant[n]["oov_rate_direction"],
                "floors_auc_floor": {
                    k: per_variant[n]["floors"][k]["auc_floor"]
                    for k in per_variant[n]["floors"]
                },
            }
            for n in per_variant
        },
        "pairwise_overlap_frac": built["meta"]["pairwise_overlap_frac"],
        "selected_for_ocpool": pick,
        "selection_rule": "argmin |oov_rate_floor - 0.5|",
        "selected_floors": per_variant[pick]["floors"],
        "ocpool": {
            pool: {
                "auc_floor": ocpool_results[pool]["auc"]["auc_floor"],
                "auc": ocpool_results[pool]["auc"]["auc"],
                "direction": ocpool_results[pool]["auc"]["direction"],
                "ci95_floor": ocpool_results[pool]["auc"]["ci95_floor"],
                "leak_spearman": ocpool_results[pool]["leak_spearman"],
            }
            for pool in ocpool_results
        },
        "ocpool_mean_residual_oov": residual,
    }
    _write_json(out / "summary.json", summary)
    _write_report_md(out, summary)
    print(f"[vocab_control] done → {out}", flush=True)


def _write_report_md(out: Path, summary: dict[str, Any]) -> None:
    lines: list[str] = []
    lines.append("# K=1000 vocabulary controls A/B/C")
    lines.append("")
    lines.append(f"- generated_utc: {summary['generated_utc']}")
    lines.append(f"- K: {summary['K']}")
    lines.append(f"- integrity: {summary['integrity']}")
    lines.append("")
    lines.append("## Definitions")
    lines.append("")
    lines.append("| vocab | description | overlap vs A |")
    lines.append("|---|---|---|")
    for name, v in summary["variants"].items():
        # description from summary nested — need from variants
        desc = {
            "A_tfidf": "train-benign TF-IDF (current)",
            "B_docfreq": "train-benign document frequency",
            "C_rawfreq": "train-benign raw corpus frequency (no labels)",
        }[name]
        lines.append(f"| {name} | {desc} | {v['overlap_with_A']:.3f} |")
    lines.append("")
    lines.append("## Coverage (fraction of call events in vocabulary)")
    lines.append("")
    lines.append("| vocab | train_benign | test_benign | test_malware |")
    lines.append("|---|---|---|---|")
    for name, v in summary["variants"].items():
        c = v["coverage"]
        lines.append(
            f"| {name} | {c['train_benign']['coverage_frac']:.4f} | "
            f"{c['test_benign']['coverage_frac']:.4f} | "
            f"{c['test_malware']['coverage_frac']:.4f} |"
        )
    lines.append("")
    lines.append("## OOV rate floor")
    lines.append("")
    lines.append("| vocab | oov_rate floor | direction | |floor−0.5| |")
    lines.append("|---|---|---|---|")
    for name, v in summary["variants"].items():
        dist = abs(float(v["oov_rate_floor"]) - 0.5)
        lines.append(
            f"| {name} | {v['oov_rate_floor']:.4f} | {v['oov_rate_direction']} | {dist:.4f} |"
        )
    lines.append("")
    pick = summary["selected_for_ocpool"]
    lines.append(f"## Selected: `{pick}` (oov_rate floor closest to 0.5)")
    lines.append("")
    lines.append("### Floors")
    lines.append("")
    lines.append("| metric | auc_floor | direction |")
    lines.append("|---|---|---|")
    for metric, block in summary["selected_floors"].items():
        lines.append(
            f"| {metric} | {block['auc_floor']:.4f} | {block['direction']} |"
        )
    lines.append("")
    lines.append("### OCPool")
    lines.append("")
    lines.append("| pool | auc_floor | direction | ci95_floor |")
    lines.append("|---|---|---|---|")
    for pool, row in summary["ocpool"].items():
        ci = row["ci95_floor"]
        lines.append(
            f"| {pool} | {row['auc_floor']:.4f} | {row['direction']} | "
            f"[{ci[0]:.4f},{ci[1]:.4f}] |"
        )
    lines.append("")
    lines.append("### OCPool_mean Spearman")
    leak = summary["ocpool"]["mean"]["leak_spearman"]
    lines.append(
        f"- inv={leak['in_vocab_events']:.3f} tot={leak['total_events']:.3f} "
        f"act={leak['active_nodes']:.3f} edg={leak['edge_count']:.3f} "
        f"dens={leak['density']:.3f} stat={leak['static_norm']:.3f}"
    )
    lines.append("")
    r = summary["ocpool_mean_residual_oov"]
    lines.append("### OCPool_mean after regressing out oov_rate")
    lines.append("")
    lines.append(f"- method: {r['method']}")
    lines.append(f"- coef_oov: {r['coef_oov']:.6f}")
    lines.append(f"- intercept: {r['coef_intercept']:.6f}")
    lines.append(f"- R²: {r['r2']:.4f}")
    lines.append(
        f"- auc_floor raw (same mask): {r['auc_raw_same_mask']['auc_floor']:.4f} "
        f"({r['auc_raw_same_mask']['direction']})"
    )
    lines.append(
        f"- auc_floor residual: {r['auc_residual']['auc_floor']:.4f} "
        f"({r['auc_residual']['direction']}) "
        f"ci95=[{r['auc_residual']['ci95_floor'][0]:.4f},"
        f"{r['auc_residual']['ci95_floor'][1]:.4f}]"
    )
    lines.append("")
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
