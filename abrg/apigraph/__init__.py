"""API-level graph representation on AndroCT 2017 (additive; read-only imports)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

APIGRAPH_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "apigraph"
VOCAB_KS = (100, 300, 500, 1000)
K_BURST = 5
SEED = 42

# 22-node structural baselines (Run 3 / OCGIN floors)
BASELINE_22 = {
    "active_nodes": 0.5164,
    "edge_count": 0.5267,
    "graph_density": 0.5267,
    "mapped_event_count": 0.7025,
}

# Stage 3 gate: structural floors must move materially
STRUCTURAL_FLOOR_PASS = 0.60
