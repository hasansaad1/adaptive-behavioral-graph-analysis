# Weighted vs unweighted GAE (v2)

Same corpus, split (seed 42), and hyperparams. Difference is whether `edge_weight` is
passed into `GCNConv` during encode.

**Loss is still adjacency BCE** (`GAE.recon_loss`) in both cases. Weights affect message
passing only.

## Train / test reconstruction (stochastic recon_loss medians)

| Encoder | Arm | Train med | Test med | Ratio | Final loss |
|---------|-----|----------:|---------:|------:|-----------:|
| **Unweighted** (weights ignored) | normalized | 0.5608 | 0.7010 | 1.250 | 0.6503 |
| **Unweighted** | raw | 0.5611 | 0.7013 | 1.250 | 0.6544 |
| **Weighted** | normalized | 0.5842 | 0.7010 | 1.200 | 0.6884 |
| **Weighted** | raw | 0.5617 | 0.7021 | 1.250 | 0.7688 |

Unweighted numbers from the original `norm_ab_v2` A/B (before encoder wiring).  
Weighted: `abrg/output/norm_ab_v2_weighted/`.

**Takeaway:** Feeding weights does not materially change test medians (~0.70). Norm vs raw
test gap remains ~0.

## Negative control (deterministic recon; edge_weight_in_encoder=True)

Artifacts: `abrg/output/negative_control_v2_weighted/`

| Model | Probe | n | med δ | AUC | Win |
|-------|-------|--:|------:|----:|----:|
| normalized | edge_shuffle | 48 | +0.000 | 0.640 | 46% |
| normalized | impossible_edge | 125 | **+0.228** | **0.945** | **100%** |
| normalized | weight_randomization | 51 | +0.000 | 0.487 | 10% |
| raw | edge_shuffle | 48 | +0.000 | 0.634 | 44% |
| raw | impossible_edge | 125 | **+0.328** | **0.966** | **100%** |
| raw | weight_randomization | 108 | +0.000 | 0.508 | 35% |

Compare to unweighted negative control (`negative_control_v2/`): impossible-edge was already
strong (~0.94 AUC / +0.228 δ); weight probe was exact null. With weights wired:

- **Impossible edge still holds**; raw δ/AUC slightly higher.
- **Weight randomization still fails as a detector** (AUC ≈ 0.5, med δ = 0) even though
  weights now enter the encoder. Shuffling proportions does not systematically raise
  *adjacency* recon error on this corpus.
- **Edge shuffle** still weak (same sparse/n=48 story).

### Why weight shuffle can stay flat with a weighted encoder

1. Many normalized graphs have identical weights (`1.0`) and are skipped (n=51 not 125).
2. Loss only scores edge *presence*, not weight magnitude — embeddings can move without
   the adjacency BCE moving much.
3. Tiny graphs (E≈2–3) leave little room for proportion structure to matter.

## Models

| Path | Role |
|------|------|
| `abrg/output/norm_ab_v2_weighted/normalized_v021/gae_corpus_model.pt` | Weighted + v0.2.1 features |
| `abrg/output/norm_ab_v2_weighted/raw_pre_v021/gae_corpus_model.pt` | Weighted + raw features |

## Re-run

```bash
.venv/bin/python -m abrg.compare_normalization_ab          # → norm_ab_v2_weighted
.venv/bin/python -m abrg.negative_control                  # → negative_control_v2_weighted
.venv/bin/python -m abrg.compare_normalization_ab --no-use-edge-weight --output-dir abrg/output/norm_ab_v2
```