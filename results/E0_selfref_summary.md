# E0 — Self-reference windowed detection

No trained neural model. Arm B N=8 tensors / identical builder path. Phase 4 is a **diagnostic capacity ceiling**, not a proposed detector.

## Spine

- Digest: `6129eb13d6a4…` (asserted `6129eb13d6a4`)
- Split: 562 / 141 / 1700
- Construction: N=8 fixed count, Arm B Part 3 always-8-slots
- Limitation: app-balanced fixed-W not evaluated (PROXY_VALID rejected mass-weighted fixed-W)

## Phase 1 — Load and verify

- Regenerated: Arm B Part 3 did not persist snap_cache; built with partition_mapped_indices N=8, update_graph_sequence k=5, w_cum, shares-not-counts, static from run2 cache, categories from apigraph sequences with categorize_soot_callee-equivalent map (2403/2403 exact).
- Apps: 703 benign / 1700 malware; 8 windows/app; x∈ℝ^{22×10}; A∈ℝ^{22×22}

| class | median mapped/win | IQR | Phase0 ref median | zero-edge frac | Phase0 ref |
|---|---:|---:|---:|---:|---:|
| benign | 21.0 | 107.0 | 21.0 | 0.2939 | 0.2939 |
| malware | 102.0 | 186.0 | 102.0 | 0.1964 | 0.1964 |

- Apps with <8 mapped-nonempty windows: **38 benign**, 0 malware.
- Decision: RETAINED — empty-range windows carry static features and zero edges (Arm B Part 3 always-8-slots policy). Included in every downstream table.
- Full list: `abrg/output/androct_2017/selfref/windows/lt8_nonempty_apps.csv`

| sha256 | n_mapped | n_nonempty |
|---|---:|---:|
| `0211BCE097636BDE4197A82E9F492C4321F9C7B35851329E2104471B4746CEC3` | 3 | 3 |
| `0B1983125AD79211FA4434B89CA462964E763B481C8B1CD4019BC9355811E68A` | 1 | 1 |
| `10790B305322B8795BF0FDC5C822DE8E9500477DEFE40B82BDBD0751AE2915BC` | 3 | 3 |
| `16C5B7F88B10FFAF101B918E394D7E9F9BB9125672CE74A4FD9F5D664B928B32` | 3 | 3 |
| `196E8735548E2E816370A541002981DAAECFC4A6D193A2D1A0E64B0F81277ABA` | 5 | 5 |
| `1F7F16C5380CBBEFE680CCE9D48632B050733A80FE11916DDB0AD926D15AD3C6` | 2 | 2 |
| `261843960025D9E11D480AF077FDB43768BABCB69E75B13C7FEECDDEBEB9F8AD` | 5 | 5 |
| `50EE797DC7D000280682F194B9271C26F572C1D0113FDC06470007C94AAA0C70` | 5 | 5 |
| `52BA12CDBEC155C1F5611A8443EE5C79840903FE2C088D7BDDEE52D1BC943331` | 4 | 4 |
| `54691D7DF0175471687B96CC135B8A1ABC86429CD08D85BA4FA10715AA8056D6` | 5 | 5 |
| `5AD260CBEA2DD63EF6BEC749FC6DFA79827BA2441932534E0FC3026272B3BE77` | 3 | 3 |
| `646AC5875D033F72955D4AF3910FDBF286AB7BD9FC538D3DF19943B0F5161C6F` | 1 | 1 |
| `6D9C23B98C26EB7B7BD0D958F77960C49FFB26487D5A9D8913CA2F86980C5D53` | 5 | 5 |
| `76538DFF4311DEE53E843C5597EBA6AAB1E8AEEA8BA041DAEC28B60BECF7B960` | 2 | 2 |
| `81E1D53AA4161D88213533C317EABD35059B6A8C077D8520835DF7198323D9FF` | 7 | 7 |
| `8FA2E4D376B3BEE0300DDAEB7A7B11F8910A35E7A945A3BDFF7A5C7BA71A7CE9` | 3 | 3 |
| `A03ECB6C5710F34F002D6B3FC380DC897295C6ED1CEBE77CF197999CB67C7868` | 2 | 2 |
| `A658722EB44B34F547EE65A362B07D4F9AC6C59EB8E55AECF82C22BE14828854` | 5 | 5 |
| `A908022CF8EC4081B15D2CC3C25F7691C77985EDAA81D7D6485480E134812681` | 1 | 1 |
| `ADFFC1659EBBB05A44CCBC1AE19093B9348A458C0A7F22DC65AD1D4BEC49CCF5` | 5 | 5 |
| `B43D18D0102560D423D916B23C839C2C26DD4BAB39E46747133C1F30EB946BA6` | 4 | 4 |
| `B4C8DDE2CB4AD0331482AE57432A9084AC125D7A270E174412C7FFC5D14603C4` | 2 | 2 |
| `B8B459120816B86FC1252DDA38396A369D9338A5B6B3EE34592FB65B5F688BD5` | 5 | 5 |
| `BD47D8A431A30EA5D491A6D2799EF45E32A60600880DC82EC06849BF48C82A2E` | 6 | 6 |
| `C06F70C3D8DCECF88DA75655808165817A35EC8BDAFA1CE3DAC093EC357C13E1` | 4 | 4 |
| `D2C3449B81AE3A63C90548B0EF61FA441C0A28D56BCF26D9037A301F63B7073E` | 6 | 6 |
| `E16ADBDCD46C0772E6012AB4F27AEECE877A3EC8CEA9247633ADBF8B85DFF1A3` | 3 | 3 |
| `E8323A43A9E02AC8A41230A011AD861E90EDCD497B7FEFE41A03DDBF62CF4660` | 5 | 5 |
| `F2EF82C9F380DB236AB68474FE2AA40F7BD83E5A3235355226CF9AC115AD5125` | 6 | 6 |
| `F3947F24D07573A400274678FFA38F51C2D0A76BC6AB70DE726FD8E95267D2EF` | 4 | 4 |
| `F3CB1C786A966B0DF8A65565A675A09E22EC783D061A66067350AD7AEBA6A141` | 3 | 3 |
| `F8912E463636FB99DB8551E0F03E0B48F9705AFBFE066FDC642311AB31FB02D9` | 4 | 4 |
| `FF92AB467B0705617D496ED5681804B0546F849F67538A35A30EFCF951FEC5B5` | 3 | 3 |
| `E3A82355EFA27F1660C6FFD1AF993CC147564AAE84490D1F7AA4238843F14613` | 7 | 7 |
| `913EE6773DF0E1A330A068A8F5550478139CAD024D41AA5C6F91FE7261B4DA52` | 7 | 7 |
| `179EF5F85367DEE0B1008DD6E3C956AF19D8A3D4F3ACEBF1987CDB9D199D9F35` | 1 | 1 |
| `A1472CD86765887039C402762472F391B6DB1837E934FA38CF19C24DEFA7806E` | 4 | 4 |
| `5DBCB2F910127AF6252AB4522F2B2498D85D896008D38026B796A8BB0833BA44` | 2 | 2 |

