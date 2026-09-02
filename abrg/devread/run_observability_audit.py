"""
Observability audit: 22-node GRAPH_CATEGORY_UNIVERSE occupancy, classification,
KS cross-check (D-2), and restricted-coordinate recomputations (4b–4d).

Measurement + documentation only — no retraining, no new corpora.
"""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from abrg.androct.paths import androct_run2_output_dir
from abrg.androct.run2_corpus import load_corpus_cache
from abrg.androct.run_gae_run2 import _auc_with_bootstrap, split_apps
from abrg.chapter_b.config import EXPORT_ROOT
from abrg.chapter_b.ingest import load_sessions, mapped_and_total, pass_sessions
from abrg.devread.run_d1_sparse_aggregation import _score_matrix
from abrg.devread.run_d2_higher_criticism import (
    D1_L2_REF,
    _compute_ladder_matrix,
    _empirical_pvalues,
    _eval_scores,
    _load_context,
)
from abrg.features import feature_vector_labels
from abrg.ocdev.part_a import load_profiles
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "results"
D2_SUMMARY = REPO / "abrg/output/androct_2017/d2_higher_criticism/summary.json"
CHECK3 = REPO / "abrg/output/androct_2017/final_validation/check3_d1_volume/check3.json"
ANDROCT_FIRE = REPO / "abrg/output/v2_chapter_b/run2_comparison/androct_graph_cache.json"
E0_DEV = REPO / "abrg/output/androct_2017/selfref/deviations"
E2_DEV = REPO / "abrg/output/androct_2017/selfref_e2/deviations"

ACT_IDX = feature_vector_labels(normalize=True).index("act_v_frac")
N_NODES = len(GRAPH_CATEGORY_UNIVERSE)

# Evidence-backed classification rules (AndroCT corpus).
ANDROCT_CLASS_EVIDENCE: dict[str, dict[str, str]] = {
    "sms": {
        "bucket": "PERMISSION_GATED",
        "reason": (
            "0/N apps fire; SmsManager APIs mapped but Monkey does not grant "
            "dangerous runtime permissions; SEND_SMS gated API 23+ (B4, B6)."
        ),
    },
    "telephony": {
        "bucket": "PERMISSION_GATED",
        "reason": (
            "Near-zero fire rate; TelephonyManager/call APIs require runtime "
            "permissions Monkey does not grant; 1/N benign fires is stimulus noise."
        ),
    },
    "clipboard": {
        "bucket": "STIMULUS_LIMITED",
        "reason": (
            "ClipboardManager mapped; 1/2231 benign fires under random Monkey — "
            "API producible but stimulus rarely reaches copy/paste flows."
        ),
    },
    "dynamic_code_loading": {
        "bucket": "STIMULUS_LIMITED",
        "reason": (
            "DexClassLoader/instrumentation APIs mapped; 4/2231 benign fires — "
            "producible in principle, rare under Monkey."
        ),
    },
}

# v2_extended: planner + AVD evidence (B4, B7, contextdroid_spec).
V2_CLASS_EVIDENCE: dict[str, dict[str, str]] = {
    "sms": {
        "bucket": "HARDWARE_ABSENT",
        "reason": (
            "0/N sessions; AVD has no cellular radio/SIM; planner action frozenset "
            "excludes SMS actions (B4 §category fire)."
        ),
    },
    "telephony": {
        "bucket": "HARDWARE_ABSENT",
        "reason": (
            "0/N sessions; no incoming/outgoing call stack on emulator AVD; "
            "planner excludes telephony actions."
        ),
    },
    "clipboard": {
        "bucket": "STIMULUS_LIMITED",
        "reason": (
            "Frida hook exists (hook_category_summary n_hooks=1) but 0/N sessions "
            "fire; planner has no clipboard action; random/LLM traversal rarely "
            "triggers ClipboardManager."
        ),
    },
    "dynamic_code_loading": {
        "bucket": "STIMULUS_LIMITED",
        "reason": (
            "Hooks present but planner excludes dex-loading actions; 0/N sessions "
            "fire under guided traversal (B4 unreachable-by-construction list)."
        ),
    },
    "accounts": {
        "bucket": "UNDETERMINED",
        "reason": (
            "0/N sessions; AccountManager hooks exist; spec marks non-firing "
            "UNDETERMINED (AVD account state unknown, B4)."
        ),
    },
    "device_info": {
        "bucket": "UNDETERMINED",
        "reason": (
            "0/N sessions; Build/Telephony identifier hooks exist; emulator may "
            "return null identifiers — spec UNDETERMINED (B4)."
        ),
    },
    "media": {
        "bucket": "UNDETERMINED",
        "reason": (
            "0/N sessions; MediaPlayer/codec hooks exist; media hardware/codec "
            "path UNDETERMINED on AVD (B4)."
        ),
    },
}


