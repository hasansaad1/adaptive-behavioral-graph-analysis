"""Data loaders for OCGTL (PyG Data from existing tensors)."""

from __future__ import annotations

from typing import Any

import torch
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader


def app_to_data(t: dict[str, Any], *, shuffle_x: torch.Tensor | None = None) -> Data:
    x = t["x"].float()
    if shuffle_x is not None:
        x = shuffle_x
    return Data(x=x, edge_index=t["edge_index"].long())


def make_loader(
    tensors: dict[str, dict],
    apps: list,
    *,
    batch_size: int,
    shuffle: bool,
    shuffled_x: dict[str, torch.Tensor] | None = None,
) -> DataLoader:
    data_list = []
    for a in apps:
        if a.sha256 not in tensors:
            continue
        sx = shuffled_x.get(a.sha256) if shuffled_x is not None else None
        data_list.append(app_to_data(tensors[a.sha256], shuffle_x=sx))
    return DataLoader(data_list, batch_size=batch_size, shuffle=shuffle)
