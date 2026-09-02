# VERDICT: **CELL_A_FAILS_GROUP_GENERALISATION**

Generated: 2026-08-22T16:13:50.317773+00:00

## Cell A definition

s_i=||X_raw_i||_2 (704-d); score |s_i - mean_train_benign(s)|

Point AUC_floor: **0.792674** (D1 reference: 0.800426; paired indistinguishable, DeLong p=0.551)

## Volume battery (Cell A | D1 reference)

### Spearman ρ vs test-app scores

| covariate | Cell A ρ | D1 ρ (ref) |
|-----------|----------|------------|
| `mapped_event_count` | -0.010187 | -0.167944 |
| `total_event_count` | +0.094434 | +0.278942 |
| `edge_count` | +0.051634 | +0.103886 |
| `graph_density` | +0.051634 | +0.103886 |
| `distinct_active_categories` | +0.031688 | +0.085446 |
| `active_nodes` | +0.031469 | +0.085546 |
| `static_feature_norm` | +0.166766 | +0.330147 |
| **max \|ρ\| Table A.4 six** | **0.094434** | **0.278942** |

### OLS residualisation (mapped_event_count, train-benign fit)

| | Cell A | D1 |
|--|-------|-----|
| R² | 0.001599 | 0.000029 |
| residualised AUC_floor | 0.788961 | 0.805 |

### Volume terciles (test mapped_event_count)

| tercile | Cell A | D1 |
|---------|--------|-----|
| T1_low | 0.742563 | 0.785 |
| T2_mid | 0.819051 | 0.796 |
| T3_high | 0.841633 | 0.854 |

### Benign-group holdout (Ward k=5, pooled OOF)

- Cell A: **0.712455** [0.683157, 0.739842]; 0/5 inverted
- D1: **0.788885**; 0/5 inverted
  (`final_validation/check4_benign_holdout/check4.json`)

### Nested bootstrap (B=200, train-benign resample)

- Cell A: point 0.792674; CI [0.791806, 0.807293]; bias +0.002449
- D1: point 0.800426; CI [0.757, 0.815]; bias -0.003
  (`ocdev/validation/check1_bias/bias_stats.json`)

## Interpretation

Cell A is statistically indistinguishable from D1 on full-sample floor AUC (DeLong p=0.551) but **less** volume-coupled than D1 on all seven covariates.
- benign-group holdout (decisive): Cell A **0.712455** vs D1 **0.788885** (Δ **-0.076430**; 0/5 folds inverted in both)

Cell A is a new trivial baseline above the 0.7025 floor, not a competitor.
D1's contribution is **robustness to unseen benign behavioural groups**, not volume independence.
