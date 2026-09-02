"""Training profiles for GLocalKD runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ProfileName = Literal["brief", "papercfg"]


@dataclass(frozen=True)
class TrainProfile:
    name: ProfileName
    hidden: int
    out_dim: int
    n_layers: int
    lr: float
    epochs: int
    batch_size: int
    weight_decay: float
    dropout: float
    batch_norm: bool
    scheduler: Literal["none", "step"] = "none"
    scheduler_step_size: int = 50
    scheduler_gamma: float = 0.5

    def summary_line(self) -> str:
        sched = ""
        if self.scheduler == "step":
            sched = (
                f" StepLR(step={self.scheduler_step_size}, gamma={self.scheduler_gamma})"
            )
        bn = "BN" if self.batch_norm else "no BN"
        do = f"dropout={self.dropout}" if self.dropout > 0 else "no dropout"
        return (
            f"hidden={self.hidden} out={self.out_dim} layers={self.n_layers} "
            f"lr={self.lr:g} epochs={self.epochs} batch={self.batch_size} "
            f"{do} {bn}{sched}"
        )


BRIEF = TrainProfile(
    name="brief",
    hidden=128,
    out_dim=128,
    n_layers=3,
    lr=0.01,
    epochs=300,
    batch_size=64,
    weight_decay=0.0,
    dropout=0.0,
    batch_norm=False,
    scheduler="none",
)

PAPERCFG = TrainProfile(
    name="papercfg",
    hidden=512,
    out_dim=256,
    n_layers=3,
    lr=1e-4,
    epochs=150,
    batch_size=300,
    weight_decay=0.0,
    dropout=0.3,
    batch_norm=True,
    scheduler="step",
    scheduler_step_size=50,
    scheduler_gamma=0.5,
)

PROFILES: dict[ProfileName, TrainProfile] = {
    "brief": BRIEF,
    "papercfg": PAPERCFG,
}
