# VERDICT: **NOT_DISTINGUISHABLE**

Generated: 2026-08-22 (scoring pass only; runner `abrg/devread/run_d3_hygiene.py`)

Paired comparison: **trained D1 centroid L2** vs **random-init D1 centroid L2**, same test apps (141 benign + 1700 malware), benign-only fit on train-benign (562 apps).

| Scorer | AUC | AUC_floor | Direction | Artifact |
|--------|----:|----------:|-----------|----------|
| Trained D1 L2 | 0.800426 | 0.800426 | malware-higher | `…/splitA_trained/trained__D1__none__centroid_euclidean__splitA__foldNA.json` |
| Random-init D1 L2 | 0.811844 | 0.811844 | malware-higher | `…/controls/random_init_splitA/random_init__D1__none__centroid_euclidean__splitA__foldNA.json` |
| **Δ (RI − trained)** | +0.011418 | +0.011418 | — | — |

Catalogue value 0.811844 matches recomputation to six decimals.

---

## Paired inferential tests

| Test | Statistic |
|------|-----------|
| DeLong raw Δ | +0.011418 |
| DeLong SE | 0.016620 |
| DeLong z | 0.687013 |
| DeLong p (two-sided) | 0.492075 |
| Bootstrap B | 2000 (seed 42) |
| Bootstrap mean Δ_floor | +0.011390 |
| Bootstrap 95% CI | [−0.019960, +0.043989] |
| CI contains zero? | **yes** |
| Spearman ρ (trained vs RI scores) | 0.837400 |
| **Distinguishable from zero?** | **no** |

Random-init is +0.011418 above trained on floor AUC — same shape as D-1’s +0.0157 L∞ follow-up that was also not distinguishable. **Stop here;** extended D1 controls (nested bootstrap, volume residualisation, terciles, Ward holdout, per-node ablation) are **not** run because the paired gain is not established.

---

## Prior-reporting check (Chapter A)

| Question | Answer |
|----------|--------|
| Is 0.811844 cited in `thesis/chapter_a/*.tex`? | **No** (grep clean) |
| In Table A.13 / §A.6.3 seven-family “trained vs untrained indistinguishable”? | **No row for random-init D1 centroid** |
| Closest existing entry | Run~8 **embedding** random-init 0.7591 (`tab:a6-family-sweep`), not D1 centroid |
| Source sheet | `ocdev/controls/random_init_splitA/random_init__D1__…json` |

**Conclusion:** The deviation-profile family currently has **no** trained-vs-untrained paired row in the seven-family table; this random-init D1 centroid pair (+0.011, p ≈ 0.49) would be that row if added — and it would support the “indistinguishable where paired” framing, not contradict it.

Trained D1 nested bootstrap reference (from prior validation): [0.757, 0.815], bias −0.003 — the point +0.011 RI advantage lies inside this interval.
