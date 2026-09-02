"""Check 2 diagnostics on Run-3 eligible population (no training)."""

from __future__ import annotations

import csv
import io
import json
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from abrg.androct.categorize import categorize_soot_callee
from abrg.androct.parse import _CALL_RE
from abrg.androct.paths import (
    EXPECTED_ARCHIVES,
    androct_raw_dir,
    androct_run2_output_dir,
    androct_run3_output_dir,
)
from abrg.androct.run2_corpus import load_corpus_cache, static_cache_dir, _static_path
from abrg.androct.run_diagnostics import TLS_NETWORK_PREFIXES, _class_from_sig, _is_tls_network_caller


def _top30(counter: Counter[str]) -> list[dict[str, Any]]:
    total = sum(counter.values()) or 1
    return [
        {"rank": i, "class": k, "count": int(v), "share": float(v) / total}
        for i, (k, v) in enumerate(counter.most_common(30), 1)
    ]


def _pkg_prefix(package_name: str) -> str:
    return (package_name or "").strip()


def _is_app_caller(caller_class: str, package_name: str) -> bool:
    pkg = _pkg_prefix(package_name)
    if not pkg or not caller_class:
        return False
    return caller_class == pkg or caller_class.startswith(pkg + ".")


def _load_package_names(shas: set[str]) -> dict[str, str]:
    sdir = static_cache_dir(androct_run2_output_dir())
    out: dict[str, str] = {}
    for sha in shas:
        sp = _static_path(sdir, sha)
        if not sp.is_file():
            continue
        payload = torch.load(sp, map_location="cpu", weights_only=False)
        if not payload.get("ok"):
            continue
        report = payload.get("report")
        if report is None:
            continue
        out[sha] = str(getattr(report, "package_name", "") or "")
    return out


def _share_block(app: int, tls: int, other: int) -> dict[str, Any]:
    total = app + tls + other
    return {
        "n_events": total,
        "app_own_package": app,
        "tls_network_library": tls,
        "other": other,
        "share_app_own_package": (app / total) if total else float("nan"),
        "share_tls_network_library": (tls / total) if total else float("nan"),
        "share_other": (other / total) if total else float("nan"),
    }


