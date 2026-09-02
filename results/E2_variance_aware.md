# E2 — Variance-aware readouts on self-reference d vectors

Runs entirely on E0 persisted d vectors. No window rebuild. Phase 4 conformal uses E0 `armb_n8_windows.pt` only to score reference windows under the same R_i / scoring function.

## Input assertions

- Digest `6129eb13d6a4…` (prefix `6129eb13d6a4`)
- Split 562/141/1700; 2403 apps × 2 test-window d ∈ ℝ²²
- PREFIX + SCATTERED; node + adj — all present
- Artifacts: `abrg/output/androct_2017/selfref/deviations`

## Phase 1 — Anisotropy diagnostic (PREFIX / node primary)

- Eigenvalue: n for 50%/90%/99% variance = **4 / 9 / 14** (of 22)
- MaRS condition (>90% variance in <⅓ of components, i.e. ≤7): **False**
- Separation lives: low-variance axes — MaRS regime (mean |log ratio| low-third=30.3435 > high-third=0.8778)
- Spearman ρ(node variance, mapped-event share) = **0.948**

**VERDICT: `LOW_VARIANCE_SEPARATION`**

| PC | var_ratio | cum | E[proj²] ben | E[proj²] mal | mal:ben |
|---:|---:|---:|---:|---:|---:|
| 0 | 0.2473 | 0.2473 | 0.552978 | 0.454597 | 0.822 |
| 1 | 0.1341 | 0.3814 | 0.116989 | 0.019135 | 0.164 |
| 2 | 0.1080 | 0.4894 | 0.083262 | 0.028976 | 0.348 |
| 3 | 0.1009 | 0.5903 | 0.078916 | 0.021820 | 0.276 |
| 4 | 0.0827 | 0.6729 | 0.068816 | 0.033582 | 0.488 |
| 5 | 0.0750 | 0.7479 | 0.065217 | 0.043306 | 0.664 |
| 6 | 0.0660 | 0.8139 | 0.053777 | 0.027505 | 0.511 |
| 7 | 0.0520 | 0.8659 | 0.050835 | 0.038333 | 0.754 |
| 8 | 0.0457 | 0.9116 | 0.063566 | 0.026306 | 0.414 |
| 9 | 0.0286 | 0.9402 | 0.038422 | 0.016013 | 0.417 |
| 10 | 0.0241 | 0.9643 | 0.033249 | 0.009400 | 0.283 |
| 11 | 0.0119 | 0.9762 | 0.010916 | 0.003847 | 0.352 |
| 12 | 0.0090 | 0.9852 | 0.004112 | 0.017581 | 4.275 |
| 13 | 0.0056 | 0.9908 | 0.011289 | 0.002013 | 0.178 |
| 14 | 0.0038 | 0.9946 | 0.010643 | 0.005815 | 0.546 |
| 15 | 0.0029 | 0.9975 | 0.000060 | 0.000022 | 0.357 |
| 16 | 0.0022 | 0.9997 | 0.002277 | 0.000164 | 0.072 |
| 17 | 0.0003 | 1.0000 | 0.000245 | 0.000221 | 0.902 |
| 18 | 0.0000 | 1.0000 | 0.000208 | 0.000000 | 0.000 |
| 19 | 0.0000 | 1.0000 | 0.000000 | 0.000000 | 9176458691914519002742784.000 |
| 20 | 0.0000 | 1.0000 | 0.000000 | 0.000453 | 4315708575708150800125526016.000 |
| 21 | 0.0000 | 1.0000 | 0.000000 | 0.000042 | 103181525804645198751334400.000 |

Full Phase 1 (all mode×space): `abrg/output/androct_2017/selfref_e2/phase1_anisotropy.json`

## Phase 2 — Mahalanobis (Ledoit-Wolf)

Covariance fit on train-benign d only. Distinct from Chapter A input-space whitening (Run 5 −0.078): this is residual-space scoring.
- PREFIX/node: cond(S)=181.57, shrinkage=0.0293
- PREFIX/adj: cond(S)=745.20, shrinkage=0.0128
- SCATTERED/node: cond(S)=200.64, shrinkage=0.0271
- SCATTERED/adj: cond(S)=759.73, shrinkage=0.0122

### Raw matrix

