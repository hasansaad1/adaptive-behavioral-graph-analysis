"""Assemble PROVENANCE.md from export + identity_check artefacts + live hashes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from abrg.chapter_b.config import (
    CONTEXTDROID_ROOT,
    EXPORT_ROOT,
    FRIDA_SERVER_BIN,
    HOOK_SCRIPT,
    IDENTITY_CHECK_DIR,
    OUTPUT_ROOT,
    PROMPTS_PY,
)
from abrg.chapter_b.stats import json_ready


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _frida_client() -> dict[str, Any]:
    try:
        import frida

        return {"version": getattr(frida, "__version__", None), "import_ok": True}
    except Exception as exc:  # noqa: BLE001
        return {"import_ok": False, "error": str(exc)}


def _frida_server_strings(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        proc = subprocess.run(
            ["strings", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    for line in proc.stdout.splitlines():
        if line.strip().startswith("17."):
            return line.strip()
    return None


def assemble_provenance(run1: dict[str, Any]) -> dict[str, Any]:
    export_prov = (EXPORT_ROOT / "PROVENANCE.md").read_text(encoding="utf-8")
    override = (EXPORT_ROOT / "OVERRIDE.md").read_text(encoding="utf-8")
    canary_md = None
    report_md = None
    if (IDENTITY_CHECK_DIR / "CANARY.md").is_file():
        canary_md = (IDENTITY_CHECK_DIR / "CANARY.md").read_text(encoding="utf-8")
    if (IDENTITY_CHECK_DIR / "REPORT.md").is_file():
        report_md = (IDENTITY_CHECK_DIR / "REPORT.md").read_text(encoding="utf-8")

    hook_sha = _sha256(HOOK_SCRIPT)
    prompt_sha = _sha256(PROMPTS_PY)
    prompt_commit = _git(
        ["log", "-1", "--format=%ci %h", "--", "extraction_pipeline/llm_agent/prompts.py"],
        CONTEXTDROID_ROOT,
    )
    frida_srv = _frida_server_strings(FRIDA_SERVER_BIN)
    frida_mtime = None
    if FRIDA_SERVER_BIN.is_file():
        frida_mtime = datetime.fromtimestamp(
            FRIDA_SERVER_BIN.stat().st_mtime, tz=timezone.utc
        ).isoformat()

    rec = {
        "assembled_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [
            str(EXPORT_ROOT / "PROVENANCE.md"),
            str(EXPORT_ROOT / "OVERRIDE.md"),
            str(IDENTITY_CHECK_DIR / "REPORT.md"),
            str(IDENTITY_CHECK_DIR / "CANARY.md"),
        ],
        "fields": [
            {
                "field": "hook_script_path",
                "value": "frida_scripts/hook_apis.js",
                "status": "recoverable",
                "note": "recorded on sessions; current path ContextDroid",
            },
            {
                "field": "hook_script_sha256",
                "value": "3192c7d6f618bb455588a7db7b26b20ccb9028af22cf1d8d8f0db99c28009ffc",
                "status": "recoverable",
                "current_file_sha256": hook_sha,
                "current_matches_recorded": hook_sha
                == "3192c7d6f618bb455588a7db7b26b20ccb9028af22cf1d8d8f0db99c28009ffc",
            },
            {
                "field": "hook_api_set",
                "value": "58 API names / 25 categories (22 GRAPH excl. lifecycle, reflection, navigation)",
                "status": "recoverable",
            },
            {
                "field": "frida_client_version",
                "july": "UNRECOVERABLE",
                "current": _frida_client(),
                "status": "UNRECOVERABLE",
            },
            {
                "field": "frida_client_install_date",
                "value": "2026-04-30",
                "status": "override evidence (not a July session field)",
            },
            {
                "field": "frida_server_version",
                "july": "UNRECOVERABLE",
                "current_strings": frida_srv,
                "current_mtime_utc": frida_mtime,
                "status": "UNRECOVERABLE",
                "override": "see OVERRIDE.md verbatim",
            },
            {
                "field": "emulator_avd_name",
                "july": "UNRECOVERABLE in session metadata",
                "extend_canary": "abrg_benign",
                "status": "UNRECOVERABLE (July); recoverable (extend/canary launch.sh AVD_NAME=abrg_benign)",
            },
            {
                "field": "emulator_system_image",
                "july": "UNRECOVERABLE",
                "current": "android-29 google_apis arm64-v8a (identity_check current)",
                "status": "UNRECOVERABLE",
            },
            {
                "field": "emulator_api_sdk",
                "value": 29,
                "status": "recoverable (July run logs)",
            },
            {
                "field": "session_duration_setting",
                "value": "420 s",
                "status": "recoverable",
            },
            {
                "field": "llm_planner_model",
                "value": "llama3.2",
                "status": "recoverable",
            },
            {
                "field": "llm_planner_digest",
                "july": "UNRECOVERABLE",
                "status": "UNRECOVERABLE",
            },
            {
                "field": "prompt_template_path",
                "value": "extraction_pipeline/llm_agent/prompts.py",
                "current_sha256": prompt_sha,
                "last_commit": prompt_commit,
                "july_frozen_sha": "UNRECOVERABLE",
                "status": "path recoverable; July frozen SHA UNRECOVERABLE",
            },
            {
                "field": "reset_protocol",
                "value": "snapshot_restored=true + pm clear (not -wipe-data); CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1 when already booted",
                "status": "recoverable",
            },
            {
                "field": "action_space",
                "value": "tap, input, back, wait, advance_goal, swipe",
                "status": "recoverable (observed)",
            },
            {
                "field": "max_steps",
                "value": "duration-bounded (no fixed max_steps)",
                "status": "recoverable as uncapped",
            },
            {
                "field": "adb_platform_tools_version_july",
                "status": "UNRECOVERABLE",
            },
            {
                "field": "python_pip_pins_july",
                "status": "UNRECOVERABLE",
            },
            {
                "field": "host_os_july",
                "status": "UNRECOVERABLE",
            },
            {
                "field": "hook_git_commit_july",
                "status": "UNRECOVERABLE",
            },
        ],
        "unrecoverable": [
            "Frida client version (July)",
            "Frida server version / binary SHA (July) — operator override in OVERRIDE.md",
            "Emulator system image identity (July)",
            "Emulator AVD name (July session metadata)",
            "LLM planner model digest (July)",
            "Prompt template SHA256 as frozen July artefact",
            "adb / platform-tools version (July)",
            "Python / collection-path pip pins (July)",
            "Host OS (July)",
            "Hook git commit during July collection",
        ],
        "override_md_verbatim": override,
        "canary_md": canary_md,
        "identity_report_present": report_md is not None,
        "date_ranges": run1.get("inventory", {}).get("collection_date_ranges"),
        "export_provenance_md": export_prov,
    }
    return rec


def write_provenance_md(payload: dict[str, Any], path: Path | None = None) -> Path:
    path = path or (OUTPUT_ROOT / "PROVENANCE.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Chapter B — PROVENANCE")
    lines.append("")
    lines.append(f"Assembled (UTC): {payload['assembled_at_utc']}")
    lines.append("")
    lines.append("Sources: `datasets/v2_extended/PROVENANCE.md`, `OVERRIDE.md`,")
    lines.append("`ContextDroid/abrg/output/v2_extend/identity_check/{REPORT,CANARY}.md`.")
    lines.append("Live hashes of current files are labelled current; July identity is as recorded.")
    lines.append("")
    lines.append("## Collection configuration")
    lines.append("")
    lines.append("| field | value | status |")
    lines.append("|-------|-------|--------|")
    for f in payload["fields"]:
        val = f.get("value")
        if val is None:
            val = f.get("july") or f.get("current") or ""
        if isinstance(val, dict):
            val = json.dumps(val)
        val_s = str(val).replace("|", "\\|")
        lines.append(f"| {f['field']} | {val_s} | {f['status']} |")
    lines.append("")
    lines.append("## UNRECOVERABLE fields")
    lines.append("")
    for i, u in enumerate(payload["unrecoverable"], 1):
        lines.append(f"{i}. {u}")
    lines.append("")
    lines.append("## Operator override (frida-server) — verbatim from `datasets/v2_extended/OVERRIDE.md`")
    lines.append("")
    lines.append("```")
    lines.append(payload["override_md_verbatim"].rstrip())
    lines.append("```")
    lines.append("")
    lines.append("## Canary verification")
    lines.append("")
    lines.append("Apps: `app.comaps.fdroid`, `app.organicmaps`, `ai.susi` (1 session each).")
    lines.append("")
    lines.append("Two recorded verdicts exist (different criteria):")
    lines.append("")
    lines.append("### Band criteria (`identity_check/CANARY.md`) — mapped in `[0.25×, 4×]` existing median; no novel / no silent-reliable category")
    lines.append("")
    if payload.get("canary_md"):
        lines.append(payload["canary_md"].rstrip())
    else:
        lines.append("(CANARY.md not readable at identity_check path)")
    lines.append("")
    lines.append("### Min–max range criteria (`identity_check/REPORT.md` §1d)")
    lines.append("")
    lines.append("| app | metric | existing min–max | canary | inside |")
    lines.append("|-----|--------|-----------------:|-------:|:------:|")
    # transcribed from REPORT.md so the table is in the Chapter B artefact even if the file moves
    rows = [
        ("app.comaps.fdroid", "total_events", "576–929", "606", "YES"),
        ("app.comaps.fdroid", "mapped_events", "148–160", "153", "YES"),
        ("app.comaps.fdroid", "mapped_rate", "0.1710–0.2569", "0.2525", "YES"),
        ("app.comaps.fdroid", "active_nodes", "5–5", "5", "YES"),
        ("app.comaps.fdroid", "edges", "7–8", "6", "NO"),
        ("app.comaps.fdroid", "elapsed_sec", "455.9–472.193", "226.642", "NO"),
        ("app.organicmaps", "total_events", "939–1004", "867", "NO"),
        ("app.organicmaps", "mapped_events", "142–145", "125", "NO"),
        ("app.organicmaps", "mapped_rate", "0.1414–0.1544", "0.1442", "YES"),
        ("app.organicmaps", "active_nodes", "5–5", "5", "YES"),
        ("app.organicmaps", "edges", "5–5", "5", "YES"),
        ("app.organicmaps", "elapsed_sec", "448.538–461.21", "450.983", "YES"),
        ("ai.susi", "total_events", "5108–7082", "5048", "NO"),
        ("ai.susi", "mapped_events", "401–421", "348", "NO"),
        ("ai.susi", "mapped_rate", "0.0594–0.0785", "0.0689", "YES"),
        ("ai.susi", "active_nodes", "6–6", "6", "YES"),
        ("ai.susi", "edges", "12–23", "12", "YES"),
        ("ai.susi", "elapsed_sec", "466.348–474.74", "544.554", "NO"),
    ]
    for r in rows:
        lines.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    lines.append("")
    lines.append("REPORT.md §1d gate: FAIL — canary metrics outside existing min–max ranges.")
    lines.append("CANARY.md / export PROVENANCE.md: CANARY PASS under the 0.25×–4× mapped band.")
    lines.append("")
    lines.append("## Collection date ranges (from session metadata in this run)")
    lines.append("")
    lines.append("| batch | n | start (UTC) | end (UTC) |")
    lines.append("|-------|--:|-------------|-----------|")
    for batch, rec in (payload.get("date_ranges") or {}).items():
        lines.append(f"| {batch} | {rec.get('n')} | {rec.get('start_utc')} | {rec.get('end_utc')} |")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUTPUT_ROOT / "artifacts" / "provenance.json").parent.mkdir(parents=True, exist_ok=True)
    (OUTPUT_ROOT / "artifacts" / "provenance.json").write_text(
        json.dumps(json_ready({k: v for k, v in payload.items() if k != "export_provenance_md"}), indent=2)
        + "\n",
        encoding="utf-8",
    )
    return path
