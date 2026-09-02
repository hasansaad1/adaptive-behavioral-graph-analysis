# D-1 follow-up: volume covariate reconciliation + random-init Linf controls

- generated: 2026-08-22T10:52:44.960573+00:00
- split digest: `6129eb13d6a46457…`
- profile: `abrg/output/androct_2017/devread/artifacts/profiles/D1_random_init_t22.npy`

## VERDICT: **NOT_DISTINGUISHABLE**

Paired bootstrap 95% CI on AUC_floor difference contains zero; DeLong p=0.340334. D1 stands. Linf selects `ipc_intents` on 99.08% of test apps (univariate ipc wrapper at AUC≈0.793 reference — §A.6.7 multivariate claim does not transfer).

## Task 1 — Volume-covariate bound reconciliation

Score: **trained D1 RAW L2** (canonical 562/141/1700 test set).

### 1a — Table A.4 six covariates (Spearman ρ vs D1 RAW L2 score)

| covariate | ρ (6 dp) |
|---|---:|
| `mapped_event_count` | −0.167944 |
| `total_event_count` | +0.278942 |
| `edge_count` | +0.103886 |
| `graph_density` | +0.103886 |
| `distinct_active_categories` | +0.085446 |
| `active_nodes` | +0.085546 |

- **max |ρ| (Table A.4 six):** 0.278942

### 1b — Same measurement as Chapter A / D-1?

**No — covariate set mismatch.** Chapter A §A.6.7 cites six **Table A.4** scalars but the archived bound 0.33 matches **`static_feature_norm`** (ρ = +0.330147), which is **not** one of those six. Among the six Table A.4 metrics recomputed here, max |ρ| = **0.278942** (`total_event_count`). The D-1 figure 0.3301 uses the **legacy check3** covariate list (includes `static_feature_norm`, omits `distinct_active_categories`). Scoring is equivalent: RAW L2 = centroid Euclidean on D1 profiles (same point AUC 0.800426).

### 1c — Source of original 0.33

- **Source:** `abrg/output/androct_2017/final_validation/check3_d1_volume/check3.json` (also `final_validation/SUMMARY.md` Check 3; T8 cites check4 holdout, not ρ).
- **`static_feature_norm` ρ in check3.json:** 0.330147 → rounds to 0.33.
- **Legacy six in check3 (not Table A.4):** max |ρ| = 0.330147 (static_feature_norm).

### 1d — Proposed chapter amendment (not applied)

**Before:**
> Six volume covariates have $|\rho|\le 0.33$ against the $D_1$ score; residualising on mapped-event count

**After:**
> Among the six Table~A.4 volume scalars, Spearman $|\rho|$ against the $D_1$ score ranges up to **0.2789** (`total_event_count`, $\rho=+0.2789$); static-feature norm reaches $\rho=+0.3301$ (legacy check~3, not a Table~A.4 floor). Residualising on mapped-event count

## Task 2 — Random-init RAW Linf control battery

### 2a — Prior-reporting check

- **Random-init D1 centroid already in catalogue:** **0.811844** at `abrg/output/androct_2017/ocdev/controls/random_init_splitA/random_init__D1__none__centroid_euclidean__splitA__foldNA.json` (ocdev validation SUMMARY: trained 0.8004 vs random-init 0.8118, `trained_and_untrained_indistinguishable`).
- **Random-init RAW Linf 0.8161:** **not** in catalogue — new from D-1 sparse sweep only.
- Catalogue centroid **0.811844** ≠ Linf **0.816097** (different aggregator on same random-init profiles).

### 2b — Paired comparison (trained D1 L2 vs random-init Linf)

| quantity | value | artifact |
|---|---:|---|
| D1 trained RAW L2 AUC_floor | 0.800426 | recomputed |
| random-init RAW Linf AUC_floor | 0.816097 | recomputed |
| point Δ (Linf − D1) | 0.015672 | — |
| DeLong Δ (raw AUC) | -0.015672 | SE=0.016436, z=-0.953505, p=0.340334 |
| paired bootstrap 95% CI on Δ_floor (B=2000) | [-0.047346, 0.015830] | `d1_randominit_controls/summary.json` |
| Spearman ρ(D1 score, Linf score) | 0.842461 | p=0.000000e+00 |

Scores are **strongly correlated** (ρ=0.842461) — the AUC gap is a small perturbation of one ranking, not two independent detectors.

**Difference distinguishable from zero?** **no** (paired bootstrap CI on Δ_floor).

### 2c — Five (+2) controls beside D1 reference

**1. Nested bootstrap (B=200, train-benign resample, fixed eval)**

| | D1 reference (centroid ≡ L2) | random-init Linf |
|---|---:|---:|
| point AUC_floor | 0.800426 | 0.816097 |
| nested 95% CI | [0.757224, 0.815440] | [0.802359, 0.820292] |
| bias (boot mean − point) | -0.002767 | -0.001738 |
| point inside CI | True | True |
| artifact | `ocdev/validation/check1_bias/bias_stats.json` | `summary.json` |

**2. Volume covariates (Table A.4 six, Spearman ρ)**

| covariate | D1 ρ | Linf ρ |
|---|---:|---:|
| `mapped_event_count` | -0.167944 | -0.094004 |
| `total_event_count` | +0.278942 | +0.148865 |
| `edge_count` | +0.103886 | +0.051857 |
| `graph_density` | +0.103886 | +0.051857 |
| `distinct_active_categories` | +0.085446 | +0.030638 |
| `active_nodes` | +0.085546 | +0.031425 |
| max \|ρ\| | 0.278942 | 0.148865 |

**3. Volume residualisation (OLS on mapped_event_count, train-benign)**

| | D1 | random-init Linf |
|---|---:|---:|
| R² | 0.000029 | 0.000689 |
| residualised AUC_floor | 0.804802 | 0.811744 |

**4. Volume terciles (test mapped_event_count)**

- T1_low: D1 **0.784880** / Linf **0.803122**
- T2_mid: D1 **0.795747** / Linf **0.828662**
- T3_high: D1 **0.854213** / Linf **0.773817**

**5. Benign-group holdout (Ward k=5, pooled OOF)**

- D1: **0.788885** [0.764212, 0.813999], 0/5 inverted
- Linf: **0.778990** [0.751496, 0.805158], 0/5 inverted

**6. Shuffled labels (seed=42)**

- D1: **0.504937** / Linf: **0.501521** (D3 analogue reference ≈ 0.5035)

**7. Per-node ablation (top drops)**

- D1: #1 `ipc_intents` Δ=0.208978; #2 `network` Δ=0.002528
- Linf: #1 `ipc_intents` Δ=0.238452; #2 `network` Δ=0.000465

**Linf max-coordinate distribution (test apps)**

- `ipc_intents` selected for **1824/1841** apps (99.08%)
- Top-5 coordinates:
  - `ipc_intents`: 1824
  - `webview`: 8
  - `storage`: 3
  - `file_io`: 2
  - `network`: 2

### 2d — Operating point (FPR target 0.01, Table A.14 protocol)

| | D1 reference | random-init Linf |
|---|---:|---:|
| FPR achieved | 0.007092 | 0.007092 |
| TPR | 0.002353 | 0.003529 |
| wild precision (π=0.01) | 0.003340 | 0.005002 |

## Artifacts

- `abrg/output/androct_2017/d1_randominit_controls/summary.json`
- `results/D1_randominit_controls_battery.csv`

