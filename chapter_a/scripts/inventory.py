"""Stage 1 — inventory every experiment directory under androct_2017 (read-only)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from lib import ANDROCT, CHAPTER_A, write_csv, rel_to_repo

FIELDS = [
    "experiment_dir",
    "module",
    "cli_command",
    "has_SUMMARY",
    "has_reproduce_md",
    "has_reproduce_config",
    "has_checkpoints",
    "has_per_app_scores",
    "n_result_rows",
    "date_last_modified",
    "size_on_disk",
    "status",
    "notes",
]

MODULE_CLI = {
    "arm_a_n1": ("androct", "python -m abrg.androct.run_gae_run2  # arm A n=1 (pre-eligibility-floor-removal)"),
    "arm_b_n8": ("androct", "python -m abrg.androct.run_gae_run2  # arm B n=8 (pre-eligibility-floor-removal)"),
    "run2": ("androct", "python -m abrg.androct.run_gae_run2 --from-cache"),
    "run3": ("androct", "python -m abrg.androct.run_gae_run3"),
    "run3_5": ("androct", "python -m abrg.androct.run_gae_run3_5"),
    "run4": ("androct", "python -m abrg.androct.run_gae_run4"),
    "run5": ("androct", "python -m abrg.androct.run_gae_run5"),
    "run6": ("androct", "python -m abrg.androct.run_gae_run6"),
    "run8": ("androct", "python -m abrg.androct.run_gae_run8"),
    "apigraph": ("apigraph", "python -m abrg.apigraph"),
    "invgraph": ("invgraph", "python -m abrg.invgraph"),
    "transitions": ("transitions", "python -m abrg.transitions"),
    "kernels": ("kernels", "python -m abrg.kernels"),
    "ocgin": ("ocgin", "python -m abrg.ocgin"),
    "glocalkd": ("glocalkd", "python -m abrg.glocalkd"),
    "ocgtl": ("ocgtl", "python -m abrg.ocgtl"),
    "ladder": ("ladder", "python -m abrg.ladder"),
    "supgnn": ("supgnn", "python -m abrg.supgnn"),
    "devread": ("devread", "python -m abrg.devread"),
    "ocdev": ("ocdev", "python -m abrg.ocdev"),
    "validation": ("validate", "python -m abrg.validate"),
    "final_validation": ("final_validate", "python -m abrg.final_validate"),
}

SKIP_NAMES = {"SUMMARY.md", "floors.json", "run_gae.log"}


def _cli_from_config(d: Path, fallback: str) -> str:
    cfg = d / "reproduce_config.json"
    if not cfg.is_file():
        art = d / "artifacts" / "reproduce_config.json"
        cfg = art if art.is_file() else cfg
    if not cfg.is_file():
        return fallback
    try:
        js = json.loads(cfg.read_text())
    except json.JSONDecodeError:
        return fallback
    mod = js.get("cli_module")
    extra = js.get("cli_extra") or []
    if mod:
        cmd = f"python -m {mod}"
        if extra:
            cmd += " " + " ".join(str(x) for x in extra)
        return cmd
    return fallback


def _has_any(d: Path, names: tuple[str, ...]) -> bool:
    for p in d.rglob("*"):
        if p.name in names:
            return True
    return False


def _has_suffix(d: Path, suffixes: tuple[str, ...]) -> bool:
    for p in d.rglob("*"):
        if p.suffix.lower() in suffixes:
            return True
    return False


def _n_result_rows(d: Path) -> int:
    n = 0
    for p in d.rglob("*.json"):
        name = p.name.lower()
        if name in {"reproduce_config.json", "meta.json", "run_meta.json"}:
            continue
        if any(k in name for k in ("result", "comparison", "summary", "grid", "floor", "check", "score")):
            n += 1
    return n


def _mtime(d: Path) -> str:
    latest = d.stat().st_mtime
    try:
        for p in d.rglob("*"):
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                pass
    except OSError:
        pass
    return datetime.fromtimestamp(latest, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _size(d: Path) -> int:
    total = 0
    try:
        for p in d.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _status_notes(name: str) -> tuple[str, str]:
    if name in {"arm_a_n1", "arm_b_n8"}:
        return (
            "superseded",
            "run1 / eligibility-floor protocol; superseded by run2+ after eligibility floor removed",
        )
    if name == "ocgtl":
        return (
            "aborted",
            "Split-A complete; Split-B aborted with no checkpoints. T22 ocgtl_K4/K6 collapsed 5/5.",
        )
    if name == "glocalkd":
        return (
            "partial",
            "Main grid complete; nested bootstrap abandoned at B=20 (B=100 infeasible on T1K).",
        )
    if name == "invgraph":
        return (
            "complete_but_artifact",
            "V2 invocation: 99.99% malware edge-drop; edge_count floor 0.7338 is an artifact of that drop, not a structural signal.",
        )
    if name == "apigraph":
        return (
            "complete",
            "A_tfidf residualized 0.8141 superseded by train-fit R2 OCPool 0.7544 (validation/check1).",
        )
    return "complete", ""


def build_manifest() -> list[dict]:
    rows = []
    for child in sorted(ANDROCT.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        if child.name in SKIP_NAMES:
            continue
        name = child.name
        module, fallback_cli = MODULE_CLI.get(name, (name, f"python -m abrg.{name}"))
        cli = _cli_from_config(child, fallback_cli)
        status, notes = _status_notes(name)
        has_sum = (child / "SUMMARY.md").is_file()
        has_rmd = any(p.name == "reproduce.md" for p in child.rglob("reproduce.md"))
        has_rcfg = any(p.name == "reproduce_config.json" for p in child.rglob("reproduce_config.json"))
        has_ckpt = _has_suffix(child, (".pt", ".joblib", ".pkl"))
        has_scores = _has_any(
            child,
            ("per_app_scores.csv", "predictions.csv"),
        ) or any("score" in p.name.lower() and p.suffix == ".json" for p in child.rglob("*.json"))
        rows.append(
            {
                "experiment_dir": rel_to_repo(child),
                "module": module,
                "cli_command": cli,
                "has_SUMMARY": has_sum,
                "has_reproduce_md": has_rmd,
                "has_reproduce_config": has_rcfg,
                "has_checkpoints": has_ckpt,
                "has_per_app_scores": has_scores,
                "n_result_rows": _n_result_rows(child),
                "date_last_modified": _mtime(child),
                "size_on_disk": _size(child),
                "status": status,
                "notes": notes,
            }
        )
    write_csv(CHAPTER_A / "MANIFEST.csv", rows, FIELDS)
    return rows


if __name__ == "__main__":
    rows = build_manifest()
    print(f"wrote {CHAPTER_A / 'MANIFEST.csv'} n={len(rows)}")
