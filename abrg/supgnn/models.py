"""Supervised GIN: 4-layer hierarchical readout + binary classification head."""

from __future__ import annotations

from typing import Literal

import torch
from torch import Tensor, nn
from torch_geometric.nn import GINConv, global_add_pool, global_max_pool, global_mean_pool

Pooling = Literal["mean", "add", "max"]


def _mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(in_dim, hidden),
        nn.ReLU(),
        nn.Linear(hidden, out_dim),
    )


def _pool(h: Tensor, batch: Tensor, pooling: Pooling) -> Tensor:
    if pooling == "mean":
        return global_mean_pool(h, batch)
    if pooling == "add":
        return global_add_pool(h, batch)
    return global_max_pool(h, batch)


class SupervisedGIN(nn.Module):
    """
    4× GINConv with BatchNorm, hierarchical readout (concat per-layer pools),
    2-layer classification head (dropout 0.5, single logit).

    GINConv does not accept edge_weight; topology-only message passing.
    """

    def __init__(
        self,
        *,
        in_dim: int,
        hidden: int = 64,
        n_layers: int = 4,
        pooling: Pooling = "mean",
        dropout: float = 0.5,
    ) -> None:
        super().__init__()
        self.pooling = pooling
        self.hidden = hidden
        self.n_layers = n_layers
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        self.readouts = nn.ModuleList()

        dims = [in_dim] + [hidden] * n_layers
        for i in range(n_layers):
            self.convs.append(GINConv(_mlp(dims[i], hidden, dims[i + 1]), train_eps=True))
            self.norms.append(nn.BatchNorm1d(dims[i + 1]))
            self.readouts.append(_mlp(dims[i + 1], hidden, hidden))

        readout_dim = hidden * n_layers
        self.head = nn.Sequential(
            nn.Linear(readout_dim, hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, 1),
        )

    @property
    def readout_dim(self) -> int:
        return self.hidden * self.n_layers

    def encode(self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None) -> Tensor:
        if batch is None:
            batch = x.new_zeros(x.size(0), dtype=torch.long)
        hs: list[Tensor] = []
        h = x
        for conv, norm, readout in zip(self.convs, self.norms, self.readouts):
            h = conv(h, edge_index)
            h = norm(h)
            h = h.relu()
            g = readout(h)
            g = _pool(g, batch, self.pooling)
            hs.append(g)
        return torch.cat(hs, dim=-1)

    def forward(self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None) -> Tensor:
        return self.head(self.encode(x, edge_index, batch)).squeeze(-1)


def build_supervised_gin(
    *,
    in_dim: int,
    pooling: Pooling,
    hidden: int = 64,
    n_layers: int = 4,
    dropout: float = 0.5,
) -> SupervisedGIN:
    return SupervisedGIN(
        in_dim=in_dim,
        hidden=hidden,
        n_layers=n_layers,
        pooling=pooling,
        dropout=dropout,
    )


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
