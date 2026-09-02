"""Train OCGTL / GTL-only / K=1 OCC; score graphs."""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import torch
from torch import Tensor
from torch_geometric.loader import DataLoader

from abrg.ocgtl import BATCH_SIZE, EPOCHS, HIDDEN, LR, N_LAYERS, TEMPERATURE, WEIGHT_DECAY
from abrg.ocgtl.data import make_loader
from abrg.ocgtl.losses import GTLOnlyLoss, OCCOnlyLoss, OCGTLLoss
from abrg.ocgtl.models import K1OCC, OCGTL, count_parameters

Mode = Literal["ocgtl", "gtl_only", "k1_occ", "untrained"]


def train_ocgtl(
    *,
    tensors: dict[str, dict],
    train_apps: list,
    in_dim: int,
    k: int,
    seed: int,
    mode: Mode = "ocgtl",
    epochs: int = EPOCHS,
    lr: float = LR,
    weight_decay: float = WEIGHT_DECAY,
    batch_size: int = BATCH_SIZE,
    device: torch.device | None = None,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = device or torch.device("cpu")

    if mode == "k1_occ":
        model: torch.nn.Module = K1OCC(in_dim=in_dim, hidden=HIDDEN, n_layers=N_LAYERS).to(device)
        loss_fn: torch.nn.Module = OCCOnlyLoss()
    else:
        model = OCGTL(in_dim=in_dim, k=k, hidden=HIDDEN, n_layers=N_LAYERS).to(device)
        loss_fn = GTLOnlyLoss(TEMPERATURE) if mode == "gtl_only" else OCGTLLoss(TEMPERATURE)

    train_loader = make_loader(tensors, train_apps, batch_size=batch_size, shuffle=True)
    init_loader = make_loader(tensors, train_apps, batch_size=batch_size, shuffle=False)

    if mode == "k1_occ":
        # Freeze center from untrained forward pass (OCGIN-style).
        model.eval()
        embs = []
        with torch.no_grad():
            for batch in init_loader:
                batch = batch.to(device)
                z, _ = model(batch.x, batch.edge_index, batch.batch)
                embs.append(z)
        theta = torch.cat(embs, dim=0).mean(dim=0, keepdim=True)
        model.center.copy_(theta)
        model.center_frozen = True

    n_params = count_parameters(model)
    if mode == "untrained":
        return {
            "model": model,
            "state_dict": model.state_dict(),
            "n_parameters": n_params,
            "train_losses": [],
            "epochs_run": 0,
            "mode": mode,
            "k": k if mode != "k1_occ" else 1,
        }

    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    losses: list[float] = []
    model.train()
    for _epoch in range(epochs):
        total = 0.0
        n = 0
        for batch in train_loader:
            batch = batch.to(device)
            opt.zero_grad()
            if mode == "k1_occ":
                z, c = model(batch.x, batch.edge_index, batch.batch)
                loss = loss_fn(z, c)
            elif mode == "gtl_only":
                z, _ = model(batch.x, batch.edge_index, batch.batch)
                loss = loss_fn(z)
            else:
                z, c = model(batch.x, batch.edge_index, batch.batch)
                loss = loss_fn(z, c)
            loss.backward()
            opt.step()
            total += float(loss.item()) * batch.num_graphs
            n += batch.num_graphs
        losses.append(total / max(n, 1))

    return {
        "model": model,
        "state_dict": model.state_dict(),
        "n_parameters": n_params,
        "train_losses": losses,
        "epochs_run": len(losses),
        "mode": mode,
        "k": k if mode != "k1_occ" else 1,
        "final_to_initial_loss_ratio": (
            float(losses[-1] / losses[0]) if losses and losses[0] != 0 else float("nan")
        ),
    }


@torch.no_grad()
def score_apps(
    model: torch.nn.Module,
    tensors: dict[str, dict],
    apps: list,
    *,
    mode: Mode,
    device: torch.device,
    batch_size: int = BATCH_SIZE,
    shuffled_x: dict[str, Tensor] | None = None,
) -> tuple[list[float], list[str]]:
    loader = make_loader(
        tensors, apps, batch_size=batch_size, shuffle=False, shuffled_x=shuffled_x
    )
    model.eval()
    if mode == "k1_occ":
        loss_fn: torch.nn.Module = OCCOnlyLoss()
    elif mode == "gtl_only":
        loss_fn = GTLOnlyLoss(TEMPERATURE)
    else:
        loss_fn = OCGTLLoss(TEMPERATURE)

    scores: list[float] = []
    shas = [a.sha256 for a in apps if a.sha256 in tensors]
    for batch in loader:
        batch = batch.to(device)
        if mode == "k1_occ":
            z, c = model(batch.x, batch.edge_index, batch.batch)
            s = loss_fn(z, c, reduce=False)
        elif mode == "gtl_only":
            z, _ = model(batch.x, batch.edge_index, batch.batch)
            s = loss_fn(z, reduce=False)
        else:
            z, c = model(batch.x, batch.edge_index, batch.batch)
            s = loss_fn(z, c, reduce=False)
        scores.extend(s.detach().cpu().tolist())
    return scores, shas


@torch.no_grad()
def collect_embeddings(
    model: OCGTL | K1OCC,
    tensors: dict[str, dict],
    apps: list,
    *,
    mode: Mode,
    device: torch.device,
    batch_size: int = BATCH_SIZE,
) -> Tensor:
    """Return embeddings: OCGTL [N,K,D]; K1 [N,D]."""
    loader = make_loader(tensors, apps, batch_size=batch_size, shuffle=False)
    model.eval()
    outs: list[Tensor] = []
    for batch in loader:
        batch = batch.to(device)
        if mode == "k1_occ":
            z, _ = model(batch.x, batch.edge_index, batch.batch)
            outs.append(z.cpu())
        else:
            z, _ = model(batch.x, batch.edge_index, batch.batch)
            outs.append(z.cpu())
    return torch.cat(outs, dim=0)