| split | score | verdict | space | auc_floor | dir | CI95 | clears | ρ_b | ρ_m |
|---|---|---|---|---:|---|---|---|---:|---:|
| PREFIX | MAHALANOBIS | MEAN | node | 0.7039 | benign_higher_score | [0.6600, 0.7433] | True | -0.127 | -0.102 |
| PREFIX | MAHALANOBIS | MAX | node | 0.7090 | benign_higher_score | [0.6663, 0.7468] | True | -0.120 | -0.104 |
| PREFIX | MAHALANOBIS | FRACTION | node | 0.5214 | benign_higher_score | [0.5017, 0.5478] | False | -0.009 | 0.053 |
| PREFIX | NODE_STD | MEAN | node | 0.7091 | benign_higher_score | [0.6702, 0.7468] | True | -0.116 | -0.162 |
| PREFIX | NODE_STD | MAX | node | 0.7124 | benign_higher_score | [0.6728, 0.7503] | True | -0.095 | -0.150 |
| PREFIX | NODE_STD | FRACTION | node | 0.5251 | benign_higher_score | [0.5028, 0.5513] | False | 0.171 | 0.076 |
| PREFIX | MAHALANOBIS | MEAN | adj | 0.6102 | benign_higher_score | [0.5577, 0.6594] | False | 0.324 | 0.078 |
| PREFIX | MAHALANOBIS | MAX | adj | 0.6010 | benign_higher_score | [0.5472, 0.6525] | False | 0.326 | 0.121 |
| PREFIX | MAHALANOBIS | FRACTION | adj | 0.5126 | benign_higher_score | [0.5005, 0.5375] | False | 0.139 | 0.091 |
| PREFIX | NODE_STD | MEAN | adj | 0.5818 | benign_higher_score | [0.5272, 0.6321] | False | 0.440 | 0.242 |
| PREFIX | NODE_STD | MAX | adj | 0.5809 | benign_higher_score | [0.5244, 0.6338] | False | 0.440 | 0.261 |
| PREFIX | NODE_STD | FRACTION | adj | 0.5058 | benign_higher_score | [0.5004, 0.5284] | False | 0.124 | 0.107 |
| SCATTERED | MAHALANOBIS | MEAN | node | 0.6945 | benign_higher_score | [0.6492, 0.7359] | False | -0.185 | -0.134 |
| SCATTERED | MAHALANOBIS | MAX | node | 0.6964 | benign_higher_score | [0.6511, 0.7372] | False | -0.204 | -0.143 |
| SCATTERED | MAHALANOBIS | FRACTION | node | 0.5328 | benign_higher_score | [0.5060, 0.5634] | False | -0.115 | 0.040 |
| SCATTERED | NODE_STD | MEAN | node | 0.7012 | benign_higher_score | [0.6605, 0.7417] | False | -0.144 | -0.176 |
| SCATTERED | NODE_STD | MAX | node | 0.7004 | benign_higher_score | [0.6600, 0.7412] | False | -0.160 | -0.174 |
| SCATTERED | NODE_STD | FRACTION | node | 0.5270 | benign_higher_score | [0.5023, 0.5564] | False | -0.020 | 0.046 |
| SCATTERED | MAHALANOBIS | MEAN | adj | 0.6087 | benign_higher_score | [0.5607, 0.6551] | False | 0.328 | 0.007 |
| SCATTERED | MAHALANOBIS | MAX | adj | 0.5997 | benign_higher_score | [0.5487, 0.6490] | False | 0.323 | 0.042 |
| SCATTERED | MAHALANOBIS | FRACTION | adj | 0.5027 | benign_higher_score | [0.5004, 0.5284] | False | 0.219 | 0.067 |
| SCATTERED | NODE_STD | MEAN | adj | 0.5815 | benign_higher_score | [0.5291, 0.6327] | False | 0.447 | 0.179 |
| SCATTERED | NODE_STD | MAX | adj | 0.5761 | benign_higher_score | [0.5243, 0.6274] | False | 0.445 | 0.172 |
| SCATTERED | NODE_STD | FRACTION | adj | 0.5042 | benign_higher_score | [0.5004, 0.5287] | False | 0.272 | 0.064 |

### Size-matched matrix (PRIMARY)

Surviving n: **benign=53, malware=1313** (overlap n_mapped ∈ [173.0, 3567.0]). Underpowered vs full test — equal prominence.

