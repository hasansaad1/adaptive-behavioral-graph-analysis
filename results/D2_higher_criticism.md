# D-2: Higher Criticism and sparse-signal ladder on D1

- generated: 2026-08-22T11:39:48.695084+00:00
- split digest: `6129eb13d6a46457…`

## VERDICT: **SIGNAL_IS_UNIVARIATE**

Ladder best pooled floor=0.649796 vs D1 0.800426 and ipc univariate 0.793191; ipc-excluded best=0.592883 (floor 0.7025). Sparse p-value aggregation does not recover the L2 readout; signal stays on ipc_intents. §A.8.3 open question closed.

## Input assertions

- digest prefix `6129eb13d6a4`; train-benign **562** / test-benign **141** / test-malware **1700**
- `D1_trained_t22.npy` shape **[2403, 22]**; index aligned with split membership
- Baselines: D1 L2 **0.800426**, ipc univariate **0.793191**, floor **0.7025**

## Phase 1 — Per-coordinate empirical p-values

Two-sided p with +1 smoothing: compare |x − μ_j| on test apps to the train-benign
empirical distribution per coordinate j (μ_j = train-benign mean), matching the L2 readout.

### 1a — p-value distribution (test-benign / test-malware)

| node | median p (benign) | IQR | median p (malware) | IQR |
|---|---:|---:|---:|---:|
| `accounts` | 0.511545 | 0.554174 | 0.928952 | 0.554174 |
| `audio` | 0.822380 | 0.000000 | 0.822380 | 0.000000 |
| `camera` | 0.669627 | 0.216696 | 0.669627 | 0.000000 |
| `clipboard` | 1.000000 | 0.000000 | 1.000000 | 0.000000 |
| `content_access` | 0.863233 | 0.000000 | 0.863233 | 0.682060 |
| `crypto` | 0.479574 | 0.355240 | 0.635879 | 0.303730 |
| `database` | 0.751332 | 0.113677 | 0.751332 | 0.113677 |
| `device_info` | 0.573712 | 0.182948 | 0.573712 | 0.182948 |
| `dynamic_code_loading` | 1.000000 | 0.733570 | 1.000000 | 0.000000 |
| `file_io` | 0.465364 | 0.378330 | 0.360568 | 0.415631 |
| `ipc_intents` | 0.605684 | 0.476021 | 0.152753 | 0.188277 |
| `location` | 0.710480 | 0.037300 | 0.710480 | 0.037300 |
| `media` | 0.616341 | 0.193606 | 0.809947 | 0.193606 |
| `native_code` | 0.460036 | 0.541741 | 0.436945 | 0.252220 |
| `network` | 0.513321 | 0.230906 | 0.513321 | 0.019538 |
| `notifications` | 0.760213 | 0.000000 | 0.760213 | 0.062167 |
| `package_manager` | 0.555950 | 0.460036 | 0.488455 | 0.381883 |
| `process` | 0.625222 | 0.076377 | 0.625222 | 0.115453 |
| `sms` | 0.978686 | 0.000000 | 0.978686 | 0.000000 |
| `storage` | 0.550622 | 0.360568 | 0.461812 | 0.273535 |
| `telephony` | 0.984014 | 0.669627 | 0.984014 | 0.669627 |
| `webview` | 0.609236 | 0.353464 | 0.609236 | 0.307282 |

### 1b — Degenerate coordinates

- **0** degenerate (SD<1e-06 or ≤2 distinct train values)

| node | train SD | n distinct | degenerate |
|---|---:|---:|---|
| `telephony` | 0.001098 | 6 | False |

Primary ladder run **both ways**: all 22 coords and **non-degenerate only** (22 retained).

### 1c — Uniformity on test-benign (KS vs U(0,1))

Worst departures from uniformity:
- `sms`: KS=0.936132, p=7.008680e-169
- `clipboard`: KS=0.851064, p=1.099957e-116
- `audio`: KS=0.801104, p=5.218810e-98
- `telephony`: KS=0.728695, p=7.215734e-77
- `content_access`: KS=0.714297, p=3.107968e-73

## Phase 2 — Sparse-signal ladder (trained primary)

