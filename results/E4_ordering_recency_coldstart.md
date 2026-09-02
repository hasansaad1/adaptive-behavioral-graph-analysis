# E4 — Ordering, recency, and cold-start on v2_extended

**v2_extended has no malware. Nothing here is a detection result.**

Sensor note: same 22-node `GRAPH_CATEGORY_UNIVERSE` as AndroCT (E0/E2), but Frida hooks (ContextDroid) ≠ DroidFax logcat — do not treat numbers as interchangeable samples.

Eligible apps: **n=26** (≥8 usable sessions). Session unit; no within-session windowing.

## Phase −1 — Provenance verdict

**E4 builder:** `abrg.chapter_b.graphs_seq.graph_from_events → update_graph_sequence`

Chapter B Run 2 unit-aligned comparison used update_graph_sequence (k-burst=5, w_cum, zero static, whole session). Export index used build_session_graph/update_graph with δ time filter → fewer edges (median 2 vs 5). E4 must match Run 2 for comparability with Chapter B.

| Stage | Pipeline | Median edges |
|---|---|---:|
| Export index (Phase 0) | build_session_graph (update_graph, δ-filtered pairs) → len(edges) | 2.0 |
| Chapter B Run 2 | graph_from_events (update_graph_sequence, k-burst only) → topology iter_edges | 5.0 |
| norm_ab_v2 (60s snaps) | 60s timed snapshots on original v2 (168 sessions), not v2_extended whole-session | GAE mean 5.11 /snap |

**579/728 archaeology:** Not found in any persisted artifact. Closest: norm_ab_v2 total_snapshots=731, gae_eligible_snapshots=565, GAE edge sum=2888.0 (mean 5.11 edges/snap on 60s windows). The thesis B5 bucket label 72831 refers to mapped-event counts in a retention curve, not edge instances.

Artifact: `abrg/output/v2_extended/e4_ordering/provenance.json`

## Phase 1 — Temporal ordering (session granularity)

Split: PREFIX = earliest 6 / latest 2; SCATTERED = random 6 / remaining 2 (seed=42+hash(app)). 9-session apps discard middle index 6 under PREFIX.

**VERDICT: `ORDERING_NEUTRAL`** — PREFIX−SCATTERED median Δ=0.0000 (IQR=0.0278, rel=0.000); rank-biserial r=0.464, p=0.4549. Behaviour is exchangeable at both granularities tested — the adaptive temporal element of ABRG has no empirical support at session scale.

Effect size (report first): rank-biserial **r=0.464**, Cohen d=0.202, median Δ=0.0000 (Wilcoxon p=0.4549).

| split | median \|\|d\|\| | IQR |
|---|---:|---:|
| PREFIX | 0.0485 | 0.4313 |
| SCATTERED | 0.0581 | 0.3704 |
| PREFIX−SCATTERED (per app) | 0.0000 | 0.0278 |

Per-app table: `abrg/output/v2_extended/e4_ordering/phase1_per_app.csv`

### Per-node mean d (PREFIX, node space)

| node | mean d_node | mean d_adj |
|---|---:|---:|
| accounts | 0.0000 | 0.0000 |
| audio | 0.0238 | 0.0195 |
| camera | 0.0000 | 0.0000 |
| clipboard | 0.0000 | 0.0000 |
| content_access | 0.0010 | 0.0022 |
| crypto | 0.1108 | 0.0685 |
| database | 0.0008 | 0.0067 |
| device_info | 0.0000 | 0.0000 |
| dynamic_code_loading | 0.0000 | 0.0000 |
| file_io | 0.0211 | 0.0602 |
| ipc_intents | 0.0060 | 0.0320 |
| location | 0.0066 | 0.0173 |
| media | 0.0000 | 0.0000 |
| native_code | 0.0345 | 0.0389 |
| network | 0.0232 | 0.0748 |
| notifications | 0.0004 | 0.0050 |
| package_manager | 0.0000 | 0.0128 |
| process | 0.0000 | 0.0000 |
| sms | 0.0000 | 0.0000 |
| storage | 0.0395 | 0.0949 |
| telephony | 0.0000 | 0.0000 |
| webview | 0.0079 | 0.0064 |

