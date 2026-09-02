"""Resolve AndroCT package-named benign traces via AndroZoo index stream (no APK download)."""

from __future__ import annotations

import csv
import gzip
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

HEX64 = re.compile(r"^[0-9A-Fa-f]{64}$")
INDEX_URL = "https://androzoo.uni.lu/static/lists/latest.csv.gz"
OUT = Path("abrg/output/androct_2017/run2")


def load_inventory() -> tuple[list[dict], list[dict]]:
    inv = Path("datasets/androct_2017/inventory")
    benign = list(csv.DictReader(open(inv / "per_app_benign.csv", encoding="utf-8")))
    malware = list(csv.DictReader(open(inv / "per_app_malware.csv", encoding="utf-8")))
    return benign, malware


def bucket(n: int) -> str:
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    if 2 <= n <= 5:
        return "2-5"
    return "6+"


def dist_counts(d: dict[str, list]) -> dict[str, int]:
    out = {"0": 0, "1": 0, "2-5": 0, "6+": 0}
    for rows in d.values():
        out[bucket(len(rows))] += 1
    return out


def year_of(dex_date: str) -> str | None:
    if not dex_date:
        return None
    # formats like "2017-04-05 17:58:46" or "2017-04-05"
    m = re.match(r"^(\d{4})", dex_date.strip().strip('"'))
    return m.group(1) if m else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    benign, malware = load_inventory()

    b_hex = [r for r in benign if HEX64.match(r["sha256"])]
    b_pkg = [r for r in benign if not HEX64.match(r["sha256"])]
    m_hex = [r for r in malware if HEX64.match(r["sha256"])]
    m_pkg = [r for r in malware if not HEX64.match(r["sha256"])]

    split = {
        "benign": {
            "n": len(benign),
            "hex64": len(b_hex),
            "package_named": len(b_pkg),
            "confirm_608_1648": len(b_hex) == 608 and len(b_pkg) == 1648,
        },
        "malware": {
            "n": len(malware),
            "hex64": len(m_hex),
            "package_named": len(m_pkg),
            "confirm_1742_0": len(m_hex) == 1742 and len(m_pkg) == 0,
        },
    }
    print("=== 1. Split ===", json.dumps(split, indent=2), flush=True)

    pkg_set = {r["sha256"].lower() for r in b_pkg}
    hex_set = {r["sha256"].upper() for r in b_hex}
    assert len(pkg_set) == 1648
    assert len(hex_set) == 608

    # pkg_lower -> list of candidate row dicts (all matching index rows)
    candidates: dict[str, list[dict[str, str]]] = {p: [] for p in pkg_set}
    # hex64 -> pkg_name from index (first/any)
    hex_pkg: dict[str, str] = {}
    hex_found: set[str] = set()

    print(f"[index] streaming {INDEX_URL} …", flush=True)
    n_lines = 0
    n_matched_pkg = 0
    # Use curl for progress resilience + gzip
    proc = subprocess.Popen(
        ["curl", "-sS", INDEX_URL],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    with gzip.GzipFile(fileobj=proc.stdout) as gz:
        # text wrapper
        import io

        text = io.TextIOWrapper(gz, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text)
        # expected fields
        for row in reader:
            n_lines += 1
            if n_lines % 2_000_000 == 0:
                print(
                    f"  … lines={n_lines} pkg_hits={n_matched_pkg} hex_hits={len(hex_found)}",
                    flush=True,
                )
            pkg = (row.get("pkg_name") or "").strip().strip('"').lower()
            sha = (row.get("sha256") or "").strip().upper()
            if pkg in pkg_set:
                candidates[pkg].append(
                    {
                        "sha256": sha,
                        "pkg_name": pkg,
                        "dex_date": (row.get("dex_date") or "").strip(),
                        "apk_size": (row.get("apk_size") or "").strip(),
                        "vt_detection": (row.get("vt_detection") or "").strip(),
                        "markets": (row.get("markets") or "").strip(),
                        "vercode": (row.get("vercode") or "").strip(),
                    }
                )
                n_matched_pkg += 1
            if sha in hex_set and sha not in hex_found:
                hex_found.add(sha)
                hex_pkg[sha] = pkg

    rc = proc.wait()
    if rc != 0:
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        raise SystemExit(f"curl failed rc={rc}: {err[:300]}")

    print(f"[index] done lines={n_lines} pkg_row_hits={n_matched_pkg} hex_found={len(hex_found)}/608", flush=True)

    # 2. pre-filter candidate-count distribution (all matching rows)
    # include packages with 0 candidates
    pre_dist = dist_counts(candidates)
    print("=== 2. Pre-filter candidate-count distribution ===", pre_dist, flush=True)

    # 3. filter dex_date year==2017 AND vt_detection==0
    filtered: dict[str, list[dict[str, str]]] = {}
    unresolvable: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for pkg, rows in candidates.items():
        keep = [
            r
            for r in rows
            if year_of(r["dex_date"]) == "2017" and r["vt_detection"] == "0"
        ]
        filtered[pkg] = keep
        if len(keep) == 1:
            resolved.append(
                {
                    "pkg_name": pkg,
                    "sha256": keep[0]["sha256"],
                    "dex_date": keep[0]["dex_date"],
                    "apk_size": keep[0]["apk_size"],
                    "markets": keep[0]["markets"],
                    "n_prefilter": len(rows),
                }
            )
        elif len(keep) == 0:
            has_any = len(rows) > 0
            has_2017 = any(year_of(r["dex_date"]) == "2017" for r in rows)
            has_clean_any = any(r["vt_detection"] == "0" for r in rows)
            has_2017_nonzero_vt = any(
                year_of(r["dex_date"]) == "2017" and r["vt_detection"] != "0"
                for r in rows
            )
            if not has_any:
                why = "no_index_match"
            elif not has_2017:
                why = "no_2017_row"
            elif has_2017_nonzero_vt and not any(
                year_of(r["dex_date"]) == "2017" and r["vt_detection"] == "0" for r in rows
            ):
                why = "no_clean_row"  # 2017 exists but none with vt==0
            else:
                why = "no_clean_row"
            unresolvable.append(
                {
                    "pkg_name": pkg,
                    "why": why,
                    "n_prefilter": len(rows),
                    "n_2017": sum(1 for r in rows if year_of(r["dex_date"]) == "2017"),
                    "n_vt0": sum(1 for r in rows if r["vt_detection"] == "0"),
                    "n_2017_vt0": 0,
                    "has_clean_any_year": has_clean_any,
                }
            )
        else:
            # ambiguous: record all + differing fields
            fields = ("dex_date", "apk_size", "markets", "sha256", "vercode", "vt_detection")
            differing = []
            for f in fields:
                vals = sorted({r[f] for r in keep})
                if len(vals) > 1:
                    differing.append({"field": f, "values": vals})
            ambiguous.append(
                {
                    "pkg_name": pkg,
                    "n_candidates": len(keep),
                    "candidates": keep,
                    "differing_fields": differing,
                    "n_prefilter": len(rows),
                }
            )

    post_dist = dist_counts(filtered)
    # fix: dist_counts on filtered includes all 1648 keys
    print("=== 3. Post-filter (2017 & vt==0) candidate-count distribution ===", post_dist, flush=True)

    why_counts: dict[str, int] = defaultdict(int)
    for u in unresolvable:
        why_counts[u["why"]] += 1

    # 4. Sanity: hex64 pkg_names overlap with 1648?
    hex_pkgs = [hex_pkg[s] for s in hex_set if s in hex_pkg and hex_pkg[s]]
    hex_pkgs_set = set(hex_pkgs)
    overlap = sorted(hex_pkgs_set & pkg_set)
    hex_missing_in_index = sorted(hex_set - hex_found)
    print(
        "=== 4. Hex64 sanity ===",
        {
            "hex64_found_in_index": len(hex_found),
            "hex64_missing_in_index": len(hex_missing_in_index),
            "unique_pkg_names_for_found_hex": len(hex_pkgs_set),
            "overlap_with_1648_package_named": len(overlap),
            "overlap_pkgs_sample": overlap[:20],
        },
        flush=True,
    )

    # 5. Final counts
    final = {
        "benign": {
            "hex64_named": len(b_hex),
            "package_resolved_exact1": len(resolved),
            "resolvable_total": len(b_hex) + len(resolved),
            "ambiguous": len(ambiguous),
            "unresolvable": len(unresolvable),
            "unresolvable_why": dict(why_counts),
            "package_named_total": len(b_pkg),
            "check_sum_pkg": len(resolved) + len(ambiguous) + len(unresolvable),
        },
        "malware": {
            "hex64_named": len(m_hex),
            "package_named": len(m_pkg),
            "resolvable_total": len(m_hex),  # control: all hex64
            "ambiguous": 0,
            "unresolvable": 0,
        },
        "prefilter_candidate_dist": pre_dist,
        "postfilter_candidate_dist": post_dist,
        "index_lines_read": n_lines,
        "utc": datetime.now(timezone.utc).isoformat(),
    }
    print("=== 5. Final counts ===", json.dumps(final, indent=2), flush=True)

    # Persist (compact; ambiguous can be large)
    (OUT / "pkg_resolve_report.json").write_text(json.dumps(final, indent=2) + "\n")
    with (OUT / "pkg_resolved.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["pkg_name", "sha256", "dex_date", "apk_size", "markets", "n_prefilter"],
        )
        w.writeheader()
        for r in sorted(resolved, key=lambda x: x["pkg_name"]):
            w.writerow(r)
    with (OUT / "pkg_unresolvable.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "pkg_name", "why", "n_prefilter", "n_2017", "n_vt0", "n_2017_vt0", "has_clean_any_year",
            ],
        )
        w.writeheader()
        for r in sorted(unresolvable, key=lambda x: x["pkg_name"]):
            w.writerow(r)
    with (OUT / "pkg_ambiguous.jsonl").open("w", encoding="utf-8") as f:
        for r in sorted(ambiguous, key=lambda x: x["pkg_name"]):
            f.write(json.dumps(r) + "\n")
    with (OUT / "hex64_pkg_overlap.txt").open("w", encoding="utf-8") as f:
        f.write("\n".join(overlap) + ("\n" if overlap else ""))
    with (OUT / "hex64_missing_in_index.txt").open("w", encoding="utf-8") as f:
        f.write("\n".join(hex_missing_in_index) + ("\n" if hex_missing_in_index else ""))

    # markdown summary
    lines = [
        "# Package→SHA256 resolution (AndroZoo index stream)",
        f"- UTC: {final['utc']}",
        f"- index_lines_read: {n_lines}",
        "",
        "## 1. Naming split",
        f"- benign: hex64={split['benign']['hex64']} package_named={split['benign']['package_named']} "
        f"(confirm_608_1648={split['benign']['confirm_608_1648']})",
        f"- malware: hex64={split['malware']['hex64']} package_named={split['malware']['package_named']} "
        f"(confirm_1742_0={split['malware']['confirm_1742_0']})",
        "",
        "## 2. Pre-filter candidate-count distribution (1648 pkgs)",
        f"- {pre_dist}",
        "",
        "## 3. Post-filter (dex_date year==2017 AND vt_detection==0)",
        f"- {post_dist}",
        f"- resolved_exact1: {len(resolved)}",
        f"- ambiguous_2plus: {len(ambiguous)}",
        f"- unresolvable: {len(unresolvable)} why={dict(why_counts)}",
        "",
        "## 4. Hex64 sanity",
        f"- hex64 found in index: {len(hex_found)}/608",
        f"- hex64 missing: {len(hex_missing_in_index)}",
        f"- overlap pkg_names with 1648: {len(overlap)}",
        "",
        "## 5. Final",
        f"- benign resolvable: {final['benign']['resolvable_total']} "
        f"(={final['benign']['hex64_named']} hex + {final['benign']['package_resolved_exact1']} pkg)",
        f"- benign ambiguous: {final['benign']['ambiguous']}",
        f"- benign unresolvable: {final['benign']['unresolvable']}",
        f"- malware resolvable: {final['malware']['resolvable_total']}",
    ]
    (OUT / "PKG_RESOLVE.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
