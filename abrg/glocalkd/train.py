"""Train GLocalKD predictor against frozen target."""

from __future__ import annotations

from typing import Any, Literal

import torch
from torch import nn
from torch.optim.lr_scheduler import StepLR

from abrg.glocalkd.config import BRIEF, TrainProfile
from abrg.glocalkd.data import make_loader
from abrg.glocalkd.models import GLocalGCN, Pooling, freeze_

LossMode = Literal["full", "node_only", "graph_only"]

# Legacy module pins (brief profile) for existing grid runner.
BATCH_SIZE = BRIEF.batch_size
EPOCHS = BRIEF.epochs
HIDDEN = BRIEF.hidden
LR = BRIEF.lr
N_LAYERS = BRIEF.n_layers
OUT_DIM = BRIEF.out_dim
WEIGHT_DECAY = BRIEF.weight_decay


def _batch_losses(
    z_s: torch.Tensor,
    h_s: torch.Tensor,
    z_t: torch.Tensor,
    h_t: torch.Tensor,
    batch: torch.Tensor,
    *,
    mode: LossMode,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    node_sq = ((z_s - z_t) ** 2).mean(dim=-1)
    n_graphs = int(batch.max().item()) + 1
    node_per_g = torch.zeros(n_graphs, device=z_s.device)
    counts = torch.zeros(n_graphs, device=z_s.device)
    node_per_g.scatter_add_(0, batch, node_sq)
    counts.scatter_add_(0, batch, torch.ones_like(node_sq))
    node_per_g = node_per_g / counts.clamp_min(1.0)
    loss_node = node_per_g.mean()

    graph_sq = ((h_s - h_t) ** 2).mean(dim=-1)
    loss_graph = graph_sq.mean()

    if mode == "full":
        loss = loss_node + loss_graph
    elif mode == "node_only":
        loss = loss_node
    elif mode == "graph_only":
        loss = loss_graph
    else:
        raise ValueError(mode)
    return loss, loss_node.detach(), loss_graph.detach()


def build_pair(
    in_dim: int,
    *,
    pooling: Pooling,
    seed: int,
    device: torch.device,
    profile: TrainProfile = BRIEF,
) -> tuple[GLocalGCN, GLocalGCN]:
    torch.manual_seed(seed)
    target = GLocalGCN(
        in_dim,
        hidden=profile.hidden,
        out_dim=profile.out_dim,
        n_layers=profile.n_layers,
        pooling=pooling,
        dropout=profile.dropout,
        batch_norm=profile.batch_norm,
    ).to(device)
    torch.manual_seed(seed + 10_000)
    predictor = GLocalGCN(
        in_dim,
        hidden=profile.hidden,
        out_dim=profile.out_dim,
        n_layers=profile.n_layers,
        pooling=pooling,
        dropout=profile.dropout,
        batch_norm=profile.batch_norm,
    ).to(device)
    freeze_(target)
    return target, predictor


def train_glocalkd(
    *,
    tensors: dict[str, dict[str, Any]],
    train_shas: list[str],
    in_dim: int,
    pooling: Pooling,
    seed: int,
    loss_mode: LossMode = "full",
    profile: TrainProfile = BRIEF,
    trained: bool = True,
    device: torch.device | None = None,
    batch_size: int | None = None,
) -> tuple[GLocalGCN, GLocalGCN, list[float], list[float], list[float]]:
    device = device or torch.device("cpu")
    bs = batch_size if batch_size is not None else profile.batch_size
    target, predictor = build_pair(
        in_dim, pooling=pooling, seed=seed, device=device, profile=profile
    )
    if not trained:
        return target, predictor, [], [], []

    loader = make_loader(tensors, train_shas, batch_size=bs, shuffle=True)
    opt = torch.optim.Adam(
        predictor.parameters(), lr=profile.lr, weight_decay=profile.weight_decay
    )
    sched: StepLR | None = None
    if profile.scheduler == "step":
        sched = StepLR(
            opt,
            step_size=profile.scheduler_step_size,
            gamma=profile.scheduler_gamma,
        )

    total_curve: list[float] = []
    node_curve: list[float] = []
    graph_curve: list[float] = []

    for _epoch in range(profile.epochs):
        predictor.train()
        target.eval()
        sum_tot = sum_n = sum_g = 0.0
        n_graphs = 0
        for batch in loader:
            batch = batch.to(device)
            opt.zero_grad()
            with torch.no_grad():
                z_t, h_t = target(batch.x, batch.edge_index, batch.batch)
            z_s, h_s = predictor(batch.x, batch.edge_index, batch.batch)
            loss, ln, lg = _batch_losses(
                z_s, h_s, z_t, h_t, batch.batch, mode=loss_mode
            )
            loss.backward()
            opt.step()
            ng = int(batch.num_graphs)
            sum_tot += float(loss.item()) * ng
            sum_n += float(ln.item()) * ng
            sum_g += float(lg.item()) * ng
            n_graphs += ng
        if sched is not None:
            sched.step()
        denom = max(n_graphs, 1)
        total_curve.append(sum_tot / denom)
        node_curve.append(sum_n / denom)
        graph_curve.append(sum_g / denom)

    return target, predictor, total_curve, node_curve, graph_curve
