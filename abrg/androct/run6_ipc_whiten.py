"""
ipc_intents scalar probes + whitened dual-recon (Run5 pins: h=8, α=0.2, N=1).
"""

from __future__ import annotations

import argparse
import io
import json
import math
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from scipy.stats import spearmanr
from sklearn.covariance import LedoitWolf

from abrg.androct.categorize import categorize_icc_callsite, categorize_soot_callee
from abrg.androct.parse import _CALL_RE, _ICC_CALLSITE, _INTENT_RECV, _INTENT_SENT
from abrg.androct.paths import (
    EXPECTED_ARCHIVES,
    androct_raw_dir,
    androct_run2_output_dir,
    androct_run6_output_dir,
)
from abrg.androct.run2_corpus import load_corpus_cache, static_cache_dir, _static_path
from abrg.androct.run_gae import EdgeWeightProbeEncoder
from abrg.androct.run_gae_run2 import (
    EPOCHS,
    LR,
    SEED,
    WD,
    _auc_with_bootstrap,
    _dist,
    floor_aucs,
    split_apps,
)
from abrg.autoencoder import (
    FeatureDecoder,
    build_gae,
    graph_reconstruction_error_dual,
    seed_rng,
    train_gae_multi_dual,
)
from abrg.config import K_BURST
from abrg.features import feature_vector_labels, node_feature_dim
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

IPC_IDX = GRAPH_CATEGORY_UNIVERSE.index("ipc_intents")
FEAT_NAMES = feature_vector_labels(normalize=True)
ACT_IDX = FEAT_NAMES.index("act_v_frac")
REACH_IDX = FEAT_NAMES.index("reach_v")
DECLARED_IDX = FEAT_NAMES.index("declared_v")

HIDDEN = 8
ALPHA = 0.2


def _rho(xs: list[float], ys: list[float]) -> float:
    pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
    if len(pairs) < 3:
        return float("nan")
    a, b = zip(*pairs)
    r, _ = spearmanr(a, b)
    return float(r)


