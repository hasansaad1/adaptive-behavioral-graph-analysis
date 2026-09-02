"""Stage 1 — caller/callee inventory over train-benign."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from abrg.androct.run_gae_run2 import _dist
from abrg.invgraph.extract import CALLER_DISCARD_SITES, ICC_DECISION

FRAMEWORK_PREFIXES = ("android.", "java.", "javax.")


def _class_of(method: str) -> str:
    cls, _, meth = method.rpartition(".")
    return cls if cls else method


def _package_prefix(class_name: str, n_seg: int = 2) -> str:
    parts = class_name.split(".")
    if len(parts) <= n_seg:
        return class_name
    return ".".join(parts[:n_seg])


def _is_framework(class_name: str) -> bool:
    return any(class_name.startswith(p) for p in FRAMEWORK_PREFIXES)


def classify_caller(caller: str, app_prefix: str) -> str:
    cls = _class_of(caller)
    if _is_framework(cls):
        return "framework"
    if app_prefix and cls.startswith(app_prefix):
        return "app"
    return "library"


def dominant_app_prefix(callers: list[str]) -> str:
    """Most frequent 2-segment package prefix among non-framework callers."""
    ctr: Counter[str] = Counter()
    for c in callers:
        cls = _class_of(c)
        if _is_framework(cls):
            continue
        ctr[_package_prefix(cls, 2)] += 1
    if not ctr:
        return ""
    return ctr.most_common(1)[0][0]


def stage1_inventory(
    train_benign_pairs: dict[str, list[tuple[str, str]]],
    train_benign_shas: list[str],
    *,
    out_dir: Path,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    callers: Counter[str] = Counter()
    callees: Counter[str] = Counter()
    pairs_ctr: Counter[tuple[str, str]] = Counter()
    caller_out_deg: Counter[str] = Counter()  # distinct callees per caller (corpus)
    callee_in_deg: Counter[str] = Counter()
    # per-app then aggregate classification counts
    class_counts = Counter({"app": 0, "framework": 0, "library": 0})
    lib_prefixes: Counter[str] = Counter()
    caller_out_degs_list: list[float] = []
    callee_in_degs_list: list[float] = []

    # build global adjacency for degree
    out_nbrs: dict[str, set[str]] = defaultdict(set)
    in_nbrs: dict[str, set[str]] = defaultdict(set)

    n_icc_note = ICC_DECISION

    for sha in train_benign_shas:
        pairs = train_benign_pairs[sha]
        app_callers = [u for u, _ in pairs]
        app_pref = dominant_app_prefix(app_callers)
        for u, v in pairs:
            callers[u] += 1
            callees[v] += 1
            pairs_ctr[(u, v)] += 1
            out_nbrs[u].add(v)
            in_nbrs[v].add(u)
            bucket = classify_caller(u, app_pref)
            class_counts[bucket] += 1
            if bucket == "library":
                lib_prefixes[_package_prefix(_class_of(u), 2)] += 1

    for u, nbrs in out_nbrs.items():
        caller_out_degs_list.append(float(len(nbrs)))
    for v, nbrs in in_nbrs.items():
        callee_in_degs_list.append(float(len(nbrs)))

    report = {
        "caller_discard_sites": CALLER_DISCARD_SITES,
        "icc_decision": n_icc_note,
        "n_train_benign_apps": len(train_benign_shas),
        "n_distinct_callers": len(callers),
        "n_distinct_callees": len(callees),
        "n_distinct_pairs": len(pairs_ctr),
        "n_call_events": int(sum(callers.values())),
        "caller_out_degree": _dist(caller_out_degs_list),
        "callee_in_degree": _dist(callee_in_degs_list),
        "caller_class_counts": dict(class_counts),
        "caller_class_frac": {
            k: class_counts[k] / max(sum(class_counts.values()), 1) for k in class_counts
        },
        "top30_library_prefixes": [
            {"prefix": p, "count": int(c)} for p, c in lib_prefixes.most_common(30)
        ],
        "top20_callers_by_freq": [
            {"caller": c, "freq": int(f)} for c, f in callers.most_common(20)
        ],
        "top20_callees_by_freq": [
            {"callee": c, "freq": int(f)} for c, f in callees.most_common(20)
        ],
        "top20_pairs_by_freq": [
            {"caller": u, "callee": v, "freq": int(f)}
            for (u, v), f in pairs_ctr.most_common(20)
        ],
    }
    (out_dir / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # degree raw for plots
    (out_dir / "caller_out_degree.json").write_text(
        json.dumps({"degrees": caller_out_degs_list[:50000]}, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "callee_in_degree.json").write_text(
        json.dumps({"degrees": callee_in_degs_list[:50000]}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[invgraph] stage1 callers={report['n_distinct_callers']} "
        f"callees={report['n_distinct_callees']} pairs={report['n_distinct_pairs']}",
        flush=True,
    )
    return report