| split | score | verdict | space | auc_floor | dir | CI95 | clears | ρ_b | ρ_m | n_b | n_m |
|---|---|---|---|---:|---|---|---|---:|---:|---:|---:|
| PREFIX | MAHALANOBIS | MEAN | node | 0.6623 | benign_higher_score | [0.5818, 0.7389] | False | -0.045 | -0.061 | 53 | 1313 |
| PREFIX | MAHALANOBIS | MAX | node | 0.6706 | benign_higher_score | [0.5891, 0.7438] | False | -0.053 | -0.045 | 53 | 1313 |
| PREFIX | MAHALANOBIS | FRACTION | node | 0.5118 | benign_higher_score | [0.5007, 0.5527] | False | 0.067 | 0.129 | 53 | 1313 |
| PREFIX | NODE_STD | MEAN | node | 0.6655 | benign_higher_score | [0.5924, 0.7350] | False | -0.026 | 0.038 | 53 | 1313 |
| PREFIX | NODE_STD | MAX | node | 0.6750 | benign_higher_score | [0.6036, 0.7438] | False | -0.017 | 0.052 | 53 | 1313 |
| PREFIX | NODE_STD | FRACTION | node | 0.5399 | benign_higher_score | [0.5026, 0.5913] | False | 0.080 | 0.138 | 53 | 1313 |
| PREFIX | MAHALANOBIS | MEAN | adj | 0.6401 | benign_higher_score | [0.5527, 0.7209] | False | 0.072 | 0.263 | 53 | 1313 |
| PREFIX | MAHALANOBIS | MAX | adj | 0.6467 | benign_higher_score | [0.5577, 0.7286] | False | 0.059 | 0.297 | 53 | 1313 |
| PREFIX | MAHALANOBIS | FRACTION | adj | 0.5403 | benign_higher_score | [0.5025, 0.5924] | False | 0.011 | 0.128 | 53 | 1313 |
| PREFIX | NODE_STD | MEAN | adj | 0.6443 | benign_higher_score | [0.5646, 0.7200] | False | 0.073 | 0.358 | 53 | 1313 |
| PREFIX | NODE_STD | MAX | adj | 0.6522 | benign_higher_score | [0.5752, 0.7284] | False | 0.057 | 0.373 | 53 | 1313 |
| PREFIX | NODE_STD | FRACTION | adj | 0.5225 | benign_higher_score | [0.5010, 0.5703] | False | 0.076 | 0.139 | 53 | 1313 |
| SCATTERED | MAHALANOBIS | MEAN | node | 0.6323 | benign_higher_score | [0.5541, 0.7088] | False | 0.014 | -0.088 | 53 | 1313 |
| SCATTERED | MAHALANOBIS | MAX | node | 0.6307 | benign_higher_score | [0.5514, 0.7081] | False | 0.007 | -0.086 | 53 | 1313 |
| SCATTERED | MAHALANOBIS | FRACTION | node | 0.5295 | benign_higher_score | [0.5015, 0.5811] | False | -0.196 | 0.096 | 53 | 1313 |
| SCATTERED | NODE_STD | MEAN | node | 0.6514 | benign_higher_score | [0.5812, 0.7200] | False | -0.015 | -0.001 | 53 | 1313 |
| SCATTERED | NODE_STD | MAX | node | 0.6464 | benign_higher_score | [0.5763, 0.7141] | False | -0.040 | 0.000 | 53 | 1313 |
| SCATTERED | NODE_STD | FRACTION | node | 0.5368 | benign_higher_score | [0.5017, 0.5915] | False | -0.160 | 0.101 | 53 | 1313 |
| SCATTERED | MAHALANOBIS | MEAN | adj | 0.6403 | benign_higher_score | [0.5603, 0.7150] | False | 0.133 | 0.156 | 53 | 1313 |
| SCATTERED | MAHALANOBIS | MAX | adj | 0.6402 | benign_higher_score | [0.5598, 0.7154] | False | 0.098 | 0.177 | 53 | 1313 |
| SCATTERED | MAHALANOBIS | FRACTION | adj | 0.5326 | benign_higher_score | [0.5019, 0.5855] | False | 0.006 | 0.094 | 53 | 1313 |
| SCATTERED | NODE_STD | MEAN | adj | 0.6447 | benign_higher_score | [0.5661, 0.7178] | False | 0.099 | 0.278 | 53 | 1313 |
| SCATTERED | NODE_STD | MAX | adj | 0.6430 | benign_higher_score | [0.5676, 0.7149] | False | 0.040 | 0.267 | 53 | 1313 |
| SCATTERED | NODE_STD | FRACTION | adj | 0.5379 | benign_higher_score | [0.5018, 0.5930] | False | -0.070 | 0.095 | 53 | 1313 |

