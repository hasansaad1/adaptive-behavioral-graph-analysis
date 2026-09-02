"""Graph autoencoder (GAE) — swappable for DOMINANT dual-channel later."""

from __future__ import annotations

import random
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor
from torch_geometric.nn import GAE, GCNConv


def seed_rng(seed: int) -> None:
    """Seed Python + Torch RNGs (PyG recon_loss uses Python random)."""
    random.seed(seed)
    torch.manual_seed(seed)


class GCNEncoder(nn.Module):
    """Two-layer GCN encoder. Optionally scales messages by edge_weight."""

    def __init__(self, in_channels: int, hidden_channels: int, out_channels: int) -> None:
        super().__init__()
        self.conv1 = GCNConv(in_channels, hidden_channels)
        self.conv2 = GCNConv(hidden_channels, out_channels)

    def forward(
        self,
        x: Tensor,
        edge_index: Tensor,
        edge_weight: Optional[Tensor] = None,
    ) -> Tensor:
        # PyG GCNConv: edge_weight=None → unweighted; else one weight per edge.
        ew = edge_weight if edge_weight is not None and edge_weight.numel() > 0 else None
        x = self.conv1(x, edge_index, edge_weight=ew).relu()
        return self.conv2(x, edge_index, edge_weight=ew)


def build_gae(in_channels: int, hidden_channels: int) -> GAE:
    encoder = GCNEncoder(in_channels, hidden_channels, hidden_channels)
    return GAE(encoder)


def train_gae(
    model: GAE,
    x: Tensor,
    edge_index: Tensor,
    epochs: int,
    lr: float,
    edge_weight: Optional[Tensor] = None,
    weight_decay: float = 0.0,
) -> tuple[list[float], float]:
    """
    Train GAE to reconstruct adjacency on a single graph (smoke test).
    Returns per-epoch reconstruction losses and final loss.
    """
    return train_gae_multi(
        model, [(x, edge_index, edge_weight)], epochs, lr, weight_decay=weight_decay
    )


def train_gae_multi(
    model: GAE,
    graphs: list[tuple[Tensor, Tensor] | tuple[Tensor, Tensor, Optional[Tensor]]],
    epochs: int,
    lr: float,
    weight_decay: float = 0.0,
) -> tuple[list[float], float]:
    """
    Train GAE on one or more graphs (batched per epoch).

    Each graph is (x, edge_index) or (x, edge_index, edge_weight).
    Loss remains PyG adjacency BCE (recon_loss); edge_weight only affects the encoder.
    """
    if not graphs:
        return [], float("nan")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    losses: list[float] = []
    rng = random.Random(0)

    model.train()
    for _ in range(epochs):
        order = [g for g in graphs if g[1].numel() > 0]
        rng.shuffle(order)
        optimizer.zero_grad()
        epoch_loss = 0.0
        for item in order:
            x, edge_index = item[0], item[1]
            edge_weight = item[2] if len(item) > 2 else None
            z = model.encode(x, edge_index, edge_weight)
            loss = model.recon_loss(z, edge_index)
            (loss / len(order)).backward()
            epoch_loss += float(loss.item())
        optimizer.step()
        losses.append(epoch_loss / max(len(order), 1))

    return losses, losses[-1] if losses else float("nan")


@torch.no_grad()
def graph_reconstruction_error(
    model: GAE,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
) -> float:
    """Per-graph adjacency reconstruction loss (BCE on positive edges)."""
    if edge_index.numel() == 0:
        return float("nan")
    model.eval()
    z = model.encode(x, edge_index, edge_weight)
    return float(model.recon_loss(z, edge_index).item())


@torch.no_grad()
def graph_reconstruction_error_deterministic(
    model: GAE,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
) -> float:
    """
    Deterministic recon error for paired / ranking diagnostics.

    Same pos BCE as GAE.recon_loss, but negatives are *all* directed non-edges
    (no self-loops, no random sampling). Needed so δ = err(corrupt) − err(benign)
    is not dominated by NegativeSampling noise.

    edge_weight is fed to the encoder only (not into recon_loss).
    """
    if edge_index.numel() == 0:
        return float("nan")
    model.eval()
    z = model.encode(x, edge_index, edge_weight)
    n = z.size(0)
    pos = edge_index
    pos_set = {(int(pos[0, i]), int(pos[1, i])) for i in range(pos.size(1))}
    neg_src: list[int] = []
    neg_dst: list[int] = []
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (i, j) in pos_set:
                continue
            neg_src.append(i)
            neg_dst.append(j)
    if not neg_src:
        return float(model.recon_loss(z, pos).item())
    neg = torch.tensor([neg_src, neg_dst], dtype=torch.long)
    return float(model.recon_loss(z, pos, neg).item())


