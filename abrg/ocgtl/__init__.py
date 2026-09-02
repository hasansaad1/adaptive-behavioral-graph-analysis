"""OCGTL: one-class graph transformation learning (additive; read-only imports)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

OCGTL_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "ocgtl"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
LADDER_ASSIGNMENTS_PATH = (
    ANDROCT_OUTPUT_ROOT / "ladder" / "grouping" / "route_b_behavioral.json"
)
LADDER_HOLDOUT_PATH = (
    ANDROCT_OUTPUT_ROOT / "ladder" / "rung2" / "behavioral_group_holdout.json"
)

# Consulted reference commit (AGPL-3.0 — not vendored; reimplemented from paper + inspection).
REF_REPO = "https://github.com/boschresearch/GraphLevel-AnomalyDetection"
REF_COMMIT = "7b2295d477f2ef48cd270c137710bae0445b5481"

SEED = 42
SEEDS = (42, 43, 44, 45, 46)
TEST_RATIO = 0.2

HIDDEN = 32
N_LAYERS = 4
# Paper/config default is 500 / 0.001 / batch 128. This run uses epochs=300, batch=64;
# lr follows paper default (0.001) rather than 0.01 — stated in README.
EPOCHS = 300
LR = 0.001
WEIGHT_DECAY = 0.0
BATCH_SIZE = 64
TEMPERATURE = 1.0  # paper leaves τ unspecified; reference uses 1.0
K_VALUES = (4, 6)  # total encoders = 1 reference + (K-1) transforms
PRIMARY_K = 4

COLLAPSE_SCORE_EPS = 1e-6
COLLAPSE_FRAC_THRESHOLD = 0.5  # flag if frac train score < 1e-6 exceeds this
ENCODER_AGREE_COS_THRESHOLD = 0.999  # mean pairwise cos among encoders

SIZE_FLOOR = 0.7025
OCPOOL_INCUMBENT = 0.7765

REF_ROWS = {
    "supervised_HGB_full": 0.9762,
    "supervised_HGB_adj_only": 0.9593,
    "supervised_GIN_M2_no_edges": 0.9000,
    "supervised_GIN_M1_with_edges": 0.8838,
    "deviation_D3_HGB": 0.9624,
    "supervised_behavioral_holdout": 0.8492,
    "supervised_behavioral_weighted": 0.8606,
    "OCPool_mean_raw": 0.7765,
    "OCPool_mean_R2": 0.7544,
    "input_centroid": 0.777,
    "random_init_GAE_embedding": 0.759,
    "WL_h3": 0.6726,
    "WL_structure_only": 0.6268,
    "GAE_D0": 0.638,
    "random_init_OCGIN_plus": 0.654,
    "trained_OCGIN_plus": 0.566,
    "GLocalKD_trained_T22_max": 0.579,
    "GLocalKD_untrained_predictor": 0.672,
    "size_floor": 0.7025,
}

IN_DIM = {"T22": 10, "T1K": 25}
REPRESENTATIONS = ("T22", "T1K")
