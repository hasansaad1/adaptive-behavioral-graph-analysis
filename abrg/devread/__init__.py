"""Deviation profile + supervised readout experiment (additive)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

DEVREAD_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "devread"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
SEEDS = (42, 43, 44, 45, 46)

RUN5_HIDDEN = 8
RUN5_ALPHA = 0.2
RUN5_REF_AUC_FLOOR = 0.638
RUN5_REF_TOL = 0.01

FEATURE_SETS = ("D0", "D1", "D2", "D3", "D4", "D5")
RAW_SETS = ("RAW_full", "RAW_node_only", "RAW_adj_only")
CLASSIFIERS = ("LR_L2", "LR_L1", "HGB")
