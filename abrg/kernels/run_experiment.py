"""Orchestrate shallow GLAD kernels experiment."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from abrg.kernels import (
    KERNELS_OUTPUT_ROOT,
    OCPOOL_MEAN_RAW,
    REF_ROWS,
    SEEDS,
    SIZE_FLOOR,
)
from abrg.kernels._nx import LabelMode, prepare_graphs
from abrg.kernels.ablation import run_ablation_for_winner, score_config_on_tensors
from abrg.kernels.bootstrap import nested_bootstrap_winner
from abrg.kernels.detectors import run_embedding_detectors, run_kernel_detectors
from abrg.kernels.embeddings import (
    embed_fgsd,
    embed_gl2vec,
    embed_graph2vec,
    embed_netlsd,
)
from abrg.kernels.graph_kernels import fit_propagation, fit_shortest_path, fit_wl
from abrg.kernels.load import covariates_for, load_bundle


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n", encoding="utf-8")


def _fail_counts(failures: list[dict[str, Any]], train: set[str], tb: set[str], tm: set[str]) -> dict:
    c = {"train_benign": 0, "test_benign": 0, "test_malware": 0, "other": 0}
    for f in failures:
        s = f.get("sha", "")
        if s in train:
            c["train_benign"] += 1
        elif s in tb:
            c["test_benign"] += 1
        elif s in tm:
            c["test_malware"] += 1
        else:
            c["other"] += 1
    return c


def _best_floor_from_detectors(det: dict[str, Any]) -> tuple[float, str, dict[str, Any]]:
    best = -1.0
    best_name = ""
    best_row: dict[str, Any] = {}
    for name, block in det.items():
        if block.get("stochastic"):
            floor = float(block["auc_floor_mean"])
            row = block
        else:
            floor = float(block["auc"]["auc_floor"])
            row = block
        if floor > best:
            best, best_name, best_row = floor, name, row
    return best, best_name, best_row


def run_representation(
    *,
    kind: str,
    tensors: dict[str, dict[str, Any]],
    train: list[str],
    test_b: list[str],
    test_m: list[str],
    out_root: Path,
) -> dict[str, Any]:
    eval_ids = test_b + test_m
    forbidden = test_b + test_m
    cov = covariates_for(tensors, eval_ids, kind=kind)
    train_set, tb_set, tm_set = set(train), set(test_b), set(test_m)
    n_tb = len(test_b)
    results: dict[str, Any] = {"kind": kind, "embeddings": {}, "kernels": {}}

    # --- label modes for embeddings that need labels (Graph2Vec) and all kernels ---
    if kind == "T22":
        primary_label: LabelMode = "identity"
        label_note = "T22 primary labels = 22-category identity (node index 0..21)"
    else:
        primary_label = "category_argmax"
        label_note = (
            "T1K primary labels = argmax of 22-category one-hot in node features x[:, 3:25]"
        )

    emb_dir = out_root / "embeddings" / kind
    det_dir = out_root / "detectors" / kind
    emb_dir.mkdir(parents=True, exist_ok=True)
    det_dir.mkdir(parents=True, exist_ok=True)

    # Build NX graphs once per label mode
    print(f"[{kind}] prepare graphs label={primary_label}", flush=True)
    nx_tr, gk_tr, lab_tr, _ = prepare_graphs(
        tensors, train, kind=kind, label_mode=primary_label
    )
    nx_ev, gk_ev, lab_ev, _ = prepare_graphs(
        tensors, eval_ids, kind=kind, label_mode=primary_label
    )

    # Embeddings (structure-only for FGSD/NetLSD/GL2Vec; Graph2Vec uses labels)
    emb_jobs = [
        (
            "FGSD",
            lambda: embed_fgsd(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            ),
        ),
        (
            "NetLSD",
            lambda: embed_netlsd(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            ),
        ),
        (
            "Graph2Vec",
            lambda: embed_graph2vec(
                nx_tr,
                nx_ev,
                lab_tr,
                lab_ev,
                train_ids=train,
                eval_ids=eval_ids,
                forbidden_ids=forbidden,
            ),
        ),
        (
            "GL2Vec",
            lambda: embed_gl2vec(
                nx_tr, nx_ev, train_ids=train, eval_ids=eval_ids, forbidden_ids=forbidden
            ),
        ),
    ]

    for name, builder in emb_jobs:
        meta_path = emb_dir / f"{name}_meta.json"
        vec_path = emb_dir / f"{name}_vectors.npz"
        det_path = det_dir / f"emb_{name}.json"
        if meta_path.is_file() and vec_path.is_file() and det_path.is_file():
            print(f"[{kind}] embedding {name} (resume cache)", flush=True)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            det = json.loads(det_path.read_text(encoding="utf-8"))
            results["embeddings"][name] = {"meta": meta, "detectors": det}
            continue
        print(f"[{kind}] embedding {name}", flush=True)
        emb = builder()
        meta = {
            "name": emb.name,
            "dim": emb.dim,
            "wall_sec": emb.wall_sec,
            "notes": emb.notes,
            "fit_scope": emb.fit_scope,
            "n_train": int(emb.X_train.shape[0]),
            "n_eval": int(emb.X_eval.shape[0]),
            "failures": emb.failures,
            "failure_counts": _fail_counts(emb.failures, train_set, tb_set, tm_set),
            "label_note": label_note if name == "Graph2Vec" else "n/a (structure descriptor)",
        }
        _write_json(meta_path, meta)
        np.savez_compressed(
            vec_path,
            X_train=emb.X_train,
            X_eval=emb.X_eval,
            train_ids=np.array(train),
            eval_ids=np.array(eval_ids),
        )
        X_tb, X_tm = emb.X_eval[:n_tb], emb.X_eval[n_tb:]
        det = run_embedding_detectors(emb.X_train, X_tb, X_tm, cov, SEEDS)
        _write_json(det_path, det)
        results["embeddings"][name] = {"meta": meta, "detectors": det}

    # Kernels — primary labels + degree variant
    for label_mode, tag in (
        (primary_label, "lab_primary"),
        ("degree", "lab_degree"),
    ):
        print(f"[{kind}] kernels label_mode={label_mode}", flush=True)
        _, gk_tr_l, _, _ = prepare_graphs(tensors, train, kind=kind, label_mode=label_mode)
        _, gk_ev_l, _, _ = prepare_graphs(tensors, eval_ids, kind=kind, label_mode=label_mode)

        kernel_builders = []
        for h in (1, 2, 3):
            kernel_builders.append(
                (
                    f"WL_h{h}",
                    lambda h=h: fit_wl(
                        gk_tr_l,
                        gk_ev_l,
                        h=h,
                        train_ids=train,
                        forbidden=forbidden,
                        label_mode=label_mode,
                    ),
                )
            )
        kernel_builders.append(
            (
                "Propagation",
                lambda: fit_propagation(
                    gk_tr_l,
                    gk_ev_l,
                    train_ids=train,
                    forbidden=forbidden,
                    label_mode=label_mode,
                ),
            )
        )
        kernel_builders.append(
            (
                "ShortestPath",
                lambda: fit_shortest_path(
                    gk_tr_l,
                    gk_ev_l,
                    train_ids=train,
                    forbidden=forbidden,
                    label_mode=label_mode,
                    kind=kind,
                ),
            )
        )

        for kname, kbuilder in kernel_builders:
            key = f"{kname}__{tag}"
            meta_path = emb_dir / f"kernel_{key}_meta.json"
            det_path = det_dir / f"kern_{key}.json"
            gram_path = emb_dir / f"kernel_{key}_gram.npz"
            if meta_path.is_file() and (
                (det_path.is_file() and gram_path.is_file())
                or (
                    meta_path.is_file()
                    and json.loads(meta_path.read_text(encoding="utf-8")).get("skipped")
                )
            ):
                print(f"[{kind}] kernel {kname} ({tag}) (resume cache)", flush=True)
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                det = json.loads(det_path.read_text(encoding="utf-8")) if det_path.is_file() else {}
                results["kernels"][key] = {"meta": meta, "detectors": det}
                continue
            print(f"[{kind}] kernel {kname} ({tag})", flush=True)
            kr = kbuilder()
            meta = {
                "name": kr.name,
                "label_mode": label_mode,
                "label_tag": tag,
                "wall_sec": kr.wall_sec,
                "skipped": kr.skipped,
                "skip_reason": kr.skip_reason,
                "notes": kr.notes,
                "K_train_shape": list(kr.K_train.shape),
                "K_eval_train_shape": list(kr.K_eval_train.shape),
                "label_note": (
                    label_note
                    if label_mode != "degree"
                    else "degree labels = undirected node degree"
                ),
            }
            _write_json(meta_path, meta)
            if kr.skipped:
                results["kernels"][key] = {"meta": meta, "detectors": {}}
                continue
            np.savez_compressed(
                gram_path,
                K_train=kr.K_train,
                K_eval_train=kr.K_eval_train,
            )
            K_et_b = kr.K_eval_train[:n_tb]
            K_et_m = kr.K_eval_train[n_tb:]
            det = run_kernel_detectors(kr.K_train, K_et_b, K_et_m, cov)
            _write_json(det_path, det)
            results["kernels"][key] = {"meta": meta, "detectors": det}

    return results


def _iter_scores(rep: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    kind = rep["kind"]
    for method, block in rep["embeddings"].items():
        for det_name, det in block["detectors"].items():
            if det.get("stochastic"):
                floor = float(det["auc_floor_mean"])
                raw = float(np.mean([p["auc"]["auc"] for p in det["per_seed"]]))
                direction = det["per_seed"][0]["auc"]["direction"]
                ci = det["per_seed"][0]["auc"]["ci95_floor"]
                gate = det["per_seed"][0]["gate"]
                # recompute gate on mean floor
                gate = {
                    "clears_size_floor_0.7025": floor > SIZE_FLOOR,
                    "clears_OCPool_mean_0.7765": floor > OCPOOL_MEAN_RAW,
                    "is_result": floor > SIZE_FLOOR,
                }
                spear = det["per_seed"][0]["leak_spearman"]
            else:
                floor = float(det["auc"]["auc_floor"])
                raw = float(det["auc"]["auc"])
                direction = det["auc"]["direction"]
                ci = det["auc"]["ci95_floor"]
                gate = det["gate"]
                spear = det["leak_spearman"]
            rows.append(
                {
                    "kind": kind,
                    "family": "embedding",
                    "method": method,
                    "detector": det_name,
                    "label_mode": block["meta"].get("label_note", ""),
                    "auc": raw,
                    "auc_floor": floor,
                    "direction": direction,
                    "ci95_floor": ci,
                    "gate": gate,
                    "leak_spearman": spear,
                    "dim": block["meta"].get("dim"),
                }
            )
    for key, block in rep["kernels"].items():
        if block["meta"].get("skipped"):
            rows.append(
                {
                    "kind": kind,
                    "family": "kernel",
                    "method": block["meta"]["name"],
                    "detector": None,
                    "label_mode": block["meta"].get("label_mode"),
                    "skipped": True,
                    "skip_reason": block["meta"].get("skip_reason"),
                }
            )
            continue
        for det_name, det in block["detectors"].items():
            floor = float(det["auc"]["auc_floor"])
            rows.append(
                {
                    "kind": kind,
                    "family": "kernel",
                    "method": block["meta"]["name"],
                    "detector": det_name,
                    "label_mode": block["meta"].get("label_mode"),
                    "label_tag": block["meta"].get("label_tag"),
                    "auc": float(det["auc"]["auc"]),
                    "auc_floor": floor,
                    "direction": det["auc"]["direction"],
                    "ci95_floor": det["auc"]["ci95_floor"],
                    "gate": det["gate"],
                    "leak_spearman": det["leak_spearman"],
                    "K_train_shape": block["meta"].get("K_train_shape"),
                    "K_eval_train_shape": block["meta"].get("K_eval_train_shape"),
                }
            )
    return rows


def pick_winner(all_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    cand = [
        r
        for r in all_rows
        if not r.get("skipped") and r.get("auc_floor") is not None and r.get("detector")
    ]
    if not cand:
        return None
    return max(cand, key=lambda r: float(r["auc_floor"]))


def write_summary(
    path: Path,
    *,
    rows: list[dict[str, Any]],
    winner: dict[str, Any] | None,
    ablation: dict[str, Any] | None,
    nested: dict[str, Any] | None,
    lib_versions: dict[str, str],
    digest: str,
) -> None:
    lines: list[str] = []
    lines.append("# Shallow GLAD kernels — SUMMARY")
    lines.append("")
    lines.append(f"- generated_utc: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- split_digest: `{digest[:16]}…` (562/141/1700)")
    lines.append(f"- libraries: {json.dumps(lib_versions)}")
    lines.append("")
    lines.append("## Reference rows (fixed)")
    lines.append("")
    lines.append(
        f"| OCPool_mean raw | OCPool_mean R2 | R2 nested CI | rand GAE | input centroid | "
        f"GAE | OCGIN_plus | mapped floor | HGB full | HGB adj |"
    )
    lines.append("|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|")
    lines.append(
        f"| {REF_ROWS['OCPool_mean_raw']} | {REF_ROWS['OCPool_mean_R2']} | "
        f"{REF_ROWS['OCPool_mean_R2_nested_CI']} | {REF_ROWS['random_init_GAE']} | "
        f"{REF_ROWS['input_centroid']} | {REF_ROWS['GAE']} | {REF_ROWS['OCGIN_plus']} | "
        f"{REF_ROWS['size_floor_mapped_events']} | {REF_ROWS['supervised_HGB_full']} | "
        f"{REF_ROWS['supervised_HGB_adj_only']} |"
    )
    lines.append("")
    lines.append("## Gate")
    lines.append("")
    lines.append(
        f"(a) size floor mapped_events **{SIZE_FLOOR}** · "
        f"(b) OCPool_mean incumbent **{OCPOOL_MEAN_RAW}** · "
        "rows with ¬(a) are not results."
    )
    lines.append("")
    lines.append("## Results grid")
    lines.append("")
    lines.append(
        "| kind | family | method | detector | label | auc | auc_floor | direction | "
        "ci95_floor | clears_(a) | clears_(b) | ρ_mapped | ρ_total | ρ_active | ρ_edges | ρ_dens | ρ_static |"
    )
    lines.append("|---|---|---|---|---|---:|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for r in sorted(
        [x for x in rows if not x.get("skipped")],
        key=lambda z: (-float(z["auc_floor"]), z["kind"], z["family"], z["method"], z["detector"]),
    ):
        g = r["gate"]
        sp = r.get("leak_spearman") or {}
        lines.append(
            f"| {r['kind']} | {r['family']} | {r['method']} | {r['detector']} | "
            f"{r.get('label_mode') or r.get('label_tag') or ''} | "
            f"{r['auc']:.4f} | {r['auc_floor']:.4f} | {r['direction']} | "
            f"{r.get('ci95_floor')} | {g['clears_size_floor_0.7025']} | "
            f"{g['clears_OCPool_mean_0.7765']} | "
            f"{sp.get('mapped_events', float('nan')):.3f} | "
            f"{sp.get('total_events', float('nan')):.3f} | "
            f"{sp.get('active_nodes', float('nan')):.3f} | "
            f"{sp.get('edge_count', float('nan')):.3f} | "
            f"{sp.get('density', float('nan')):.3f} | "
            f"{sp.get('static_norm', float('nan')):.3f} |"
        )
    skipped = [x for x in rows if x.get("skipped")]
    if skipped:
        lines.append("")
        lines.append("## Skipped")
        lines.append("")
        for s in skipped:
            lines.append(
                f"- {s['kind']} {s['method']} label={s.get('label_mode')}: {s.get('skip_reason')}"
            )

    lines.append("")
    lines.append("## Winner")
    lines.append("")
    if winner:
        lines.append(
            f"- {winner['kind']} · {winner['family']} · {winner['method']} · "
            f"{winner['detector']} · label={winner.get('label_mode')} · "
            f"auc_floor={winner['auc_floor']:.4f}"
        )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("## Ablation (winner)")
    lines.append("")
    if ablation:
        lines.append(
            "| as_built | edges_removed | features_constant | Δ(full−no_edges) | Δ(struct_only−full) |"
        )
        lines.append("|---:|---:|---:|---:|---:|")
        lines.append(
            f"| {ablation['as_built_auc_floor']:.4f} | "
            f"{ablation['edges_removed_auc_floor']:.4f} | "
            f"{ablation['features_constant_auc_floor']:.4f} | "
            f"{ablation['delta_structure_minus_no_edges']:.4f} | "
            f"{ablation['delta_structure_only_minus_full']:.4f} |"
        )
    else:
        lines.append("- n/a")

    lines.append("")
    lines.append("## Nested bootstrap (winner)")
    lines.append("")
    if nested:
        lines.append(
            f"| B_ok | mean | std | percentile_ci95 | naive_ci95 | wall_sec |"
        )
        lines.append("|---:|---:|---:|---|---|---:|")
        lines.append(
            f"| {nested.get('B_ok')} | {nested.get('auc_floor_mean')} | "
            f"{nested.get('auc_floor_std')} | {nested.get('percentile_ci95')} | "
            f"{nested.get('naive_score_resample_ci95')} | {nested.get('wall_sec')} |"
        )
    else:
        lines.append("- n/a")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def library_versions() -> dict[str, str]:
    import networkx
    import numpy
    import scipy
    import sklearn

    vers = {
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "scikit-learn": sklearn.__version__,
        "networkx": networkx.__version__,
    }
    try:
        import grakel

        vers["grakel"] = getattr(grakel, "__version__", "unknown")
    except Exception as e:  # noqa: BLE001
        vers["grakel"] = f"unavailable:{e}"
    vers["karateclub"] = "unavailable_on_cpython_3.14"
    vers["gensim"] = "unavailable_on_cpython_3.14"
    vers["embedding_impl"] = "native_fgsd_netlsd_graph2vec-tfidf-svd_gl2vec-tfidf-svd"
    return vers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Shallow GLAD kernels experiment")
    ap.add_argument("--out", type=Path, default=KERNELS_OUTPUT_ROOT)
    ap.add_argument("--skip-nested", action="store_true")
    ap.add_argument("--nested-B", type=int, default=None)
    ap.add_argument("--nested-only", action="store_true", help="Skip grid; run ablation+nested from winner.json")
    args = ap.parse_args(argv)

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("embeddings", "detectors", "ablation", "bootstrap"):
        (out / sub).mkdir(parents=True, exist_ok=True)

    t_all = time.perf_counter()
    bundle = load_bundle()
    train, test_b, test_m = bundle["train"], bundle["test_benign"], bundle["test_malware"]
    libv = library_versions()
    _write_json(out / "reproduce_config.json", {
        "split_digest": bundle["digest"],
        "n_train_benign": 562,
        "n_test_benign": 141,
        "n_test_malware": 1700,
        "seeds": list(SEEDS),
        "libraries": libv,
        "size_floor": SIZE_FLOOR,
        "ocpool_mean_raw": OCPOOL_MEAN_RAW,
        "T22_x": [22, 10],
        "T1K_x": [1000, 25],
        "WL_node_labels": {
            "T22": "identity (node index = category id)",
            "T1K": "argmax of 22-category one-hot in x[:,3:25]",
            "degree_variant": "undirected degree",
        },
        "fit_discipline": "train_benign_only; kernels use train×train + eval×train Gram",
    })

    all_rows: list[dict[str, Any]] = []
    if args.nested_only and (out / "detectors" / "grid_rows.json").is_file():
        grid = json.loads((out / "detectors" / "grid_rows.json").read_text(encoding="utf-8"))
        all_rows = grid["rows"]
        winner = grid.get("winner") or pick_winner(all_rows)
    else:
        for kind, tensors in (("T22", bundle["t22"]), ("T1K", bundle["t1k"])):
            rep = run_representation(
                kind=kind,
                tensors=tensors,
                train=train,
                test_b=test_b,
                test_m=test_m,
                out_root=out,
            )
            all_rows.extend(_iter_scores(rep))
            _write_json(out / "detectors" / f"{kind}_all.json", rep)
        winner = pick_winner(all_rows)
        _write_json(out / "detectors" / "winner.json", winner)
        _write_json(
            out / "detectors" / "grid_rows.json",
            {"rows": all_rows, "winner": winner},
        )

    ablation = None
    nested = None
    if winner is not None:
        kind = winner["kind"]
        tensors = bundle["t22"] if kind == "T22" else bundle["t1k"]
        cov = covariates_for(tensors, test_b + test_m, kind=kind)
        label_mode: LabelMode
        if winner["family"] == "kernel":
            label_mode = winner.get("label_mode") or (
                "identity" if kind == "T22" else "category_argmax"
            )
        else:
            label_mode = "identity" if kind == "T22" else "category_argmax"
            if winner["method"] == "Graph2Vec":
                pass

        def _score(tens: dict[str, dict[str, Any]]) -> dict[str, Any]:
            return score_config_on_tensors(
                tens,
                train=train,
                test_b=test_b,
                test_m=test_m,
                kind=kind,
                cov=cov,
                seeds=SEEDS,
                family=winner["family"],
                method=winner["method"],
                detector=winner["detector"],
                label_mode=label_mode,  # type: ignore[arg-type]
            )

        print("[ablation] winner", winner["method"], winner["detector"], flush=True)
        ablation = run_ablation_for_winner(
            winner=winner,
            tensors=tensors,
            train=train,
            test_b=test_b,
            test_m=test_m,
            kind=kind,
            cov=cov,
            seeds=SEEDS,
            score_fn=_score,
        )
        _write_json(out / "ablation" / "winner_ablation.json", ablation)

        if not args.skip_nested:
            print("[nested] bootstrap", flush=True)
            naive_ci = winner.get("ci95_floor") or [float("nan"), float("nan")]
            nested = nested_bootstrap_winner(
                tensors=tensors,
                train=train,
                test_b=test_b,
                test_m=test_m,
                kind=kind,
                family=winner["family"],
                method=winner["method"],
                detector=winner["detector"],
                label_mode=label_mode,  # type: ignore[arg-type]
                naive_ci=list(naive_ci),
                B=args.nested_B,
            )
            _write_json(out / "bootstrap" / "winner_nested.json", nested)

    write_summary(
        out / "SUMMARY.md",
        rows=all_rows,
        winner=winner,
        ablation=ablation,
        nested=nested,
        lib_versions=libv,
        digest=bundle["digest"],
    )
    _write_json(
        out / "detectors" / "grid_rows.json",
        {"rows": all_rows, "winner": winner, "wall_sec": time.perf_counter() - t_all},
    )
    print(f"[kernels] done in {time.perf_counter() - t_all:.1f}s → {out / 'SUMMARY.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
