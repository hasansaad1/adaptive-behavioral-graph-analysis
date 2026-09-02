"""
OCGTL / GTL / OCC losses.

Reimplemented from Qiu et al. IJCAI 2022 Eqns (1)–(3) and cross-checked against
boschresearch/GraphLevel-AnomalyDetection@7b2295d (AGPL — not copied).

Exact training objective (OCGTL, equal weight — paper Eqn 1, no λ):

  L_OCGTL(G) = L_OCC(G) + L_GTL(G)

  L_OCC(G) = sum_{k=1}^{K-1} || f_k(G) - θ ||_2     # transforms only; L2 not L2²

  L_GTL(G) = sum_{k=1}^{K-1} [ log(C_k) - log(c_k) ]
  c_k = exp( sim(f_k(G), f(G)) / τ )
  C_k = sum_{j ≠ k} exp( sim(f_k(G), f_j(G)) / τ )   # j over all K views incl. ref
  sim = cosine similarity; τ = 1.0 (reference default; paper omits numeric τ)

AMBIGUITY (flagged): user brief said push away from *other graphs in the batch*;
paper Eqn (2) and the reference are *within-graph* among the K views. We follow
paper/reference.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor, nn


class OCGTLLoss(nn.Module):
    def __init__(self, temperature: float = 1.0) -> None:
        super().__init__()
        self.temp = temperature

    def forward(self, z: Tensor, center: Tensor, *, reduce: bool = True) -> Tensor:
        """
        z: [B, K, D], center: [1, 1, D] or [1, D]
        Returns per-graph scores [B] (or mean if reduce).
        """
        c = center.view(1, 1, -1)
        z_norm = (z - c).norm(p=2, dim=-1)  # [B, K]
        z_n = F.normalize(z, p=2, dim=-1)
        bsz, k, _ = z_n.shape
        if k < 2:
            raise ValueError("OCGTLLoss requires K >= 2")

        sim = torch.exp(torch.matmul(z_n, z_n.transpose(-1, -2)) / self.temp)  # [B,K,K]
        eye = torch.eye(k, device=z.device, dtype=torch.bool).unsqueeze(0)
        off = sim.masked_fill(eye, 0.0)
        # For each transform row k>=1: C_k = sum_{j≠k} exp(sim)
        c_denom = off[:, 1:, :].sum(dim=-1)  # [B, K-1]
        z_ori = z_n[:, 0]
        z_trans = z_n[:, 1:]
        pos = torch.exp((z_trans * z_ori.unsqueeze(1)).sum(dim=-1) / self.temp)  # [B,K-1]
        gtl = torch.log(c_denom.clamp_min(1e-12)) - torch.log(pos.clamp_min(1e-12))
        occ = z_norm[:, 1:]
        per_graph = (occ + gtl).sum(dim=-1)
        return per_graph.mean() if reduce else per_graph


class GTLOnlyLoss(nn.Module):
    """Transformation learning without OCC (reference applies 1/|log(1/K)| scale)."""

    def __init__(self, temperature: float = 1.0) -> None:
        super().__init__()
        self.temp = temperature

    def forward(self, z: Tensor, *, reduce: bool = True) -> Tensor:
        z_n = F.normalize(z, p=2, dim=-1)
        bsz, k, _ = z_n.shape
        if k < 2:
            raise ValueError("GTLOnlyLoss requires K >= 2")
        sim = torch.exp(torch.matmul(z_n, z_n.transpose(-1, -2)) / self.temp)
        eye = torch.eye(k, device=z.device, dtype=torch.bool).unsqueeze(0)
        off = sim.masked_fill(eye, 0.0)
        c_denom = off[:, 1:, :].sum(dim=-1)
        z_ori = z_n[:, 0]
        z_trans = z_n[:, 1:]
        pos = torch.exp((z_trans * z_ori.unsqueeze(1)).sum(dim=-1) / self.temp)
        n_trans = k - 1
        scale = 1.0 / abs(float(torch.log(torch.tensor(1.0 / n_trans))))
        per = (torch.log(c_denom.clamp_min(1e-12)) - torch.log(pos.clamp_min(1e-12))) * scale
        per_graph = per.mean(dim=-1)
        return per_graph.mean() if reduce else per_graph


class OCCOnlyLoss(nn.Module):
    """||z - θ||_2² mean over batch (K=1 OCGIN-style)."""

    def forward(self, z: Tensor, center: Tensor, *, reduce: bool = True) -> Tensor:
        # z: [B, D]
        d = ((z - center.view(1, -1)) ** 2).sum(dim=-1)
        return d.mean() if reduce else d
