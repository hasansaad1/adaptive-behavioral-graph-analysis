# GLocalKD on AndroCT 2017

Additive package. Does **not** modify graph/apigraph/transitions/invgraph/kernels/
models/ocgin/validate/mapper/parser.

## Why

Reference: Ma et al., WSDM 2022 — distill a **frozen random** target GNN into a
predictor on benign-only data; anomaly = prediction mismatch. Matches this project's
finding that random-init encoders beat trained ones.

## Implementation

**Reimplementation** (not a vendor of the CUDA-hardcoded reference). Consulted
`github.com/RongrongMa/GLocalKD` commit `1c8c15f4996dd710e8db477b9a8e7ac36f1681a0`
for loss weighting (`L = L_node + L_graph`, equal) and max-pool default.

| Item | Value |
|------|-------|
| Layers | `GCNConv(in→128)+ReLU → GCNConv(128→128)+ReLU → GCNConv(128→128)` |
| Pooling | `mean`, `add`, and `max` (reference default) as separate variants |
| Loss | `L_node + L_graph` (equal); also node-only / graph-only ablations |
| Train | epochs 300, lr 0.01, wd 0, Adam, benign-only, seeds {42..46} |
| Score | `s_graph` (primary); `mean(s_node)`; `max(s_node)`; `s_graph+mean(s_node)` |

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/glocalkd/` |
| Outputs | `abrg/output/androct_2017/glocalkd/` |
| CLI | `python -m abrg.glocalkd` |
| Split | digest `6129eb13d6a4…` asserted |

## Representations

T22 `(22,10)` and T1K `(1000,25)` via `abrg.kernels.load` (read-only).

## Degeneracy

Every run reports target/predictor embedding variance, train score distribution,
loss final/initial ratio, fraction of train scores `<1e-6`. Flagged runs suppress AUC
as results.

## CLI

```bash
python -m abrg.glocalkd
python -m abrg.glocalkd --quick          # debug: 1 seed, mean only
python -m abrg.glocalkd --skip-nested
python -m abrg.glocalkd.run_papercfg     # paper-config validation arm (T22 mean, 5 seeds)
```

Outputs for `run_papercfg`: `abrg/output/androct_2017/glocalkd_papercfg/`.
