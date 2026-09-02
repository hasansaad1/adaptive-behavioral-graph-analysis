"""Pinned paths and constants for Chapter B (descriptive; no detector)."""

from __future__ import annotations

import os

from pathlib import Path

from abrg.androct.run_gae_run2 import STATIC_SLICE
from abrg.config import K_BURST
from abrg.dataset_paths import REPO_ROOT
from abrg.registry import GATE_V_DIM, GRAPH_CATEGORY_UNIVERSE

EXPORT_ROOT = REPO_ROOT / "datasets" / "v2_extended"
OUTPUT_ROOT = REPO_ROOT / "abrg" / "output" / "v2_chapter_b"
RUN1_DIR = OUTPUT_ROOT / "run1_corpus"
RUN2_DIR = OUTPUT_ROOT / "run2_comparison"
FIGURES_DIR = OUTPUT_ROOT / "figures"
ARTIFACTS_DIR = OUTPUT_ROOT / "artifacts"

# Sibling ContextDroid collector repo. Override with CONTEXTDROID_ROOT.
CONTEXTDROID_ROOT = Path(os.environ.get("CONTEXTDROID_ROOT", str(REPO_ROOT.parent / "ContextDroid")))
IDENTITY_CHECK_DIR = CONTEXTDROID_ROOT / "abrg" / "output" / "v2_extend" / "identity_check"
HOOK_SCRIPT = CONTEXTDROID_ROOT / "frida_scripts" / "hook_apis.js"
PROMPTS_PY = CONTEXTDROID_ROOT / "extraction_pipeline" / "llm_agent" / "prompts.py"
FRIDA_SERVER_BIN = CONTEXTDROID_ROOT / "tools" / "frida-server-android-arm64"

N_NODES = len(GRAPH_CATEGORY_UNIVERSE)
assert N_NODES == 22
POSSIBLE_EDGES = N_NODES * (N_NODES - 1)  # 22*21 directed, no self-loops

K_BURST_PIN = K_BURST  # 5; AndroCT sequence builder
STATIC_SLICE_DIM = STATIC_SLICE  # 2 + GATE_V_DIM + 2
assert STATIC_SLICE_DIM == 2 + GATE_V_DIM + 2

# AndroCT collection protocol duration (Monkey). Traces have no wall-clock.
# Li, Fu, Cai, MSR 2021 AndroCT data paper: 10 min / 600 s per app.
ANDROCT_PROTOCOL_WALL_SEC = 600.0

# GAE eligibility (export-time timed graphs): ≥2 active nodes and ≥1 edge.
GAE_MIN_ACTIVE = 2
GAE_MIN_EDGES = 1

# Material-difference rule for 1b / 2b (declared before looking at numbers).
# Cliff's δ thresholds: Romano et al. 2006 (negligible <0.147, small, medium 0.33, large 0.474).
MATERIAL_P = 0.05
MATERIAL_CLIFF_SMALL = 0.147

STATIC_COORD_LABELS = (
    "s_v",
    "declared_v",
    "gate_v[0]_normal",
    "gate_v[1]_dangerous",
    "gate_v[2]_signature",
    "reach_v",
    "epoch_v",
)

POOLED_METHOD = "concat_then_build"
POOLED_JUSTIFICATION = (
    "Per-app pooled v2 graphs are built by concatenating each app's usable "
    "sessions' mapped category streams in session_index_within_app order "
    "(start-time order), then calling abrg.androct.graph_build.update_graph_sequence "
    "once on the concatenated stream. This matches AndroCT's unit: one ordered "
    "whole-trace category stream → one graph. Graphs are not built per session "
    "and then merged; no edge-weight combination rule is applied."
)