| statistic | α₀ | AUC_floor | CI95 | Δ vs D1 | Δ vs ipc | clears |
|---|---:|---:|---|---:|---:|---|
| FISHER | — | 0.649796 | [0.5966,0.7021] | -0.150630 | -0.143396 | False |
| FISHER | — | 0.649796 | [0.5966,0.7021] | -0.150630 | -0.143396 | False |
| FISHER | — | 0.649796 | [0.5966,0.7021] | -0.150630 | -0.143396 | False |
| BERK_JONES | — | 0.586329 | [0.5462,0.6267] | -0.214097 | -0.206863 | False |
| BERK_JONES | — | 0.586329 | [0.5462,0.6267] | -0.214097 | -0.206863 | False |
| BERK_JONES | — | 0.586329 | [0.5462,0.6267] | -0.214097 | -0.206863 | False |
| STOUFFER | — | 0.578490 | [0.5253,0.6356] | -0.221936 | -0.214702 | False |
| STOUFFER | — | 0.578490 | [0.5253,0.6356] | -0.221936 | -0.214702 | False |
| STOUFFER | — | 0.578490 | [0.5253,0.6356] | -0.221936 | -0.214702 | False |
| MIN_P | — | 0.540960 | [0.5025,0.5976] | -0.259466 | -0.252232 | False |
| MIN_P | — | 0.540960 | [0.5025,0.5976] | -0.259466 | -0.252232 | False |
| MIN_P | — | 0.540960 | [0.5025,0.5976] | -0.259466 | -0.252232 | False |
| BONFERRONI | — | 0.519007 | [0.5008,0.5581] | -0.281418 | -0.274184 | False |
| BONFERRONI | — | 0.519007 | [0.5008,0.5581] | -0.281418 | -0.274184 | False |
| BONFERRONI | — | 0.519007 | [0.5008,0.5581] | -0.281418 | -0.274184 | False |
| HC_rank | 0.25 | 0.508974 | [0.5008,0.5462] | -0.291452 | -0.284218 | False |
| HC_rank | 1.0 | 0.508373 | [0.5007,0.5466] | -0.292053 | -0.284819 | False |
| HC | 0.25 | 0.507808 | [0.5009,0.5458] | -0.292618 | -0.285384 | False |
| HC_rank | 0.5 | 0.504337 | [0.5006,0.5443] | -0.296089 | -0.288855 | False |
| HC | 0.5 | 0.503611 | [0.5007,0.5441] | -0.296815 | -0.289581 | False |
| HC | 1.0 | 0.501489 | [0.5007,0.5433] | -0.298936 | -0.291702 | False |

**Best trained row:** `FISHER` (α₀=—) floor **0.649796**

Secondary arm (random-init) and non-degenerate runs: see CSV.

## Phase 3 — Volume strata and ipc-excluded arm

### 3a — Terciles (trained, all 22, α₀=1.0)

| statistic | T1_low | T2_mid | T3_high | pooled |
|---|---:|---:|---:|---:|
| D1 L2 (ref) | 0.784880 | 0.795747 | 0.854213 | 0.800426 |
| Linf random-init (ref T3) | — | — | 0.773817 | — |
| HC | 0.558528 | 0.606395 | 0.578168 | 0.501489 |
| HC_rank | 0.557530 | 0.607630 | 0.545636 | 0.508373 |
| MIN_P | 0.544438 | 0.568218 | 0.557627 | 0.540960 |
| FISHER | 0.664125 | 0.741140 | 0.626327 | 0.649796 |
| STOUFFER | 0.533479 | 0.672143 | 0.635041 | 0.578490 |
| BERK_JONES | 0.597361 | 0.548217 | 0.584065 | 0.586329 |
| BONFERRONI | 0.578608 | 0.524995 | 0.557004 | 0.519007 |

### 3b — ipc-excluded arm (21 coordinates)

- D1 with ipc zeroed (L2 ref): **0.591448**
- Best ipc-excluded ladder: **FISHER** α₀=0.25 floor **0.592883**
- Clears 0.7025 floor: **False**

### 3c — Contribution map (best statistic)

- Best stat `FISHER` (min-p coordinate): **ipc_intents fraction 27.16%**
- Compare Linf D-1: **99.08%** ipc
- Top-5 argmax coordinates:
  - `content_access`: 529
  - `ipc_intents`: 500
  - `network`: 96
  - `camera`: 90
  - `sms`: 85

## Phase 4 — Controls (best row)

- Best: `FISHER` α₀=— floor=0.649796
- Paired vs D1: not run (best ≤ D1 point estimate)
- Nested B=200: point=0.649796, CI [0.612361, 0.674981], bias=-0.000867
- Holdout: 0.587488 [0.567269, 0.608545], 5/5 inverted
- max |ρ| Table A.4: **0.275740**; static_feature_norm: **+0.401544**
- Residualised AUC: **0.649562**, R²=0.002557
- Shuffled labels: **0.505849**

## Phase 5 — Calibrated operating points

### 5a — Split-conformal FPR (cal slice of train-benign)

- α=0.01: achieved FPR=0.035461, TPR=0.026471 (With n_cal=112, split-conformal FPR is bounded by alpha + 1/(n_cal+1) ≈ 0.0188 under exchangeability)
- α=0.05: achieved FPR=0.085106, TPR=0.205294 (With n_cal=112, split-conformal FPR is bounded by alpha + 1/(n_cal+1) ≈ 0.0588 under exchangeability)
- α=0.10: achieved FPR=0.106383, TPR=0.235294 (With n_cal=112, split-conformal FPR is bounded by alpha + 1/(n_cal+1) ≈ 0.1088 under exchangeability)

### 5b — Operating point @ FPR target 0.01

| | ladder best | D1 ref |
|---|---:|---:|
| FPR achieved | 0.000000 | 0.007092 |
| TPR | 0.001765 | 0.002353 |
| wild precision π=0.01 | 1.000000 | 0.003340 |

### 5c — Nominal FPR achievement

- At nominal α=0.01, achieved FPR **0.035461** (target 0.01; finite-sample bound ≈ 0.0188). **Nominal FPR is not achieved** — conformal threshold is conservative on this heavy-tailed ladder score, and the ladder does not improve AUC over D1 anyway.
- A guaranteed-FPR operating point would require a score with better benign calibration; the ladder’s primary p-value combination does not provide that on this profile.


## Artifacts

- `abrg/output/androct_2017/d2_higher_criticism/summary.json`
- `results/D2_higher_criticism_ladder.csv`

