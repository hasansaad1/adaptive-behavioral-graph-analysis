# W-selection measurement (pre-E0 Phase 1)

Measurement only. No graph building, no model, no AUC.

## Spine — AndroCT split assert

- Digest prefix: `6129eb13d6a4` (full `6129eb13d6a46457cd60627372b7b5479df0aa1f4efc9bbb70adc17826c64000`)

- Counts: train-benign=562 / test-benign=141 / test-malware=1700

- Eligible apps: 2403 (703 benign / 1700 malware)

- Artifact: `abrg/output/androct_2017/run2/corpus_cache/meta.json` + `apps.jsonl`

- Mapped sequences: `abrg/output/androct_2017/apigraph/cache/sequences/*.json` → HOOK-first mapping matching `categorize_soot_callee`. **2403/2403** exact n_mapped match vs AppRec (sum=4721782). No separate mapped-category cache; this derivation is verified.

## Part A — AndroCT 2017

### A1. n_mapped distribution per class

| class | n | min | p10 | p25 | median | p75 | p90 | max |

|---|---:|---:|---:|---:|---:|---:|---:|---:|

| benign | 703 | 1 | 12 | 36.5 | 167 | 898 | 2864 | 140951 |
| malware | 1700 | 10 | 173 | 318 | 819.5 | 1802.8 | 4273.7 | 454481 |

Apps with n_mapped below threshold:

| threshold | benign | malware |

|---:|---:|---:|

| 60 | 230 | 53 |
| 100 | 282 | 73 |
| 120 | 301 | 88 |
| 150 | 338 | 122 |
| 200 | 368 | 217 |
| 250 | 389 | 309 |
| 300 | 407 | 383 |
| 400 | 441 | 556 |

Source: `abrg/output/androct_2017/run2/corpus_cache/apps.jsonl` (verified against sequences).

### A2. Zero-edge estimate vs W

Contiguous disjoint W-windows; trailing remainder dropped. Zero-edge proxy = mono-category window.

| W | class | n_windows | zero_edge_count | zero_edge_fraction | exactly_2_cats_fraction |

|---:|---|---:|---:|---:|---:|

| 10 | benign | 146893 | 116845 | 0.7954 | 0.0706 |
| 10 | malware | 324231 | 174435 | 0.5380 | 0.1485 |
| 15 | benign | 97804 | 75594 | 0.7729 | 0.0608 |
| 15 | malware | 215860 | 103954 | 0.4816 | 0.1048 |
| 20 | benign | 73280 | 55483 | 0.7571 | 0.0548 |
| 20 | malware | 161669 | 73489 | 0.4546 | 0.0820 |
| 25 | benign | 58546 | 43685 | 0.7462 | 0.0492 |
| 25 | malware | 129176 | 55708 | 0.4313 | 0.0671 |
| 30 | benign | 48732 | 35935 | 0.7374 | 0.0458 |
| 30 | malware | 107508 | 44069 | 0.4099 | 0.0621 |
| 40 | benign | 36476 | 26308 | 0.7212 | 0.0432 |
| 40 | malware | 80408 | 30177 | 0.3753 | 0.0526 |

### A3. Attrition vs W

Rule C: `n_mapped >= 10W`. Rule CAPPED: `n_mapped >= 6W`.

#### Rule C

| W | threshold | benign elig | benign dropped | benign drop frac | malware elig | malware dropped | malware drop frac | **surviving test-benign** |

|---:|---:|---:|---:|---:|---:|---:|---:|---:|

| 10 | 100 | 421 | 282 | 0.4011 | 1627 | 73 | 0.0429 | **82**/141 |
| 15 | 150 | 365 | 338 | 0.4808 | 1578 | 122 | 0.0718 | **74**/141 |
| 20 | 200 | 335 | 368 | 0.5235 | 1483 | 217 | 0.1276 | **66**/141 |
| 25 | 250 | 314 | 389 | 0.5533 | 1391 | 309 | 0.1818 | **66**/141 |
| 30 | 300 | 296 | 407 | 0.5789 | 1317 | 383 | 0.2253 | **61**/141 |
| 40 | 400 | 262 | 441 | 0.6273 | 1144 | 556 | 0.3271 | **57**/141 |

#### Rule CAPPED