def _act_counts_from_tensor(t: dict[str, Any], n_mapped: int) -> np.ndarray:
    x = t["x"]
    if hasattr(x, "numpy"):
        x = x.numpy()
    frac = np.asarray(x[:, ACT_IDX], dtype=np.float64)
    return frac * float(n_mapped)


def _measure_androct() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    bundle = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(bundle.eligible)
    train_shas = {a.sha256 for a in split["train"]}
    arrays_tr, shas = load_profiles("trained_t22")
    d1 = arrays_tr["D1"]
    sha_to_i = {s: i for i, s in enumerate(shas)}

    by_label: dict[str, list[str]] = {"benign": [], "malware": []}
    for a in bundle.eligible:
        by_label[a.label].append(a.sha256)

    rows: list[dict[str, Any]] = []
    meta: dict[str, Any] = {"n_benign": len(by_label["benign"]), "n_malware": len(by_label["malware"])}

    for j, cat in enumerate(GRAPH_CATEGORY_UNIVERSE):
        counts_ben: list[float] = []
        counts_mal: list[float] = []
        all_counts: list[float] = []
        nz_ben = nz_mal = 0
        total_events = 0.0

        for label, shas_l in by_label.items():
            for sha in shas_l:
                app = next(a for a in bundle.eligible if a.sha256 == sha)
                c = float(_act_counts_from_tensor(bundle.tensors[sha], app.n_mapped)[j])
                all_counts.append(c)
                total_events += c
                if c > 0:
                    if label == "benign":
                        nz_ben += 1
                        counts_ben.append(c)
                    else:
                        nz_mal += 1
                        counts_mal.append(c)

        train_vals = []
        for sha in train_shas:
            if sha in sha_to_i:
                train_vals.append(float(d1[sha_to_i[sha], j]))

        nz_train = [v for v in train_vals if v > 0]
        row = {
            "category": cat,
            "frac_nonzero_benign": nz_ben / len(by_label["benign"]) if by_label["benign"] else 0.0,
            "frac_nonzero_malware": nz_mal / len(by_label["malware"]) if by_label["malware"] else 0.0,
            "frac_nonzero_overall": sum(1 for c in all_counts if c > 0) / len(all_counts),
            "n_nonzero_benign": nz_ben,
            "n_nonzero_malware": nz_mal,
            "n_apps_benign": len(by_label["benign"]),
            "n_apps_malware": len(by_label["malware"]),
            "n_distinct_train_benign_d1": int(len(set(round(v, 12) for v in train_vals))),
            "n_distinct_train_benign_d1_nonzero": int(len(set(round(v, 12) for v in nz_train))),
            "mean_act_count_nonzero_benign": float(np.mean(counts_ben)) if counts_ben else 0.0,
            "median_act_count_nonzero_benign": float(np.median(counts_ben)) if counts_ben else 0.0,
            "mean_act_count_nonzero_malware": float(np.mean(counts_mal)) if counts_mal else 0.0,
            "median_act_count_nonzero_malware": float(np.median(counts_mal)) if counts_mal else 0.0,
            "mean_act_count_nonzero_overall": float(np.mean([c for c in all_counts if c > 0]))
            if any(c > 0 for c in all_counts)
            else 0.0,
            "median_act_count_nonzero_overall": float(np.median([c for c in all_counts if c > 0]))
            if any(c > 0 for c in all_counts)
            else 0.0,
            "total_mapped_events": int(round(total_events)),
            "train_benign_d1_sd": float(np.std(train_vals, ddof=0)),
        }
        rows.append(row)

    rows.sort(key=lambda r: r["frac_nonzero_overall"])
    return rows, meta