## Phase 2 — Recency vs cumulative reference

**Prerequisite:** All 26 eligible apps span multiple calendar days — recency weighting has temporal separation to act on. (multi-day 26/26).

**W_REC does not beat W_CUM at any fixed decay — recency channel specified, implemented, and measured as not helping on this corpus.**

Decay half-lives (fixed before run): fast=1h, medium=4.86h (Phase 0 median gap), slow=24h.

| decay | half-life | median \|\|d\|\| W_CUM | median W_REC | Δ(W_REC−W_CUM) | r | p | W_REC wins |
|---|---:|---:|---:|---:|---:|---:|---:|
| fast | 1.00h | 0.0485 | 0.0412 | 0.0000 | 0.316 | 0.3914 | 12/26 |
| medium | 4.86h | 0.0485 | 0.0503 | 0.0000 | 0.419 | 0.1036 | 7/26 |
| slow | 24.00h | 0.0485 | 0.0478 | 0.0000 | 0.339 | 0.2109 | 9/26 |

Artifact: `abrg/output/v2_extended/e4_ordering/phase2_recency.json`

## Phase 4 — Cold start / convergence

**Self-deviation median: k=1 0.0081 (minimum) → k=7 0.0430; cross-app at k=7 ≈3.1. Held-out deviation does not decrease with reference size — has not converged within 8 sessions; the cold-start answer is non-convergence (minimum at k=1).**

Cross-app draw seed=42. d = L2 combined (node + adj deviation vectors).

| k | median d_self | IQR self | median d_cross | IQR cross |
|---:|---:|---:|---:|---:|
| 1 | 0.0081 | 0.0451 | 3.3444 | 0.7779 |
| 2 | 0.0167 | 0.0983 | 3.0750 | 1.3310 |
| 3 | 0.0503 | 0.1461 | 3.0197 | 2.1626 |
| 4 | 0.0257 | 0.1509 | 3.1829 | 1.7118 |
| 5 | 0.0404 | 0.1281 | 3.1675 | 1.0088 |
| 6 | 0.0358 | 0.3050 | 3.1971 | 0.7851 |
| 7 | 0.0430 | 0.3692 | 3.1122 | 1.4039 |

**Convergence:** held-out deviation does **not** decrease with k — minimum at k=1 (median=0.0081). Non-convergence within 8 sessions is the cold-start answer.

Apps with 9 sessions (per-app curves in JSON): 10.
Artifact: `abrg/output/v2_extended/e4_ordering/phase4_coldstart.json`

---

## Diagnostics

**Overturn (Phase 4):** The reported cold-start verdict *“has not converged within 8 sessions”* is **withdrawn**. Diagnostic 2 shows `d_self` rises with `k` under both chronological and permuted reference orderings while `d/||R||` rises; the k-curve is dominated by reference smoothing against sparse session graphs, not behavioural non-convergence. Revised label: **`REFERENCE_DILUTION`**.

**Correction (Phase 1, not a verdict overturn):** Reported rank-biserial **r = 0.464** used `n = 26` in the denominator while `scipy.stats.wilcoxon` (`zero_method='wilcox'`) dropped **5** zero-difference pairs (`N_effective = 21`). Corrected **r = 0.186** is mutually consistent with **W = 94**, **p = 0.455**. Phase 1 verdict **`ORDERING_NEUTRAL`** stands (`N_effective ≥ 20`, median Δ = 0).

Artifacts: `abrg/output/v2_extended/e4_ordering/diagnostics/phase1_diagnostics.json`, `phase4_diagnostics.json`, `summary.json`. Recomputed via `python -m abrg.chapter_b.run_e4_diagnostics`.