def _spearman_per_class(
    apps: list, get_x, get_y
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for lab in ("benign", "malware", "all"):
        subset = apps if lab == "all" else [a for a in apps if a.label == lab]
        xs = [get_x(a) for a in subset]
        ys = [get_y(a) for a in subset]
        pairs = [(x, y) for x, y in zip(xs, ys) if math.isfinite(x) and math.isfinite(y)]
        if len(pairs) < 3:
            out[lab] = {"rho": float("nan"), "n": len(pairs)}
        else:
            a, b = zip(*pairs)
            out[lab] = {"rho": float(spearmanr(a, b).correlation), "n": len(pairs)}
    return out


def _scan_ipc_sent_recv(eligible: list) -> dict[str, dict[str, float]]:
    """Per-app counts: ipc_call, icc_sent, icc_recv, n_mapped_total."""
    want = {a.path: a for a in eligible}
    stats = {
        a.sha256: {
            "ipc_call": 0,
            "icc_sent": 0,
            "icc_recv": 0,
            "n_mapped": 0,
            "n_events": 0,
        }
        for a in eligible
    }
    raw = androct_raw_dir()
    for fname, meta in EXPECTED_ARCHIVES.items():
        print(f"[ipc] scan {meta['label']} …", flush=True)
        n = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                app = want.get(member.name)
                if app is None:
                    continue
                n += 1
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                st = stats[app.sha256]
                in_icc = False
                icc_kind = None
                try:
                    for raw_line in text:
                        line = raw_line.rstrip("\n\r")
                        if not line.strip():
                            continue
                        if _INTENT_SENT.match(line):
                            in_icc = True
                            icc_kind = "sent"
                            continue
                        if _INTENT_RECV.match(line):
                            in_icc = True
                            icc_kind = "recv"
                            continue
                        if in_icc:
                            mc = _ICC_CALLSITE.match(line)
                            if mc:
                                st["n_events"] += 1
                                cat = categorize_icc_callsite(mc.group(1).strip())
                                if cat is not None:
                                    st["n_mapped"] += 1
                                    if icc_kind == "sent":
                                        st["icc_sent"] += 1
                                    elif icc_kind == "recv":
                                        st["icc_recv"] += 1
                                in_icc = False
                                icc_kind = None
                                continue
                            if line.startswith("caller=") or line.startswith("\t"):
                                continue
                            in_icc = False
                            icc_kind = None
                        m = _CALL_RE.match(line)
                        if m:
                            st["n_events"] += 1
                            cat = categorize_soot_callee(m.group(2))
                            if cat is not None:
                                st["n_mapped"] += 1
                                if cat == "ipc_intents":
                                    st["ipc_call"] += 1
                finally:
                    text.detach()
                if n % 200 == 0:
                    print(f"  … {meta['label']} {n}", flush=True)
    out: dict[str, dict[str, float]] = {}
    for sha, st in stats.items():
        denom = float(st["n_mapped"]) if st["n_mapped"] else float("nan")
        out[sha] = {
            **{k: float(v) for k, v in st.items()},
            "ipc_call_share": st["ipc_call"] / denom if st["n_mapped"] else float("nan"),
            "icc_sent_share": st["icc_sent"] / denom if st["n_mapped"] else float("nan"),
            "icc_recv_share": st["icc_recv"] / denom if st["n_mapped"] else float("nan"),
            "ipc_total_share": (st["ipc_call"] + st["icc_sent"] + st["icc_recv"]) / denom
            if st["n_mapped"]
            else float("nan"),
        }
    return out


def _whiten_fit(X_rows: np.ndarray, eps: float = 1e-5) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean, whitening_matrix) so (x-mean) @ W.T is whitened."""
    mu = X_rows.mean(axis=0)
    Xc = X_rows - mu
    lw = LedoitWolf().fit(Xc)
    cov = lw.covariance_
    evals, evecs = np.linalg.eigh(cov)
    evals = np.maximum(evals, eps)
    W = evecs @ np.diag(1.0 / np.sqrt(evals)) @ evecs.T
    return mu.astype(np.float64), W.astype(np.float64)


def _apply_whiten(x: torch.Tensor, mu: np.ndarray, W: np.ndarray) -> torch.Tensor:
    arr = x.detach().cpu().numpy().astype(np.float64)
    out = (arr - mu) @ W.T
    return torch.tensor(out, dtype=x.dtype)


def run_ipc_probes(bundle, split, out: Path) -> dict[str, Any]:
    tensors = bundle.tensors
    eligible = bundle.eligible
    test_apps = split["test_benign"] + split["test_malware"]

    # 1a) act_v_frac from tensors
    ipc_share = {a.sha256: float(tensors[a.sha256]["x"][IPC_IDX, ACT_IDX].item()) for a in eligible}
    scores = [ipc_share[a.sha256] for a in test_apps]
    labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
    auc_act = _auc_with_bootstrap(scores, labels)

    # 1b) sent vs recv from traces
    cache = out / "ipc_sent_recv_per_app.json"
    if cache.is_file():
        sent_recv = json.loads(cache.read_text(encoding="utf-8"))
        print(f"[ipc] loaded sent/recv cache n={len(sent_recv)}", flush=True)
    else:
        sent_recv = _scan_ipc_sent_recv(eligible)
        cache.write_text(json.dumps(sent_recv, indent=2) + "\n")

    def auc_for(key: str) -> dict[str, Any]:
        sc = [float(sent_recv[a.sha256][key]) for a in test_apps]
        return _auc_with_bootstrap(sc, labels)

    auc_sent = auc_for("icc_sent_share")
    auc_recv = auc_for("icc_recv_share")
    auc_call = auc_for("ipc_call_share")
    auc_total = auc_for("ipc_total_share")

    # 2) Spearman(ipc share, declared component count = reach_v)
    def act(a):
        return ipc_share[a.sha256]

    def reach(a):
        return float(tensors[a.sha256]["x"][IPC_IDX, REACH_IDX].item())

    def declared(a):
        return float(tensors[a.sha256]["x"][IPC_IDX, DECLARED_IDX].item())

    spear_reach = _spearman_per_class(eligible, act, reach)
    spear_declared = _spearman_per_class(eligible, act, declared)

    # Also total component count from static report if available
    def total_components(a) -> float:
        sp = _static_path(static_cache_dir(androct_run2_output_dir()), a.sha256)
        if not sp.is_file():
            return float("nan")
        payload = torch.load(sp, map_location="cpu", weights_only=False)
        if not payload.get("ok") or payload.get("report") is None:
            return float("nan")
        # reach_v already encodes per-cat component counts; sum across cats as proxy
        # Better: count unique components from report — not stored. Use max reach or sum.
        # Use Androguard-derived: sum of reach_v is not unique. Stick to ipc reach_v as primary.
        return reach(a)

    result = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "split": {
            "train": len(split["train"]),
            "test_benign": len(split["test_benign"]),
            "test_malware": len(split["test_malware"]),
        },
        "ipc_act_v_frac_auc": auc_act,
        "icc_sent_share_auc": auc_sent,
        "icc_recv_share_auc": auc_recv,
        "ipc_call_share_auc": auc_call,
        "ipc_total_mapped_share_auc": auc_total,
        "spearman_ipc_act_vs_reach_v": spear_reach,
        "spearman_ipc_act_vs_declared_v": spear_declared,
        "defs": {
            "ipc_act_v_frac": "normalized activity share on ipc_intents node (tensor)",
            "icc_sent_share": "ICC Intent-sent blocks / n_mapped",
            "icc_recv_share": "ICC Intent-received blocks / n_mapped",
            "reach_v": "static feature: # components declaring ipc-related APIs",
            "declared_v": "static feature: binary declared ipc APIs on node",
        },
    }
    # distributions
    for lab, apps in (
        ("test_benign", split["test_benign"]),
        ("test_malware", split["test_malware"]),
    ):
        result[f"ipc_act_v_frac_dist_{lab}"] = _dist([ipc_share[a.sha256] for a in apps])
        result[f"icc_sent_share_dist_{lab}"] = _dist(
            [float(sent_recv[a.sha256]["icc_sent_share"]) for a in apps
             if math.isfinite(sent_recv[a.sha256]["icc_sent_share"])]
        )
        result[f"icc_recv_share_dist_{lab}"] = _dist(
            [float(sent_recv[a.sha256]["icc_recv_share"]) for a in apps
             if math.isfinite(sent_recv[a.sha256]["icc_recv_share"])]
        )

    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = [
        "# ipc_intents scalar probes",
        f"- UTC: {result['utc']}",
        "",
        "## AUC (same GAE test split)",
        f"- ipc_act_v_frac: floor={auc_act['auc_floor']:.6f} "
        f"CI=[{auc_act['ci95_floor'][0]:.6f}, {auc_act['ci95_floor'][1]:.6f}] "
        f"dir={auc_act['direction']} raw={auc_act['auc']:.6f}",
        f"- icc_sent_share: floor={auc_sent['auc_floor']:.6f} "
        f"CI=[{auc_sent['ci95_floor'][0]:.6f}, {auc_sent['ci95_floor'][1]:.6f}] "
        f"dir={auc_sent['direction']} raw={auc_sent['auc']:.6f}",
        f"- icc_recv_share: floor={auc_recv['auc_floor']:.6f} "
        f"CI=[{auc_recv['ci95_floor'][0]:.6f}, {auc_recv['ci95_floor'][1]:.6f}] "
        f"dir={auc_recv['direction']} raw={auc_recv['auc']:.6f}",
        f"- ipc_call_share (non-ICC calls→ipc): floor={auc_call['auc_floor']:.6f} "
        f"dir={auc_call['direction']}",
        "",
        "## Spearman(ipc_act_v_frac, static)",
        f"- vs reach_v (declared component count): {json.dumps(spear_reach)}",
        f"- vs declared_v (binary): {json.dumps(spear_declared)}",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return result


def run_whiten(bundle, split, out: Path) -> dict[str, Any]:
    tensors = bundle.tensors
    train = split["train"]
    test_apps = split["test_benign"] + split["test_malware"]

    # Fit whitening on all train-benign node feature rows
    rows = torch.cat([tensors[a.sha256]["x"] for a in train], dim=0).numpy()
    mu, W = _whiten_fit(rows)
    print(f"[whiten] fit on {rows.shape[0]} node-rows × {rows.shape[1]} feats", flush=True)

    def whiten_graph(a):
        t = tensors[a.sha256]
        x_w = _apply_whiten(t["x"], mu, W)
        return (x_w, t["edge_index"], t["edge_weight"])

    train_graphs = [
        whiten_graph(a)
        for a in train
        if tensors[a.sha256]["edge_index"].numel() > 0
    ]

    seed_rng(SEED)
    model = build_gae(node_feature_dim(), HIDDEN)
    model.encoder = EdgeWeightProbeEncoder(model.encoder)
    feat_dec = FeatureDecoder(HIDDEN, node_feature_dim())
    losses, final_loss = train_gae_multi_dual(
        model, feat_dec, train_graphs, EPOCHS, LR, alpha=ALPHA, weight_decay=WD
    )

    def score_app(a) -> float:
        x, ei, ew = whiten_graph(a)
        return graph_reconstruction_error_dual(model, feat_dec, x, ei, ew, alpha=ALPHA)

    train_scores = {a.sha256: score_app(a) for a in train}
    tb = {a.sha256: score_app(a) for a in split["test_benign"]}
    tm = {a.sha256: score_app(a) for a in split["test_malware"]}
    scores = [tb[a.sha256] for a in split["test_benign"]] + [
        tm[a.sha256] for a in split["test_malware"]
    ]
    labels = [0] * len(split["test_benign"]) + [1] * len(split["test_malware"])
    auc = _auc_with_bootstrap(scores, labels)

    sc = list(scores)
    leak = {
        "mapped_event_count": _rho(sc, [float(tensors[a.sha256]["n_mapped"]) for a in test_apps]),
        "total_event_count": _rho(sc, [float(tensors[a.sha256]["n_events"]) for a in test_apps]),
        "active_nodes": _rho(sc, [float(tensors[a.sha256]["n_active"]) for a in test_apps]),
        "edge_count": _rho(sc, [float(tensors[a.sha256]["n_edges"]) for a in test_apps]),
        "graph_density": _rho(sc, [float(tensors[a.sha256]["density"]) for a in test_apps]),
        "static_feature_norm": _rho(sc, [float(tensors[a.sha256]["static_norm"]) for a in test_apps]),
    }
    floors = floor_aucs(test_apps, tensors)
    highest = max(floors[k]["auc_floor"] for k in floors)
    d_tr = _dist([v for v in train_scores.values() if math.isfinite(v)])
    d_tb = _dist([v for v in tb.values() if math.isfinite(v)])
    d_tm = _dist([v for v in tm.values() if math.isfinite(v)])
    higher = (
        "test_malware"
        if d_tm["median"] > d_tb["median"]
        else ("test_benign" if d_tb["median"] > d_tm["median"] else "tied")
    )

    result = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "axis": "whiten node features vs train-benign (LedoitWolf) before encoder",
        "pins": {
            "hidden": HIDDEN,
            "alpha": ALPHA,
            "epochs": EPOCHS,
            "seed": SEED,
            "n_parts": 1,
            "match": "Run5 h=8 alpha=0.2 dual-recon",
        },
        "final_train_loss": final_loss,
        "auc": auc,
        "leak_spearman": leak,
        "floors": {
            k: {
                "auc_floor": v["auc_floor"],
                "direction": v["direction"],
                "ci95_floor": v["ci95_floor"],
            }
            for k, v in floors.items()
        },
        "highest_floor": highest,
        "arm_below_highest_floor": auc["auc_floor"] < highest,
        "recon_error": {
            "train_benign": d_tr,
            "test_benign": d_tb,
            "test_malware": d_tm,
            "higher_median_error_class": higher,
            "benign_malware_error_direction_inverted": higher == "test_benign",
        },
        "whiten": {
            "n_fit_rows": int(rows.shape[0]),
            "feat_dim": int(rows.shape[1]),
            "mean_l2": float(np.linalg.norm(mu)),
        },
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.json").write_text(json.dumps(result, indent=2) + "\n")
    torch.save(
        {"model_state": model.state_dict(), "feature_decoder_state": feat_dec.state_dict(),
         "mu": mu, "W": W, "hidden": HIDDEN, "alpha": ALPHA},
        out / "gae_whiten_h8_a02.pt",
    )
    lines = [
        "# Whitened dual-recon (h=8, α=0.2, N=1)",
        f"- UTC: {result['utc']}",
        f"- whiten: center+LedoitWolf on train-benign node rows "
        f"(n={rows.shape[0]} × F={rows.shape[1]})",
        f"- auc={auc['auc']:.6f} auc_floor={auc['auc_floor']:.6f} "
        f"CI_floor=[{auc['ci95_floor'][0]:.6f}, {auc['ci95_floor'][1]:.6f}] "
        f"dir={auc['direction']}",
        f"- below_floor={result['arm_below_highest_floor']} highest_floor={highest:.6f}",
        f"- higher_err={higher} inverted={higher == 'test_benign'}",
        f"- recon medians train={d_tr['median']:.6f} "
        f"test_ben={d_tb['median']:.6f} test_mal={d_tm['median']:.6f}",
        "",
        "## Spearman ρ",
    ]
    for k, v in leak.items():
        lines.append(f"- {k}: {v:.6f}" if math.isfinite(v) else f"- {k}: nan")
    lines.append("")
    lines.append("## Floors")
    for k, v in floors.items():
        lines.append(
            f"- {k}: floor={v['auc_floor']:.6f} dir={v['direction']} "
            f"CI=[{v['ci95_floor'][0]:.6f}, {v['ci95_floor'][1]:.6f}]"
        )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 6 — ipc probes + whitened GAE")
    parser.add_argument(
        "--task",
        choices=("ipc", "whiten", "both"),
        default="both",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    root = androct_run6_output_dir()
    bundle = load_corpus_cache(androct_run2_output_dir())
    split = split_apps(bundle.eligible)
    print(
        f"[run] split train={len(split['train'])} "
        f"test_b={len(split['test_benign'])} test_m={len(split['test_malware'])}",
        flush=True,
    )
    if args.task in ("ipc", "both"):
        ipc_out = args.output_dir if args.task == "ipc" and args.output_dir else root / "ipc_scalar_probes"
        run_ipc_probes(bundle, split, ipc_out)
    if args.task in ("whiten", "both"):
        wh_out = args.output_dir if args.task == "whiten" and args.output_dir else root / "whiten_h8_a02"
        run_whiten(bundle, split, wh_out)
    print(f"[run] done → {root}", flush=True)


if __name__ == "__main__":
    main()