def full_adjacency_weighted_recon_loss(
    model: GAE,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
) -> Tensor:
    """
    Deterministic BCE over the full n×n adjacency (including diagonal).

    Targets: 1 on observed directed edges, 0 elsewhere (self-loops stay 0 unless
    present in edge_index). Positive-class weighting pos_weight = n_neg / n_pos
    handles sparsity; if n_pos == 0, unweighted BCE over all-negative targets.
    Encoder still receives edge_weight; the loss itself is unweighted on edges
    beyond the binary adjacency target.
    """
    z = model.encode(x, edge_index, edge_weight)
    # Inner-product decoder over all ordered pairs (incl. diagonal): n×n logits.
    logits = z @ z.t()
    n = logits.size(0)
    target = torch.zeros(n, n, dtype=logits.dtype, device=logits.device)
    if edge_index.numel() > 0:
        target[edge_index[0], edge_index[1]] = 1.0
    n_pos = float(target.sum().item())
    n_tot = float(target.numel())
    n_neg = n_tot - n_pos
    flat_logits = logits.reshape(-1)
    flat_target = target.reshape(-1)
    if n_pos > 0.0:
        pos_weight = torch.tensor(n_neg / n_pos, dtype=logits.dtype, device=logits.device)
        return F.binary_cross_entropy_with_logits(
            flat_logits, flat_target, pos_weight=pos_weight
        )
    return F.binary_cross_entropy_with_logits(flat_logits, flat_target)


@torch.no_grad()
def graph_reconstruction_error_full_adjacency_weighted(
    model: GAE,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
) -> float:
    """Eval counterpart of full_adjacency_weighted_recon_loss (always finite)."""
    model.eval()
    return float(
        full_adjacency_weighted_recon_loss(model, x, edge_index, edge_weight).item()
    )


def train_gae_multi_full_adjacency_weighted(
    model: GAE,
    graphs: list[tuple[Tensor, Tensor] | tuple[Tensor, Tensor, Optional[Tensor]]],
    epochs: int,
    lr: float,
    weight_decay: float = 0.0,
) -> tuple[list[float], float]:
    """
    Train GAE with deterministic full-adjacency BCE + positive-class weighting.

    Same graph filter as train_gae_multi: skip empty edge_index graphs.
    """
    if not graphs:
        return [], float("nan")

    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    losses: list[float] = []
    rng = random.Random(0)

    model.train()
    for _ in range(epochs):
        order = [g for g in graphs if g[1].numel() > 0]
        rng.shuffle(order)
        optimizer.zero_grad()
        epoch_loss = 0.0
        for item in order:
            x, edge_index = item[0], item[1]
            edge_weight = item[2] if len(item) > 2 else None
            loss = full_adjacency_weighted_recon_loss(model, x, edge_index, edge_weight)
            (loss / len(order)).backward()
            epoch_loss += float(loss.item())
        optimizer.step()
        losses.append(epoch_loss / max(len(order), 1))

    return losses, losses[-1] if losses else float("nan")


class FeatureDecoder(nn.Module):
    """Linear attribute decoder X̂ = z Wᵀ + b (DOMINANT-style feature channel)."""

    def __init__(self, hidden_channels: int, out_channels: int) -> None:
        super().__init__()
        self.lin = nn.Linear(hidden_channels, out_channels)

    def forward(self, z: Tensor) -> Tensor:
        return self.lin(z)


