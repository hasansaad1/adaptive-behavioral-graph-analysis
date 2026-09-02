"""One-class detection on 22-node transition features + category invocation edges."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

TRANSITIONS_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "transitions"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
SEEDS = (42, 43, 44, 45, 46)
N_NODES = 22
PCA_COMPONENTS = (8, 16, 32, 64)

# Reference rows (fixed)
REF = {
    "OCPool_mean": 0.7765,
    "OCPool_mean_residualized": 0.8141,
    "GAE": 0.638,
    "supervised_adj_only_HGB": 0.959,
    "supervised_full_HGB": 0.976,
    "highest_size_floor_mapped": 0.7025,
}

BASELINE_EDGE = {
    "22node_proximity": 0.5267,
    "api1000": 0.5013,
    "V2_invocation_artifact": 0.7338,
    "V3_projected": 0.5070,
}

STRUCTURAL_EDGE_PASS = 0.60
DROP_ASYMMETRY_WARN = 0.05  # 5 points
