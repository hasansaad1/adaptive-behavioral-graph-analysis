"""Validation of OCPool residual 0.8141 — additive, read-only imports."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

VALIDATE_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "validation"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
SEED = 42
BOOTSTRAP_B = 200  # reduce to 100 if runtime infeasible; recorded in SUMMARY
BOOTSTRAP_B_FALLBACK = 100

# Headline cell from vocab_control
HEADLINE_VOCAB = "B_docfreq"
HEADLINE_K = 1000
EXPECTED_R0 = 0.7765
EXPECTED_R1 = 0.8141
NAIVE_CI = (0.771, 0.851)

VOCAB_METHODS = ("A_tfidf", "B_docfreq", "C_rawfreq")
GRID_KS = (300, 500, 1000)
