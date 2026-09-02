"""OCGIN deep one-class graph-level AD on AndroCT 2017 (additive; read-only imports)."""

from __future__ import annotations

from pathlib import Path

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

OCGIN_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "ocgin"
SEEDS = (42, 43, 44, 45, 46)
HIDDEN = 32
N_LAYERS = 4
EPOCHS = 300
LR = 0.01
WEIGHT_DECAY = 0.0
BATCH_SIZE = 32
# Hypersphere collapse: mean per-dim embedding variance below this → COLLAPSE DETECTED
COLLAPSE_VAR_THRESHOLD = 1e-6
NEAR_THETA_EPS = 1e-3

# Reference rows (do not re-run) — AndroCT Runs 3–8 headlines
REF_ROWS = {
    "gae_recon_run5": {"auc_floor": 0.638, "inverted": True, "note": "GAE recon Run5"},
    "run8_trained_embedding": {"auc_floor": 0.683, "inverted": False, "note": "Run8 max/centroid_cosine"},
    "run8_random_init": {"auc_floor": 0.759, "inverted": False, "note": "Run8 random-init mean/centroid_euclidean"},
    "input_centroid": {"auc_floor": 0.777, "inverted": False, "note": "704-dim input centroid Euclidean"},
    "supervised_hgb": {"auc_floor": 0.976, "inverted": False, "note": "Run3.5 HGB full"},
}

HIGHEST_SIZE_FLOOR_REF = 0.703  # mapped events (malware-higher); recomputed each run
