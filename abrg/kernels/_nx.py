"""Convert ABRG tensors → NetworkX + GraKeL graphs with discrete node labels."""

from __future__ import annotations

from typing import Any, Literal

import networkx as nx
import numpy as np
import torch

LabelMode = Literal["identity", "category_argmax", "degree"]


def _edge_list(t: dict[str, Any]) -> list[tuple[int, int]]:
    ei = t["edge_index"]
    if isinstance(ei, torch.Tensor):
        if ei.numel() == 0:
            return []
        src = ei[0].detach().cpu().numpy().tolist()
        dst = ei[1].detach().cpu().numpy().tolist()
        return list(zip(src, dst))
    return []


def _edge_weights(t: dict[str, Any]) -> list[float]:
    ew = t.get("edge_weight")
    if ew is None:
        return []
    if isinstance(ew, torch.Tensor):
        return ew.detach().cpu().numpy().astype(float).tolist()
    return []


def tensor_to_nx(
    t: dict[str, Any],
    *,
    n_nodes: int,
    undirected: bool = True,
) -> nx.Graph:
    """Build NetworkX graph. Isolated nodes retained (fixed universe size)."""
    G: nx.Graph = nx.Graph() if undirected else nx.DiGraph()
    G.add_nodes_from(range(n_nodes))
    edges = _edge_list(t)
    weights = _edge_weights(t)
    if weights and len(weights) == len(edges):
        for (u, v), w in zip(edges, weights):
            if u == v:
                continue
            if G.has_edge(u, v):
                G[u][v]["weight"] = max(float(G[u][v].get("weight", 0.0)), float(w))
            else:
                G.add_edge(u, v, weight=float(w))
    else:
        for u, v in edges:
            if u != v:
                G.add_edge(u, v, weight=1.0)
    return G


def node_labels_t22(t: dict[str, Any], mode: LabelMode) -> dict[int, int]:
    """
    T22 discrete labels:
      identity — node index 0..21 (22-category identity)
      degree — undirected degree
    """
    n = int(t["x"].shape[0])
    if mode == "identity" or mode == "category_argmax":
        return {i: i for i in range(n)}
    G = tensor_to_nx(t, n_nodes=n)
    return {i: int(G.degree(i)) for i in range(n)}


def node_labels_t1k(t: dict[str, Any], mode: LabelMode) -> dict[int, int]:
    """
    T1K discrete labels:
      category_argmax — argmax over the 22-category one-hot block in x[:, 3:]
      degree — undirected degree
    """
    x = t["x"].detach().cpu().numpy()
    n = x.shape[0]
    if mode == "degree":
        G = tensor_to_nx(t, n_nodes=n)
        return {i: int(G.degree(i)) for i in range(n)}
    # features: act_share, active, first_norm, onehot[22]
    onehot = x[:, 3:]
    if onehot.shape[1] < 22:
        raise SystemExit(f"STOP: T1K expected ≥22 one-hot cols, got {onehot.shape}")
    labels = {}
    for i in range(n):
        labels[i] = int(np.argmax(onehot[i, :22]))
    return labels


def to_grakel_graph(G: nx.Graph, labels: dict[int, int]):
    """GraKeL Graph from NetworkX + int labels (dict adjacency preserves isolates).

    Fully edgeless graphs get a self-loop on every node so GraKeL's vertex
    histogram path does not hit ZeroDivisionError; self-loops are not present
    in the as-built corpus (documented for edges-removed ablation).
    """
    from abrg.kernels._grakel_shim import Graph

    adj: dict[int, list[int]] = {int(n): [] for n in G.nodes()}
    for u, v in G.edges():
        ui, vi = int(u), int(v)
        if vi not in adj[ui]:
            adj[ui].append(vi)
        if ui not in adj[vi]:
            adj[vi].append(ui)
    if sum(len(v) for v in adj.values()) == 0:
        adj = {int(n): [int(n)] for n in G.nodes()}
    node_labels = {int(n): int(labels[n]) for n in G.nodes()}
    return Graph(adj, node_labels=node_labels)


def prepare_graphs(
    tensors: dict[str, dict[str, Any]],
    shas: list[str],
    *,
    kind: str,
    label_mode: LabelMode,
) -> tuple[list[nx.Graph], list[Any], list[dict[int, int]], list[str]]:
    """
    Returns (nx_graphs, grakel_graphs, label_dicts, failure notes empty — failures tracked upstream).
    """
    nx_graphs: list[nx.Graph] = []
    gk_graphs: list[Any] = []
    label_dicts: list[dict[int, int]] = []
    for sha in shas:
        t = tensors[sha]
        n = int(t["x"].shape[0])
        G = tensor_to_nx(t, n_nodes=n)
        if kind == "T22":
            labs = node_labels_t22(t, label_mode)
        else:
            labs = node_labels_t1k(t, label_mode)
        nx_graphs.append(G)
        label_dicts.append(labs)
        gk_graphs.append(to_grakel_graph(G, labs))
    return nx_graphs, gk_graphs, label_dicts, []