- Artifacts: `abrg/output/androct_2017/selfref/windows/armb_n8_windows.pt`, `abrg/output/androct_2017/selfref/windows/manifest.csv`

## Phase 3 — Raw 24-row matrix

FRACTION granularity with 2 test windows: **{0, 0.5, 1}** only.
Floor = mapped_event_count **0.7025**. μ_benign fit on train-benign test windows only.

| split | score | verdict | space | auc_floor | direction | CI95 floor | clears_floor | ρ_benign | ρ_malware |
|---|---|---|---|---:|---|---|---|---:|---:|
| PREFIX | SCALAR | MEAN | node | 0.6966 | benign_higher_score | [0.6583, 0.7341] | False | -0.330 | -0.199 |
| PREFIX | SCALAR | MAX | node | 0.6997 | benign_higher_score | [0.6614, 0.7378] | False | -0.301 | -0.186 |
| PREFIX | SCALAR | FRACTION | node | 0.5253 | benign_higher_score | [0.5037, 0.5479] | False | -0.175 | 0.024 |
| PREFIX | SCALAR | MEAN | adj | 0.5673 | benign_higher_score | [0.5148, 0.6171] | False | 0.382 | 0.245 |
| PREFIX | SCALAR | MAX | adj | 0.5650 | benign_higher_score | [0.5119, 0.6162] | False | 0.392 | 0.266 |
| PREFIX | SCALAR | FRACTION | adj | 0.5065 | benign_higher_score | [0.5005, 0.5292] | False | 0.168 | 0.060 |
| PREFIX | CENTROID | MEAN | node | 0.5880 | benign_higher_score | [0.5320, 0.6443] | False | -0.280 | 0.060 |
| PREFIX | CENTROID | MAX | node | 0.5936 | benign_higher_score | [0.5363, 0.6497] | False | -0.255 | 0.070 |
| PREFIX | CENTROID | FRACTION | node | 0.5194 | benign_higher_score | [0.5020, 0.5401] | False | -0.183 | 0.016 |
| PREFIX | CENTROID | MEAN | adj | 0.6063 | benign_higher_score | [0.5610, 0.6532] | False | 0.115 | -0.297 |
| PREFIX | CENTROID | MAX | adj | 0.6036 | benign_higher_score | [0.5556, 0.6515] | False | 0.161 | -0.241 |
| PREFIX | CENTROID | FRACTION | adj | 0.5085 | benign_higher_score | [0.5004, 0.5315] | False | 0.160 | 0.052 |
| SCATTERED | SCALAR | MEAN | node | 0.6960 | benign_higher_score | [0.6561, 0.7357] | False | -0.354 | -0.206 |
| SCATTERED | SCALAR | MAX | node | 0.6985 | benign_higher_score | [0.6585, 0.7387] | False | -0.344 | -0.202 |
| SCATTERED | SCALAR | FRACTION | node | 0.5257 | benign_higher_score | [0.5035, 0.5515] | False | -0.208 | -0.059 |
| SCATTERED | SCALAR | MEAN | adj | 0.5688 | benign_higher_score | [0.5163, 0.6210] | False | 0.388 | 0.176 |
| SCATTERED | SCALAR | MAX | adj | 0.5632 | benign_higher_score | [0.5113, 0.6150] | False | 0.400 | 0.168 |
| SCATTERED | SCALAR | FRACTION | adj | 0.5061 | malware_higher_score | [0.5005, 0.5263] | False | 0.192 | -0.019 |
| SCATTERED | CENTROID | MEAN | node | 0.5931 | benign_higher_score | [0.5337, 0.6499] | False | -0.297 | -0.041 |
| SCATTERED | CENTROID | MAX | node | 0.5945 | benign_higher_score | [0.5351, 0.6536] | False | -0.284 | -0.044 |
| SCATTERED | CENTROID | FRACTION | node | 0.5353 | benign_higher_score | [0.5117, 0.5608] | False | -0.254 | -0.041 |
| SCATTERED | CENTROID | MEAN | adj | 0.6211 | benign_higher_score | [0.5784, 0.6630] | False | 0.167 | -0.352 |
| SCATTERED | CENTROID | MAX | adj | 0.6203 | benign_higher_score | [0.5763, 0.6623] | False | 0.208 | -0.303 |
| SCATTERED | CENTROID | FRACTION | adj | 0.5000 | malware_higher_score | [0.5003, 0.5250] | False | 0.206 | -0.022 |

