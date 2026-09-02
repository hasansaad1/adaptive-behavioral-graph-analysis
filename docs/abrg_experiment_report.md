# ABRG experiment report

**Scope:** benign corpus GAE pilots, v0.2.1 normalization A/B, and corruption negative controls.  
**Not malware detection.** Active dataset: `datasets/CURRENT` → **v2**.

Artifacts live under `abrg/output/`. Interactive summary: Cursor canvas `abrg-experiment-report`.

---

## Headline findings

1. **Normalization is neutral for reconstruction** on the same v2 split (Δ test median ≈ 0). Earlier “worse than v1” was a **dataset** change, not feature normalization.
2. **Impossible-edge injection** separates strongly on both models (AUC ≈ 0.94–0.97, 100% win). Detection premise holds for structurally forbidden transitions.
3. **Feeding `edge_weight` into the encoder does not fix the weight probe** — med δ ≈ 0, AUC ≈ 0.5 even with weighted GCN message passing (loss remains adjacency BCE).
4. **Edge shuffle is weak** (median δ = 0, AUC ≈ 0.64) on this sparse graph corpus (median ~2–3 edges).
5. **Weighted vs unweighted test medians are nearly identical** (~0.70); weights affect embeddings but not adjacency recon scores much on this corpus.

---

## Setup pins

| Pin | Value |
|-----|--------|
| Hook taxonomy | `CATEGORY_UNIVERSE` = 25 |
| Graph nodes | `GRAPH_CATEGORY_UNIVERSE` = 22 |
| Edge formation | k=5, δ=5s |
| Recency λ | 0.01 / s |
| Processing window | 60s multi-window cumulative snapshots |
| Static layer | zero stub (corpus path) |
| GAE | hidden=16, 300 epochs, lr=0.01 |
| Split | 80/20 by app, seed=42 |

---

## 1. Corpus build (v2)

| Metric | Value |
|--------|------:|
| Sessions | 168 |
| Distinct apps | 59 |
| Snapshots built | 731 |
| Trainable snapshots | 634 (133 sessions) |
| Excluded (no trainable window) | 35 sessions |
| GAE-eligible | 565 snaps · 40 apps |
| Train / test | 440 / 125 snaps · 32 / 8 apps |
| Observed directed category pairs | 82 / 462 possible |

Source: ContextDroid `bulk_llm_benign_v2`, hook_apis.js **v3**, 420s sessions.

---

## 2. Benign GAE reconstruction (historical)

Median reconstruction error under **stochastic** PyG `recon_loss` (random negative sampling).

| Run | Data | Features | Train med | Test med | Ratio | n (train/test) |
|-----|------|----------|----------:|---------:|------:|----------------|
| `corpus_pilot_multiwindow_22` | ~v1 (109 sess) | pre-v0.2.1 raw | 0.556 | 0.572 | 1.03× | 296 / 60 |
| `notebook_pilot` | v1 export | pre / mixed | 0.557 | 0.599 | 1.08× | 296 / 60 |
| `notebook_pilot_v2` (interactive) | v2 | v0.2.1 norm | 0.560 | 0.630 | 1.12× | 440 / 125 |
| `norm_ab` · normalized (unweighted) | v2 | act frac + P(edge) | 0.561 | 0.701 | 1.25× | 440 / 125 |
| `norm_ab` · raw (unweighted) | v2 | log1p + raw w_cum | 0.561 | 0.701 | 1.25× | 440 / 125 |
| `norm_ab_weighted` · normalized | v2 | same + weight→GCN | 0.584 | 0.701 | 1.20× | 440 / 125 |
| `norm_ab_weighted` · raw | v2 | same + weight→GCN | 0.562 | 0.702 | 1.25× | 440 / 125 |

Whole-session 22-node pilot (56 apps): train 0.557 · test 0.580.

---

## 3. Normalization A/B (same corpus / split / seed)

### Unweighted encoder (baseline; `edge_weight` ignored)

