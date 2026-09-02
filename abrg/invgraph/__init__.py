"""Invocation-graph representation on AndroCT 2017 (additive; read-only imports)."""

from __future__ import annotations

from abrg.androct.paths import ANDROCT_OUTPUT_ROOT

INVGRAPH_OUTPUT_ROOT = ANDROCT_OUTPUT_ROOT / "invgraph"
EXPECTED_SPLIT_DIGEST_PREFIX = "6129eb13d6a4"
K = 1000
K_BURST = 5
# V3: look back this many prior in-vocabulary method sightings for a caller proxy
V3_LOOKBACK = 32
SEED = 42
SEEDS = (42, 43, 44, 45, 46)

# Prior edge floors (reference)
BASELINE_EDGE = {
    "22node": 0.5267,
    "api1000_tfidf": 0.5013,
    "B_docfreq": 0.5013,
}
V1_EDGE_FLOOR_TARGET = 0.5013
V1_EDGE_FLOOR_TOL = 0.005  # must reproduce B_docfreq control
STRUCTURAL_EDGE_PASS = 0.60

B_DOCFREQ_VOCAB_CSV = (
    ANDROCT_OUTPUT_ROOT / "apigraph" / "vocab_control" / "vocab_B_docfreq_K1000.csv"
)