Artifact: `abrg/output/androct_2017/selfref_e2/matrix.csv`

## Phase 4 — Conformal p-values

Wrapped **E2** `NODE_STD` on PREFIX/node (ref verdict MAX, auc_floor=0.7124). Calibration = app's own 6 reference-window scores. Licensed by E0 exchangeability (|PREFIX−SCATTERED|=0.0055).

| tag | verdict | auc_floor | dir | clears | ρ_b | ρ_m | n_b | n_m |
|---|---|---:|---|---|---:|---:|---:|---:|
| raw | min_p | 0.5385 | benign_higher_score | False | -0.241 | -0.249 | 141 | 1700 |
| size_matched | min_p | 0.5143 | malware_higher_score | False | 0.071 | -0.285 | 53 | 1313 |
| raw | frac_p_lt_0.05 | 0.5000 | malware_higher_score | False | nan | nan | 141 | 1700 |
| size_matched | frac_p_lt_0.05 | 0.5000 | malware_higher_score | False | nan | nan | 53 | 1313 |
| raw | frac_p_lt_0.1 | 0.5000 | malware_higher_score | False | nan | nan | 141 | 1700 |
| size_matched | frac_p_lt_0.1 | 0.5000 | malware_higher_score | False | nan | nan | 53 | 1313 |
| raw | frac_p_lt_0.2 | 0.5074 | malware_higher_score | False | -0.009 | 0.139 | 141 | 1700 |
| size_matched | frac_p_lt_0.2 | 0.5018 | benign_higher_score | False | -0.123 | 0.147 | 53 | 1313 |

Volume coupling (does conformal reduce |ρ| vs raw wrap score?):
- raw ρ_b=-0.116, ρ_m=-0.162
- min_p ρ_b=-0.241, ρ_m=-0.249
- |ρ| reduction benign=-0.125, malware=-0.086

## Phase 5 — Controls

### 1–3. Size-matched, floor, volume — see matrices above.

### 4. Shuffled labels

Mean shuffled auc_floor = **0.5171** (E0 was 0.517; treat <~0.53 as noise). Artifact: `abrg/output/androct_2017/selfref_e2/shuffled_labels.csv`

### 5. PREFIX − SCATTERED delta

Mean |Δ| = **0.0062**. Artifact: `abrg/output/androct_2017/selfref_e2/prefix_scattered_delta.csv`

| score | verdict | space | PREFIX | SCATTERED | Δ |
|---|---|---|---:|---:|---:|
| MAHALANOBIS | MEAN | node | 0.7039 | 0.6945 | 0.0094 |
| MAHALANOBIS | MEAN | adj | 0.6102 | 0.6087 | 0.0016 |
| MAHALANOBIS | MAX | node | 0.7090 | 0.6964 | 0.0127 |
| MAHALANOBIS | MAX | adj | 0.6010 | 0.5997 | 0.0012 |
| MAHALANOBIS | FRACTION | node | 0.5214 | 0.5328 | -0.0114 |
| MAHALANOBIS | FRACTION | adj | 0.5126 | 0.5027 | 0.0099 |
| NODE_STD | MEAN | node | 0.7091 | 0.7012 | 0.0079 |
| NODE_STD | MEAN | adj | 0.5818 | 0.5815 | 0.0002 |
| NODE_STD | MAX | node | 0.7124 | 0.7004 | 0.0120 |
| NODE_STD | MAX | adj | 0.5809 | 0.5761 | 0.0048 |
| NODE_STD | FRACTION | node | 0.5251 | 0.5270 | -0.0019 |
| NODE_STD | FRACTION | adj | 0.5058 | 0.5042 | 0.0016 |

### 6. E0 comparison (HEADLINE)