Artifact: `abrg/output/androct_2017/selfref/matrix_24.csv` (tag=raw)

## Phase 5.1 — Size-matched matrix (PRIMARY control)

Overlapping central mass of class n_mapped distributions on the test set: [max(p10_b,p10_m), min(p90_b,p90_m)] = [173.0, 3567.0] (benign p10/p90=15.0/3567.0; malware p10/p90=173.0/4273.7). Kept n_benign=53, n_malware=1313.

| split | score | verdict | space | auc_floor | direction | CI95 floor | clears_floor | ρ_benign | ρ_malware |
|---|---|---|---|---:|---|---|---|---:|---:|
| PREFIX | SCALAR | MEAN | node | 0.6137 | benign_higher_score | [0.5477, 0.6750] | False | -0.230 | 0.007 |
| PREFIX | SCALAR | MAX | node | 0.6229 | benign_higher_score | [0.5570, 0.6851] | False | -0.213 | 0.021 |
| PREFIX | SCALAR | FRACTION | node | 0.5046 | benign_higher_score | [0.5012, 0.5348] | False | -0.142 | 0.108 |
| PREFIX | SCALAR | MEAN | adj | 0.6074 | benign_higher_score | [0.5290, 0.6810] | False | -0.035 | 0.360 |
| PREFIX | SCALAR | MAX | adj | 0.6161 | benign_higher_score | [0.5387, 0.6917] | False | -0.012 | 0.375 |
| PREFIX | SCALAR | FRACTION | adj | 0.5207 | benign_higher_score | [0.5008, 0.5676] | False | -0.102 | 0.077 |
| PREFIX | CENTROID | MEAN | node | 0.5098 | benign_higher_score | [0.5018, 0.6100] | False | -0.208 | 0.030 |
| PREFIX | CENTROID | MAX | node | 0.5220 | benign_higher_score | [0.5020, 0.6162] | False | -0.210 | 0.070 |
| PREFIX | CENTROID | FRACTION | node | 0.5034 | malware_higher_score | [0.5004, 0.5189] | False | -0.199 | 0.098 |
| PREFIX | CENTROID | MEAN | adj | 0.5914 | benign_higher_score | [0.5144, 0.6704] | False | -0.021 | -0.166 |
| PREFIX | CENTROID | MAX | adj | 0.6058 | benign_higher_score | [0.5267, 0.6848] | False | 0.016 | -0.103 |
| PREFIX | CENTROID | FRACTION | adj | 0.5197 | benign_higher_score | [0.5007, 0.5663] | False | -0.102 | 0.078 |
| SCATTERED | SCALAR | MEAN | node | 0.6099 | benign_higher_score | [0.5469, 0.6701] | False | -0.208 | -0.021 |
| SCATTERED | SCALAR | MAX | node | 0.6112 | benign_higher_score | [0.5486, 0.6718] | False | -0.220 | -0.018 |
| SCATTERED | SCALAR | FRACTION | node | 0.5115 | malware_higher_score | [0.5006, 0.5251] | False | -0.222 | 0.036 |
| SCATTERED | SCALAR | MEAN | adj | 0.6191 | benign_higher_score | [0.5424, 0.6920] | False | 0.007 | 0.271 |
| SCATTERED | SCALAR | MAX | adj | 0.6186 | benign_higher_score | [0.5429, 0.6890] | False | -0.045 | 0.259 |
| SCATTERED | SCALAR | FRACTION | adj | 0.5005 | benign_higher_score | [0.5006, 0.5477] | False | -0.167 | -0.000 |
| SCATTERED | CENTROID | MEAN | node | 0.5016 | benign_higher_score | [0.5014, 0.6051] | False | -0.120 | -0.048 |
| SCATTERED | CENTROID | MAX | node | 0.5004 | benign_higher_score | [0.5016, 0.6055] | False | -0.109 | -0.031 |
| SCATTERED | CENTROID | FRACTION | node | 0.5054 | malware_higher_score | [0.5009, 0.5198] | False | -0.222 | 0.039 |
| SCATTERED | CENTROID | MEAN | adj | 0.6073 | benign_higher_score | [0.5291, 0.6834] | False | 0.004 | -0.228 |
| SCATTERED | CENTROID | MAX | adj | 0.6235 | benign_higher_score | [0.5485, 0.6956] | False | -0.046 | -0.185 |
| SCATTERED | CENTROID | FRACTION | adj | 0.5136 | benign_higher_score | [0.5009, 0.5597] | False | -0.138 | -0.006 |