def _measure_v2() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sessions = pass_sessions(load_sessions(EXPORT_ROOT))
    n_sess = len(sessions)
    train_apps = sorted({r.app_id for r in sessions})  # benign-only corpus

    by_cat_counts: dict[str, list[int]] = {c: [] for c in GRAPH_CATEGORY_UNIVERSE}
    fire_sess = {c: 0 for c in GRAPH_CATEGORY_UNIVERSE}
    total_events = {c: 0 for c in GRAPH_CATEGORY_UNIVERSE}

    for r in sessions:
        _mapped, _total, cat_counts, _apis = mapped_and_total(Path(r.events_path))
        for c in GRAPH_CATEGORY_UNIVERSE:
            n = int(cat_counts.get(c, 0))
            by_cat_counts[c].append(n)
            total_events[c] += n
            if n > 0:
                fire_sess[c] += 1

    rows = []
    for c in GRAPH_CATEGORY_UNIVERSE:
        nz = [x for x in by_cat_counts[c] if x > 0]
        rows.append(
            {
                "category": c,
                "frac_nonzero_sessions": fire_sess[c] / n_sess if n_sess else 0.0,
                "n_nonzero_sessions": fire_sess[c],
                "n_sessions": n_sess,
                "n_distinct_values_session_counts": int(len(set(by_cat_counts[c]))),
                "n_distinct_nonzero_session_counts": int(len(set(nz))) if nz else 0,
                "mean_count_nonzero_sessions": float(np.mean(nz)) if nz else 0.0,
                "median_count_nonzero_sessions": float(np.median(nz)) if nz else 0.0,
                "total_mapped_events": total_events[c],
            }
        )
    rows.sort(key=lambda r: r["frac_nonzero_sessions"])
    meta = {"n_sessions": n_sess, "n_apps": len(train_apps)}
    return rows, meta


def _default_classify(
    row: dict[str, Any],
    corpus: str,
    *,
    frac_key: str,
) -> tuple[str, str]:
    cat = row["category"]
    ev_map = ANDROCT_CLASS_EVIDENCE if corpus == "androct" else V2_CLASS_EVIDENCE
    if cat in ev_map:
        return ev_map[cat]["bucket"], ev_map[cat]["reason"]

    frac = float(row[frac_key])
    if frac > 0:
        return "PRODUCIBLE", f"Observed on {frac:.4%} of units ({frac_key}={frac:.6f})."

    # Zero occupancy — corpus-specific fallbacks
    if corpus == "androct":
        if cat in ("audio", "camera", "location", "media", "notifications", "accounts"):
            return (
                "STIMULUS_LIMITED",
                f"0% occupancy on AndroCT but APIs mapped; rare under Monkey "
                f"(category_fire.csv dead on v2 side too for some).",
            )
        return (
            "UNDETERMINED",
            f"0% occupancy; no dedicated permission/hardware doc beyond aggregate fire table.",
        )

    # v2 zero not in explicit list
    return (
        "UNDETERMINED",
        f"0% session occupancy; hook may exist but stimulus/AVD path not identified in spec.",
    )


def _classify_corpus(rows: list[dict[str, Any]], corpus: str, frac_key: str) -> list[dict[str, Any]]:
    out = []
    for row in rows:
        bucket, reason = _default_classify(row, corpus, frac_key=frac_key)
        out.append({**row, "bucket": bucket, "bucket_reason": reason})
    return out


def _ks_cross(classified: list[dict[str, Any]]) -> dict[str, Any]:
    d2 = json.loads(D2_SUMMARY.read_text(encoding="utf-8"))
    ks_by_node = {
        r["node"]: float(r["ks_statistic_test_benign_vs_uniform"])
        for r in d2["phase1"]["p_distribution_table"]
    }
    occ_by_node = {r["category"]: float(r["frac_nonzero_overall"]) for r in classified}

    merged = []
    for r in classified:
        cat = r["category"]
        merged.append(
            {
                "category": cat,
                "bucket": r["bucket"],
                "occupancy": occ_by_node[cat],
                "ks_statistic": ks_by_node.get(cat, float("nan")),
            }
        )

    bucket_ks: dict[str, list[float]] = defaultdict(list)
    for m in merged:
        if math.isfinite(m["ks_statistic"]):
            bucket_ks[m["bucket"]].append(m["ks_statistic"])

    mean_ks = {b: float(np.mean(v)) if v else float("nan") for b, v in bucket_ks.items()}
    prod_mean = mean_ks.get("PRODUCIBLE", float("nan"))
    gated_mean = np.nanmean(
        [mean_ks.get(b, float("nan")) for b in ("PERMISSION_GATED", "HARDWARE_ABSENT", "STIMULUS_LIMITED")]
    )
    rho, rho_p = stats.spearmanr(
        [m["occupancy"] for m in merged],
        [m["ks_statistic"] for m in merged],
    )

    # Verdict logic
    non_prod = [m for m in merged if m["bucket"] != "PRODUCIBLE" and m["bucket"] != "UNDETERMINED"]
    prod = [m for m in merged if m["bucket"] == "PRODUCIBLE"]
    top5_ks = sorted(merged, key=lambda x: -x["ks_statistic"])[:5]
    top5_non_prod = sum(1 for t in top5_ks if t["bucket"] != "PRODUCIBLE")

    if top5_non_prod >= 4 and prod_mean < gated_mean:
        verdict = "CONFIRMED"
    elif top5_non_prod >= 2:
        verdict = "PARTIAL"
    else:
        verdict = "NOT_CONFIRMED"

    return {
        "merged": merged,
        "mean_ks_by_bucket": mean_ks,
        "spearman_occupancy_vs_ks": {"rho": float(rho), "p": float(rho_p)},
        "verdict": verdict,
        "top5_ks": top5_ks,
    }