### Diagnostic 1 — Phase 1 tie-handling and scattered-draw audit

#### 1a. Per-app PREFIX and SCATTERED ‖d‖ (full precision, n = 26)

Source: `abrg/output/v2_extended/e4_ordering/phase1_per_app.csv`

| app_id | n_sess | PREFIX ‖d‖ | SCATTERED ‖d‖ |
|---|---:|---:|---:|
| ac.robinson.mediaphone | 9 | 0.04754698376072494 | 0.07015013385421848 |
| ai.susi | 9 | 2.7486492846495882 | 0.968964848317975 |
| app.fedilab.nitterizeme | 9 | 0.006391160401048757 | 0.004589694338275445 |
| app.fedilab.nitterizemelite | 9 | 0.00523359742621195 | 0.0033313641755659583 |
| app.michaelwuensch.bitbanana | 9 | 1.2620932546677504 | 0.5468309421025039 |
| app.prav.client | 9 | 0.0 | 0.0 |
| app.tujice.jergasColombia | 9 | 0.049359214958087455 | 0.012017872504788018 |
| at.linuxtage.Eventfahrplan | 9 | 0.7206150164958653 | 1.0466248707937262 |
| au.com.wallaceit.reddinator | 9 | 0.9262268253301695 | 1.3141772667258982 |
| barilyuk.batterytemperature | 9 | 0.06087315680057283 | 0.07067872454781486 |
| be.digitalia.fosdem | 8 | 0.47142183446151265 | 0.47611243415256743 |
| be.mygod.vpnhotspot_foss | 8 | 0.15299593078232157 | 0.20442575458114984 |
| biz.binarysolutions.vatcalculator | 8 | 0.0 | 0.0 |
| bluepie.ad_silence | 8 | 0.033275611248927014 | 0.033275611248927014 |
| bus.chio.wishmaster | 8 | 0.0 | 0.0 |
| ca.chancehorizon.paseo | 8 | 0.6173014599351584 | 0.6354358210893044 |
| ca.farrelltonsolar.classic | 8 | 0.03442989106031222 | 0.04600874933133328 |
| ca.rmen.android.frenchcalendar | 8 | 0.005203031082849928 | 0.008535756250358057 |
| ca.rmen.android.scrumchatter | 8 | 0.060406988678856466 | 0.08493694459496555 |
| ca.rmen.nounours | 8 | 0.03543787804255848 | 0.027634698117655704 |
| cat.jordihernandez.cinecat | 8 | 0.11750685015345975 | 0.17300314570384354 |
| cf.playhi.freezeyou | 8 | 0.3412609226063613 | 0.4118804990074724 |
| ch.joshuah.bibleverseapp | 8 | 0.010988820713262397 | 0.002149968694724375 |
| ch.mydoli.focal | 8 | 0.005851918694186764 | 0.005851918694186764 |
| cityfreqs.com.pilfershushjammer | 8 | 0.8160230581918808 | 0.2720076860639602 |
| cl.coders.faketraveler | 8 | 0.016966410853155273 | 0.00919328140437418 |

#### 1b. Delta counts (full precision)

Per-app Δ = PREFIX − SCATTERED (same CSV). Tie counts:

| threshold | count |
|---|---:|
| exact zero (Δ = 0) | 5 |
| \|Δ\| < 1e−6 | 5 |
| \|Δ\| < 1e−4 | 5 |
| \|Δ\| < 1e−3 | 5 |

The ~18-tie hypothesis does **not** apply: only **5/26** apps have exactly equal PREFIX and SCATTERED mean ‖d‖ (apps with identical test-session pairs under both splits: `app.prav.client`, `biz.binarysolutions.vatcalculator`, `bus.chio.wishmaster`, `bluepie.ad_silence`, `ch.mydoli.focal`).

#### 1c. N_effective and tie-handling rule

| quantity | value |
|---|---:|
| N_total pairs | 26 |
| Zero-difference pairs dropped | 5 |
| **N_effective** | **21** |
| Tie rule | `scipy.stats.wilcoxon(..., zero_method='wilcox')` — **drop zero-difference pairs** before ranking |

