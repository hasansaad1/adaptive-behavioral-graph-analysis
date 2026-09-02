"""Shared paths and helpers for Chapter A (read artifacts only; never train)."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CHAPTER_A = SCRIPTS.parent
REPO = CHAPTER_A.parent
ANDROCT = REPO / "abrg" / "output" / "androct_2017"
FV = ANDROCT / "final_validation"

os.environ.setdefault("MPLCONFIGDIR", str(CHAPTER_A / ".mplconfig"))
os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
Path(os.environ["MPLCONFIGDIR"]).mkdir(parents=True, exist_ok=True)

SIZE_FLOOR_ARTIFACT = ANDROCT / "run3" / "floors.json"
OCPOOL_ARTIFACT = ANDROCT / "validation" / "check1_residualization" / "check1_summary.json"


def load_json(path: Path):
    with path.open() as f:
        return json.load(f)


def rel_to_repo(path: Path | str) -> str:
    p = Path(path)
    try:
        return str(p.resolve().relative_to(REPO))
    except ValueError:
        return str(p)


def abs_artifact(path: str | Path) -> Path:
    p = Path(str(path))
    if p.is_absolute():
        return p
    return (REPO / p).resolve()


def map_ci_type(raw) -> str:
    if raw is None or (isinstance(raw, float) and str(raw) == "nan"):
        return "none"
    s = str(raw).strip()
    if not s or s.lower() in {"none", "nan"}:
        return "none"
    allowed = {"none", "score_bootstrap", "nested_bootstrap", "per_fold_std"}
    if s in allowed:
        return s
    if "nested" in s:
        return "nested_bootstrap"
    if s in {"score_resample_percentile"} or "score_resample" in s:
        return "score_bootstrap"
    if "per_fold" in s or s in {"seed_mean_no_ci"}:
        return "per_fold_std" if "std" in s or "per_fold" in s else "none"
    if s == "pooled_oof_ci_on_floor_mean_row":
        return "none"
    return "none"


def auc_fields(blob: dict) -> dict:
    """Pull auc / floor / direction / CI from a saved detector JSON blob."""
    a = blob.get("auc", blob) if isinstance(blob, dict) else {}
    if not isinstance(a, dict):
        a = {}
    auc = a.get("auc", blob.get("raw_auc") if isinstance(blob, dict) else None)
    floor = a.get("auc_floor", blob.get("auc_floor") if isinstance(blob, dict) else None)
    direction = a.get("direction", blob.get("direction") if isinstance(blob, dict) else "")
    ci = a.get("ci95_floor") or a.get("ci95") or blob.get("ci95_floor") or blob.get("ci95")
    ci_low = ci_high = ""
    if isinstance(ci, (list, tuple)) and len(ci) == 2:
        ci_low, ci_high = ci[0], ci[1]
    n_boot = a.get("n_boot") or blob.get("n_boot")
    ci_type = "score_bootstrap" if n_boot else "none"
    return {
        "raw_auc": auc,
        "auc_floor": floor,
        "direction": direction or "",
        "ci_low": ci_low,
        "ci_high": ci_high,
        "ci_type": ci_type,
    }


def load_size_floor() -> float:
    d = load_json(SIZE_FLOOR_ARTIFACT)
    return float(d["mapped_event_count"]["auc_floor"])


def load_ocpool_raw() -> float:
    d = load_json(OCPOOL_ARTIFACT)
    return float(d["R0"]["auc"]["auc_floor"])


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {}
            for k in fieldnames:
                v = r.get(k, "")
                if v is None:
                    v = ""
                elif isinstance(v, bool):
                    v = "True" if v else "False"
                out[k] = v
            w.writerow(out)


def fmt_num(v, nd=6):
    if v is None or v == "":
        return ""
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def booktabs_table(path: Path, columns: list[str], rows: list[list[str]], caption: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    align = "l" + "r" * (len(columns) - 1)
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        rf"\begin{{tabular}}{{{align}}}",
        r"\toprule",
        " & ".join(columns) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(str(c) for c in row) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    path.write_text("\n".join(lines))


def summary_for(exp_dir: Path) -> Path | None:
    for cand in (exp_dir / "SUMMARY.md", exp_dir / "artifacts" / "SUMMARY.md"):
        if cand.is_file():
            return cand
    return None