def _recompute_d2_producible(producible_mask: np.ndarray) -> dict[str, float]:
    ctx = _load_context()
    keep = np.where(producible_mask)[0]
    X_tr = ctx["X_trained"]
    p = _empirical_pvalues(X_tr[ctx["tr_idx"]], X_tr[ctx["te_idx"]])
    scores, _, _ = _compute_ladder_matrix(p, keep, alpha0=1.0)
    ev_fisher = _eval_scores(scores["FISHER"], ctx["labels"])
    ev_hc = _eval_scores(scores["HC"], ctx["labels"])
    return {
        "fisher_floor": float(ev_fisher["auc_floor"]),
        "hc_floor": float(ev_hc["auc_floor"]),
        "n_coords": int(keep.size),
    }


def _recompute_d1_l2_producible(producible_mask: np.ndarray) -> float:
    ctx = _load_context()
    X = ctx["X_trained"][:, producible_mask]
    sc, _ = _score_matrix(X[ctx["tr_idx"]], X[ctx["te_idx"]], "RAW", "L2")
    block = _auc_with_bootstrap(sc.tolist(), ctx["labels"].tolist())
    return float(block["auc_floor"])


def _impact_ablation(classified: list[dict[str, Any]], check3: dict[str, Any]) -> dict[str, Any]:
    bucket_by = {r["category"]: r["bucket"] for r in classified}
    near_zero = []
    structural = []
    for a in check3["per_node_ablation_ranked"]:
        if a["node"] == "ipc_intents":
            continue
        if a["delta_auc_floor"] < 0.01:
            near_zero.append(a)
            if bucket_by.get(a["node"]) != "PRODUCIBLE":
                structural.append(a)
    return {
        "near_zero_count": len(near_zero),
        "non_producible_near_zero": len(structural),
        "near_zero_nodes": [a["node"] for a in near_zero],
        "structural_near_zero_nodes": [a["node"] for a in structural],
    }


