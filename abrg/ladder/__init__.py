"""Supervision ladder: generalization to unseen malware groups (additive)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

LADDER_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "ladder"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
SEEDS = (42, 43, 44, 45, 46)
TEST_RATIO = 0.2

SIZE_FLOOR_REF = 0.7025
REF_ROWS = {
    "supervised_HGB_full": 0.976,
    "supervised_HGB_adj_only": 0.959,
    "OCPool_mean_raw": 0.7765,
    "OCPool_mean_R2": 0.7544,
    "OCPool_mean_R2_nested_CI": (0.699, 0.800),
}

MODES = ("full", "node_only", "adj_only")
MODELS = ("logistic_regression", "hist_gradient_boosting")
HARNESS_TOLERANCE = 0.01
CLUSTER_K_GRID = (5, 10, 15, 20, 30)