E2 best raw=0.7124 vs E0 0.6997 (raw clears floor on 4 NODE_STD/MAHALANOBIS cells); E2 best size-matched=0.6750 vs E0 0.6235. Max Δ(E2−E0) raw=+0.1159, size-matched=+0.1526. Soft read: variance-aware beats isotropic E0 on several cells. Hard read (stop rule): **size-matched clears floor = False** — geometry does not salvage a legitimate one-class detector.

Pairing: MAHALANOBIS↔E0 CENTROID, NODE_STD↔E0 SCALAR.

| tag | split | verdict | space | E2 | E0 | E2 floor | E0 floor | Δ |
|---|---|---|---|---|---|---:|---:|---:|
| raw | PREFIX | MEAN | node | MAHALANOBIS | CENTROID | 0.7039 | 0.5880 | 0.1159 |
| raw | PREFIX | MAX | node | MAHALANOBIS | CENTROID | 0.7090 | 0.5936 | 0.1155 |
| raw | PREFIX | FRACTION | node | MAHALANOBIS | CENTROID | 0.5214 | 0.5194 | 0.0020 |
| raw | PREFIX | MEAN | node | NODE_STD | SCALAR | 0.7091 | 0.6966 | 0.0125 |
| raw | PREFIX | MAX | node | NODE_STD | SCALAR | 0.7124 | 0.6997 | 0.0127 |
| raw | PREFIX | FRACTION | node | NODE_STD | SCALAR | 0.5251 | 0.5253 | -0.0002 |
| raw | PREFIX | MEAN | adj | MAHALANOBIS | CENTROID | 0.6102 | 0.6063 | 0.0040 |
| raw | PREFIX | MAX | adj | MAHALANOBIS | CENTROID | 0.6010 | 0.6036 | -0.0027 |
| raw | PREFIX | FRACTION | adj | MAHALANOBIS | CENTROID | 0.5126 | 0.5085 | 0.0041 |
| raw | PREFIX | MEAN | adj | NODE_STD | SCALAR | 0.5818 | 0.5673 | 0.0145 |
| raw | PREFIX | MAX | adj | NODE_STD | SCALAR | 0.5809 | 0.5650 | 0.0159 |
| raw | PREFIX | FRACTION | adj | NODE_STD | SCALAR | 0.5058 | 0.5065 | -0.0007 |
| raw | SCATTERED | MEAN | node | MAHALANOBIS | CENTROID | 0.6945 | 0.5931 | 0.1015 |
| raw | SCATTERED | MAX | node | MAHALANOBIS | CENTROID | 0.6964 | 0.5945 | 0.1018 |
| raw | SCATTERED | FRACTION | node | MAHALANOBIS | CENTROID | 0.5328 | 0.5353 | -0.0026 |
| raw | SCATTERED | MEAN | node | NODE_STD | SCALAR | 0.7012 | 0.6960 | 0.0052 |
| raw | SCATTERED | MAX | node | NODE_STD | SCALAR | 0.7004 | 0.6985 | 0.0019 |
| raw | SCATTERED | FRACTION | node | NODE_STD | SCALAR | 0.5270 | 0.5257 | 0.0013 |
| raw | SCATTERED | MEAN | adj | MAHALANOBIS | CENTROID | 0.6087 | 0.6211 | -0.0124 |
| raw | SCATTERED | MAX | adj | MAHALANOBIS | CENTROID | 0.5997 | 0.6203 | -0.0205 |
| raw | SCATTERED | FRACTION | adj | MAHALANOBIS | CENTROID | 0.5027 | 0.5000 | 0.0027 |
| raw | SCATTERED | MEAN | adj | NODE_STD | SCALAR | 0.5815 | 0.5688 | 0.0127 |
| raw | SCATTERED | MAX | adj | NODE_STD | SCALAR | 0.5761 | 0.5632 | 0.0130 |
| raw | SCATTERED | FRACTION | adj | NODE_STD | SCALAR | 0.5042 | 0.5061 | -0.0020 |
| size_matched | PREFIX | MEAN | node | MAHALANOBIS | CENTROID | 0.6623 | 0.5098 | 0.1526 |
| size_matched | PREFIX | MAX | node | MAHALANOBIS | CENTROID | 0.6706 | 0.5220 | 0.1486 |
| size_matched | PREFIX | FRACTION | node | MAHALANOBIS | CENTROID | 0.5118 | 0.5034 | 0.0084 |
| size_matched | PREFIX | MEAN | node | NODE_STD | SCALAR | 0.6655 | 0.6137 | 0.0518 |
| size_matched | PREFIX | MAX | node | NODE_STD | SCALAR | 0.6750 | 0.6229 | 0.0521 |
| size_matched | PREFIX | FRACTION | node | NODE_STD | SCALAR | 0.5399 | 0.5046 | 0.0353 |
| size_matched | PREFIX | MEAN | adj | MAHALANOBIS | CENTROID | 0.6401 | 0.5914 | 0.0487 |
| size_matched | PREFIX | MAX | adj | MAHALANOBIS | CENTROID | 0.6467 | 0.6058 | 0.0409 |
| size_matched | PREFIX | FRACTION | adj | MAHALANOBIS | CENTROID | 0.5403 | 0.5197 | 0.0206 |
| size_matched | PREFIX | MEAN | adj | NODE_STD | SCALAR | 0.6443 | 0.6074 | 0.0369 |
| size_matched | PREFIX | MAX | adj | NODE_STD | SCALAR | 0.6522 | 0.6161 | 0.0361 |
| size_matched | PREFIX | FRACTION | adj | NODE_STD | SCALAR | 0.5225 | 0.5207 | 0.0017 |
| size_matched | SCATTERED | MEAN | node | MAHALANOBIS | CENTROID | 0.6323 | 0.5016 | 0.1307 |
| size_matched | SCATTERED | MAX | node | MAHALANOBIS | CENTROID | 0.6307 | 0.5004 | 0.1303 |
| size_matched | SCATTERED | FRACTION | node | MAHALANOBIS | CENTROID | 0.5295 | 0.5054 | 0.0241 |
| size_matched | SCATTERED | MEAN | node | NODE_STD | SCALAR | 0.6514 | 0.6099 | 0.0415 |
| size_matched | SCATTERED | MAX | node | NODE_STD | SCALAR | 0.6464 | 0.6112 | 0.0351 |
| size_matched | SCATTERED | FRACTION | node | NODE_STD | SCALAR | 0.5368 | 0.5115 | 0.0253 |
| size_matched | SCATTERED | MEAN | adj | MAHALANOBIS | CENTROID | 0.6403 | 0.6073 | 0.0330 |
| size_matched | SCATTERED | MAX | adj | MAHALANOBIS | CENTROID | 0.6402 | 0.6235 | 0.0168 |
| size_matched | SCATTERED | FRACTION | adj | MAHALANOBIS | CENTROID | 0.5326 | 0.5136 | 0.0189 |
| size_matched | SCATTERED | MEAN | adj | NODE_STD | SCALAR | 0.6447 | 0.6191 | 0.0256 |
| size_matched | SCATTERED | MAX | adj | NODE_STD | SCALAR | 0.6430 | 0.6186 | 0.0244 |
| size_matched | SCATTERED | FRACTION | adj | NODE_STD | SCALAR | 0.5379 | 0.5005 | 0.0374 |

