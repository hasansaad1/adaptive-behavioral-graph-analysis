"""§3.1 BuildInitialGraph static layer via Androguard."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

# Androguard uses loguru; keep pilot output readable.
os.environ.setdefault("LOGURU_LEVEL", "ERROR")
logging.getLogger("androguard").setLevel(logging.ERROR)

from androguard.misc import AnalyzeAPK

from abrg.api_category_map import (
    CATEGORY_SENSITIVITY_OVERRIDE,
    PERM_TO_CATEGORIES,
    PROTECTION_TO_GATE_IDX,
    PROTECTION_TO_SENSITIVITY,
    categorize_callee,
    perm_short_name,
)
from abrg.registry import GRAPH_CATEGORY_UNIVERSE, GATE_V_DIM

logger = logging.getLogger(__name__)


@dataclass
class StaticNodeAttrs:
    s_v: float = 0.0
    declared_v: float = 0.0
    gate_v: list[float] = field(default_factory=lambda: [0.0] * GATE_V_DIM)
    reach_v: float = 0.0
    epoch_v: float = 0.0
    declared_apis: set[str] = field(default_factory=set)
    gating_permissions: set[str] = field(default_factory=set)


@dataclass
class StaticReport:
    apk_path: str
    package_name: str
    permissions: list[str]
    nodes: dict[str, StaticNodeAttrs]


def _parse_protection_level(raw: str | None) -> str:
    if not raw:
        return "normal"
    # e.g. "0x2" or "dangerous" or "signature|privileged"
    raw_l = raw.lower()
    if "signature" in raw_l or "privileged" in raw_l:
        return "signature"
    if "dangerous" in raw_l:
        return "dangerous"
    if "normal" in raw_l:
        return "normal"
    # hex flags: 0x2 dangerous, 0x1 normal
    if "0x" in raw_l:
        try:
            val = int(raw_l.split()[0], 16)
            if val & 0x2:
                return "dangerous"
        except ValueError:
            pass
    return "normal"


def _manifest_permissions(a, manifest) -> dict[str, str]:
    """permission short name -> protection level string."""
    ns = "{http://schemas.android.com/apk/res/android}"
    perms: dict[str, str] = {}
    for p in a.get_permissions():
        perms[perm_short_name(p)] = "normal"

    for uses in manifest.findall(".//uses-permission"):
        name = uses.get(f"{ns}name") or uses.get("name")
        if not name:
            continue
        short = perm_short_name(name)
        level = uses.get(f"{ns}protectionLevel") or uses.get("protectionLevel")
        perms[short] = _parse_protection_level(level)

    return perms


def _normalize_component(package_name: str, raw_name: str) -> str:
    if raw_name.startswith("."):
        return package_name + raw_name
    if "." not in raw_name:
        return f"{package_name}.{raw_name}"
    return raw_name


def analyze_apk_static(apk_path: Path) -> StaticReport:
    """
    Androguard static analysis → per-category declared_v, gate_v, reach_v, s_v.
    """
    apk_path = apk_path.resolve()
    if not apk_path.is_file():
        raise FileNotFoundError(f"APK not found: {apk_path}")

    logger.info("Androguard static analysis: %s", apk_path)
    a, _d, dx = AnalyzeAPK(str(apk_path))
    manifest = a.get_android_manifest_xml()
    package_name = a.get_package()
    ns = "{http://schemas.android.com/apk/res/android}"

    perm_levels = _manifest_permissions(a, manifest)

    # component class path (slash) -> component id
    component_classes: dict[str, str] = {}
    for tag in ("activity", "service", "receiver"):
        for entry in manifest.findall(f".//{tag}"):
            raw_name = entry.get(f"{ns}name")
            if not raw_name:
                continue
            comp = _normalize_component(package_name, raw_name)
            smali = "L" + comp.replace(".", "/") + ";"
            component_classes[smali] = comp

    nodes: dict[str, StaticNodeAttrs] = {c: StaticNodeAttrs() for c in GRAPH_CATEGORY_UNIVERSE}
    category_components: dict[str, set[str]] = {c: set() for c in GRAPH_CATEGORY_UNIVERSE}

    for method_analysis in dx.get_methods():
        try:
            method = method_analysis.get_method()
            caller_class = method.get_class_name()
            xrefs = method_analysis.get_xref_to()
        except Exception:
            continue

        caller_comp = None
        for smali_prefix, comp_name in component_classes.items():
            if caller_class.startswith(smali_prefix.rstrip(";")) or smali_prefix.rstrip(";") in caller_class:
                caller_comp = comp_name
                break

        for _cls_a, callee_ma, _off in xrefs:
            try:
                callee_method = callee_ma.get_method()
                callee_class = callee_method.get_class_name()
                if not (
                    callee_class.startswith("Landroid/")
                    or callee_class.startswith("Ljavax/")
                    or callee_class.startswith("Ljava/")
                    or callee_class.startswith("Ldalvik/")
                    or callee_class.startswith("Lokhttp")
                    or callee_class.startswith("Lretrofit")
                    or "volley" in callee_class.lower()
                ):
                    continue
                callee_name = callee_method.get_name()
                cats = categorize_callee(callee_class, callee_name)
                api_label = f"{_smali_simple(callee_class)}.{callee_name}"
                for cat in cats:
                    if cat not in nodes:
                        continue
                    nodes[cat].declared_v = 1.0
                    nodes[cat].declared_apis.add(api_label)
                    if caller_comp:
                        category_components[cat].add(caller_comp)
            except Exception:
                continue

    # Permission-gated categories: gate_v and s_v from manifest
    category_perms: dict[str, list[str]] = {c: [] for c in GRAPH_CATEGORY_UNIVERSE}
    for perm, cats in PERM_TO_CATEGORIES.items():
        if perm in perm_levels:
            for cat in cats:
                if cat in category_perms:
                    category_perms[cat].append(perm)

    for cat, node in nodes.items():
        node.reach_v = float(len(category_components[cat]))
        perms_for_cat = category_perms[cat]
        node.gating_permissions = set(perms_for_cat)

        sensitivities: list[float] = []
        for perm in perms_for_cat:
            level = perm_levels.get(perm, "normal")
            idx = PROTECTION_TO_GATE_IDX.get(level, 0)
            if 0 <= idx < GATE_V_DIM:
                node.gate_v[idx] = 1.0
            sensitivities.append(PROTECTION_TO_SENSITIVITY.get(level, 0.2))

        if cat in CATEGORY_SENSITIVITY_OVERRIDE:
            sensitivities.append(CATEGORY_SENSITIVITY_OVERRIDE[cat])
        node.s_v = max(sensitivities) if sensitivities else (0.2 if node.declared_v else 0.0)
        node.epoch_v = 0.0

    return StaticReport(
        apk_path=str(apk_path),
        package_name=package_name,
        permissions=sorted(perm_levels.keys()),
        nodes=nodes,
    )


def zero_static_report(package_name: str = "") -> StaticReport:
    """Pinned pilot stub: schema-preserving static slots, all zero."""
    return StaticReport(
        apk_path="",
        package_name=package_name,
        permissions=[],
        nodes={c: StaticNodeAttrs() for c in GRAPH_CATEGORY_UNIVERSE},
    )


def _smali_simple(class_name: str) -> str:
    inner = class_name.strip("L;").split("/")[-1]
    return inner
