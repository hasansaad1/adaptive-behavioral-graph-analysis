"""Descriptive stats — inventory percentile / MWU plus Cliff's δ. No new scorers."""

from __future__ import annotations

import math
from typing import Any

from abrg.androct.inventory import _mann_whitney_u, _percentile, _summarize_dist

from abrg.chapter_b.config import MATERIAL_CLIFF_SMALL, MATERIAL_P


def summarize_dist(vals: list[float] | list[int]) -> dict[str, float]:
    """Inventory `_summarize_dist` plus p10 and IQR."""
    raw = [float(v) for v in vals if v == v]  # drop NaN
    d = _summarize_dist(raw)  # type: ignore[arg-type]
    if not raw:
        d["p10"] = math.nan
        d["iqr"] = math.nan
        return d
    s = sorted(raw)
    d["p10"] = _percentile(s, 10)
    d["iqr"] = float(d["p75"]) - float(d["p25"])
    return d


def value_counts(vals: list[int]) -> dict[str, int]:
    from collections import Counter

    return {str(k): int(v) for k, v in sorted(Counter(vals).items())}


def mann_whitney(
    x: list[float] | list[int],
    y: list[float] | list[int],
    *,
    label_x: str,
    label_y: str,
) -> dict[str, Any]:
    """Inventory MWU + Cliff's δ = 2U/(n1 n2) − 1 (U is scipy statistic for x)."""
    xf = [float(v) for v in x if v == v]
    yf = [float(v) for v in y if v == v]
    raw = _mann_whitney_u(xf, yf)  # type: ignore[arg-type]
    out: dict[str, Any] = dict(raw)
    out["label_x"] = label_x
    out["label_y"] = label_y
    out["n_x"] = len(xf)
    out["n_y"] = len(yf)
    if xf:
        out["median_x"] = float(sorted(xf)[len(xf) // 2])
    if yf:
        out["median_y"] = float(sorted(yf)[len(yf) // 2])
    n1, n2 = len(xf), len(yf)
    if "U" in out and n1 and n2:
        u = float(out["U"])
        delta = (2.0 * u) / (n1 * n2) - 1.0
        out["cliffs_delta"] = delta
        out["cliffs_delta_formula"] = "2*U/(n_x*n_y) - 1"
        out["effect_size_name"] = "cliffs_delta"
        abs_d = abs(delta)
        if abs_d < MATERIAL_CLIFF_SMALL:
            mag = "negligible"
        elif abs_d < 0.33:
            mag = "small"
        elif abs_d < 0.474:
            mag = "medium"
        else:
            mag = "large"
        out["cliffs_magnitude_romano2006"] = mag
        p = float(out.get("p_value", math.nan))
        material = (p < MATERIAL_P) and (abs_d >= MATERIAL_CLIFF_SMALL)
        out["material_by_declared_rule"] = material
        out["material_rule"] = (
            f"p < {MATERIAL_P} and |cliffs_delta| >= {MATERIAL_CLIFF_SMALL}"
        )
        if not (p == p):
            out["material_statement"] = "MWU p-value undefined"
        elif material:
            out["material_statement"] = (
                f"differs materially ({label_x} vs {label_y}: p={p:.3g}, "
                f"Cliff δ={delta:.3g}, {mag})"
            )
        elif p < MATERIAL_P:
            out["material_statement"] = (
                f"p < {MATERIAL_P} but |Cliff δ|={abs_d:.3g} below small "
                f"threshold {MATERIAL_CLIFF_SMALL} ({label_x} vs {label_y})"
            )
        else:
            out["material_statement"] = (
                f"does not differ at p < {MATERIAL_P} "
                f"({label_x} vs {label_y}: p={p:.3g}, Cliff δ={delta:.3g})"
            )
    return out


def json_ready(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): json_ready(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_ready(v) for v in obj]
    if hasattr(obj, "item") and callable(obj.item):
        try:
            return json_ready(obj.item())
        except Exception:  # noqa: BLE001
            return str(obj)
    return obj
