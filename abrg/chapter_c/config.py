"""Pinned parameters for Chapter C (v2-extended convergence / recency)."""

from __future__ import annotations

from pathlib import Path

from abrg.config import DELTA_SEC, K_BURST, LAMBDA_REC, DEFAULT_WINDOW_SEC

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = REPO_ROOT / "datasets" / "v2_extended"
OUTPUT_ROOT = REPO_ROOT / "abrg" / "output" / "v2_chapter_c"
TENSORS_DIR = OUTPUT_ROOT / "tensors"
FIGURES_DIR = OUTPUT_ROOT / "figures"
ARTIFACTS_DIR = OUTPUT_ROOT / "artifacts"

# Graph pins (timed UpdateGraph path — see README GRAPH_BUILDER_NOTE).
K_BURST_PIN: int = K_BURST  # 5
DELTA_SEC_PIN: float = DELTA_SEC  # 5.0
LAMBDA_REC_PIN: float = LAMBDA_REC  # 0.01 /s from abrg.config
LAMBDA_REC_SWEEP: tuple[float, ...] = (0.001, 0.01, 0.05, 0.1)
WINDOW_SEC_PIN: float = DEFAULT_WINDOW_SEC  # 60.0 multi-window cumulative

# Convergence corpus gate.
MIN_APPS_WITH_GE5: int = 30
MIN_SESSIONS_FOR_CURVE: int = 5
STABILISATION_FRAC: float = 0.10  # d(R_k,R_{k+1}) < frac * d(R_1,R_2)
COLD_START_FRAC: float = 0.10  # within 10% of e at k=n-1

SHUFFLE_SEEDS: tuple[int, ...] = (0, 1, 2, 3, 4)
N_NODES: int = 22  # asserted against GRAPH_CATEGORY_UNIVERSE at load

# Reference combination (documented in SUMMARY / README).
REFERENCE_COMBINE: str = "equal_mean_normalised_session_tensors"
REFERENCE_COMBINE_JUSTIFICATION: str = (
    "Each session graph is built independently with timed update_graph, then "
    "converted to a shares-not-counts dense tensor. R_k is the equal-weight "
    "arithmetic mean of session tensors 1..k. Sessions contribute equally "
    "(event-count does not overweight long traces); distances stay on the "
    "normalised scale used for GAE feeds; Stage-3 channel variants differ only "
    "in which adjacency channel(s) enter the tensor."
)

# Stage-3 "adds" criterion (declared before results).
RECENCY_ADDS_CRITERION: str = (
    "primary=within_vs_cross_separation "
    "(Mann-Whitney U direction: within error < cross error, larger effect preferred); "
    "secondary=faster_stabilisation (smaller median stabilisation k)."
)

EDGE_WEIGHT_VARIANTS: tuple[str, ...] = ("w_cum", "w_rec", "both")