Any cell clears floor? raw=False, size_matched=False

## Phase 4 — Supervised ceiling (DIAGNOSTIC ONLY)

HistGradientBoosting on concatenated test-window d vectors (44-dim), stratified both-class split seed=42. **Not a proposed detector.**

| split_mode | space | auc_floor | direction | CI95 floor |
|---|---|---:|---|---|
| PREFIX | node | 0.9340 | malware_higher_score | [0.9117, 0.9544] |
| PREFIX | adj | 0.9187 | malware_higher_score | [0.8910, 0.9422] |
| SCATTERED | node | 0.9274 | malware_higher_score | [0.9038, 0.9499] |
| SCATTERED | adj | 0.9154 | malware_higher_score | [0.8866, 0.9398] |

Ceiling range: [0.9154, 0.9340]. Artifact: `abrg/output/androct_2017/selfref/phase4_ceiling.csv`

## Phase 5 — Controls

### 1. Size-matched — see matrix above (primary).

### 2. Floor
Every row flagged `clears_floor` vs 0.7025 (see matrices).

### 3. Volume coupling
Spearman ρ(app score, n_mapped) per class — columns in matrices above.

### 4. Within-trace density trend

| snap_idx | benign mean mapped | malware mean mapped |
|---:|---:|---:|
| 0 | 262.17 | 239.39 |
| 1 | 262.06 | 239.28 |
| 2 | 261.92 | 239.16 |
| 3 | 261.79 | 239.02 |
| 4 | 261.63 | 238.90 |
| 5 | 261.51 | 238.77 |
| 6 | 261.39 | 238.65 |
| 7 | 261.30 | 238.52 |

Artifact: `abrg/output/androct_2017/selfref/density_trend.json`

### 5. Shuffled labels

