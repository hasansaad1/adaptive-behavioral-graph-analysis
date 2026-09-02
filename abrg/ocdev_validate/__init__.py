"""Validation of ocdev headline numbers — additive, read-only imports."""

from __future__ import annotations

from abrg.ocdev import EXPECTED_SPLIT_DIGEST_PREFIX, OCDEV_OUTPUT_ROOT, OCPOOL_INCUMBENT, SEEDS

VALIDATE_OUTPUT_ROOT = OCDEV_OUTPUT_ROOT / "validation"
NESTED_B = 200
NESTED_SEED = 42
SIZE_FLOOR = 0.7025

HEADLINE_A = {
    "config": "trained/D1/none/centroid_euclidean/splitA",
    "point_auc_floor": 0.8004255319148936,
}
HEADLINE_B = {
    "config": "T1K_B_docfreq/S1_norm",
    "point_auc_floor": 0.8226011681268252,
}

__all__ = [
    "EXPECTED_SPLIT_DIGEST_PREFIX",
    "OCPOOL_INCUMBENT",
    "SEEDS",
    "VALIDATE_OUTPUT_ROOT",
    "NESTED_B",
    "NESTED_SEED",
    "SIZE_FLOOR",
    "HEADLINE_A",
    "HEADLINE_B",
]
