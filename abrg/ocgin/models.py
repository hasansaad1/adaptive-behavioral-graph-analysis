"""OCGIN architectures: OCGIN_orig and OCGIN_plus (no bias; collapse guards)."""

from __future__ import annotations

from typing import Literal

import torch
from torch import Tensor, nn
from torch_geometric.nn import GINConv, GraphNorm, global_add_pool, global_mean_pool

Variant = Literal["OCGIN_orig", "OCGIN_plus"]


def _mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    """Two-layer MLP with NO bias (hypersphere collapse guard)."""
    return nn.Sequential(
        nn.Linear(in_dim, hidden, bias=False),
        nn.ReLU(),
        nn.Linear(hidden, out_dim, bias=False),
    )


class OCGIN(nn.Module):
    """
    4-layer GIN with hierarchical readout (concat of per-layer pooled graph vectors).

    Edge weights (w_cum): GINConv.forward does not accept edge_weight/edge_attr.
    Topology-only message passing; edge weights are intentionally unused.
    """

    def __init__(
        self,
        in_dim: int = 10,
        hidden: int = 32,
        n_layers: int = 4,
        variant: Variant = "OCGIN_orig",
    ) -> None:
        super().__init__()
        self.variant = variant
        self.hidden = hidden
        self.n_layers = n_layers
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        self.readouts = nn.ModuleList()

        dims = [in_dim] + [hidden] * n_layers
        for i in range(n_layers):
            self.convs.append(GINConv(_mlp(dims[i], hidden, dims[i + 1]), train_eps=True))
            if variant == "OCGIN_orig":
                self.norms.append(nn.BatchNorm1d(dims[i + 1]))
            else:
                self.norms.append(GraphNorm(dims[i + 1]))
            self.readouts.append(_mlp(dims[i + 1], hidden, hidden))

        # No bounded activation on final embedding (collapse guard)

    @property
    def graph_embedding_dim(self) -> int:
        return self.hidden * self.n_layers

    def forward(self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None) -> Tensor:
        if batch is None:
            batch = x.new_zeros(x.size(0), dtype=torch.long)
        hs: list[Tensor] = []
        h = x
        for conv, norm, readout in zip(self.convs, self.norms, self.readouts):
            h = conv(h, edge_index)
            if self.variant == "OCGIN_orig":
                h = norm(h)
            else:
                h = norm(h, batch)
            h = h.relu()
            g = readout(h)
            if self.variant == "OCGIN_orig":
                g = global_mean_pool(g, batch)
            else:
                g = global_add_pool(g, batch)
            hs.append(g)
        return torch.cat(hs, dim=-1)


def build_ocgin(variant: Variant, *, in_dim: int = 10, hidden: int = 32, n_layers: int = 4) -> OCGIN:
    return OCGIN(in_dim=in_dim, hidden=hidden, n_layers=n_layers, variant=variant)