| Arm | Train med | Test med | Final loss | Δ vs other (test) |
|-----|----------:|---------:|-----------:|------------------:|
| **normalized_v021** | 0.5608 | 0.7010 | 0.6503 | −0.0003 |
| **raw_pre_v021** | 0.5611 | 0.7013 | 0.6544 | — |

### Weighted encoder (`edge_weight` → `GCNConv`; loss still adjacency BCE)

| Arm | Train med | Test med | Final loss | Δ vs other (test) |
|-----|----------:|---------:|-----------:|------------------:|
| **normalized_v021** | 0.5842 | 0.7010 | 0.6884 | −0.0011 |
| **raw_pre_v021** | 0.5617 | 0.7021 | 0.7688 | — |

**Verdict:** Norm vs raw test gap stays ~0 either way. Feeding weights does not move test medians (~0.70). See `docs/weighted_gae_v2_results.md`.

**Models:**

- Unweighted: `abrg/output/norm_ab_v2/{normalized_v021,raw_pre_v021}/gae_corpus_model.pt`
- Weighted: `abrg/output/norm_ab_v2_weighted/{normalized_v021,raw_pre_v021}/gae_corpus_model.pt`

**Re-run:**

```bash
.venv/bin/python -m abrg.compare_normalization_ab          # weighted → norm_ab_v2_weighted
.venv/bin/python -m abrg.compare_normalization_ab --no-use-edge-weight --output-dir abrg/output/norm_ab_v2
```

---

## 4. Negative control

Deterministic recon score: BCE with **all** directed non-edges as negatives (avoids NegativeSampling noise).  
δᵢ = err(corruptᵢ) − err(benignᵢ). Corruption types **never pooled**.

### Unweighted models (`negative_control_v2/`)

Normalized baseline median = 0.652 · raw = 0.653

| Probe | n | med δ | AUC | Win |
|-------|--:|------:|----:|----:|
| Edge shuffle | 48 | +0.000 | ~0.64 | 46% |
| Impossible edge | 125 | **+0.228** | **~0.94** | **100%** |
| Weight randomize | 51 / 108 | +0.000 | 0.500 | 0% (exact null) |

### Weighted models (`negative_control_v2_weighted/`)

Normalized baseline median = 0.653 · raw = 0.647

| Model | Probe | n | med δ | AUC | Win |
|-------|-------|--:|------:|----:|----:|
| norm | edge_shuffle | 48 | +0.000 | 0.640 | 46% |
| norm | impossible_edge | 125 | **+0.228** | **0.945** | **100%** |
| norm | weight_randomization | 51 | +0.000 | 0.487 | 10% |
| raw | edge_shuffle | 48 | +0.000 | 0.634 | 44% |
| raw | impossible_edge | 125 | **+0.328** | **0.966** | **100%** |
| raw | weight_randomization | 108 | +0.000 | 0.508 | 35% |

### Interpretation

| Probe | Reading |
|-------|---------|
| Impossible edge | Still strong; raw weighted slightly higher δ/AUC |
| Edge shuffle | Still weak / sparsity-limited |
| Weight randomize | **Still fails** after wiring weights into the encoder — adjacency loss does not punish proportion shuffle on this sparse corpus |

**Re-run:** `.venv/bin/python -m abrg.negative_control` → `abrg/output/negative_control_v2_weighted/`  
**Detail:** `docs/weighted_gae_v2_results.md`

---

## 5. Scorer note

| Scorer | Benign test median (approx.) | Used in |
|--------|-----------------------------:|---------|
| Stochastic `recon_loss` | ~0.70 | Pilots, norm A/B tables |
| Deterministic full-negative | ~0.65 | Negative control |

Always state which scorer produced a quoted number.

---

## 6. Open follow-ups

1. ~~Wire `edge_weight` into GCN / training; retrain both A/B models; re-run weight probe.~~ Done — weight probe still null; consider weighted recon loss or denser graphs.
2. Restrict edge-shuffle analysis to E≥k, or denser windows, for a fairer transition-structure test.
3. Replace zero static stub with real Androguard features when comparing tiers later.
4. Keep malware safety harness work in ContextDroid (out of scope for this report).
