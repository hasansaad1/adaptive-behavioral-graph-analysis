"""Recover package→SHA resolution using observed hex64 benign year range (index stream only)."""

from __future__ import annotations

import csv
import gzip
import io
import json
import random
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HEX64 = re.compile(r"^[0-9A-Fa-f]{64}$")
INDEX_URL = "https://androzoo.uni.lu/static/lists/latest.csv.gz"
OUT = Path("abrg/output/androct_2017/run2")
SEED = 42
MALWARE_SAMPLE_N = 300


def year_of(dex_date: str) -> str | None:
    if not dex_date:
        return None
    m = re.match(r"^(\d{4})", dex_date.strip().strip('"'))
    return m.group(1) if m else None


def bucket(n: int) -> str:
    if n == 0:
        return "0"
    if n == 1:
        return "1"
    if 2 <= n <= 5:
        return "2-5"
    return "6+"


def dist_counts(keys: set[str], mapping: dict[str, list]) -> dict[str, int]:
    out = {"0": 0, "1": 0, "2-5": 0, "6+": 0}
    for k in keys:
        out[bucket(len(mapping.get(k, [])))] += 1
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    inv = Path("datasets/androct_2017/inventory")
    benign = list(csv.DictReader(open(inv / "per_app_benign.csv", encoding="utf-8")))
    malware = list(csv.DictReader(open(inv / "per_app_malware.csv", encoding="utf-8")))

    b_hex = [r for r in benign if HEX64.match(r["sha256"])]
    b_pkg = [r for r in benign if not HEX64.match(r["sha256"])]
    m_hex = [r for r in malware if HEX64.match(r["sha256"])]
    assert len(b_hex) == 608 and len(b_pkg) == 1648
    assert len(m_hex) == 1742

    hex_set = {r["sha256"].upper() for r in b_hex}
    pkg_set = {r["sha256"].lower() for r in b_pkg}
    rng = random.Random(SEED)
    mal_sample = [r["sha256"].upper() for r in rng.sample(m_hex, MALWARE_SAMPLE_N)]
    mal_set = set(mal_sample)

    # Collectors
    hex_rows: dict[str, dict[str, str]] = {}  # sha -> {dex_date, vt, year, pkg}
    mal_rows: dict[str, dict[str, str]] = {}
    candidates: dict[str, list[dict[str, str]]] = {p: [] for p in pkg_set}

    print(f"[index] streaming {INDEX_URL} …", flush=True)
    n_lines = 0
    proc = subprocess.Popen(
        ["curl", "-sS", INDEX_URL],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout is not None
    with gzip.GzipFile(fileobj=proc.stdout) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", errors="replace", newline="")
        reader = csv.DictReader(text)
        for row in reader:
            n_lines += 1
            if n_lines % 2_000_000 == 0:
                print(
                    f"  … lines={n_lines} hex={len(hex_rows)}/608 "
                    f"mal={len(mal_rows)}/{MALWARE_SAMPLE_N}",
                    flush=True,
                )
            sha = (row.get("sha256") or "").strip().upper()
            pkg = (row.get("pkg_name") or "").strip().strip('"').lower()
            dex = (row.get("dex_date") or "").strip()
            vt = (row.get("vt_detection") or "").strip()
            markets = (row.get("markets") or "").strip()
            size = (row.get("apk_size") or "").strip()
            ver = (row.get("vercode") or "").strip()

            if sha in hex_set and sha not in hex_rows:
                hex_rows[sha] = {
                    "sha256": sha,
                    "pkg_name": pkg,
                    "dex_date": dex,
                    "vt_detection": vt,
                    "year": year_of(dex) or "",
                }
            if sha in mal_set and sha not in mal_rows:
                mal_rows[sha] = {
                    "sha256": sha,
                    "dex_date": dex,
                    "vt_detection": vt,
                    "year": year_of(dex) or "",
                }
            if pkg in pkg_set:
                candidates[pkg].append(
                    {
                        "sha256": sha,
                        "pkg_name": pkg,
                        "dex_date": dex,
                        "apk_size": size,
                        "vt_detection": vt,
                        "markets": markets,
                        "vercode": ver,
                        "year": year_of(dex) or "",
                    }
                )

    rc = proc.wait()
    if rc != 0:
        err = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        raise SystemExit(f"curl failed rc={rc}: {err[:300]}")
    print(
        f"[index] done lines={n_lines} hex={len(hex_rows)}/608 mal={len(mal_rows)}/{MALWARE_SAMPLE_N}",
        flush=True,
    )

    # --- 1. hex64 benign ground truth ---
    year_dist = Counter(r["year"] or "MISSING" for r in hex_rows.values())
    vt_dist = Counter(r["vt_detection"] if r["vt_detection"] != "" else "EMPTY" for r in hex_rows.values())
    observed_years = sorted(y for y in year_dist if y not in ("", "MISSING") and y.isdigit())
    year_min = observed_years[0] if observed_years else None
    year_max = observed_years[-1] if observed_years else None
    year_range = set(observed_years)  # discrete observed years (not interpolated gaps)

    step1 = {
        "n_looked_up": len(hex_rows),
        "n_missing_in_index": len(hex_set - set(hex_rows)),
        "year_distribution": dict(sorted(year_dist.items())),
        "vt_detection_distribution": dict(sorted(vt_dist.items(), key=lambda x: str(x[0]))),
        "observed_years_sorted": observed_years,
        "year_min": year_min,
        "year_max": year_max,
        "filter_years_used": observed_years,
    }
    print("=== 1. Hex64 benign dex_date / vt ===", json.dumps(step1, indent=2), flush=True)

    # --- 2. malware sample ---
    mal_year = Counter(r["year"] or "MISSING" for r in mal_rows.values())
    step2 = {
        "n_sample": MALWARE_SAMPLE_N,
        "n_found": len(mal_rows),
        "n_missing": len(mal_set - set(mal_rows)),
        "year_distribution": dict(sorted(mal_year.items())),
        "n_distinct_years": len([y for y in mal_year if y not in ("", "MISSING")]),
    }
    print("=== 2. Malware sample year ===", json.dumps(step2, indent=2), flush=True)

    # --- 3. re-resolve with observed years + vt==0 ---
    filtered: dict[str, list[dict[str, str]]] = {}
    resolved: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    unresolvable: list[dict[str, Any]] = []

    for pkg, rows in candidates.items():
        keep = [
            r
            for r in rows
            if r["year"] in year_range and r["vt_detection"] == "0"
        ]
        filtered[pkg] = keep
        if len(keep) == 1:
            resolved.append(
                {
                    "pkg_name": pkg,
                    "sha256": keep[0]["sha256"],
                    "dex_date": keep[0]["dex_date"],
                    "year": keep[0]["year"],
                    "apk_size": keep[0]["apk_size"],
                    "markets": keep[0]["markets"],
                    "n_prefilter": len(rows),
                }
            )
        elif len(keep) == 0:
            has_any = len(rows) > 0
            has_year = any(r["year"] in year_range for r in rows)
            if not has_any:
                why = "no_index_match"
            elif not has_year:
                why = "no_row_in_observed_year_range"
            else:
                why = "no_clean_row"
            unresolvable.append(
                {
                    "pkg_name": pkg,
                    "why": why,
                    "n_prefilter": len(rows),
                    "n_in_year_range": sum(1 for r in rows if r["year"] in year_range),
                    "n_vt0": sum(1 for r in rows if r["vt_detection"] == "0"),
                }
            )
        else:
            years = sorted({r["year"] for r in keep})
            ambiguous.append(
                {
                    "pkg_name": pkg,
                    "n_candidates": len(keep),
                    "years": years,
                    "years_differ": len(years) > 1,
                    "candidates": keep,
                }
            )

    post_dist = dist_counts(pkg_set, filtered)
    why_c = Counter(u["why"] for u in unresolvable)
    step3 = {
        "filter": {
            "years": observed_years,
            "vt_detection": "0",
        },
        "candidate_dist": post_dist,
        "resolved_exact1": len(resolved),
        "ambiguous": len(ambiguous),
        "unresolvable": len(unresolvable),
        "unresolvable_why": dict(why_c),
    }
    print("=== 3. Corrected-filter resolution ===", json.dumps(step3, indent=2), flush=True)

    # --- 4. ambiguous analysis ---
    amb_year_differ = [a for a in ambiguous if a["years_differ"]]
    amb_same_year = [a for a in ambiguous if not a["years_differ"]]
    # among same-year: could apk_size uniquely identify? markets uniquely?
    could_apk_size = 0
    could_markets = 0
    could_either = 0
    for a in amb_same_year:
        sizes = [c["apk_size"] for c in a["candidates"]]
        mkts = [c["markets"] for c in a["candidates"]]
        # unique sizes for all candidates (all distinct) → fully disambiguable by size
        size_unique = len(set(sizes)) == len(sizes)
        mkt_unique = len(set(mkts)) == len(mkts)
        if size_unique:
            could_apk_size += 1
        if mkt_unique:
            could_markets += 1
        if size_unique or mkt_unique:
            could_either += 1

    step4 = {
        "n_ambiguous": len(ambiguous),
        "n_differ_in_dex_date_year": len(amb_year_differ),
        "n_same_dex_date_year": len(amb_same_year),
        "same_year_could_disambiguate_by_apk_size_all_distinct": could_apk_size,
        "same_year_could_disambiguate_by_markets_all_distinct": could_markets,
        "same_year_could_disambiguate_by_apk_size_OR_markets": could_either,
        "same_year_distribution_of_that_year": dict(
            Counter(a["years"][0] if a["years"] else "MISSING" for a in amb_same_year)
        ),
    }
    print("=== 4. Ambiguous analysis ===", json.dumps(step4, indent=2), flush=True)

    # --- 5. final ---
    final = {
        "benign_hex64": 608,
        "benign_package_resolved_exact1": len(resolved),
        "benign_resolvable_total": 608 + len(resolved),
        "benign_ambiguous": len(ambiguous),
        "benign_unresolvable": len(unresolvable),
        "malware_resolvable_control": 1742,
        "filter_years": observed_years,
    }
    print("=== 5. Final ===", json.dumps(final, indent=2), flush=True)

    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "index_lines_read": n_lines,
        "step1_hex64_benign": step1,
        "step2_malware_sample": step2,
        "step3_corrected_resolution": step3,
        "step4_ambiguous": step4,
        "step5_final": final,
    }
    (OUT / "pkg_resolve_recovered_report.json").write_text(json.dumps(report, indent=2) + "\n")

    with (OUT / "pkg_resolved_recovered.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["pkg_name", "sha256", "dex_date", "year", "apk_size", "markets", "n_prefilter"],
        )
        w.writeheader()
        for r in sorted(resolved, key=lambda x: x["pkg_name"]):
            w.writerow(r)

    with (OUT / "hex64_benign_dex_vt.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sha256", "pkg_name", "dex_date", "year", "vt_detection"])
        w.writeheader()
        for sha in sorted(hex_rows):
            w.writerow(hex_rows[sha])

    with (OUT / "malware_sample_dex.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["sha256", "dex_date", "year", "vt_detection"])
        w.writeheader()
        for sha in sorted(mal_rows):
            w.writerow(mal_rows[sha])

    with (OUT / "pkg_ambiguous_recovered.jsonl").open("w", encoding="utf-8") as f:
        for a in sorted(ambiguous, key=lambda x: x["pkg_name"]):
            # omit full candidate dump size control — keep differing summary + sha list
            slim = {
                "pkg_name": a["pkg_name"],
                "n_candidates": a["n_candidates"],
                "years": a["years"],
                "years_differ": a["years_differ"],
                "sha256s": [c["sha256"] for c in a["candidates"]],
                "apk_sizes": [c["apk_size"] for c in a["candidates"]],
                "markets": [c["markets"] for c in a["candidates"]],
                "dex_dates": [c["dex_date"] for c in a["candidates"]],
            }
            f.write(json.dumps(slim) + "\n")

    lines = [
        "# Package resolution recovered (observed year filter)",
        f"- UTC: {report['utc']}",
        f"- index_lines: {n_lines}",
        "",
        "## 1. Hex64 benign ground truth (n=608)",
        f"- year_distribution: {dict(sorted(year_dist.items()))}",
        f"- vt_detection_distribution: {dict(sorted(vt_dist.items(), key=lambda x: str(x[0])))}",
        f"- filter_years: {observed_years}",
        "",
        "## 2. Malware sample (n=300, seed=42)",
        f"- year_distribution: {dict(sorted(mal_year.items()))}",
        f"- n_distinct_years: {step2['n_distinct_years']}",
        "",
        "## 3. Corrected filter resolution (1648 pkgs)",
        f"- candidate_dist: {post_dist}",
        f"- resolved_exact1: {len(resolved)}",
        f"- ambiguous: {len(ambiguous)}",
        f"- unresolvable: {len(unresolvable)} why={dict(why_c)}",
        "",
        "## 4. Ambiguous",
        f"- differ_in_year: {len(amb_year_differ)}",
        f"- same_year: {len(amb_same_year)}",
        f"- same_year disambiguable by apk_size (all distinct): {could_apk_size}",
        f"- same_year disambiguable by markets (all distinct): {could_markets}",
        f"- same_year disambiguable by apk_size OR markets: {could_either}",
        "",
        "## 5. Final benign resolvable",
        f"- {608 + len(resolved)} (=608 hex + {len(resolved)} pkg)",
        f"- ambiguous={len(ambiguous)} unresolvable={len(unresolvable)}",
        f"- malware control resolvable={1742}",
    ]
    (OUT / "PKG_RESOLVE_RECOVERED.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