#### 1d. Wilcoxon recomputation and r consistency

| statistic | reported (E4) | recomputed |
|---|---:|---:|
| W | 94.0 | 94.0 |
| p | 0.4549 | 0.4549 |
| rank-biserial r | 0.464 (n = 26) | **0.186 (n_effective = 21)** |

Formula (Kerby 2014, paired Wilcoxon): `r = 1 − 2W / (n(n+1)/2)`.

- With **n = 26**: r = 0.464 — **inconsistent** with p ≈ 0.45 (would imply p < 0.05).
- With **n_effective = 21**: r = 0.186 — **consistent** with W = 94, p = 0.455.

The discrepancy is in the **effect-size computation** (`run_e4_ordering._rank_biserial` always used `n_total`), not in the Wilcoxon p-value.

#### 1e. Scattered-draw audit (VOID check)

Source: `abrg/output/v2_extended/e4_ordering/phase1_ordering.json` + seed replay via `_split_indices_scattered(n, app_id)` with seed `42 + hash(app_id)`.

| check | result |
|---|---|
| Apps with PREFIX ref == SCATTERED ref | **0 / 26** |
| Scattered ref matches seed replay | **26 / 26** |
| Duplicate seeds across apps | **0** |

Example (first app): PREFIX ref `[0,1,2,3,4,5]` vs SCATTERED ref `[0,1,2,4,7,8]` (seed 672883067). Scattering ran; Phase 1 contrast is **not void**.

Full per-app indices: `diagnostics/phase1_diagnostics.json` → `scatter_audit`.

#### 1f. Sign distribution (no interpretation)

| relation | count |
|---|---:|
| PREFIX ‖d‖ < SCATTERED ‖d‖ | 12 |
| PREFIX ‖d‖ > SCATTERED ‖d‖ | 9 |
| PREFIX ‖d‖ = SCATTERED ‖d‖ | 5 |

Medians (full precision): PREFIX **0.0484530993594062** vs SCATTERED **0.05807944159277588** — PREFIX deviates less on average.

#### Revised Phase 1 verdict

**`ORDERING_NEUTRAL`** — `N_effective = 21 ≥ 20`, median Δ = 0, p = 0.455. Not **`UNDERPOWERED`** (adequate n after tie drop). Not **`VOID`** (scattered draw verified). Report corrected **r = 0.186** (not 0.464) alongside p.

---

### Diagnostic 2 — Phase 4 reference dilution

#### 2a. Normalised k-curve

`||R||` = Frobenius combined reference magnitude `sqrt(||R_x||_F² + ||R_a||_F²)`. Source: `diagnostics/phase4_diagnostics.json` → `pooled`.

| k | median d_self (chrono) | IQR d_self | median \|\|R\|\| | IQR \|\|R\|\| | median d/ \|\|R\|\| | IQR d/ \|\|R\|\| |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.008143 | 0.045070 | 2.385837 | 0.523672 | 0.003522 | 0.017789 |
| 2 | 0.016692 | 0.098282 | 2.390548 | 0.523097 | 0.007333 | 0.040560 |
| 3 | 0.050298 | 0.146054 | 2.390923 | 0.524032 | 0.021340 | 0.054443 |
| 4 | 0.025720 | 0.150867 | 2.319525 | 0.527454 | 0.010924 | 0.052621 |
| 5 | 0.040403 | 0.128054 | 2.296221 | 0.536128 | 0.017385 | 0.057211 |
| 6 | 0.035837 | 0.305011 | 2.296508 | 0.526630 | 0.015539 | 0.108868 |
| 7 | 0.042989 | 0.369166 | 2.304253 | 0.526987 | 0.018770 | 0.142490 |

