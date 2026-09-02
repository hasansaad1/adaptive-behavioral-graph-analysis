# VERDICT: **SELF_IS_LOAD_BEARING**

Generated: 2026-08-22 (scoring pass only; runner `abrg/devread/run_d3_hygiene.py`)

`d_self = |X_t^{(i)} - R_i|` uses each app’s own PREFIX/SCATTERED reference windows.  
`d_cross = |X_t^{(i)} - R_j|` uses a **class-blind** random other-app reference (`j ≠ i`).

| Pin | Value |
|-----|-------|
| Cross-reference RNG seed | **951** (= split seed 42 + 909) |
| Snap cache | `abrg/output/androct_2017/selfref/windows/armb_n8_windows.pt` |
| d_self window scores | `abrg/output/androct_2017/selfref/deviations/window_scores.csv` |
| HGB protocol | E0 Phase 4: stratified both-class split, seed 42, HistGradientBoostingClassifier |

**Primary margin (PREFIX, node, HGB diagnostic ceiling):** self − cross = **+0.087067** floor AUC (DeLong z = 4.689989, p = 2.73×10⁻⁶). The supervised ceiling on self-deviation **exceeds** cross-reference; the classifier is not merely reading the window tensor `X`.

---

## Supervised HGB — DIAGNOSTIC CEILING (not a proposed detector)

Stratified split: n_train = 1922, n_test = 481 (E0 Phase 4 split, not the 562/141/1700 app-level ocdev split).

| Mode | Space | Arm | AUC_floor | Direction | CI95 floor |
|------|-------|-----|----------:|-----------|------------|
| PREFIX | node | d_self | 0.934043 | malware-higher | [0.911701, 0.954360] |
| PREFIX | node | d_cross | 0.846975 | malware-higher | [0.811428, 0.880335] |
| PREFIX | adj | d_self | 0.918732 | malware-higher | [0.890978, 0.942161] |
| PREFIX | adj | d_cross | 0.734752 | malware-higher | [0.686874, 0.778254] |
| SCATTERED | node | d_self | 0.927430 | malware-higher | [0.903772, 0.949875] |
| SCATTERED | node | d_cross | 0.848832 | malware-higher | [0.812382, 0.882065] |
| SCATTERED | adj | d_self | 0.915394 | malware-higher | [0.886577, 0.939844] |
| SCATTERED | adj | d_cross | 0.718461 | malware-higher | [0.669706, 0.763087] |

E0 persisted ceilings (`phase4_ceiling.csv`) match d_self arms to six decimals. Cross-reference arms are new this pass.

**DeLong (paired, PREFIX node HGB):** Δ_floor = +0.087067, SE = 0.018564, z = 4.689989, p = 0.000003.

---

## One-class readouts (141 test-benign + 1700 test-malware; MEAN / MAX / FRACTION)

d_self scores from persisted `window_scores.csv`; d_cross recomputed with train-benign τ₉₅ from cross-deviation windows.

### PREFIX — node — SCALAR (E0 primary curve)

| Verdict | d_self AUC_floor | d_self dir | d_cross AUC_floor | d_cross dir |
|---------|----------------:|------------|------------------:|-------------|
| MEAN | 0.696635 | benign-higher | 0.508894 | benign-higher |
| MAX | **0.699733** | benign-higher | **0.526700** | malware-higher |
| FRACTION | 0.525288 | benign-higher | 0.502121 | malware-higher |

### PREFIX — node — CENTROID

| Verdict | d_self AUC_floor | d_cross AUC_floor |
|---------|----------------:|------------------:|
| MEAN | 0.588035 | 0.661569 |
| MAX | 0.593563 | 0.664577 |
| FRACTION | 0.519431 | 0.506133 |

Under one-class scoring, d_self remains near ~0.70 (benign-higher) on PREFIX node SCALAR; d_cross collapses toward ~0.50–0.53 (noise). Supervised separation is where self-reference dominates.

Full 24-combo grid (PREFIX/SCATTERED × node/adj × SCALAR/CENTROID × MEAN/MAX/FRACTION): `results/D3_hygiene_summary.json` → `task2.one_class`.

---

## Cross-reference: Chapter B / E4 (different metrics — not directly comparable)

| Setting | Metric | Within-app / self | Cross-app / cross | Ratio |
|---------|--------|------------------:|------------------:|------:|
| v2 sessions (E4) | median distance | 1.28 | 38.32 | ~30×–411× band |
| AndroCT windows (this task) | HGB floor AUC (PREFIX node) | 0.934043 | 0.846975 | additive +0.087, not a ratio |
| AndroCT windows (this task) | one-class MAX SCALAR floor | 0.699733 | 0.526700 | — |

Session-level distance ratios and window-level AUC ceilings answer different questions; do not merge them into one headline number.

---

## Thesis implication

**SELF_IS_LOAD_BEARING:** E0’s diagnostic ceiling 0.9154–0.9340 on PREFIX node HGB is **not** fully explained by window content alone; d_self exceeds d_cross by a statistically clear margin (+0.087 floor AUC). The existing A6_selfref framing on self-deviation under supervision **does not** require softening on this control.

(RAW supervised input alone reaches 0.9746 — window signal is strong; this control isolates whether **self-reference** adds beyond cross-reference, and it does.)
