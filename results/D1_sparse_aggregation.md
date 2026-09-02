# D1 sparse aggregation (D-1 scoring pass)

Artifacts: `abrg/output/androct_2017/d1_sparse_aggregation/`

## Input assertions
- Split digest: `6129eb13d6a46457…` (prefix `6129eb13d6a4`)
- Counts: 562 train-benign / 141 test-benign / 1700 test-malware
- Profiles: `devread/artifacts/profiles/D1_{trained,random_init}_t22.npy` (22 coords)
- Baseline: D1 centroid Euclidean floor AUC **0.8004**

## Phase 1 — variance structure (train-benign D1, trained)
- SD ratio max/min: **45419.7105**
- Spearman ρ(coordinate SD, mapped-event share): **0.9122** (p=3.39e-09)
- PCA: n90=1/22; MaRS condition (n90 ≤ 7): **True**; verdict **LOW_VARIANCE_SEPARATION** — low-variance axes (sep_low=2.4244 > sep_high=0.8601)

| node | mean | SD | mapped_share |
|------|------|-----|--------------|
| accounts | 0.004517 | 0.023488 | 0.0001 |
| audio | 0.001239 | 0.006088 | 0.0018 |
| camera | 0.002226 | 0.007092 | 0.0010 |
| clipboard | 0.002611 | 0.001325 | 0.0000 |
| content_access | 0.015095 | 0.053526 | 0.0013 |
| crypto | 0.692157 | 4.372422 | 0.2117 |
| database | 0.325736 | 2.393876 | 0.0166 |
| device_info | 0.164897 | 3.343615 | 0.0021 |
| dynamic_code_loading | 0.001631 | 0.001273 | 0.0000 |
| file_io | 0.675518 | 3.458347 | 0.1690 |
| ipc_intents | 10.741964 | 49.864145 | 0.1256 |
| location | 0.025169 | 0.374396 | 0.0004 |
| media | 0.077108 | 0.721667 | 0.0019 |
| native_code | 0.768467 | 4.185406 | 0.1453 |
| network | 0.254790 | 1.508115 | 0.0803 |
| notifications | 0.008619 | 0.016713 | 0.0000 |
| package_manager | 1.096741 | 8.353555 | 0.0898 |
| process | 0.358318 | 4.004774 | 0.0475 |
| sms | 0.000640 | 0.002250 | 0.0000 |
| storage | 0.178086 | 1.169084 | 0.0286 |
| telephony | 0.000872 | 0.001098 | 0.0000 |
| webview | 0.125125 | 0.565912 | 0.0769 |

Full Phase 1: `abrg/output/androct_2017/d1_sparse_aggregation/phase1.json`

## Phase 2 — aggregator sweep
Matrix: `abrg/output/androct_2017/d1_sparse_aggregation/matrix.csv` (37 rows)

