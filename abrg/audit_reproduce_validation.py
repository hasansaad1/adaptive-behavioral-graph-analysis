#!/usr/bin/env python3
"""Summarize reproduce validation vs frozen expected metrics."""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "abrg" / "output"


def headline(cfg: dict) -> str:
    exp = cfg.get("expected") or {}
    kind = cfg.get("kind", "ratio")
    if kind == "ratio":
        return f"ratio={exp.get('ratio', float('nan')):.4f}"
    if kind == "negative_control":
        return f"imp_auc={exp.get('impossible_edge_auc', float('nan')):.4f}"
    return f"auc_floor={exp.get('auc_floor', float('nan')):.4f}"


def main() -> int:
    rows: list[dict] = []
    for cfg_path in sorted(OUT.rglob("reproduce_config.json")):
        if "nb_repro" in cfg_path.parts:
            continue
        run_dir = cfg_path.parent
        rel = run_dir.relative_to(OUT).as_posix()
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        vr = run_dir / "validate_reproduce_report.json"
        status = "pending"
        detail = ""
        if vr.exists():
            rep = json.loads(vr.read_text(encoding="utf-8"))
            reports = rep.get("reports") or []
            if reports:
                r = reports[-1]
                status = "ok" if r.get("ok") else "fail"
                if not r.get("ok"):
                    diffs = r.get("diffs") or {}
                    detail = ", ".join(f"{k}={v:+.4f}" for k, v in diffs.items())
        rows.append(
            {
                "run_id": rel,
                "kind": cfg.get("kind", "ratio"),
                "headline": headline(cfg),
                "status": status,
                "detail": detail,
            }
        )

    ok = sum(1 for r in rows if r["status"] == "ok")
    fail = sum(1 for r in rows if r["status"] == "fail")
    pending = sum(1 for r in rows if r["status"] == "pending")

    lines = [
        "# Reproduce validation audit",
        "",
        f"Total: {len(rows)} | ok: {ok} | fail: {fail} | pending: {pending}",
        "",
        "| run_id | kind | frozen headline | status | diff (if fail) |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['run_id']}` | {r['kind']} | {r['headline']} | {r['status']} | {r['detail']} |"
        )
    audit = OUT / "REPRODUCE_VALIDATION_AUDIT.md"
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(audit)
    print(f"ok={ok} fail={fail} pending={pending}")
    if fail:
        print("\nFailed runs:")
        for r in rows:
            if r["status"] == "fail":
                print(f"  {r['run_id']}: {r['detail']}")
    return 2 if fail else (1 if pending else 0)


if __name__ == "__main__":
    raise SystemExit(main())