def main() -> None:
    run2 = androct_run2_output_dir()
    out = androct_run3_output_dir() / "check2_run3_population"
    out.mkdir(parents=True, exist_ok=True)

    print("[check2] load Run-3 eligible population from corpus cache …", flush=True)
    bundle = load_corpus_cache(run2)
    eligible = bundle.eligible
    want_path = {a.path: a for a in eligible}
    shas = {a.sha256 for a in eligible}
    print(f"[check2] n_eligible={len(eligible)} loading package_name from static cache …", flush=True)
    pkg_by_sha = _load_package_names(shas)
    print(f"[check2] package_name resolved for {len(pkg_by_sha)}/{len(shas)} apps", flush=True)

    # per label + overall
    labels = ("benign", "malware", "all")

    def fresh_acc() -> dict[str, Any]:
        return {
            "crypto_callee": Counter(),
            "crypto_caller": Counter(),
            "network_callee": Counter(),
            "network_caller": Counter(),
            "file_io_callee": Counter(),
            "file_io_caller": Counter(),
            "crypto_share": {"app": 0, "tls": 0, "other": 0},
            "network_share": {"app": 0, "tls": 0, "other": 0},
            "file_io_share": {"app": 0, "tls": 0, "other": 0},
            "n_apps": 0,
            "n_apps_with_pkg": 0,
        }

    acc: dict[str, dict[str, Any]] = {lab: fresh_acc() for lab in labels}

    def bump_share(bucket: dict[str, int], caller_cls: str, package_name: str) -> None:
        if _is_tls_network_caller(caller_cls):
            bucket["tls"] += 1
        elif _is_app_caller(caller_cls, package_name):
            bucket["app"] += 1
        else:
            bucket["other"] += 1

    raw = androct_raw_dir()
    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        inner = meta["inner_dir"]
        print(f"[check2] scan {label} …", flush=True)
        n = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                if member.name.split("/", 1)[0] != inner:
                    continue
                app = want_path.get(member.name)
                if app is None:
                    continue
                n += 1
                package_name = pkg_by_sha.get(app.sha256, "")
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                targets = [acc[label], acc["all"]]
                for t in targets:
                    t["n_apps"] += 1
                    if package_name:
                        t["n_apps_with_pkg"] += 1
                try:
                    for line in text:
                        m = _CALL_RE.match(line.rstrip("\n\r"))
                        if not m:
                            continue
                        caller_sig, callee_sig = m.group(1), m.group(2)
                        cat = categorize_soot_callee(callee_sig)
                        if cat not in ("crypto", "network", "file_io"):
                            continue
                        caller_cls = _class_from_sig(caller_sig) or ""
                        callee_cls = _class_from_sig(callee_sig) or ""
                        for t in targets:
                            if cat == "crypto":
                                t["crypto_callee"][callee_cls] += 1
                                t["crypto_caller"][caller_cls] += 1
                                bump_share(t["crypto_share"], caller_cls, package_name)
                            elif cat == "network":
                                t["network_callee"][callee_cls] += 1
                                t["network_caller"][caller_cls] += 1
                                bump_share(t["network_share"], caller_cls, package_name)
                            else:
                                t["file_io_callee"][callee_cls] += 1
                                t["file_io_caller"][caller_cls] += 1
                                bump_share(t["file_io_share"], caller_cls, package_name)
                finally:
                    text.detach()
                if n % 200 == 0:
                    print(f"  … {label} apps={n}", flush=True)
        print(f"  {label} done apps={n}", flush=True)

    report: dict[str, Any] = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "population": "run3_eligible_from_corpus_cache",
        "n_eligible": len(eligible),
        "tls_network_prefixes": list(TLS_NETWORK_PREFIXES),
        "app_own_package_rule": (
            "caller class == package_name or startswith package_name+'.' "
            "(package_name from Androguard static cache); TLS checked first"
        ),
        "per_class": {},
    }

    lines = [
        "# Check 2 — crypto / network / file_io caller diagnostics (Run-3 population)",
        f"- UTC: {report['utc']}",
        f"- population: Run-3 eligible n={len(eligible)} (corpus_cache)",
        f"- package_name from static cache for {len(pkg_by_sha)} apps",
        f"- TLS prefixes: {', '.join(TLS_NETWORK_PREFIXES)}",
        "",
    ]

    for lab in labels:
        a = acc[lab]
        report["per_class"][lab] = {
            "n_apps": a["n_apps"],
            "n_apps_with_pkg": a["n_apps_with_pkg"],
            "top30_crypto_callee_classes": _top30(a["crypto_callee"]),
            "top30_crypto_caller_classes": _top30(a["crypto_caller"]),
            "top30_network_callee_classes": _top30(a["network_callee"]),
            "top30_network_caller_classes": _top30(a["network_caller"]),
            "top30_file_io_callee_classes": _top30(a["file_io_callee"]),
            "top30_file_io_caller_classes": _top30(a["file_io_caller"]),
            "crypto_caller_share": _share_block(
                a["crypto_share"]["app"], a["crypto_share"]["tls"], a["crypto_share"]["other"]
            ),
            "network_caller_share": _share_block(
                a["network_share"]["app"], a["network_share"]["tls"], a["network_share"]["other"]
            ),
            "file_io_caller_share": _share_block(
                a["file_io_share"]["app"], a["file_io_share"]["tls"], a["file_io_share"]["other"]
            ),
        }
        pc = report["per_class"][lab]
        lines.append(f"## Class `{lab}` (n_apps={pc['n_apps']}, with_pkg={pc['n_apps_with_pkg']})")
        for cat in ("crypto", "network", "file_io"):
            sh = pc[f"{cat}_caller_share"]
            lines.append(
                f"- {cat} caller share: app_own={sh['share_app_own_package']:.4f} "
                f"tls_net={sh['share_tls_network_library']:.4f} other={sh['share_other']:.4f} "
                f"(n={sh['n_events']})"
            )
        lines.append("")
        lines.append(f"### Top 30 crypto callee classes ({lab})")
        for row in pc["top30_crypto_callee_classes"]:
            lines.append(f"- {row['rank']}. `{row['class']}` count={row['count']} share={row['share']:.4f}")
        lines.append(f"### Top 30 crypto caller classes ({lab})")
        for row in pc["top30_crypto_caller_classes"]:
            lines.append(f"- {row['rank']}. `{row['class']}` count={row['count']} share={row['share']:.4f}")
        lines.append(f"### Top 30 network caller classes ({lab})")
        for row in pc["top30_network_caller_classes"]:
            lines.append(f"- {row['rank']}. `{row['class']}` count={row['count']} share={row['share']:.4f}")
        lines.append(f"### Top 30 file_io caller classes ({lab})")
        for row in pc["top30_file_io_caller_classes"]:
            lines.append(f"- {row['rank']}. `{row['class']}` count={row['count']} share={row['share']:.4f}")
        lines.append("")

        # CSVs
        for name, key in (
            ("crypto_callees", "top30_crypto_callee_classes"),
            ("crypto_callers", "top30_crypto_caller_classes"),
            ("network_callers", "top30_network_caller_classes"),
            ("file_io_callers", "top30_file_io_caller_classes"),
        ):
            with (out / f"check2_{name}_{lab}.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["rank", "class", "count", "share"])
                w.writeheader()
                for row in pc[key]:
                    w.writerow(row)

    (out / "check2_report.json").write_text(json.dumps(report, indent=2) + "\n")
    (out / "CHECK2.md").write_text("\n".join(lines) + "\n")
    # also copy pointer under run2 prep
    prep = run2 / "RUN4_PREP.md"
    prep.write_text(
        "\n".join(
            [
                "# Run 4 prep",
                "",
                "## Check 1 — encoder capacity vs node features",
                "- per-node feature dim: **10** (`s_v, declared_v, gate_v[0..2], reach_v, epoch_v, act_v_frac, sess_v, rec_v`)",
                "- nodes: **22** → flattened total **220**",
                "- GAE hidden: **64**",
                "- encoder map: **10 → 64 per node → EXPANDS** (×6.4), does not compress",
                "",
                "## Check 2 — crypto/network/file_io callers (Run-3 population)",
                f"- see `{out.relative_to(run2.parent.parent.parent) if False else out}`",
                f"- markdown: `{out / 'CHECK2.md'}`",
                "",
            ]
        )
        + "\n"
    )
    print("\n".join(lines[:80]), flush=True)
    print(f"[check2] done → {out}", flush=True)


if __name__ == "__main__":
    main()