`||R||` falls modestly (k = 1 → 7 median −3.4%) while **d/||R||** rises **5.3×** (0.00352 → 0.01877). Raw d_self also rises (minimum still at k = 1). Dilution signature: normalised deviation grows even as reference magnitude shrinks slightly.

Chronological medians match original `phase4_coldstart.json` (bit-identical).

#### 2b. Scattered-order k-curve vs chronological

Permuted session order per app (seed `42 + hash(app_id)`); reference = first k sessions in permuted order, test = session k in permuted order.

| k | median d_self (chrono) | median d_self (scattered order) |
|---:|---:|---:|
| 1 | 0.008143 | 0.020773 |
| 2 | 0.016692 | 0.032785 |
| 3 | 0.050298 | 0.056218 |
| 4 | 0.025720 | 0.034760 |
| 5 | 0.040403 | 0.047216 |
| 6 | 0.035837 | 0.045554 |
| 7 | 0.042989 | 0.046640 |

**Both curves rise from k = 1 toward k = 7** (chrono k = 1 → k = 7: +428%; scattered: +124%). This is **not** chronological drift alone — permuted references show the same pattern. No contradiction with Phase 1 ordering neutrality.

#### 2c. d_cross and self/cross ratio (normalised check)

| k | median d_cross | median d_self | d_cross / d_self |
|---:|---:|---:|---:|
| 1 | 3.344374 | 0.008143 | 411× |
| 2 | 3.075008 | 0.016692 | 184× |
| 3 | 3.019689 | 0.050298 | 60× |
| 4 | 3.182945 | 0.025720 | 124× |
| 5 | 3.167506 | 0.040403 | 78× |
| 6 | 3.197077 | 0.035837 | 89× |
| 7 | 3.112206 | 0.042989 | 72× |

Cross-app baseline **~3.1** stable across k; ratio **72×–411×** (large at k = 1 because d_self is near zero). Self/cross separation is not an artifact of reference magnitude alone.

#### 2d. Per-node contribution (k = 1 vs k = 7)

Mean per-node `(d_node + d_adj)` pooled over 26 apps. Largest increases k = 7 − k = 1:

| node | mean @ k = 1 | mean @ k = 7 | Δ |
|---|---:|---:|---:|
| crypto | 0.01005 | 0.15524 | +0.145 |
| storage | 0.02396 | 0.12570 | +0.102 |
| audio | 0.00063 | 0.08282 | +0.082 |
| network | 0.00253 | 0.08410 | +0.082 |
| native_code | 0.00352 | 0.07390 | +0.070 |
| file_io | 0.03135 | 0.06638 | +0.035 |

Increase concentrates in high-activity / high-variance nodes (crypto, storage, network), consistent with averaging sparse references that under-estimate spiky test sessions.

#### Revised Phase 4 statement

**`REFERENCE_DILUTION`:** Adding reference sessions smooths R (modest `||R||` shrink, rising `d/||R||`); raw `d_self` increases under **both** chronological and permuted reference draws. The statistic measures magnitude mismatch between a smoothed reference and a single sparse session graph, not failure of within-app behaviour to converge. **Withdraw** the behavioural claim *“does not converge within 8 sessions.”* Descriptive fact retained: minimum pooled median d_self at **k = 1** (0.0081).

---

### Confirmations (unchanged)

**Phase 4 self vs cross:** d_self 0.008–0.043 vs d_cross ~3.1; ratio 72×–411× at each k (table 2c). Confirmed under normalisation from 2a.

**Phase 2:** All **26/26** apps multi-day (`phase2_recency.json` → `multi_day_prerequisite.all_multi_day = true`). **W_REC does not beat W_CUM** at decays 1 h / 4.86 h / 24 h — unchanged.

**Phase −1:** Three builders reconciled; E4 on `update_graph_sequence` (Run 2 stage). Unchanged (`provenance.json`).

---

Generated 2026-08-22T07:56:32.962812+00:00. Summary: `abrg/output/v2_extended/e4_ordering/summary.json`. Diagnostics appended 2026-08-22.
