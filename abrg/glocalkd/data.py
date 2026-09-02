"""Tensor → PyG Data helpers; covariates."""

from __future__ import annotations

from typing import Any

import torch
from torch_geometric.data import Data
from torch_geometric.loader import DataLoader


def tensor_to_data(t: dict[str, Any], *, sha: str = "") -> Data:
    x = t["x"].float()
    ei = t["edge_index"].long()
    # empty edge_index is OK for GCNConv
    return Data(x=x, edge_index=ei, sha=sha)


def make_loader(
    tensors: dict[str, dict[str, Any]],
    shas: list[str],
    *,
    batch_size: int,
    shuffle: bool,
) -> DataLoader:
    data = [tensor_to_data(tensors[s], sha=s) for s in shas]
    return DataLoader(data, batch_size=batch_size, shuffle=shuffle)


def covariates_for(
    tensors: dict[str, dict[str, Any]], shas: list[str], *, kind: str
) -> dict[str, list[float]]:
    rows = []
    for s in shas:
        t = tensors[s]
        if kind == "T22":
            rows.append(
                {
                    "mapped_events": float(t["n_mapped"]),
                    "total_events": float(t["n_events"]),
                    "active_nodes": float(t["n_active"]),
                    "edge_count": float(t["n_edges"]),
                    "density": float(t["density"]),
                    "static_norm": float(t["static_norm"]),
                }
            )
        else:
            sg = t["static_global"]
            sn = float(sg.norm().item()) if hasattr(sg, "norm") else float(sg)
            rows.append(
                {
                    "mapped_events": float(t["n_inv_events"]),
                    "total_events": float(t["n_total_events"]),
                    "active_nodes": float(t["n_active"]),
                    "edge_count": float(t["n_edges"]),
                    "density": float(t["density"]),
                    "static_norm": sn,
                }
            )
    keys = rows[0].keys()
    return {k: [r[k] for r in rows] for k in keys}
