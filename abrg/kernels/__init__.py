"""Two-stage shallow GLAD: graph kernels/embeddings + one-class detectors (additive)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

KERNELS_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "kernels"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
SEEDS = (42, 43, 44, 45, 46)
NESTED_BOOTSTRAP_B = 200
NESTED_BOOTSTRAP_B_FALLBACK = 100

SIZE_FLOOR = 0.7025
OCPOOL_MEAN_RAW = 0.7765
OCPOOL_MEAN_R2 = 0.7544
OCPOOL_MEAN_R2_NESTED_CI = (0.699, 0.800)

REF_ROWS = {
    "OCPool_mean_raw": 0.7765,
    "OCPool_mean_R2": 0.7544,
    "OCPool_mean_R2_nested_CI": [0.699, 0.800],
    "random_init_GAE": 0.759,
    "input_centroid": 0.777,
    "GAE": 0.638,
    "OCGIN_plus": 0.566,
    "size_floor_mapped_events": 0.7025,
    "supervised_HGB_full": 0.976,
    "supervised_HGB_adj_only": 0.959,
}

T22_EXPECTED_X = (22, 10)
T1K_EXPECTED_X = (1000, 25)
