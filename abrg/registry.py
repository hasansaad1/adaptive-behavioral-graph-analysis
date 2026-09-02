"""Category registries — hook trace taxonomy (25) vs graph node set (22)."""

from __future__ import annotations

# Full hook taxonomy (hook_apis.js v3 / ContextDroid evaluate_corpus.py).
CATEGORY_UNIVERSE: tuple[str, ...] = (
    "accounts",
    "audio",
    "camera",
    "clipboard",
    "content_access",
    "crypto",
    "database",
    "device_info",
    "dynamic_code_loading",
    "file_io",
    "ipc_intents",
    "lifecycle",
    "location",
    "media",
    "native_code",
    "navigation",
    "network",
    "notifications",
    "package_manager",
    "process",
    "reflection",
    "sms",
    "storage",
    "telephony",
    "webview",
)

# Fixed behavioral-graph node set — ONLY this list defines graph nodes / tensor indexing.
GRAPH_CATEGORY_UNIVERSE: tuple[str, ...] = (
    "accounts",
    "audio",
    "camera",
    "clipboard",
    "content_access",
    "crypto",
    "database",
    "device_info",
    "dynamic_code_loading",
    "file_io",
    "ipc_intents",
    "location",
    "media",
    "native_code",
    "network",
    "notifications",
    "package_manager",
    "process",
    "sms",
    "storage",
    "telephony",
    "webview",
)

# Hook categories collected in traces but excluded from graphs.
NON_GRAPH_HOOK_CATEGORIES: frozenset[str] = frozenset({
    "lifecycle",
    "reflection",
    "navigation",
})

# Stripped at trace load before graph build (non-graph hook cats + legacy labels).
DROPPED_CATEGORIES: frozenset[str] = NON_GRAPH_HOOK_CATEGORIES | frozenset({
    "unknown",
    "contacts",  # legacy hook_apis label → content_access in v3
})

# Static gate_v stub width: Android protection-level buckets (normal / dangerous / signature+).
GATE_V_DIM: int = 3


def _assert_category_universes() -> None:
    hook = set(CATEGORY_UNIVERSE)
    graph = set(GRAPH_CATEGORY_UNIVERSE)
    excluded = hook - graph
    assert len(CATEGORY_UNIVERSE) == 25, f"CATEGORY_UNIVERSE must be 25, got {len(CATEGORY_UNIVERSE)}"
    assert len(GRAPH_CATEGORY_UNIVERSE) == 22, (
        f"GRAPH_CATEGORY_UNIVERSE must be 22, got {len(GRAPH_CATEGORY_UNIVERSE)}"
    )
    assert excluded == NON_GRAPH_HOOK_CATEGORIES, (
        f"GRAPH_CATEGORY_UNIVERSE must be CATEGORY_UNIVERSE minus "
        f"{sorted(NON_GRAPH_HOOK_CATEGORIES)}; extra/missing: "
        f"only-in-hook={sorted(excluded ^ NON_GRAPH_HOOK_CATEGORIES)}"
    )
    assert graph <= hook, "GRAPH_CATEGORY_UNIVERSE must be a subset of CATEGORY_UNIVERSE"
    assert DROPPED_CATEGORIES >= NON_GRAPH_HOOK_CATEGORIES
    assert not (graph & DROPPED_CATEGORIES), "Graph nodes must not appear in DROPPED_CATEGORIES"


_assert_category_universes()
