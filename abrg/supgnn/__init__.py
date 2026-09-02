"""Supervised GIN end-to-end on AndroCT graphs (additive; read-only imports)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

SUPGNN_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "supgnn"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
LADDER_ASSIGNMENTS_PATH = (
    ANDROCT_OUTPUT_ROOT / "ladder" / "grouping" / "route_b_behavioral.json"
)
LADDER_HOLDOUT_PATH = (
    ANDROCT_OUTPUT_ROOT / "ladder" / "rung2" / "behavioral_group_holdout.json"
)

SEED = 42
SEEDS = (42, 43, 44, 45, 46)
TEST_RATIO = 0.2
VAL_FRAC = 0.1

HIDDEN = 64
N_LAYERS = 4
EPOCHS = 200
LR = 0.001
WEIGHT_DECAY = 5e-4
BATCH_SIZE = 64
DROPOUT = 0.5
EARLY_STOP_PATIENCE = 15

REPRESENTATIONS = ("T22", "T1K")
POOLINGS = ("mean", "add", "max")
MODES = ("M1_full", "M2_no_edges", "M3_const_feats")
IN_DIM = {"T22": 10, "T1K": 25}

REF_ROWS = {
    "HGB_full_random": 0.9762,
    "HGB_adj_only_random": 0.9593,
    "HGB_full_behavioral": 0.8492,
    "HGB_full_behavioral_weighted": 0.8606,
    "OCPool_mean_raw": 0.7765,
    "OCPool_mean_R2": 0.7544,
    "GAE": 0.638,
    "OCGIN_plus": 0.566,
    "WL_h3": 0.6726,
    "WL_structure_only": 0.6268,
    "size_floor": 0.7025,
}