| split | score | verdict | space | auc_floor |
|---|---|---|---|---:|
| PREFIX | SCALAR | MEAN | node | 0.5017 |
| PREFIX | SCALAR | MAX | node | 0.5044 |
| PREFIX | SCALAR | FRACTION | node | 0.5090 |
| PREFIX | SCALAR | MEAN | adj | 0.5234 |
| PREFIX | SCALAR | MAX | adj | 0.5142 |
| PREFIX | SCALAR | FRACTION | adj | 0.5045 |
| PREFIX | CENTROID | MEAN | node | 0.5316 |
| PREFIX | CENTROID | MAX | node | 0.5181 |
| PREFIX | CENTROID | FRACTION | node | 0.5074 |
| PREFIX | CENTROID | MEAN | adj | 0.5212 |
| PREFIX | CENTROID | MAX | adj | 0.5118 |
| PREFIX | CENTROID | FRACTION | adj | 0.5062 |
| SCATTERED | SCALAR | MEAN | node | 0.5353 |
| SCATTERED | SCALAR | MAX | node | 0.5221 |
| SCATTERED | SCALAR | FRACTION | node | 0.5177 |
| SCATTERED | SCALAR | MEAN | adj | 0.5263 |
| SCATTERED | SCALAR | MAX | adj | 0.5123 |
| SCATTERED | SCALAR | FRACTION | adj | 0.5012 |
| SCATTERED | CENTROID | MEAN | node | 0.5037 |
| SCATTERED | CENTROID | MAX | node | 0.5327 |
| SCATTERED | CENTROID | FRACTION | node | 0.5070 |
| SCATTERED | CENTROID | MEAN | adj | 0.5307 |
| SCATTERED | CENTROID | MAX | adj | 0.5147 |
| SCATTERED | CENTROID | FRACTION | adj | 0.5000 |
| PREFIX | HGB_CEILING | DIAGNOSTIC | node | 0.5380 |
| PREFIX | HGB_CEILING | DIAGNOSTIC | adj | 0.5181 |
| SCATTERED | HGB_CEILING | DIAGNOSTIC | node | 0.5189 |
| SCATTERED | HGB_CEILING | DIAGNOSTIC | adj | 0.5495 |

Mean shuffled auc_floor=0.5172 (expect ~0.50). Artifact: `abrg/output/androct_2017/selfref/shuffled_labels.csv`

### 6. PREFIX − SCATTERED delta

| score | verdict | space | auc_floor PREFIX | auc_floor SCATTERED | Δ |
|---|---|---|---:|---:|---:|
| SCALAR | MEAN | node | 0.6966 | 0.6960 | 0.0007 |
| SCALAR | MEAN | adj | 0.5673 | 0.5688 | -0.0015 |
| SCALAR | MAX | node | 0.6997 | 0.6985 | 0.0012 |
| SCALAR | MAX | adj | 0.5650 | 0.5632 | 0.0018 |
| SCALAR | FRACTION | node | 0.5253 | 0.5257 | -0.0004 |
| SCALAR | FRACTION | adj | 0.5065 | 0.5061 | 0.0003 |
| CENTROID | MEAN | node | 0.5880 | 0.5931 | -0.0050 |
| CENTROID | MEAN | adj | 0.6063 | 0.6211 | -0.0148 |
| CENTROID | MAX | node | 0.5936 | 0.5945 | -0.0010 |
| CENTROID | MAX | adj | 0.6036 | 0.6203 | -0.0166 |
| CENTROID | FRACTION | node | 0.5194 | 0.5353 | -0.0159 |
| CENTROID | FRACTION | adj | 0.5085 | 0.5000 | 0.0085 |
| HGB_CEILING | DIAGNOSTIC | node | 0.9340 | 0.9274 | 0.0066 |
| HGB_CEILING | DIAGNOSTIC | adj | 0.9187 | 0.9154 | 0.0033 |

Mean |Δ|=0.0055. Artifact: `abrg/output/androct_2017/selfref/prefix_scattered_delta.csv`

## Tau sweep (FRACTION)

Full curve 50th–99th percentile in `abrg/output/androct_2017/selfref/tau_sweep.csv`. Snapshot at 95th is the FRACTION row in the matrix.

## Gate / stop rule

**PROCEED_E2_STRONG** — Phase 4 ceiling max=0.9340 ≥ 0.85 — d-vector representation carries class signal under full supervision.

One-class matrix (PRIMARY: size-matched): **no cell clears floor 0.7025** (best size-matched ≈0.6235; best raw ≈0.6997, just under floor). Per stop rule: report the null for one-class self-deviation and **move to E2**. Do not sweep N / distance / split ratio / reference rule.

Direction note: raw one-class rows are mostly `benign_higher_score` (benign more self-deviant than malware) — consistent with born-malicious traces absorbing payload into R_i.

PREFIX−SCATTERED mean |Δ|=0.0055 ≈ 0, but ceiling is high → temporal order is not the story; do **not** apply the low-ceiling order-null stop.

Density trend is nearly flat across snap_idx (remainder-to-earliest) → PREFIX is not density-confounded.

---

Generated 2026-08-21T14:56:58.852815+00:00. Summary JSON: `abrg/output/androct_2017/selfref/summary.json`.
