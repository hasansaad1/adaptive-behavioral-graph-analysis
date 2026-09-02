"""Train supervised GIN with inverse-frequency class weights and val early stopping."""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn
from torch_geometric.loader import DataLoader

from abrg.supgnn import BATCH_SIZE, DROPOUT, EARLY_STOP_PATIENCE, EPOCHS, HIDDEN, LR, N_LAYERS, SEED, VAL_FRAC, WEIGHT_DECAY
from abrg.supgnn.data import Mode, make_loader, score_loader
from abrg.supgnn.models import Pooling, SupervisedGIN, build_supervised_gin, count_parameters


def inverse_frequency_weights(labels: list[int]) -> tuple[torch.Tensor, dict[str, float]]:
    y = np.asarray(labels, dtype=np.int64)
    n_pos = int((y == 1).sum())
    n_neg = int((y == 0).sum())
    n = len(y)
    if n_pos == 0 or n_neg == 0:
        w_pos = 1.0
        w_neg = 1.0
    else:
        w_pos = n / (2.0 * n_pos)
        w_neg = n / (2.0 * n_neg)
    weight = torch.tensor([w_neg, w_pos], dtype=torch.float32)
    return weight, {"pos_weight": float(w_pos / w_neg), "w_neg": w_neg, "w_pos": w_pos, "n_pos": n_pos, "n_neg": n_neg}


def stratified_val_split(
    apps: list[Any],
    *,
    val_frac: float = VAL_FRAC,
    seed: int = SEED,
) -> tuple[list[Any], list[Any]]:
    rng = np.random.default_rng(seed)
    benign = [a for a in apps if a.label == "benign"]
    malware = [a for a in apps if a.label == "malware"]
    rng.shuffle(benign)
    rng.shuffle(malware)
    n_vb = max(1, int(round(len(benign) * val_frac))) if benign else 0
    n_vm = max(1, int(round(len(malware) * val_frac))) if malware else 0
    val = benign[:n_vb] + malware[:n_vm]
    train = benign[n_vb:] + malware[n_vm:]
    return train, val


def train_supervised_gin(
    *,
    tensors: dict[str, dict[str, Any]],
    train_apps: list[Any],
    val_apps: list[Any] | None = None,
    in_dim: int,
    mode: Mode,
    pooling: Pooling,
    seed: int,
    device: torch.device | None = None,
    epochs: int = EPOCHS,
    batch_size: int = BATCH_SIZE,
    lr: float = LR,
    weight_decay: float = WEIGHT_DECAY,
) -> dict[str, Any]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    device = device or torch.device("cpu")

    if val_apps is None:
        train_apps, val_apps = stratified_val_split(train_apps, seed=SEED)

    train_labels = [1 if a.label == "malware" else 0 for a in train_apps]
    _, cw_meta = inverse_frequency_weights(train_labels)
    pos_weight = torch.tensor([cw_meta["pos_weight"]], dtype=torch.float32, device=device)

    model = build_supervised_gin(in_dim=in_dim, pooling=pooling, hidden=HIDDEN, n_layers=N_LAYERS, dropout=DROPOUT).to(device)
    n_params = count_parameters(model)

    train_loader = make_loader(tensors, train_apps, mode=mode, batch_size=batch_size, shuffle=True)
    val_loader = make_loader(tensors, val_apps, mode=mode, batch_size=batch_size, shuffle=False)

    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

    train_losses: list[float] = []
    val_losses: list[float] = []
    best_val = float("inf")
    best_state: dict[str, Any] | None = None
    patience = 0
    val_diverged = False

    for _epoch in range(epochs):
        model.train()
        total = 0.0
        n = 0
        for batch in train_loader:
            batch = batch.to(device)
            opt.zero_grad()
            logits = model(batch.x, batch.edge_index, batch.batch)
            loss = loss_fn(logits, batch.y.view(-1))
            loss.backward()
            opt.step()
            total += float(loss.item()) * batch.num_graphs
            n += batch.num_graphs
        train_loss = total / max(n, 1)
        train_losses.append(train_loss)

        model.eval()
        v_total = 0.0
        v_n = 0
        with torch.no_grad():
            for batch in val_loader:
                batch = batch.to(device)
                logits = model(batch.x, batch.edge_index, batch.batch)
                loss = loss_fn(logits, batch.y.view(-1))
                v_total += float(loss.item()) * batch.num_graphs
                v_n += batch.num_graphs
        val_loss = v_total / max(v_n, 1)
        val_losses.append(val_loss)

        if len(val_losses) >= 3 and val_loss > val_losses[-2] > val_losses[-3]:
            val_diverged = True

        if val_loss < best_val - 1e-6:
            best_val = val_loss
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            patience = 0
        else:
            patience += 1
            if patience >= EARLY_STOP_PATIENCE:
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return {
        "model": model,
        "state_dict": model.state_dict(),
        "n_parameters": n_params,
        "class_weights": cw_meta,
        "train_losses": train_losses,
        "val_losses": val_losses,
        "best_val_loss": float(best_val),
        "epochs_run": len(train_losses),
        "val_loss_diverged": val_diverged,
        "train_apps_n": len(train_apps),
        "val_apps_n": len(val_apps),
    }


@torch.no_grad()
def evaluate_apps(
    model: SupervisedGIN,
    tensors: dict[str, dict[str, Any]],
    apps: list[Any],
    *,
    mode: Mode,
    device: torch.device,
    batch_size: int = BATCH_SIZE,
) -> tuple[list[float], list[int], list[str]]:
    loader = make_loader(tensors, apps, mode=mode, batch_size=batch_size, shuffle=False)
    scores, labels = score_loader(model, loader, device)
    shas = [a.sha256 for a in apps if a.sha256 in tensors]
    return scores, labels, shas
