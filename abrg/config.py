"""Pinned pilot constants (ABRG v0.2 smoke test)."""

from __future__ import annotations

# Edge-formation window (pin #4) — separate from processing window.
K_BURST: int = 5
DELTA_SEC: float = 5.0

# Recency decay (pin #5).
LAMBDA_REC: float = 0.01  # per second; provisional — see pilot report.

# Node feature layout (§2.1): static slots are zero-filled stubs (pin #6).
STATIC_FEATURE_NAMES: tuple[str, ...] = (
    "s_v",
    "declared_v",
    "reach_v",
    "epoch_v",
)
# gate_v occupies GATE_V_DIM columns (see registry.GATE_V_DIM).

DYNAMIC_FEATURE_NAMES: tuple[str, ...] = (
    "act_v_log",
    "sess_v",
    "rec_v",
)

# GAE training defaults (pilot smoke test).
GAE_HIDDEN_DIM: int = 16
GAE_EPOCHS: int = 300
GAE_LR: float = 0.01

# §3.6 processing window (separate from edge-formation k/δ).
DEFAULT_WINDOW_MODE: str = "time_sec"
DEFAULT_WINDOW_SEC: float = 60.0
