"""Train OCGIN with fixed hypersphere center theta."""

from __future__ import annotations

from typing import Any

import torch
from torch import Tensor, nn
from torch_geometric.data import Batch, Data
from torch_geometric.loader import DataLoader

from abrg.ocgin.models import OCGIN, Variant, build_ocgin


def app_to_data(t: dict[str, Any]) -> Data:
    return Data(x=t["x"].float(), edge_index=t["edge_index"].long())


def make_loader(tensors: dict[str, dict], apps: list, *, batch_size: int, shuffle: bool) -> DataLoader:
    data_list = [app_to_data(tensors[a.sha256]) for a in apps if a.sha256 in tensors]
    return DataLoader(data_list, batch_size=batch_size, shuffle=shuffle)


@torch.no_grad()
def embed_loader(model: OCGIN, loader: DataLoader, device: torch.device) -> Tensor:
    model.eval()
    outs: list[Tensor] = []
    for batch in loader:
        batch = batch.to(device)
        outs.append(model(batch.x, batch.edge_index, batch.batch).cpu())
    if not outs:
        return torch.empty(0, model.graph_embedding_dim)
    return torch.cat(outs, dim=0)


@torch.no_grad()
def init_theta(model: OCGIN, train_loader: DataLoader, device: torch.device) -> Tensor:
    """Forward untrained net over full train set; theta = mean embedding; frozen."""
    emb = embed_loader(model, train_loader, device)
    theta = emb.mean(dim=0)
    return theta.detach().clone()


def train_ocgin(
    *,
    variant: Variant,
    tensors: dict[str, dict],
    train_apps: list,
    seed: int,
    epochs: int,
    lr: float,
    weight_decay: float,
    batch_size: int,
    device: torch.device | None = None,
    trained: bool = True,
) -> tuple[OCGIN, Tensor, list[float]]:
    torch.manual_seed(seed)
    device = device or torch.device("cpu")
    model = build_ocgin(variant).to(device)
    train_loader = make_loader(tensors, train_apps, batch_size=batch_size, shuffle=True)
    # Deterministic loader for theta init (full train, no shuffle)
    init_loader = make_loader(tensors, train_apps, batch_size=batch_size, shuffle=False)

    theta = init_theta(model, init_loader, device).to(device)
    theta.requires_grad_(False)

    if not trained:
        return model, theta.cpu(), []

    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    losses: list[float] = []
    model.train()
    for _epoch in range(epochs):
        total = 0.0
        n = 0
        for batch in train_loader:
            batch = batch.to(device)
            opt.zero_grad()
            z = model(batch.x, batch.edge_index, batch.batch)
            # L = mean_G ||f(G) - theta||^2
            loss = ((z - theta) ** 2).sum(dim=-1).mean()
            loss.backward()
            opt.step()
            total += float(loss.item()) * batch.num_graphs
            n += batch.num_graphs
        losses.append(total / max(n, 1))
    return model, theta.cpu(), losses