def dual_recon_loss(
    model: GAE,
    feature_decoder: FeatureDecoder,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
    *,
    alpha: float = 0.5,
) -> tuple[Tensor, Tensor, Tensor]:
    """
    DOMINANT-style dual reconstruction.

    total = alpha * structure_loss + (1-alpha) * feature_loss
    structure_loss: deterministic full-adjacency weighted BCE (Run 3)
    feature_loss: MSE(X̂, X) with X̂ = FeatureDecoder(z)
    """
    z = model.encode(x, edge_index, edge_weight)
    # Structure (same as full_adjacency_weighted_recon_loss, reuse z)
    logits = z @ z.t()
    n = logits.size(0)
    target = torch.zeros(n, n, dtype=logits.dtype, device=logits.device)
    if edge_index.numel() > 0:
        target[edge_index[0], edge_index[1]] = 1.0
    n_pos = float(target.sum().item())
    n_tot = float(target.numel())
    n_neg = n_tot - n_pos
    flat_logits = logits.reshape(-1)
    flat_target = target.reshape(-1)
    if n_pos > 0.0:
        pos_weight = torch.tensor(n_neg / n_pos, dtype=logits.dtype, device=logits.device)
        structure_loss = F.binary_cross_entropy_with_logits(
            flat_logits, flat_target, pos_weight=pos_weight
        )
    else:
        structure_loss = F.binary_cross_entropy_with_logits(flat_logits, flat_target)

    x_hat = feature_decoder(z)
    feature_loss = F.mse_loss(x_hat, x)
    total = alpha * structure_loss + (1.0 - alpha) * feature_loss
    return total, structure_loss, feature_loss


@torch.no_grad()
def graph_reconstruction_error_dual(
    model: GAE,
    feature_decoder: FeatureDecoder,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Optional[Tensor] = None,
    *,
    alpha: float = 0.5,
) -> float:
    model.eval()
    feature_decoder.eval()
    total, _, _ = dual_recon_loss(
        model, feature_decoder, x, edge_index, edge_weight, alpha=alpha
    )
    return float(total.item())


def train_gae_multi_dual(
    model: GAE,
    feature_decoder: FeatureDecoder,
    graphs: list[tuple[Tensor, Tensor] | tuple[Tensor, Tensor, Optional[Tensor]]],
    epochs: int,
    lr: float,
    *,
    alpha: float = 0.5,
    weight_decay: float = 0.0,
) -> tuple[list[float], float]:
    if not graphs:
        return [], float("nan")

    params = list(model.parameters()) + list(feature_decoder.parameters())
    optimizer = torch.optim.Adam(params, lr=lr, weight_decay=weight_decay)
    losses: list[float] = []
    rng = random.Random(0)

    model.train()
    feature_decoder.train()
    for _ in range(epochs):
        order = [g for g in graphs if g[1].numel() > 0]
        rng.shuffle(order)
        optimizer.zero_grad()
        epoch_loss = 0.0
        for item in order:
            x, edge_index = item[0], item[1]
            edge_weight = item[2] if len(item) > 2 else None
            loss, _, _ = dual_recon_loss(
                model, feature_decoder, x, edge_index, edge_weight, alpha=alpha
            )
            (loss / len(order)).backward()
            epoch_loss += float(loss.item())
        optimizer.step()
        losses.append(epoch_loss / max(len(order), 1))

    return losses, losses[-1] if losses else float("nan")


@torch.no_grad()
def reconstruction_sanity(
    model: GAE,
    x: Tensor,
    edge_index: Tensor,
    edge_weight: Tensor,
) -> dict[str, float]:
    """Compare reconstructed edge scores to observed w_cum on positive edges."""
    model.eval()
    z = model.encode(x, edge_index, edge_weight)
    row, col = edge_index
    scores = (z[row] * z[col]).sum(dim=-1)
    scores = torch.sigmoid(scores)

    if edge_weight.numel() == 0:
        return {"mean_score": 0.0, "mean_w_cum": 0.0, "pearson_approx": 0.0}

    w = edge_weight.float()
    median_w = w.median()
    high = scores[w >= median_w].mean().item() if (w >= median_w).any() else 0.0
    low = scores[w < median_w].mean().item() if (w < median_w).any() else 0.0

    return {
        "mean_edge_score": float(scores.mean().item()),
        "mean_w_cum": float(w.mean().item()),
        "mean_score_high_w_cum_half": high,
        "mean_score_low_w_cum_half": low,
        "score_gap_high_minus_low": high - low,
    }