Artifact: `abrg/output/androct_2017/selfref_e2/e0_comparison.csv`

### 7. Per-node ablation + deviation-difference profile

Ablation target: NODE_STD / PREFIX / node / MAX (baseline auc_floor=0.7124).
**ipc_intents dominates?** **False** (ipc drop=-0.0012; top=file_io drop=0.0144).
ipc_intents does **not** dominate — self-deviation is not the Chapter A univariate Intent detector.
Spearman ρ(ablation drop, node variance) = 0.118

| rank | node | auc_floor | drop | node_var | mapped_share |
|---:|---|---:|---:|---:|---:|
| 1 | file_io | 0.6980 | 0.0144 | 0.130191 | 0.1647 |
| 2 | database | 0.7035 | 0.0089 | 0.026797 | 0.0165 |
| 3 | native_code | 0.7052 | 0.0073 | 0.114985 | 0.1399 |
| 4 | storage | 0.7057 | 0.0068 | 0.060742 | 0.0285 |
| 5 | location | 0.7061 | 0.0063 | 0.005722 | 0.0004 |
| 6 | webview | 0.7064 | 0.0061 | 0.066358 | 0.0747 |
| 7 | accounts | 0.7067 | 0.0057 | 0.002683 | 0.0001 |
| 8 | audio | 0.7069 | 0.0055 | 0.000284 | 0.0018 |
| 9 | notifications | 0.7099 | 0.0025 | 0.003870 | 0.0000 |
| 10 | device_info | 0.7107 | 0.0018 | 0.029046 | 0.0021 |
| 11 | telephony | 0.7110 | 0.0015 | 0.000000 | 0.0000 |
| 12 | package_manager | 0.7123 | 0.0001 | 0.109040 | 0.0858 |
| 13 | content_access | 0.7123 | 0.0001 | 0.014437 | 0.0013 |
| 14 | camera | 0.7124 | 0.0000 | 0.002931 | 0.0010 |
| 15 | clipboard | 0.7124 | 0.0000 | 0.000000 | 0.0000 |
| 16 | sms | 0.7124 | 0.0000 | 0.000000 | 0.0000 |
| 17 | network | 0.7131 | -0.0007 | 0.082060 | 0.0775 |
| 18 | ipc_intents | 0.7136 | -0.0012 | 0.140564 | 0.1198 |
| 19 | crypto | 0.7137 | -0.0013 | 0.097801 | 0.2110 |
| 20 | dynamic_code_loading | 0.7143 | -0.0018 | 0.000000 | 0.0000 |
| 21 | media | 0.7170 | -0.0045 | 0.009376 | 0.0020 |
| 22 | process | 0.7219 | -0.0095 | 0.105468 | 0.0460 |

