"""One-class readout on deviation profiles + support-novelty scoring (additive)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

OCDEV_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "ocdev"
DEVREAD_PROFILES = ANDROCT_OUTPUT_ROOT / "devread" / "artifacts" / "profiles"
LADDER_ASSIGNMENTS_PATH = (
    ANDROCT_OUTPUT_ROOT / "ladder" / "grouping" / "route_b_behavioral.json"
)
LADDER_HOLDOUT_PATH = (
    ANDROCT_OUTPUT_ROOT / "ladder" / "rung2" / "behavioral_group_holdout.json"
)

EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
SEEDS = (42, 43, 44, 45, 46)

EXPECTED_DIMS = {
    "D0": 1,
    "D1": 22,
    "D2": 484,
    "D3": 44,
    "D4": 66,
    "D5": 506,
}
FEATURE_SETS = ("D0", "D1", "D2", "D3", "D4", "D5")
PCA_SETS = ("D2", "D5")
PCA_COMPONENTS = (8, 16, 32, 64)

EPS = 1e-12
SIZE_FLOOR = 0.7025
OCPOOL_INCUMBENT = 0.7765

REF_ROWS = {
    "supervised_HGB_full": 0.9762,
    "supervised_HGB_adj_only": 0.9593,
    "deviation_D3_HGB_splitA": 0.9624,
    "deviation_D3_LR_L1_splitB_weighted": 0.8542,
    "supervised_behavioral_holdout": 0.8492,
    "supervised_behavioral_weighted": 0.8606,
    "OCPool_mean_raw": 0.7765,
    "OCPool_mean_R2": 0.7544,
    "input_centroid": 0.777,
    "random_init_GAE_embedding": 0.759,
    "WL_h3": 0.6726,
    "GAE_D0": 0.638,
    "oneclass_adj_only_F1_best": 0.545,
    "size_floor": 0.7025,
}
