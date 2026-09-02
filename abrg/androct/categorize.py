"""Map Jimple/Soot callee signatures onto ABRG GRAPH_CATEGORY_UNIVERSE."""

from __future__ import annotations

from abrg.api_category_map import HOOK_API_TO_CATEGORY, categorize_callee
from abrg.registry import DROPPED_CATEGORIES, GRAPH_CATEGORY_UNIVERSE

_GRAPH_SET = frozenset(GRAPH_CATEGORY_UNIVERSE)

# Prefer exact Frida-aligned labels over broad package prefixes when both fire.
_PRIORITY: tuple[str, ...] = (
    "sms",
    "telephony",
    "device_info",
    "location",
    "camera",
    "audio",
    "clipboard",
    "accounts",
    "dynamic_code_loading",
    "native_code",
    "crypto",
    "network",
    "file_io",
    "content_access",
    "database",
    "storage",
    "webview",
    "media",
    "package_manager",
    "notifications",
    "ipc_intents",
    "process",
)


def unquote_jimple_ident(tok: str) -> str:
    """Strip Jimple single-quotes around reserved / non-ASCII identifiers."""
    tok = tok.strip()
    if len(tok) >= 2 and tok[0] == "'" and tok[-1] == "'":
        return tok[1:-1]
    return tok


def parse_soot_method_signature(sig: str) -> tuple[str, str] | None:
    """
    Parse ``<class: ret method(args)>`` into (dotted_class, method_name).

    Handles Jimple quoting on class segments and method names
    (e.g. ``'with'``, ``java.lang.'annotation'.Annotation``).
    """
    s = sig.strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    if ": " not in s:
        return None
    class_part, rest = s.split(": ", 1)
    class_part = ".".join(unquote_jimple_ident(p) for p in class_part.split("."))
    rest = rest.strip()
    # ret_type method_name(args)  — method may be quoted
    paren = rest.find("(")
    if paren < 0:
        return None
    head = rest[:paren].strip()
    # last whitespace-separated token is the method name
    bits = head.rsplit(None, 1)
    if len(bits) != 2:
        return None
    method = unquote_jimple_ident(bits[1])
    return class_part, method


def categorize_soot_callee(sig: str) -> str | None:
    """
    Single graph category for a Soot callee, or None if unmapped / non-graph-only.

    Exact ``HOOK_API_TO_CATEGORY`` hits win when present in the graph set;
    otherwise choose by ``_PRIORITY`` among ``categorize_callee`` results.
    """
    parsed = parse_soot_method_signature(sig)
    if parsed is None:
        return None
    class_name, method_name = parsed
    simple = class_name.split(".")[-1]
    label = f"{simple}.{method_name}"

    exact = HOOK_API_TO_CATEGORY.get(label)
    if exact and exact in _GRAPH_SET:
        return exact

    cats = categorize_callee(class_name, method_name) - DROPPED_CATEGORIES
    cats &= _GRAPH_SET
    if not cats:
        return None
    for pref in _PRIORITY:
        if pref in cats:
            return pref
    return sorted(cats)[0]


def categorize_icc_callsite(callsite: str | None) -> str:
    """
    ICC blocks map to ``ipc_intents``; startActivity* also implies navigation
    (dropped from graphs) — graph label remains ipc_intents.
    """
    if not callsite:
        return "ipc_intents"
    # Extract the soot method inside virtualinvoke ... .<cls: ret meth(args)>(...)
    start = callsite.find(".<")
    end = callsite.rfind(">(")
    if start >= 0 and end > start:
        inner = callsite[start + 1 : end + 1]  # <cls: ...>
        parsed = parse_soot_method_signature(inner)
        if parsed is not None:
            _, method = parsed
            if method in ("startActivity", "startActivities", "startActivityForResult"):
                return "ipc_intents"
            if method in ("sendBroadcast", "sendOrderedBroadcast", "startService", "bindService"):
                return "ipc_intents"
            if method == "getIntent":
                return "ipc_intents"
    return "ipc_intents"
