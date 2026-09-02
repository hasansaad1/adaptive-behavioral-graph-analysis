"""GLocalKD on AndroCT 2017 — additive; read-only imports."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

GLOCALKD_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "glocalkd"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEEDS = (42, 43, 44, 45, 46)
HIDDEN = 128
OUT_DIM = 128
N_LAYERS = 3
EPOCHS = 300
LR = 0.01
WEIGHT_DECAY = 0.0
BATCH_SIZE = 64
NESTED_B = 100
NESTED_B_FULL = 200

SIZE_FLOOR = 0.7025
OCPOOL_MEAN_RAW = 0.7765

# Degeneracy thresholds
TARGET_VAR_MEAN_MIN = 1e-6
PREDICTOR_VAR_MEAN_MIN = 1e-6
LOSS_RATIO_DEGENERATE = 1e-4  # final/initial below this → matched everywhere
FRAC_NEAR_ZERO_MAX = 0.5  # fraction of train scores < 1e-6

REF_ROWS = {
    "OCPool_mean_raw": 0.7765,
    "OCPool_mean_R2": 0.7544,
    "OCPool_mean_R2_nested_CI": [0.699, 0.800],
    "input_centroid": 0.777,
    "random_init_GAE": 0.759,
    "GAE": 0.638,
    "OCGIN_plus": 0.566,
    "WL_h3_kernel": 0.6726,
    "WL_structure_only": 0.6268,
    "size_floor_mapped_events": 0.7025,
    "supervised_HGB_full": 0.976,
    "supervised_HGB_adj_only": 0.959,
}

REF_COMMIT = "1c8c15f4996dd710e8db477b9a8e7ac36f1681a0"
IMPLEMENTATION = (
    "reimplementation from Ma et al. WSDM 2022 + reference main.py loss "
    f"(equal L_node+L_graph); consulted github.com/RongrongMa/GLocalKD@{REF_COMMIT}. "
    "Training hypers (epochs=300, lr=0.01, hidden=128, out=128) per experiment brief; "
    "reference defaults were epochs=150, lr=1e-4, hidden=512, out=256, max-pool. "
    "Pooling variants: mean and add (brief); max also run (reference default)."
)

POOLINGS = ("mean", "add", "max")
LOSS_MODES = ("full", "node_only", "graph_only")  # full = L_node + L_graph
SCORE_VARIANTS = ("s_graph", "mean_s_node", "max_s_node", "s_graph_plus_mean_node")
