# Experiment S1 — supervised GIN end-to-end on graphs

Additive module `abrg/supgnn/`. Does not modify graph builders, GAE, OCGIN, ladder,
or existing tensor caches.

## Question

When labels are available, does message passing on ABRG / API-level graphs improve
supervised malware detection vs flat models (HGB) and vs structure-only / no-edge
controls?

## Model

- 4× `GINConv`, 2-layer MLP per conv, hidden=64, ReLU, `BatchNorm1d`
- Hierarchical readout: pool after each layer (mean / add / max), concat → 256-d
- Classification head: Linear→ReLU→Dropout(0.5)→Linear(1)
- Loss: `BCEWithLogitsLoss` with inverse-frequency `pos_weight`
- Optimizer: Adam lr=0.001, wd=5e-4, batch=64, max 200 epochs
- Early stopping on 10% validation split carved from **train only** (seed=42)

`GINConv` does not accept `edge_weight`; topology-only message passing.

## Modes

| Mode | Features | Edges |
|------|----------|-------|
| M1_full | as built | as built |
| M2_no_edges | as built | empty `edge_index` |
| M3_const_feats | constant vector | as built |

**Headline:** M1 − M2 = message-passing contribution under supervision.

## Representations

- **T22** — run-3 22-node tensors, `x` shape `(22, 10)`
- **T1K** — B_docfreq K=1000 tensors, `x` shape `(1000, 25)`

Loaded read-only via `abrg.kernels.load.load_bundle()`.

## Splits

- **Split-A** — stratified both-class 80/20, seed=42 (comparable to ladder rung 1 / HGB)
- **Split-B** — Ward k=30 leave-one-cluster-out on test malware; benign train/test
  fixed at app-level 80/20; assignments from
  `abrg/output/androct_2017/ladder/grouping/route_b_behavioral.json` (asserted vs ladder)

## Seeds

Five seeds `{42,43,44,45,46}`. Split-B reports per-fold, mean±std, size-weighted mean,
and pooled out-of-fold AUC.

## CLI

```bash
python -m abrg.supgnn
python -m abrg.supgnn --resume --skip-split-b   # resume partial runs
python -m abrg.supgnn --reps T22                # T22 only (faster)
```

## Output

```
abrg/output/androct_2017/supgnn/
  artifacts/     checkpoints, indices, predictions.csv, reproduce_config.json
  splitA/
  splitB/
  ablation/
  SUMMARY.md
```

## Isolation

New files under `abrg/supgnn/` and `abrg/output/androct_2017/supgnn/` only.
Read-only imports from kernels, ladder artifacts, apigraph split, androct split helpers.
