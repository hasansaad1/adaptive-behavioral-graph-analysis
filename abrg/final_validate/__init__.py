"""Final validation sweep — additive, read-only imports."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

FINAL_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "final_validation"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
SEEDS = (42, 43, 44, 45, 46)
SIZE_FLOOR = 0.7025
OCPOOL_INCUMBENT = 0.7765
FPR_POINTS = (0.001, 0.01, 0.05, 0.10)
WILD_MALWARE_BASE_RATE = 0.01
WILD_BASE_RATE_NOTE = "assumed wild malware prevalence = 0.01 (1%)"
TEST_N_BENIGN = 141
TEST_N_MALWARE = 1700