Deviation-difference profile (mean d malware − benign), sorted by |Δ|:

| node | mean_d_ben | mean_d_mal | Δ | var tertile | abl drop |
|---|---:|---:|---:|---|---:|
| file_io | 0.2299 | 0.1216 | -0.1083 | high | 0.0144 |
| ipc_intents | 0.2303 | 0.1592 | -0.0711 | high | -0.0012 |
| network | 0.0931 | 0.1621 | 0.0690 | high | -0.0007 |
| package_manager | 0.2126 | 0.1439 | -0.0687 | high | 0.0001 |
| storage | 0.1329 | 0.0734 | -0.0595 | mid | 0.0068 |
| native_code | 0.2055 | 0.1487 | -0.0568 | high | 0.0073 |
| webview | 0.1119 | 0.0557 | -0.0562 | high | 0.0061 |
| database | 0.0721 | 0.0169 | -0.0552 | mid | 0.0089 |
| crypto | 0.1463 | 0.0960 | -0.0503 | high | -0.0013 |
| content_access | 0.0269 | 0.0012 | -0.0257 | mid | 0.0001 |
| media | 0.0085 | 0.0335 | 0.0250 | mid | -0.0045 |
| device_info | 0.0593 | 0.0382 | -0.0211 | mid | 0.0018 |
| process | 0.1196 | 0.1068 | -0.0128 | high | -0.0095 |
| location | 0.0133 | 0.0032 | -0.0101 | mid | 0.0063 |
| notifications | 0.0173 | 0.0085 | -0.0087 | mid | 0.0025 |
| accounts | 0.0048 | 0.0003 | -0.0045 | low | 0.0057 |
| dynamic_code_loading | 0.0000 | 0.0014 | 0.0014 | low | -0.0018 |
| telephony | 0.0012 | 0.0000 | -0.0012 | low | 0.0015 |
| audio | 0.0013 | 0.0003 | -0.0010 | low | 0.0055 |
| camera | 0.0000 | 0.0000 | 0.0000 | low | 0.0000 |
| clipboard | 0.0000 | 0.0000 | 0.0000 | low | 0.0000 |
| sms | 0.0000 | 0.0000 | 0.0000 | low | 0.0000 |

Artifacts: `abrg/output/androct_2017/selfref_e2/ablation.csv`, `abrg/output/androct_2017/selfref_e2/deviation_difference_profile.csv`

## Predictions recorded (not run)

- E0 |PREFIX−SCATTERED|=0.0055 ⇒ exchangeable windows; recency-weighted R_i predicted no-op — not run.
- Chapter A Run5+LedoitWolf whitened X before the encoder (−0.078 floor). E2 Mahalanobis is residual-space scoring on d — different object.

## Stop rule

**Nothing clears 0.7025 after size-matching. E0's null was not a geometry artifact — variance-aware readouts do not recover signal.**

---

Generated 2026-08-21T16:20:07.874838+00:00. Summary: `abrg/output/androct_2017/selfref_e2/summary.json`.