| tag | prep | aggregator | AUC_floor | direction | clears | Δ vs 0.8004 |
|-----|------|------------|-----------|-----------|--------|-------------|
| random_init_t22 | RAW | Linf | 0.8161 | malware_higher_score | True | +0.0157 |
| random_init_t22 | RAW | MAX | 0.8161 | malware_higher_score | True | +0.0157 |
| random_init_t22 | RAW | L2 | 0.8118 | malware_higher_score | True | +0.0114 |
| random_init_t22 | RAW | L1 | 0.8091 | malware_higher_score | True | +0.0087 |
| random_init_t22 | RAW | TOPK_MEAN_3 | 0.8072 | malware_higher_score | True | +0.0068 |
| random_init_t22 | RAW | WINSOR_L2 | 0.8039 | malware_higher_score | True | +0.0035 |
| random_init_t22 | RAW | TOPK_MEAN_5 | 0.8019 | malware_higher_score | True | +0.0015 |
| random_init_t22 | RAW | TOPK_MEAN_2 | 0.8012 | malware_higher_score | True | +0.0008 |
| trained_t22 | RAW | D1_CENTROID_EUCLIDEAN | 0.8004 | malware_higher_score | True | +0.0000 |
| trained_t22 | RAW | L2 | 0.8004 | malware_higher_score | True | +0.0000 |
| trained_t22 | RAW | Linf | 0.7945 | malware_higher_score | True | -0.0059 |
| trained_t22 | RAW | MAX | 0.7945 | malware_higher_score | True | -0.0059 |
| trained_t22 | RAW | TOPK_MEAN_2 | 0.7900 | malware_higher_score | True | -0.0104 |
| trained_t22 | RAW | TOPK_MEAN_3 | 0.7728 | malware_higher_score | True | -0.0276 |
| trained_t22 | RAW | L1 | 0.7594 | malware_higher_score | True | -0.0410 |
| trained_t22 | RAW | TOPK_MEAN_5 | 0.7428 | malware_higher_score | True | -0.0576 |
| random_init_t22 | RAW | TRIMMED_L2 | 0.7412 | malware_higher_score | True | -0.0592 |
| trained_t22 | RAW | WINSOR_L2 | 0.7207 | malware_higher_score | True | -0.0797 |
| random_init_t22 | ZSTD | TRIMMED_L2 | 0.6702 | malware_higher_score | False | -0.1302 |
| trained_t22 | RAW | TRIMMED_L2 | 0.6422 | malware_higher_score | False | -0.1582 |
| random_init_t22 | ZSTD | L1 | 0.6259 | malware_higher_score | False | -0.1745 |
| trained_t22 | ZSTD | TRIMMED_L2 | 0.6141 | malware_higher_score | False | -0.1863 |
| random_init_t22 | ZSTD | L2 | 0.6008 | malware_higher_score | False | -0.1996 |
| random_init_t22 | ZSTD | TOPK_MEAN_5 | 0.5880 | malware_higher_score | False | -0.2124 |
| random_init_t22 | ZSTD | TOPK_MEAN_3 | 0.5742 | malware_higher_score | False | -0.2262 |
| random_init_t22 | ZSTD | TOPK_MEAN_2 | 0.5588 | malware_higher_score | False | -0.2416 |
| random_init_t22 | ZSTD | Linf | 0.5379 | malware_higher_score | False | -0.2625 |
| random_init_t22 | ZSTD | MAX | 0.5379 | malware_higher_score | False | -0.2625 |
| trained_t22 | ZSTD | L1 | 0.5268 | malware_higher_score | False | -0.2736 |
| random_init_t22 | ZSTD | WINSOR_L2 | 0.5175 | malware_higher_score | False | -0.2829 |
| trained_t22 | ZSTD | TOPK_MEAN_2 | 0.5157 | benign_higher_score | False | -0.2847 |
| trained_t22 | ZSTD | TOPK_MEAN_3 | 0.5138 | benign_higher_score | False | -0.2866 |
| trained_t22 | ZSTD | WINSOR_L2 | 0.5112 | benign_higher_score | False | -0.2892 |
| trained_t22 | ZSTD | TOPK_MEAN_5 | 0.5096 | malware_higher_score | False | -0.2908 |
| trained_t22 | ZSTD | L2 | 0.5089 | malware_higher_score | False | -0.2915 |
| trained_t22 | ZSTD | Linf | 0.5010 | malware_higher_score | False | -0.2994 |
| trained_t22 | ZSTD | MAX | 0.5010 | malware_higher_score | False | -0.2994 |

## Phase 3 — controls (best trained row)
- Best row: **RAW / L2** — floor **0.8004**
- max |ρ| vs six covariates: **0.3301** (D1 standard: ≤0.33) → **False**
- Residualised on mapped events: R²=0.000029; floor **0.8048** (malware_higher_score)
- Volume terciles (test mapped events):
  - T1_low: floor **0.7849** (n=614)
  - T2_mid: floor **0.7957** (n=614)
  - T3_high: floor **0.8542** (n=613)
- Benign-group holdout (Ward k=5): pooled OOF floor **0.7889**; folds inverted **0/5**
- Shuffled labels: floor **0.5049** (benign_higher_score)
- Top per-node ablation drops:
  - ipc_intents: Δ **0.2090**
  - network: Δ **0.0025**
  - package_manager: Δ **0.0022**
  - file_io: Δ **0.0013**
  - native_code: Δ **0.0010**

## Phase 4 — interpretation
4a. **No (trained).** Best trained row is **RAW/L2** at **0.8004** — identical to D1 centroid; no sparse or alternative aggregator improves the trained profile. Volume coupling max |ρ|=**0.3301** (D1 standard ≤0.33; marginal fail by 0.0001). Residualised floor **0.8048** and holdout **0.7889** (0/5 inverted) match D1's existing controls. §A.8.3's readout-gap diagnosis is correct about mechanism; replacing the L2 aggregator does not close it on trained weights.
4b. ZSTD vs RAW mean Δ floor (trained, matched aggregators): **-0.2350** — diagonal standardisation **hurts** on D1 (opposite of E2 on self-ref d-vectors).
4c. Sparse vs L2 mean Δ (RAW trained): **-0.0443** — MAX/Linf/TOPK **underperform** dense L2 on D1 (opposite of E0/E2 window framings).
4d. Random-init best: Linf/RAW **0.8161** (+0.0157 vs baseline) vs trained best **0.8004** — **random beats trained** (seventh family pattern). Full volume controls were not re-run on this secondary arm; treat as diagnostic only.
4e. ρ(SD, mapped share)=**0.9122** (near E2's 0.948): per-coordinate SD on D1 is largely density-driven; ZSTD collapses signal (best trained ZSTD floor **0.5089**). Residualised honest figure for the D1-equivalent row: **0.8048**.