| W | threshold | benign elig | benign dropped | benign drop frac | malware elig | malware dropped | malware drop frac | **surviving test-benign** |

|---:|---:|---:|---:|---:|---:|---:|---:|---:|

| 10 | 60 | 473 | 230 | 0.3272 | 1647 | 53 | 0.0312 | **99**/141 |
| 15 | 90 | 430 | 273 | 0.3883 | 1637 | 63 | 0.0371 | **85**/141 |
| 20 | 120 | 402 | 301 | 0.4282 | 1612 | 88 | 0.0518 | **79**/141 |
| 25 | 150 | 365 | 338 | 0.4808 | 1578 | 122 | 0.0718 | **74**/141 |
| 30 | 180 | 344 | 359 | 0.5107 | 1521 | 179 | 0.1053 | **66**/141 |
| 40 | 240 | 318 | 385 | 0.5477 | 1406 | 294 | 0.1729 | **66**/141 |

### A4. Window count vs W (eligible apps only)

#### Rule C

Windows/app = `floor(n_mapped/W)` among `n_mapped >= 10W`.

| W | benign med | benign IQR | malware med | malware IQR | benign:malware med ratio | hit N_max benign | hit N_max malware |

|---:|---:|---:|---:|---:|---:|---:|---:|

| 10 | 67 | 158 | 88 | 151.5 | 0.761 | — | — |
| 15 | 55 | 122 | 62 | 102.8 | 0.887 | — | — |
| 20 | 48 | 105 | 50 | 78 | 0.960 | — | — |
| 25 | 44 | 85 | 44 | 62 | 1 | — | — |
| 30 | 40.5 | 71 | 40 | 52 | 1.012 | — | — |
| 40 | 35 | 55.8 | 34 | 43 | 1.029 | — | — |

#### Rule CAPPED

Windows/app = `min(10, floor(n_mapped/W))`.

| W | benign med | benign IQR | malware med | malware IQR | benign:malware med ratio | hit N_max benign | hit N_max malware |

|---:|---:|---:|---:|---:|---:|---:|---:|

| 10 | 10 | 0 | 10 | 0 | 1 | 421 | 1627 |
| 15 | 10 | 0 | 10 | 0 | 1 | 365 | 1578 |
| 20 | 10 | 0 | 10 | 0 | 1 | 335 | 1483 |
| 25 | 10 | 0 | 10 | 0 | 1 | 314 | 1391 |
| 30 | 10 | 0 | 10 | 0 | 1 | 296 | 1317 |
| 40 | 10 | 0 | 10 | 0 | 1 | 262 | 1144 |

### A5. Category diversity per window vs W

| W | class | n_windows | distinct cats median | IQR |

|---:|---|---:|---:|---:|

| 10 | benign | 146893 | 1 | 0 |
| 10 | malware | 324231 | 1 | 2 |
| 15 | benign | 97804 | 1 | 0 |
| 15 | malware | 215860 | 2 | 2 |
| 20 | benign | 73280 | 1 | 0 |
| 20 | malware | 161669 | 2 | 3 |
| 25 | benign | 58546 | 1 | 1 |
| 25 | malware | 129176 | 3 | 4 |
| 30 | benign | 48732 | 1 | 1 |
| 30 | malware | 107508 | 3 | 4 |
| 40 | benign | 36476 | 1 | 1 |
| 40 | malware | 80408 | 3 | 4 |

## Part B — v2_extended

### B0. Inventory

- Total apps (reference-tier pass): **59**

- Total sessions (pass): **342**; failed-reference: 46

- Sessions per app: median=7 IQR=5 (min=1 max=9)

- Graph-eligible apps: **40**

- Usable sessions: **342**

- Mapped-category sequence: **yes, per session** — `events.jsonl` `type==event` with `category ∈ GRAPH_CATEGORY_UNIVERSE`.

- Vocabulary: Frida hooks (not DroidFax/Soot). Same 22-label keep-set. Non-universe in pass set: `{'lifecycle': 1652, 'reflection': 827700, 'navigation': 226}`.

- n_mapped events vs index mismatches: **0**.

- Artifacts: `datasets/v2_extended/sessions_index.jsonl`, `datasets/v2_extended/sessions/**/events.jsonl`

### B1. n_mapped per session (and per-app sum)

