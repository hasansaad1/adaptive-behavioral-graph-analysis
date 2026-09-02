"""PyG Data construction and mode ablations (M1/M2/M3)."""

from __future__ import annotations

from typing import Any, Literal

import torch
from torch import Tensor
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader

Mode = Literal["M1_full", "M2_no_edges", "M3_const_feats"]


def _empty_edge_index(device: torch.device | None = None) -> Tensor:
    return torch.zeros((2, 0), dtype=torch.long, device=device)


def tensor_to_data(
    t: dict[str, Any],
    *,
    label: int,
    mode: Mode,
    const_value: float = 1.0,
) -> Data:
    x = t["x"].float()
    edge_index = t["edge_index"].long()
    if mode == "M2_no_edges":
        edge_index = _empty_edge_index(x.device)
    elif mode == "M3_const_feats":
        x = torch.full_like(x, const_value)
    elif mode != "M1_full":
        raise ValueError(f"unknown mode {mode!r}")
    return Data(x=x, edge_index=edge_index, y=torch.tensor([float(label)], dtype=torch.float32))


def make_loader(
    tensors: dict[str, dict[str, Any]],
    apps: list[Any],
    *,
    mode: Mode,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    data_list = [
        tensor_to_data(tensors[a.sha256], label=1 if a.label == "malware" else 0, mode=mode)
        for a in apps
        if a.sha256 in tensors
    ]
    return DataLoader(data_list, batch_size=batch_size, shuffle=shuffle)


@torch.no_grad()
def score_loader(
    model: torch.nn.Module,
    loader: DataLoader,
    device: torch.device,
) -> tuple[list[float], list[int]]:
    model.eval()
    scores: list[float] = []
    labels: list[int] = []
    for batch in loader:
        batch = batch.to(device)
        logits = model(batch.x, batch.edge_index, batch.batch)
        probs = torch.sigmoid(logits).cpu().tolist()
        ys = batch.y.cpu().tolist()
        scores.extend(probs)
        labels.extend(int(round(y)) for y in ys)
    return scores, labels


def apps_to_indices(apps: list[Any], eligible: list[Any]) -> list[int]:
    idx = {a.sha256: i for i, a in enumerate(eligible)}
    return [idx[a.sha256] for a in apps]
