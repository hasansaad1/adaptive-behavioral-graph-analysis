"""AndroZoo APK fetch for AndroCT — vault-only, stream-to-disk, SHA256 verify, static-only."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from abrg.androct.paths import (
    androct_apk_dir,
    androct_inventory_dir,
    androct_run2_output_dir,
)
from abrg.dataset_paths import REPO_ROOT as _REPO_ROOT

ANDROZOO_DOWNLOAD = "https://androzoo.uni.lu/api/download"
RESOLUTION_GATE = 0.90
ZIP_MAGIC = b"PK\x03\x04"
# Conservative rate limit: max concurrent downloads (AndroZoo courtesy).
DEFAULT_WORKERS = 4
CHUNK = 1024 * 1024  # 1 MiB stream chunks


@dataclass
class ResolveRow:
    sha256: str
    label: str
    path: str
    n_mapped: int
    status: str
    detail: str = ""
    apk_path: str = ""
    bytes: int = 0


def _load_api_key() -> Optional[str]:
    env = os.environ.get("ANDROZOO_API_KEY", "").strip()
    if env:
        return env
    candidates = [
        _REPO_ROOT / ".androzoo_api_key",
        Path.cwd() / ".androzoo_api_key",
        Path.home() / ".androzoo_api_key",
        Path("/Volumes/ABRG_MW/.androzoo_api_key"),
        Path("/Volumes/ABRG_MW/credentials/androzoo_api_key"),
    ]
    for p in candidates:
        if p.is_file():
            key = p.read_text(encoding="utf-8").strip()
            if key:
                return key
    return None


def inventory_apps_with_mapped() -> list[dict[str, Any]]:
    inv = androct_inventory_dir()
    rows: list[dict[str, Any]] = []
    for label in ("benign", "malware"):
        with (inv / f"per_app_{label}.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                rows.append(
                    {
                        "sha256": r["sha256"].upper(),
                        "path": r["path"],
                        "label": label,
                        "n_mapped": int(r["n_mapped"]),
                        "n_events": int(r["n_events"]),
                        "n_active_cats": int(r["n_active_cats"]),
                    }
                )
    return rows


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest().upper()


def _verify_apk(path: Path, expected_sha: str) -> tuple[bool, str, int]:
    """Return (ok, detail, size). Checks ZIP magic + SHA256."""
    if not path.is_file():
        return False, "missing", 0
    size = path.stat().st_size
    if size < 4:
        return False, "too_small", size
    with path.open("rb") as f:
        magic = f.read(4)
    if magic != ZIP_MAGIC:
        return False, f"not_apk_magic={magic!r}", size
    got = _sha256_file(path)
    if got != expected_sha.upper():
        return False, f"sha256_mismatch got={got}", size
    return True, "ok", size


def assert_safe_write_path(apk_dir: Path) -> None:
    """Refuse writes into git worktree, synced dirs, or system temp."""
    apk_dir = apk_dir.resolve()
    repo = _REPO_ROOT.resolve()
    if str(apk_dir).startswith(str(repo) + os.sep) or apk_dir == repo:
        raise SystemExit(f"REFUSE: apk_dir inside git worktree: {apk_dir}")
    forbidden_prefixes = [
        Path("/tmp").resolve(),
        Path(tempfile.gettempdir()).resolve(),
        Path("/var/folders"),
        Path.home() / "Library" / "Mobile Documents",
        Path.home() / "Library" / "CloudStorage",
        Path.home() / "Dropbox",
        Path.home() / "Google Drive",
        Path.home() / "OneDrive",
    ]
    for pref in forbidden_prefixes:
        try:
            pref_r = pref.resolve()
        except OSError:
            continue
        if str(apk_dir).startswith(str(pref_r) + os.sep) or apk_dir == pref_r:
            raise SystemExit(f"REFUSE: apk_dir under forbidden prefix {pref_r}: {apk_dir}")
    # Must be under an attached vault volume
    allowed_roots = [
        Path("/Volumes/ABRG_ANDROCT_APKS").resolve(),
        Path("/Volumes/ABRG_MW").resolve(),
    ]
    if not any(
        str(apk_dir).startswith(str(root) + os.sep) or apk_dir == root
        for root in allowed_roots
        if root.is_dir()
    ):
        raise SystemExit(
            f"REFUSE: apk_dir must be under /Volumes/ABRG_ANDROCT_APKS or "
            f"/Volumes/ABRG_MW, got {apk_dir}"
        )


def fetch_one(
    *,
    sha256: str,
    label: str,
    path: str,
    n_mapped: int,
    apk_dir: Path,
    api_key: Optional[str],
    timeout: int = 300,
) -> ResolveRow:
    """Stream APK directly to vault .part then rename. Never uses /tmp."""
    dest = apk_dir / f"{sha256}.apk"
    part = apk_dir / f"{sha256}.apk.part"

    if dest.is_file():
        ok, detail, size = _verify_apk(dest, sha256)
        if ok:
            return ResolveRow(
                sha256=sha256,
                label=label,
                path=path,
                n_mapped=n_mapped,
                status="resolved",
                detail="cached_verified",
                apk_path=str(dest),
                bytes=size,
            )
        # corrupt cache — remove and re-fetch
        dest.unlink(missing_ok=True)
        detail_cache = detail
    else:
        detail_cache = ""

    if api_key is None:
        return ResolveRow(
            sha256=sha256,
            label=label,
            path=path,
            n_mapped=n_mapped,
            status="missing_key",
            detail="ANDROZOO_API_KEY not set",
        )

    qs = urlencode({"apikey": api_key, "sha256": sha256})
    url = f"{ANDROZOO_DOWNLOAD}?{qs}"
    h = hashlib.sha256()
    nbytes = 0
    try:
        if part.exists():
            part.unlink()
        req = Request(url, headers={"User-Agent": "abrg-androct-static/1.0"})
        with urlopen(req, timeout=timeout) as resp, part.open("wb") as out:
            # stream — no full buffer, no tempfile module
            first = True
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                if first:
                    if chunk[:4] != ZIP_MAGIC and len(chunk) >= 4:
                        part.unlink(missing_ok=True)
                        return ResolveRow(
                            sha256=sha256,
                            label=label,
                            path=path,
                            n_mapped=n_mapped,
                            status="not_apk",
                            detail=f"magic={chunk[:4]!r} prior={detail_cache}",
                        )
                    first = False
                out.write(chunk)
                h.update(chunk)
                nbytes += len(chunk)
        got = h.hexdigest().upper()
        if got != sha256.upper():
            part.unlink(missing_ok=True)
            return ResolveRow(
                sha256=sha256,
                label=label,
                path=path,
                n_mapped=n_mapped,
                status="sha256_mismatch",
                detail=f"got={got}",
                bytes=nbytes,
            )
        part.replace(dest)
        return ResolveRow(
            sha256=sha256,
            label=label,
            path=path,
            n_mapped=n_mapped,
            status="resolved",
            detail="downloaded_verified" + (f";replaced_corrupt:{detail_cache}" if detail_cache else ""),
            apk_path=str(dest),
            bytes=nbytes,
        )
    except HTTPError as exc:
        part.unlink(missing_ok=True)
        return ResolveRow(
            sha256=sha256,
            label=label,
            path=path,
            n_mapped=n_mapped,
            status="http_error",
            detail=f"HTTP {exc.code}: {exc.reason}",
        )
    except (URLError, TimeoutError, OSError) as exc:
        part.unlink(missing_ok=True)
        return ResolveRow(
            sha256=sha256,
            label=label,
            path=path,
            n_mapped=n_mapped,
            status="io_error",
            detail=str(exc)[:200],
        )


def summarize_resolution(rows: list[ResolveRow]) -> dict[str, Any]:
    per_class: dict[str, Any] = {}
    for label in ("benign", "malware"):
        cls = [r for r in rows if r.label == label]
        n = len(cls)
        n_ok = sum(1 for r in cls if r.status == "resolved")
        status_counts: dict[str, int] = {}
        sizes = [r.bytes for r in cls if r.status == "resolved" and r.bytes > 0]
        for r in cls:
            status_counts[r.status] = status_counts.get(r.status, 0) + 1
        rate = (n_ok / n) if n else 0.0
        sizes_sorted = sorted(sizes)
        med = sizes_sorted[len(sizes_sorted) // 2] if sizes_sorted else 0
        per_class[label] = {
            "n": n,
            "n_resolved": n_ok,
            "n_failed": n - n_ok,
            "resolution_rate": rate,
            "gate_pass": rate >= RESOLUTION_GATE,
            "status_counts": status_counts,
            "resolved_bytes_total": int(sum(sizes)),
            "resolved_bytes_median": int(med),
            "resolved_bytes_mean": (sum(sizes) / len(sizes)) if sizes else 0.0,
        }
    b, m = per_class["benign"], per_class["malware"]
    fail_b = (b["n_failed"] / b["n"]) if b["n"] else float("nan")
    fail_m = (m["n_failed"] / m["n"]) if m["n"] else float("nan")
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "gate_threshold": RESOLUTION_GATE,
        "apk_dir": str(androct_apk_dir()),
        "api_key_present": _load_api_key() is not None,
        "per_class": per_class,
        "failure_rate_benign": fail_b,
        "failure_rate_malware": fail_m,
        "failure_rate_delta_malware_minus_benign": fail_m - fail_b,
        "gate_pass_both_classes": b["gate_pass"] and m["gate_pass"],
        "n_total": len(rows),
        "n_resolved_total": sum(1 for r in rows if r.status == "resolved"),
    }


def _write_rows_csv(path: Path, rows: list[ResolveRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "sha256", "label", "path", "n_mapped", "status", "detail", "apk_path", "bytes",
            ],
        )
        w.writeheader()
        for r in sorted(rows, key=lambda x: (x.label, x.sha256)):
            w.writerow(asdict(r))


def fetch_batch(
    apps: list[dict[str, Any]],
    *,
    workers: int = DEFAULT_WORKERS,
    label: str = "fetch",
) -> list[ResolveRow]:
    apk_dir = androct_apk_dir()
    apk_dir.mkdir(parents=True, exist_ok=True)
    assert_safe_write_path(apk_dir)
    print(f"[{label}] write_path={apk_dir.resolve()} n={len(apps)} workers={workers}", flush=True)
    api_key = _load_api_key()
    if api_key is None:
        raise SystemExit("ANDROZOO_API_KEY / .androzoo_api_key missing")

    rows: list[ResolveRow] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [
            pool.submit(
                fetch_one,
                sha256=a["sha256"],
                label=a["label"],
                path=a["path"],
                n_mapped=a["n_mapped"],
                apk_dir=apk_dir,
                api_key=api_key,
            )
            for a in apps
        ]
        for fut in as_completed(futs):
            rows.append(fut.result())
            done += 1
            if done % 25 == 0 or done == len(apps):
                n_ok = sum(1 for r in rows if r.status == "resolved")
                print(f"  … {label} {done}/{len(apps)} resolved_so_far={n_ok}", flush=True)
    return rows


def stratified_pilot(seed: int = 42, n_per_class: int = 100) -> list[dict[str, Any]]:
    apps = [a for a in inventory_apps_with_mapped() if a["n_mapped"] >= 1]
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for label in ("benign", "malware"):
        pool = [a for a in apps if a["label"] == label]
        rng.shuffle(pool)
        out.extend(pool[:n_per_class])
    return out


def run_pilot() -> dict[str, Any]:
    """Stage 0 — 100+100 pilot with Androguard parse probe."""
    out = androct_run2_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    apk_dir = androct_apk_dir()
    apk_dir.mkdir(parents=True, exist_ok=True)
    assert_safe_write_path(apk_dir)

    pilot_apps = stratified_pilot()
    rows = fetch_batch(pilot_apps, workers=DEFAULT_WORKERS, label="pilot")
    summary = summarize_resolution(rows)

    # Project full corpus disk from pilot medians
    full = [a for a in inventory_apps_with_mapped() if a["n_mapped"] >= 1]
    n_b = sum(1 for a in full if a["label"] == "benign")
    n_m = sum(1 for a in full if a["label"] == "malware")
    med_b = summary["per_class"]["benign"]["resolved_bytes_median"]
    med_m = summary["per_class"]["malware"]["resolved_bytes_median"]
    mean_b = summary["per_class"]["benign"]["resolved_bytes_mean"]
    mean_m = summary["per_class"]["malware"]["resolved_bytes_mean"]
    proj_median = n_b * med_b + n_m * med_m
    proj_mean = n_b * mean_b + n_m * mean_m
    import shutil

    free = shutil.disk_usage(apk_dir).free
    summary["pilot"] = True
    summary["projection"] = {
        "n_benign_full": n_b,
        "n_malware_full": n_m,
        "projected_bytes_from_median": int(proj_median),
        "projected_bytes_from_mean": int(proj_mean),
        "projected_GB_from_median": proj_median / (1024**3),
        "projected_GB_from_mean": proj_mean / (1024**3),
        "vault_free_bytes": int(free),
        "vault_free_GB": free / (1024**3),
        "disk_gate_pass": proj_mean <= free * 0.95,  # leave 5% headroom
    }

    # Androguard parse on resolved pilot APKs
    from abrg.static import analyze_apk_static

    parse_rows: list[dict[str, Any]] = []
    for r in rows:
        if r.status != "resolved":
            continue
        try:
            report = analyze_apk_static(Path(r.apk_path))
            n_perm = len(report.permissions)
            n_nonzero = sum(
                1
                for n in report.nodes.values()
                if n.declared_v > 0 or n.reach_v > 0 or n.s_v > 0 or any(n.gate_v)
            )
            parse_rows.append(
                {
                    "sha256": r.sha256,
                    "label": r.label,
                    "status": "ok",
                    "n_permissions": n_perm,
                    "n_cats_nonzero_static": n_nonzero,
                    "package": report.package_name,
                    "detail": "",
                }
            )
        except Exception as exc:  # noqa: BLE001 — collect reasons
            parse_rows.append(
                {
                    "sha256": r.sha256,
                    "label": r.label,
                    "status": "fail",
                    "n_permissions": 0,
                    "n_cats_nonzero_static": 0,
                    "package": "",
                    "detail": f"{type(exc).__name__}: {exc}"[:300],
                }
            )

    parse_summary: dict[str, Any] = {"per_class": {}}
    for label in ("benign", "malware"):
        pr = [p for p in parse_rows if p["label"] == label]
        n_ok = sum(1 for p in pr if p["status"] == "ok")
        fails = [p["detail"] for p in pr if p["status"] == "fail"]
        reasons: dict[str, int] = {}
        for d in fails:
            key = d.split(":")[0] if d else "unknown"
            reasons[key] = reasons.get(key, 0) + 1
        parse_summary["per_class"][label] = {
            "n_attempted": len(pr),
            "n_ok": n_ok,
            "n_fail": len(pr) - n_ok,
            "success_rate": (n_ok / len(pr)) if pr else 0.0,
            "failure_reasons": reasons,
        }
    summary["androguard_pilot"] = parse_summary

    _write_rows_csv(out / "pilot_resolution_rows.csv", rows)
    (out / "pilot_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (out / "pilot_androguard_rows.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "sha256", "label", "status", "n_permissions",
                "n_cats_nonzero_static", "package", "detail",
            ],
        )
        w.writeheader()
        for p in parse_rows:
            w.writerow(p)

    lines = [
        "# Stage 0 — Pilot fetch GATE",
        f"- UTC: {summary['utc']}",
        f"- write_path: `{summary['apk_dir']}`",
        f"- sample: 100 benign + 100 malware (seed=42)",
        "",
        "## Resolution",
        "| Class | n | resolved | failed | rate | median_bytes | total_bytes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in ("benign", "malware"):
        pc = summary["per_class"][label]
        lines.append(
            f"| {label} | {pc['n']} | {pc['n_resolved']} | {pc['n_failed']} | "
            f"{pc['resolution_rate']:.4f} | {pc['resolved_bytes_median']} | {pc['resolved_bytes_total']} |"
        )
    proj = summary["projection"]
    lines += [
        "",
        "## Disk projection (full 2122+1703)",
        f"- projected_GB_from_median: {proj['projected_GB_from_median']:.2f}",
        f"- projected_GB_from_mean: {proj['projected_GB_from_mean']:.2f}",
        f"- vault_free_GB: {proj['vault_free_GB']:.2f}",
        f"- disk_gate_pass: {proj['disk_gate_pass']}",
        "",
        "## Androguard parse (resolved pilot)",
    ]
    for label in ("benign", "malware"):
        pc = parse_summary["per_class"][label]
        lines.append(
            f"- {label}: ok={pc['n_ok']}/{pc['n_attempted']} "
            f"rate={pc['success_rate']:.4f} fail_reasons={pc['failure_reasons']}"
        )
    lines.append("")
    res_ok = summary["gate_pass_both_classes"]
    disk_ok = proj["disk_gate_pass"]
    if res_ok and disk_ok:
        lines.append("## Verdict\nPILOT GATE PASS — proceed to Stage 1 full fetch.")
    else:
        lines.append("## Verdict\nPILOT GATE FAIL — STOP.")
        if not res_ok:
            lines.append("- resolution < 90% in at least one class")
        if not disk_ok:
            lines.append("- projected disk exceeds free space")
    (out / "STAGE0_PILOT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)
    summary["pilot_gate_pass"] = res_ok and disk_ok
    return summary


def run_stage1_full() -> dict[str, Any]:
    out = androct_run2_output_dir()
    apps = [a for a in inventory_apps_with_mapped() if a["n_mapped"] >= 1]
    rows = fetch_batch(apps, workers=DEFAULT_WORKERS, label="stage1_full")
    summary = summarize_resolution(rows)
    # append-friendly names — keep prior resolution_* from missing_key run
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _write_rows_csv(out / f"resolution_rows_full_{stamp}.csv", rows)
    (out / f"resolution_report_full_{stamp}.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    # also write current pointers
    _write_rows_csv(out / "resolution_rows_full.csv", rows)
    (out / "resolution_report_full.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Stage 1 — Full fetch GATE ({summary['utc']})",
        f"- write_path: `{summary['apk_dir']}`",
        "",
        "| Class | n | resolved | failed | rate | status_counts |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for label in ("benign", "malware"):
        pc = summary["per_class"][label]
        lines.append(
            f"| {label} | {pc['n']} | {pc['n_resolved']} | {pc['n_failed']} | "
            f"{pc['resolution_rate']:.4f} | `{pc['status_counts']}` |"
        )
    lines += [
        "",
        f"- failure_rate_benign={summary['failure_rate_benign']:.4f}",
        f"- failure_rate_malware={summary['failure_rate_malware']:.4f}",
        f"- delta(malware−benign)={summary['failure_rate_delta_malware_minus_benign']:.4f}",
        "",
    ]
    if summary["gate_pass_both_classes"]:
        lines.append("## Verdict\nGATE PASS — proceed to Stage 2.")
    else:
        lines.append("## Verdict\nGATE FAIL — STOP. Do not fall back to dynamic-only.")
    # append to STAGE1 if exists
    gate_path = out / "STAGE1_FULL_GATE.md"
    gate_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)
    return summary


def run_preflight() -> dict[str, Any]:
    import shutil

    apk_dir = androct_apk_dir()
    apk_dir.mkdir(parents=True, exist_ok=True)
    assert_safe_write_path(apk_dir)
    free_gb = shutil.disk_usage(apk_dir).free / (1024**3)
    key_ok = _load_api_key() is not None
    report = {
        "utc": datetime.now(timezone.utc).isoformat(),
        "write_path": str(apk_dir.resolve()),
        "free_GB": free_gb,
        "required_GB": 100.0,
        "disk_pass": free_gb >= 100.0,
        "key_present": key_ok,
        "inside_git_worktree": False,
        "tempdir": tempfile.gettempdir(),
        "streams_to_vault_only": True,
    }
    report["gate_pass"] = report["disk_pass"] and report["key_present"]
    out = androct_run2_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (out / f"PREFLIGHT_{stamp}.json").write_text(json.dumps(report, indent=2) + "\n")
    md = out / "PREFLIGHT.md"
    section = (
        f"# Pre-flight — {report['utc']}\n\n"
        f"- write_path: `{report['write_path']}`\n"
        f"- free_GB: **{free_gb:.2f}** (need ≥100) → {'PASS' if report['disk_pass'] else 'FAIL'}\n"
        f"- key_present: {key_ok}\n"
        f"- streams to vault only (no /tmp): True\n"
        f"- verdict: {'PASS' if report['gate_pass'] else 'FAIL — STOP'}\n\n---\n\n"
    )
    prev = md.read_text(encoding="utf-8") if md.exists() else ""
    md.write_text(prev + section, encoding="utf-8")
    print(section, flush=True)
    return report


def run_stage1_manifest(
    manifest_path: Path | None = None,
    *,
    workers: int = DEFAULT_WORKERS,
) -> dict[str, Any]:
    """Stage 1 — fetch APKs listed in run2/fetch_manifest.csv (resume-safe)."""
    out = androct_run2_output_dir()
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_path or (out / "fetch_manifest.csv")
    apps: list[dict[str, Any]] = []
    with manifest_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            apps.append(
                {
                    "sha256": row["sha256"].upper(),
                    "label": row["label"],
                    "path": row["path"],
                    "n_mapped": int(row["n_mapped"]),
                }
            )
    pre = run_preflight()
    if not pre["gate_pass"]:
        raise SystemExit(2)

    rows = fetch_batch(apps, workers=workers, label="stage1_manifest")
    summary = summarize_resolution(rows)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _write_rows_csv(out / f"resolution_rows_manifest_{stamp}.csv", rows)
    _write_rows_csv(out / "resolution_rows_manifest.csv", rows)
    (out / "resolution_report_manifest.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"# Stage 1 — Manifest full fetch ({summary['utc']})",
        f"- write_path: `{summary['apk_dir']}`",
        f"- manifest: `{manifest_path}` n={len(apps)}",
        "",
        "| Class | n | resolved | failed | rate | status_counts |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for label in ("benign", "malware"):
        pc = summary["per_class"][label]
        lines.append(
            f"| {label} | {pc['n']} | {pc['n_resolved']} | {pc['n_failed']} | "
            f"{pc['resolution_rate']:.4f} | `{pc['status_counts']}` |"
        )
    lines += [
        "",
        f"- failure_rate_benign={summary['failure_rate_benign']:.4f}",
        f"- failure_rate_malware={summary['failure_rate_malware']:.4f}",
        f"- delta(malware−benign)={summary['failure_rate_delta_malware_minus_benign']:.4f}",
        "",
    ]
    if summary["gate_pass_both_classes"]:
        lines.append("## Verdict\nGATE PASS — proceed to Stage 2.")
    else:
        lines.append("## Verdict\nGATE FAIL — STOP. Do not fall back to dynamic-only.")
    (out / "STAGE1_MANIFEST_GATE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)
    return summary


def main() -> None:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        choices=["preflight", "pilot", "full", "pipeline", "manifest"],
    )
    args = p.parse_args()
    if args.command == "preflight":
        r = run_preflight()
        raise SystemExit(0 if r["gate_pass"] else 2)
    if args.command == "pilot":
        r = run_pilot()
        raise SystemExit(0 if r.get("pilot_gate_pass") else 2)
    if args.command == "full":
        r = run_stage1_full()
        raise SystemExit(0 if r["gate_pass_both_classes"] else 2)
    if args.command == "manifest":
        r = run_stage1_manifest()
        raise SystemExit(0 if r["gate_pass_both_classes"] else 2)
    if args.command == "pipeline":
        r = run_preflight()
        if not r["gate_pass"]:
            raise SystemExit(2)
        r = run_pilot()
        if not r.get("pilot_gate_pass"):
            raise SystemExit(2)
        r = run_stage1_full()
        raise SystemExit(0 if r["gate_pass_both_classes"] else 2)


if __name__ == "__main__":
    main()