| unit | n | min | p10 | p25 | median | p75 | p90 | max |

|---|---:|---:|---:|---:|---:|---:|---:|---:|

| per session | 342 | 1 | 8 | 26.8 | 84 | 254 | 697.8 | 1941 |
| per app (summed) | 59 | 5 | 11.4 | 37.5 | 372 | 1335 | 4308.8 | 13497 |

### B2. Zero-edge estimate vs W (per session)

| W | n_windows | zero_edge_count | zero_edge_fraction | exactly_2_cats_fraction | distinct cats med | IQR |

|---:|---:|---:|---:|---:|---:|---:|

| 10 | 8120 | 3838 | 0.4727 | 0.3733 | 2 | 1 |
| 15 | 5355 | 2166 | 0.4045 | 0.3754 | 2 | 1 |
| 20 | 3980 | 1431 | 0.3595 | 0.3686 | 2 | 2 |
| 25 | 3149 | 1012 | 0.3214 | 0.3754 | 2 | 2 |
| 30 | 2597 | 744 | 0.2865 | 0.3612 | 2 | 2 |
| 40 | 1920 | 492 | 0.2562 | 0.3385 | 2 | 2 |

### B3. Attrition vs W

| W | sess ≥10W | sess ≥6W | frac drop 10W | frac drop 6W | apps ≥1 (10W) | apps ≥1 (6W) | apps ≥3 (10W) | apps ≥3 (6W) |

|---:|---:|---:|---:|---:|---:|---:|---:|---:|

| 10 | 165/342 | 189/342 | 0.5175 | 0.4474 | 26/59 | 29/59 | 24/59 | 27/59 |
| 15 | 139/342 | 169/342 | 0.5936 | 0.5058 | 21/59 | 27/59 | 19/59 | 24/59 |
| 20 | 102/342 | 151/342 | 0.7018 | 0.5585 | 16/59 | 23/59 | 13/59 | 21/59 |
| 25 | 88/342 | 139/342 | 0.7427 | 0.5936 | 13/59 | 21/59 | 12/59 | 19/59 |
| 30 | 70/342 | 120/342 | 0.7953 | 0.6491 | 11/59 | 19/59 | 10/59 | 16/59 |
| 40 | 62/342 | 91/342 | 0.8187 | 0.7339 | 9/59 | 14/59 | 9/59 | 12/59 |

### B4. Windows per session vs W

| W | med (all) | IQR | med (≥1 win) | IQR | total windows |

|---:|---:|---:|---:|---:|---:|

| 10 | 8 | 23 | 11 | 22 | 8120 |
| 15 | 5 | 15 | 10 | 20 | 5355 |
| 20 | 4 | 11 | 8 | 16.5 | 3980 |
| 25 | 3 | 9 | 6 | 13 | 3149 |
| 30 | 2 | 8 | 5 | 10 | 2597 |
| 40 | 2 | 6 | 4 | 9 | 1920 |

### B5. Sanity check — known v2 sparsity

- Cited “579 edge instances / ~728 snapshots”: **not found** in persisted artifacts. Closest: `norm_ab_v2` total_snapshots=731.

- v2_extended whole-session edges (`sessions_index.jsonl`, n=342): median=2 IQR=5 sum=1384 frac_zero=0.1579 frac_≤1=0.3012.

- `abrg/output/norm_ab_v2/comparison.json` (original v2, 60s windows): snapshots=731 trainable=634 gae_eligible=565; edges trainable med=2.0 mean=4.56; gae_eligible med=3 mean=5.11.

- `abrg/output/v2_chapter_b/SUMMARY.md`: per-session edges med=5 IQR=[2,10] frac≤2=0.462 n=342.

B1 median n_mapped/session=84 is consistent with sparse whole-session graphs (med edges=2). B2 shows mono-category rates stay high on the grid (≥ 0.2562). **v2 does not need W≥100 to form whole-session edges, but fixed-W windowing on this grid does not clear the 0.15 mono-category floor.** Windowed self-reference on v2 is not viable on {10…40} under the stated floor.

## Part C — Cross-corpus comparison

### C1. Side-by-side

#### n_mapped

| corpus / unit | n | min | p25 | median | p75 | p90 | max |

|---|---:|---:|---:|---:|---:|---:|---:|