def _recompute_e0_e2(producible_mask: np.ndarray) -> dict[str, Any]:
    """E0 PREFIX SCALAR MAX node; E2 NODE_STD MAX node (E0 deviations + E2 sigma)."""
    bundle = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(bundle.eligible)
    test_b = split["test_benign"]
    test_m = split["test_malware"]
    labels = [0] * len(test_b) + [1] * len(test_m)
    test_apps = test_b + test_m

    def _load_d(mode: str, space: str, sha: str) -> np.ndarray:
        p = E0_DEV / mode / space / f"{sha}.npy"
        return np.load(p)  # [2, 22]

    def _mask_rows(d: np.ndarray) -> np.ndarray:
        if producible_mask.all():
            return d
        return d[:, producible_mask]

    e0_scores = []
    for app in test_apps:
        d = _load_d("PREFIX", "node", app.sha256)
        win = np.linalg.norm(_mask_rows(d), axis=1)
        e0_scores.append(float(np.max(win)))
    e0_block = _auc_with_bootstrap(e0_scores, labels)

    e2_result: dict[str, Any] = {"skipped": True}
    sigma_path = REPO / "abrg/output/androct_2017/selfref_e2/sigma_PREFIX_node.npy"
    if sigma_path.is_file():
        sigma_full = np.load(sigma_path)
        sigma = sigma_full[producible_mask] if not producible_mask.all() else sigma_full
        sigma = sigma + 1e-12

        def _node_std_score(d22: np.ndarray) -> float:
            d = d22[producible_mask] if not producible_mask.all() else d22
            return float(np.linalg.norm(d / sigma))

        e2_scores = []
        for app in test_apps:
            d = _load_d("PREFIX", "node", app.sha256)
            win = [_node_std_score(row) for row in d]
            e2_scores.append(float(np.max(win)))
        e2_block = _auc_with_bootstrap(e2_scores, labels)
        e2_result = {"skipped": False, "auc_floor": float(e2_block["auc_floor"])}

    non_producible = [GRAPH_CATEGORY_UNIVERSE[j] for j in range(N_NODES) if not producible_mask[j]]

    return {
        "e0_auc_floor_restricted": float(e0_block["auc_floor"]),
        "e0_ref": 0.6997,
        "e2": e2_result,
        "e2_ref": 0.7124322069253233,
        "non_producible_categories": non_producible,
        "n_non_producible": int((~producible_mask).sum()),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _part5_strings(
    androct_cls: list[dict[str, Any]],
    v2_cls: list[dict[str, Any]],
    ks: dict[str, Any],
    n_prod_ac: int,
    n_prod_v2: int,
) -> list[dict[str, str]]:
    """Return before/after pairs for thesis (not applied)."""
    verdict = ks["verdict"]
    pairs: list[dict[str, str]] = []

    # 5a A4_method.tex
    pairs.append(
        {
            "id": "5a",
            "file": "thesis/chapter_a/A4_method.tex",
            "line": "~59-61",
            "before": (
                "Because the node set does not depend on the app, graphs are directly comparable\n"
                "and can be stacked as tensors of constant shape. Inactive categories remain as\n"
                "zero-feature, zero-degree nodes rather than being dropped."
            ),
            "after": (
                "Because the node set does not depend on the app, graphs are directly comparable\n"
                "and can be stacked as tensors of constant shape. Inactive categories remain as\n"
                "zero-feature, zero-degree nodes rather than being dropped. Comparability across\n"
                f"a structurally unobservable coordinate is vacuous: on AndroCT only {n_prod_ac} of\n"
                "22 categories are environment-producible under the Monkey protocol; the remainder\n"
                "are permission-gated or stimulus-limited (\\S\\ref{sec:observability-audit})."
            ),
        }
    )

    # 5b A10_threats.tex — new paragraph after design commitments or corpus
    pairs.append(
        {
            "id": "5b",
            "file": "thesis/chapter_a/A10_threats.tex",
            "line": "after §a10-corpus (~65)",
            "before": "(no observability threat entry)",
            "after": (
                "\\paragraph{Observability and ambiguous zeros.}\n"
                "A zero coordinate conflates ``the app did not perform this behaviour'' with\n"
                "``the environment could not produce observable events for this category.'' The\n"
                f"schema does not distinguish them. AndroCT effective universe: {n_prod_ac}/22\n"
                f"PRODUCIBLE; v2\\_extended: {n_prod_v2}/22. D-2 KS uniformity cross-check:\n"
                f"{verdict} (\\S\\ref{{sec:observability-audit}})."
            ),
        }
    )

    # 5c B3/B4 corpus
    pairs.append(
        {
            "id": "5c",
            "file": "thesis/chapter_b/B3_corpus.tex or B4_comparison.tex",
            "line": "new threat subsection",
            "before": "(v2 AVD described without effective-universe size)",
            "after": (
                "The v2 AVD has no cellular radio and no SIM; telephony/SMS-class events are\n"
                "not physically producible. Combined with the planner action frozenset, seven\n"
                f"categories never fire (0/59 apps); effective PRODUCIBLE universe: {n_prod_v2}/22.\n"
                "Occupancy table: \\texttt{results/observability\\_v2\\_extended.csv}."
            ),
        }
    )

    # 5d granularity A6_results.tex ~627-629
    pairs.append(
        {
            "id": "5d",
            "file": "thesis/chapter_a/A6_results.tex",
            "line": "~627-629",
            "before": (
                "support novelty is granularity-dependent and at chance where every category is\n"
                "always in vocabulary."
            ),
            "after": (
                "support novelty is granularity-dependent and at chance where every category is\n"
                "always in vocabulary. The converse also holds: readouts that require a\n"
                "well-conditioned per-coordinate null fail when some nodes are structurally empty\n"
                "(permission-gated or hardware-absent), because zeros encode instrumentation\n"
                "artifacts as well as behaviour."
            ),
        }
    )

    # 5e D-2 write-up
    if verdict in ("CONFIRMED", "PARTIAL"):
        d2_after = (
            "Uniformity failures on sparse coordinates (sms, clipboard, telephony) track\n"
            "non-producibility under the Monkey emulator protocol, not merely low benign\n"
            "base rate: KS ranks align with PERMISSION_GATED and STIMULUS_LIMITED buckets\n"
            f"(verdict {verdict})."
        )
    else:
        d2_after = (
            "An instrumentation hypothesis (KS failure driven by non-producible coordinates)\n"
            "was tested and rejected; uniformity departure remains explained primarily by\n"
            "sparsity and degenerate benign marginals."
        )
    pairs.append(
        {
            "id": "5e",
            "file": "results/D2_higher_criticism.md or future A6_selfref subsection",
            "line": "§1c uniformity paragraph",
            "before": "Worst departures from uniformity: sms KS=0.936, clipboard KS=0.851 ...",
            "after": d2_after,
        }
    )

    # 5f future work A8_discussion or A10
    pairs.append(
        {
            "id": "5f",
            "file": "thesis/chapter_a/A8_discussion.tex (future work)",
            "line": "new bullet",
            "before": "(no observability mask)",
            "after": (
                "Future work: per-corpus observability mask $\\mathcal{O}_c \\subseteq \\mathcal{U}$\n"
                "so that $x_j=0$ when $j\\notin \\mathcal{O}_c$ is tagged instrumentation-unavailable\n"
                "rather than behavioural absence. The current ABRG schema has no field for this."
            ),
        }
    )
    return pairs


def _render_report(
    androct_rows: list[dict[str, Any]],
    v2_rows: list[dict[str, Any]],
    androct_cls: list[dict[str, Any]],
    v2_cls: list[dict[str, Any]],
    ks: dict[str, Any],
    impact: dict[str, Any],
    pairs: list[dict[str, str]],
) -> str:
    n_prod_ac = sum(1 for r in androct_cls if r["bucket"] == "PRODUCIBLE")
    n_prod_v2 = sum(1 for r in v2_cls if r["bucket"] == "PRODUCIBLE")
    lines: list[str] = []

    if ks["verdict"] == "NOT_CONFIRMED":
        lines.extend(
            [
                "> **Instrumentation hypothesis NOT_CONFIRMED** — KS failure is not systematically "
                "explained by non-producibility alone; see Part 3.",
                "",
            ]
        )

    lines.extend(
        [
            "# ABRG observability audit — 22-node universe",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "",
            f"**Effective universe (PRODUCIBLE):** AndroCT **{n_prod_ac}/22**; "
            f"v2_extended **{n_prod_v2}/22**.",
            "",
            "---",
            "",
            "## Part 1 — Occupancy tables",
            "",
            "Coordinate = mapped-event `act_count` per category (graph tensor `act_v_frac × n_mapped`).",
            "1b distinct values are on **D1 train-benign** deviation profiles (562 apps).",
            "",
            "CSV: `results/observability_androct.csv`, `results/observability_v2_extended.csv`.",
            "",
            "### AndroCT (graph-eligible, n=2403)",
            "",
            _md_table(
                androct_rows,
                [
                    "category",
                    "frac_nonzero_benign",
                    "frac_nonzero_malware",
                    "n_distinct_train_benign_d1",
                    "median_act_count_nonzero_overall",
                    "total_mapped_events",
                ],
            ),
            "",
            "### v2_extended (reference-tier sessions)",
            "",
            _md_table(
                v2_rows,
                [
                    "category",
                    "frac_nonzero_sessions",
                    "n_distinct_nonzero_session_counts",
                    "median_count_nonzero_sessions",
                    "total_mapped_events",
                ],
            ),
            "",
            "---",
            "",
            "## Part 2 — Classification",
            "",
            "### AndroCT",
            "",
        ]
    )
    for r in androct_cls:
        lines.append(
            f"- **{r['category']}** → `{r['bucket']}`: {r['bucket_reason']}"
        )
    lines.extend(["", f"**Effective universe size: {n_prod_ac}/22**", "", "### v2_extended", ""])
    for r in v2_cls:
        lines.append(
            f"- **{r['category']}** → `{r['bucket']}`: {r['bucket_reason']}"
        )
    lines.extend(["", f"**Effective universe size: {n_prod_v2}/22**", "", "---", "", "## Part 3 — KS hypothesis", ""])

    lines.append(f"**Verdict: {ks['verdict']}**")
    if ks["verdict"] == "PARTIAL":
        exceptions = [
            m for m in ks["merged"]
            if m["bucket"] == "PRODUCIBLE" and m["ks_statistic"] >= 0.70
        ]
        if exceptions:
            lines.append("")
            lines.append(
                "Exceptions (high KS despite PRODUCIBLE bucket): "
                + ", ".join(f"`{m['category']}` KS={m['ks_statistic']:.3f}" for m in exceptions)
                + ". Uniformity failure is not exclusively non-producibility; sparse PRODUCIBLE "
                "coordinates (audio, content_access) also depart strongly from U(0,1)."
            )
    lines.append("")
    lines.append("### 3a — KS vs occupancy (AndroCT, D-2 Phase 1c)")
    lines.append("")
    lines.append(
        _md_table(
            ks["merged"],
            ["category", "bucket", "occupancy", "ks_statistic"],
        )
    )
    lines.append("")
    lines.append("### 3b — Mean KS by bucket")
    for b, v in sorted(ks["mean_ks_by_bucket"].items()):
        lines.append(f"- `{b}`: {v:.4f} (n={sum(1 for m in ks['merged'] if m['bucket']==b)})")
    lines.append(
        f"- Spearman(occupancy, KS): ρ={ks['spearman_occupancy_vs_ks']['rho']:.4f}, "
        f"p={ks['spearman_occupancy_vs_ks']['p']:.2e}"
    )
    lines.append("")

    lines.extend(["---", "", "## Part 4 — Impact on existing results", ""])
    ab = impact["ablation"]
    lines.extend(
        [
            "### 4a — D1 per-node ablation",
            "",
            f"- Near-zero ablations (Δ<0.01, excl. ipc_intents): **{ab['near_zero_count']}** nodes",
            f"- Of those, non-PRODUCIBLE: **{ab['non_producible_near_zero']}** → "
            f"{ab['structural_near_zero_nodes']}",
            "- ipc_intents drop 0.209 is on a PRODUCIBLE coordinate (real signal).",
            "- network Δ=0.0025 and remaining near-zero drops on PRODUCIBLE coords are measured, "
            f"not structurally guaranteed ({ab['non_producible_near_zero']} structural no-ops).",
            "",
            "### 4b — D-2 ladder restricted to PRODUCIBLE",
            "",
            f"| coords | FISHER floor | HC α₀=1 floor |",
            f"|--------|--------------|---------------|",
            f"| 22 (ref) | 0.649796 | 0.501489 |",
            f"| {impact['d2_restricted']['n_coords']} PRODUCIBLE | "
            f"{impact['d2_restricted']['fisher_floor']:.6f} | "
            f"{impact['d2_restricted']['hc_floor']:.6f} |",
            f"| D1 L2 ref | 0.800426 | — |",
            "",
            "### 4c — D1 L2 restricted",
            "",
            f"- Full 22: **{D1_L2_REF:.6f}**",
            f"- PRODUCIBLE-only: **{impact['d1_l2_restricted']:.6f}**",
            f"- Δ: {impact['d1_l2_restricted'] - D1_L2_REF:+.6f}",
            "",
            "### 4d — E0/E2 self-reference d vectors",
            "",
            f"- Non-PRODUCIBLE categories (excluded from mask): "
            f"**{impact['e0_e2']['n_non_producible']}** — "
            f"{', '.join(impact['e0_e2']['non_producible_categories'])}",
            f"- E0 PREFIX SCALAR MAX node: ref 0.6997 → restricted "
            f"{impact['e0_e2']['e0_auc_floor_restricted']:.6f}",
        ]
    )
    if not impact["e0_e2"]["e2"].get("skipped"):
        lines.append(
            f"- E2 NODE_STD MAX node: ref 0.7124 → restricted "
            f"{impact['e0_e2']['e2']['auc_floor']:.6f}"
        )
    else:
        lines.append("- E2: deviation path missing — skipped")
    lines.extend(["", "---", "", "## Part 5 — Proposed text changes (not applied)", ""])
    for p in pairs:
        lines.extend(
            [
                f"### {p['id']} — `{p['file']}` ({p['line']})",
                "",
                "**Before:**",
                "```",
                p["before"],
                "```",
                "",
                "**After:**",
                "```",
                p["after"],
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def _md_table(rows: list[dict[str, Any]], cols: list[str]) -> str:
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = []
    for r in rows:
        body.append("| " + " | ".join(f"{r.get(c, '')}" for c in cols) + " |")
    return "\n".join([header, sep, *body])


def main() -> None:
    print("[obs] AndroCT occupancy …", flush=True)
    androct_rows, ac_meta = _measure_androct()
    print("[obs] v2_extended occupancy …", flush=True)
    v2_rows, v2_meta = _measure_v2()

    androct_cls = _classify_corpus(androct_rows, "androct", "frac_nonzero_overall")
    v2_cls = _classify_corpus(v2_rows, "v2", "frac_nonzero_sessions")

    # Refine AndroCT / v2 classifications; preserve explicit evidence overrides.
    fire_cache = json.loads(ANDROCT_FIRE.read_text(encoding="utf-8"))
    for r in androct_cls:
        cat = r["category"]
        if cat in ANDROCT_CLASS_EVIDENCE:
            r["bucket"] = ANDROCT_CLASS_EVIDENCE[cat]["bucket"]
            r["bucket_reason"] = ANDROCT_CLASS_EVIDENCE[cat]["reason"]
            if cat == "sms":
                r["bucket_reason"] = (
                    f"0/{fire_cache['n_effective']['benign']} benign and "
                    f"0/{fire_cache['n_effective']['malware']} malware fire (androct_graph_cache); "
                    "SmsManager mapped; Monkey grants no dangerous permissions."
                )
            continue
        if cat == "telephony" and r["frac_nonzero_overall"] < 0.001:
            r["bucket"] = "PERMISSION_GATED"
            r["bucket_reason"] = (
                f"Near-zero fire ({r['frac_nonzero_overall']:.4%}); TelephonyManager APIs "
                "require runtime permissions Monkey does not grant."
            )
            continue
        if r["frac_nonzero_overall"] > 0:
            r["bucket"] = "PRODUCIBLE"
            r["bucket_reason"] = (
                f"Observed act_count>0 on {r['frac_nonzero_overall']:.2%} of eligible apps."
            )

    for r in v2_cls:
        if r["category"] in V2_CLASS_EVIDENCE:
            r["bucket"] = V2_CLASS_EVIDENCE[r["category"]]["bucket"]
            r["bucket_reason"] = V2_CLASS_EVIDENCE[r["category"]]["reason"]
            continue
        if r["frac_nonzero_sessions"] > 0:
            r["bucket"] = "PRODUCIBLE"
            r["bucket_reason"] = (
                f"Observed on {r['n_nonzero_sessions']}/{r['n_sessions']} sessions."
            )

    ks = _ks_cross(androct_cls)

    bucket_by = {r["category"]: r["bucket"] for r in androct_cls}
    producible_mask = np.array(
        [bucket_by[c] == "PRODUCIBLE" for c in GRAPH_CATEGORY_UNIVERSE], dtype=bool
    )

    check3 = json.loads(CHECK3.read_text(encoding="utf-8"))
    impact = {
        "ablation": _impact_ablation(androct_cls, check3),
        "d2_restricted": _recompute_d2_producible(producible_mask),
        "d1_l2_restricted": _recompute_d1_l2_producible(producible_mask),
        "e0_e2": _recompute_e0_e2(producible_mask),
    }

    pairs = _part5_strings(
        androct_cls,
        v2_cls,
        ks,
        int(producible_mask.sum()),
        sum(1 for r in v2_cls if r["bucket"] == "PRODUCIBLE"),
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    _write_csv(
        RESULTS / "observability_androct.csv",
        androct_rows,
        list(androct_rows[0].keys()),
    )
    _write_csv(
        RESULTS / "observability_v2_extended.csv",
        v2_rows,
        list(v2_rows[0].keys()),
    )

    report = _render_report(androct_rows, v2_rows, androct_cls, v2_cls, ks, impact, pairs)
    out_md = RESULTS / "observability_audit.md"
    out_md.write_text(report, encoding="utf-8")
    print(f"[obs] → {out_md}", flush=True)

    summary = {
        "androct_effective_universe": int(producible_mask.sum()),
        "v2_effective_universe": sum(1 for r in v2_cls if r["bucket"] == "PRODUCIBLE"),
        "ks_verdict": ks["verdict"],
        "d2_restricted": impact["d2_restricted"],
        "d1_l2_restricted": impact["d1_l2_restricted"],
        "meta": {"androct": ac_meta, "v2": v2_meta},
    }
    (RESULTS / "observability_audit_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
