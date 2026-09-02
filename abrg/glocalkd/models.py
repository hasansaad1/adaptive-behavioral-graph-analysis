"""GCN encoder for GLocalKD (target frozen / predictor trained)."""

from __future__ import annotations

from typing import Literal

import torch
from torch import Tensor, nn
from torch_geometric.nn import GCNConv, global_add_pool, global_max_pool, global_mean_pool

Pooling = Literal["mean", "add", "max"]


class GLocalGCN(nn.Module):
    """
    3-layer GCN with optional dropout (block layers) and batch norm after ReLU.

    Default (brief profile): hidden=128, out=128, no dropout/BN.
    Paper profile: hidden=512, out=256, dropout=0.3, BN on hidden activations.
    """

    def __init__(
        self,
        in_dim: int,
        *,
        hidden: int = 128,
        out_dim: int = 128,
        n_layers: int = 3,
        pooling: Pooling = "mean",
        dropout: float = 0.0,
        batch_norm: bool = False,
    ) -> None:
        super().__init__()
        if n_layers != 3:
            raise ValueError("experiment pin: n_layers=3")
        self.pooling = pooling
        self.hidden = hidden
        self.out_dim = out_dim
        self.dropout = float(dropout)
        self.batch_norm = batch_norm
        self.convs = nn.ModuleList(
            [
                GCNConv(in_dim, hidden),
                GCNConv(hidden, hidden),
                GCNConv(hidden, out_dim),
            ]
        )
        self.drop = nn.Dropout(self.dropout) if self.dropout > 0 else None
        self.bn1 = nn.BatchNorm1d(hidden) if batch_norm else None
        self.bn2 = nn.BatchNorm1d(hidden) if batch_norm else None

    def _pool(self, z: Tensor, batch: Tensor) -> Tensor:
        if self.pooling == "mean":
            return global_mean_pool(z, batch)
        if self.pooling == "add":
            return global_add_pool(z, batch)
        if self.pooling == "max":
            return global_max_pool(z, batch)
        raise ValueError(self.pooling)

    def _post_conv(self, h: Tensor, bn: nn.BatchNorm1d | None) -> Tensor:
        h = h.relu()
        if bn is not None:
            h = bn(h)
        return h

    def forward(
        self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None
    ) -> tuple[Tensor, Tensor]:
        if batch is None:
            batch = x.new_zeros(x.size(0), dtype=torch.long)
        h = x
        for i, conv in enumerate(self.convs):
            if i > 0 and self.drop is not None:
                h = self.drop(h)
            h = conv(h, edge_index)
            if i < len(self.convs) - 1:
                bn = self.bn1 if i == 0 else self.bn2
                h = self._post_conv(h, bn)
        z = h
        g = self._pool(z, batch)
        return z, g


def freeze_(model: nn.Module) -> None:
    for p in model.parameters():
        p.requires_grad_(False)
    model.eval()