| AndroCT benign (per app) | 703 | 1 | 36.5 | 167 | 898 | 2864 | 140951 |
| AndroCT malware (per app) | 1700 | 10 | 318 | 819.5 | 1802.8 | 4273.7 | 454481 |
| v2_extended (per session) | 342 | 1 | 26.8 | 84 | 254 | 697.8 | 1941 |

#### Zero-edge fraction vs W

| W | AndroCT benign | AndroCT malware | v2 session |

|---:|---:|---:|---:|

| 10 | 0.7954 | 0.5380 | 0.4727 |
| 15 | 0.7729 | 0.4816 | 0.4045 |
| 20 | 0.7571 | 0.4546 | 0.3595 |
| 25 | 0.7462 | 0.4313 | 0.3214 |
| 30 | 0.7374 | 0.4099 | 0.2865 |
| 40 | 0.7212 | 0.3753 | 0.2562 |

#### Attrition

| W | AndroCT test-benign @C | @CAPPED | v2 sess @10W | @6W |

|---:|---:|---:|---:|---:|

| 10 | 82/141 | 99/141 | 165/342 | 189/342 |
| 15 | 74/141 | 85/141 | 139/342 | 169/342 |
| 20 | 66/141 | 79/141 | 102/342 | 151/342 |
| 25 | 66/141 | 74/141 | 88/342 | 139/342 |
| 30 | 61/141 | 66/141 | 70/342 | 120/342 |
| 40 | 57/141 | 66/141 | 62/342 | 91/342 |

### C2. Case

- AndroCT choice: W=10 branch=`CAPPED_max_testbenign` benign_zero_edge=0.7954 surviving_test_benign=99; **no W reaches test-benign≥100; chose max survivors under CAPPED; zero-edge stated limitation**

- v2 choice: W=10 branch=`CAPPED_sessions_only` zero_edge=0.4727 sessions_eligible=189 apps_ge1=29; **zero-edge floor not met on v2 at any grid W**

- Formal OVERLAP (zero-edge < 0.15 ∧ ceiling on both): **none**

- **Case: COINCIDENT_FALLBACK** (not formal OVERLAP / CLOSE / DISJOINT)

- Both corpora independently select **W=10** under the final fallback. Formal decision-rule OVERLAP never fires because the zero-edge floor is unmet everywhere on the grid. Spec CLOSE/DISJOINT do not apply when chosen values are identical. Treat as a shared practical W with stated limitations; comparability of later `d = |X − R_i|` does not require the floor to have cleared.

### C3. Recommendation

- **Recommended W = 10**
- Rule branch that produced it (AndroCT): `CAPPED_max_testbenign` (third branch of the decision rule; C and CAPPED both fail the joint floor+ceiling test; no W hits test-benign≥100, so max-survivor CAPPED pick)
- Surviving test-benign at W=10: **82/141 under C**; **99/141 under CAPPED** (one short of the ≥100 gate)
- AndroCT benign zero-edge at W=10: **0.7954** (floor < 0.15 **not met** on the entire grid: W=10→0.7954 … W=40→0.7212)
- v2 session zero-edge at W=10: **0.4727** (grid min at W=40 is still 0.2562)

### Numbers that argue against the recommendation

- **No W on the grid clears zero-edge < 0.15** on either corpus — the floor branch of the decision rule never fires.
- **No W reaches surviving test-benign ≥ 100** under C or CAPPED (best: W=10 CAPPED → 99/141). The ceiling gate alone forces a compromised pick.
- AndroCT benign exactly-2-cats at W=10: 0.0706 (adjacency still thin even when not mono-category).
- Rule C benign drop at W=10: 0.4011.
- v2 apps with ≥3 eligible sessions at W=10: 10W→24/59; 6W→27/59 — weak for cross-session work.
- Larger W on AndroCT *lowers* mono-category only modestly (0.7954→0.7212) while destroying test-benign (99→66 under CAPPED). The floor is not reachable inside the grid without abandoning the ceiling.
- On v2, even W=40 leaves zero-edge_frac=0.2562; **fixed-W windowing on {10…40} is not viable under the stated floor** without leaving the grid or changing the edge model.

---

Decision case **COINCIDENT_FALLBACK**. Sidecar JSON: `results/W_selection.json`.

