"""GIN backbone for OCGTL (OCGIN_plus-style: add pool + GraphNorm; no bias)."""

from __future__ import annotations

import torch
from torch import Tensor, nn
from torch_geometric.nn import GINConv, GraphNorm, global_add_pool


def _mlp(in_dim: int, hidden: int, out_dim: int) -> nn.Sequential:
    """Two-layer MLP with NO bias (collapse guard, carried from OCGIN)."""
    return nn.Sequential(
        nn.Linear(in_dim, hidden, bias=False),
        nn.ReLU(),
        nn.Linear(hidden, out_dim, bias=False),
    )


class GINEncoder(nn.Module):
    """
    4× GINConv, GraphNorm, ReLU, hierarchical readout (add pool after each layer),
    concat → hidden * n_layers. No bias in MLPs/readouts; no bounded final activation.
    """

    def __init__(self, *, in_dim: int, hidden: int = 32, n_layers: int = 4) -> None:
        super().__init__()
        self.hidden = hidden
        self.n_layers = n_layers
        self.convs = nn.ModuleList()
        self.norms = nn.ModuleList()
        self.readouts = nn.ModuleList()
        dims = [in_dim] + [hidden] * n_layers
        for i in range(n_layers):
            self.convs.append(GINConv(_mlp(dims[i], hidden, dims[i + 1]), train_eps=True))
            self.norms.append(GraphNorm(dims[i + 1]))
            self.readouts.append(_mlp(dims[i + 1], hidden, hidden))

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
            h = norm(h, batch)
            h = h.relu()
            g = global_add_pool(readout(h), batch)
            hs.append(g)
        return torch.cat(hs, dim=-1)


class OCGTL(nn.Module):
    """
    Ensemble of K encoders: index 0 = reference, 1..K-1 = transformation encoders.

    Center θ is a trainable Parameter (paper §3.1.2 / reference Models.OCGTL).
    Reference embedding is shifted by θ before return (reference forward quirk).
    """

    def __init__(
        self,
        *,
        in_dim: int,
        k: int,
        hidden: int = 32,
        n_layers: int = 4,
    ) -> None:
        super().__init__()
        if k < 1:
            raise ValueError("k must be >= 1")
        self.k = k
        self.encoders = nn.ModuleList(
            [GINEncoder(in_dim=in_dim, hidden=hidden, n_layers=n_layers) for _ in range(k)]
        )
        emb_dim = hidden * n_layers
        self.center = nn.Parameter(torch.empty(1, 1, emb_dim))
        nn.init.normal_(self.center)

    @property
    def graph_embedding_dim(self) -> int:
        return self.encoders[0].graph_embedding_dim

    def encode_views(self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None) -> Tensor:
        """Return z of shape [n_graphs, K, emb_dim]."""
        zs = [enc(x, edge_index, batch).unsqueeze(1) for enc in self.encoders]
        z = torch.cat(zs, dim=1)
        # Match reference: add trainable center to the reference view.
        z = z.clone()
        z[:, 0] = z[:, 0] + self.center[:, 0]
        return z

    def forward(self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None) -> tuple[Tensor, Tensor]:
        return self.encode_views(x, edge_index, batch), self.center


class K1OCC(nn.Module):
    """Single-encoder OCC (≈ OCGIN): frozen center from untrained mean embedding."""

    def __init__(self, *, in_dim: int, hidden: int = 32, n_layers: int = 4) -> None:
        super().__init__()
        self.encoder = GINEncoder(in_dim=in_dim, hidden=hidden, n_layers=n_layers)
        emb_dim = hidden * n_layers
        self.register_buffer("center", torch.zeros(1, emb_dim))
        self.center_frozen = True

    @property
    def graph_embedding_dim(self) -> int:
        return self.encoder.graph_embedding_dim

    def forward(self, x: Tensor, edge_index: Tensor, batch: Tensor | None = None) -> tuple[Tensor, Tensor]:
        z = self.encoder(x, edge_index, batch)
        return z, self.center


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
