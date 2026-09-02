# Chapter C final audit (Phase 2)

Date: 2026-08-31. Branch: `submission-work`. No numbers changed in this pass.

## Structural arc

| Section | Four questions | Verdict |
|---------|----------------|---------|
| **C1** Framing | Q1–Q4 stated; three result blocks + empty cell | **OK** |
| **C2** Method | Populations, builders, split rule; defers characterisation to B | **OK** (minor wording) |
| **C3** Premise | Q2 positive; never-merge; shuffle honesty; 11/35 stabilise | **OK** |
| **C4.1** Ordering | Q3 null; Cohen's *d*; session granularity vs A | **OK** |
| **C4.2** Recency | Q3 null; three half-lives; `w_rec_beats_w_cum` false | **OK** |
| **C4.3** Cold-start | Dilution not convergence; withdrawn claim explicit; k-table | **OK** |
| **C5** Desc-seed | Q4; three framings; mechanism; limits | **OK** |
| **C5** Interpret | Synthesis; reference-needs-variance link to A8 | **FLAG** → fixed |
| **C6** Threats | Session unit; dependence; boundary table | **OK** |
| **C7** Conclusions | Closes Q1–Q4; no new numbers | **OK** |

**C1 ↔ C7:** Four questions match closing paragraphs 1:1.

---

## Artefact trace (headline numbers)

| Claim | Thesis | Artefact | Match |
|-------|--------|----------|-------|
| Within / cross Frobenius medians | 1.28 / 38.3 | `v2_chapter_c/artifacts/stage2.json` `_within`/`_cross` medians | **OK** (full precision in table) |
| Mann–Whitney *p* | ≈ 1.02×10⁻⁷³ | `stage2.json` `cross_app.mannwhitney_u.p` | **OK** |
| Cliff's δ | 0.684 | Recomputed from `_within`/`_cross` lists (comment in C3) | **OK** |
| Never stabilise / stabilise | 24 / 11 of 35 | `stage2.json` `convergence.n_never_stabilise=24`, `n_apps=35` | **OK** |
| E4 *k*=1 / *k*=7 self | 0.008143 / 0.042989 | `e4_ordering/phase4_coldstart.json` pooled_self | **OK** |
| E4 ratios 411× / 72× | Table C cold-start | phase4 pooled medians | **OK** |
| ORDERING_NEUTRAL, Cohen's *d* | 0.202 | `phase1_ordering.json`, diagnostics | **OK** |
| Recency null | 12/26, 7/26, 9/26 wins | `phase2_recency.json`, `w_rec_beats_w_cum=false` | **OK** |
| Desc self/cross AUC | 0.501 / ceiling 0.979 | `desc_seed/SUMMARY.md`, `stage2b_report.json` | **OK** |
| Within-app median vs prior | 0.725 / 0.952 | `desc_seed/SUMMARY.md` | **OK** |
| 112/342 near-replicates | C6 (3) | B3, B7, `m2_session_mode.json` | **OK** |

`desc_seed` validates under `abrg.batch_validate_reproduce` (53-report index; 51 pass / 2 fail — see `abrg/output/REPRODUCE_STATUS.md`).

---

## Handoff checklist

| Rule | Status |
|------|--------|
| Never merge Stage 2 and E4 | **OK** — stated C1, C3, table, C7 |
| Shuffle = session-order only, not within/cross null | **OK** — C3 §shuffle |
| Convergence claim withdrawn | **OK** — C4.3 explicit |
| Prior work: Lane/Forrest (C3), CHABADA/WHYPER/AutoCog (C5) | **OK** |
| Session non-independence | **OK** — C3, C6 (1)+(3), B7 |
| Builder named per measurement | **OK** — C2, C4 tables, B7 |
| No malware / no detection AUC except desc diagnostics | **OK** — C1, C6, C5 |
| Configuration-matched comparisons | **OK** — AndroCT window paragraph disclaims metric |

---

## Flags and resolutions

### FLAG 1 — C5 “under recency weighting” (coherence)

**Issue:** C5 stated self/cross separation “holds … under both cumulative and recency weighting.” §C.4.2 only tests whether *W*_REC lowers mean *L*₂ deviation vs *W*_CUM (it does not). Stage~3 Frobenius within/cross under `w_rec`/`w_cum` exists in `v2_chapter_c/SUMMARY.md` but is **not reported** in the chapter body.

**Risk:** Reader infers recency preserves or improves the premise; §C.4.2 says the opposite for reference error.

**Fix applied:** Reword C5 to tie separation to *k* and ordering/cold-start; cite §C.4.2 for the recency **null** separately.

### FLAG 2 — C2 “Stage~2 convergence apps” (wording)

**Issue:** Internal JSON key name; reads like withdrawn convergence claim.

**Fix applied:** “Stage~2 eligible apps.”

### OPEN (no edit) — Stage 3 channel variants

`v2_chapter_c` Stage~3 shows within/cross separation unchanged under `w_rec` vs `w_cum` (medians ~1.24 vs ~1.28 within). Not in thesis text. Optional one sentence in §C.4.2 or appendix if you want the stronger recency-null argument; omitting is honest given §C.4.2 already closes the design commitment.

### OPEN — C3 AndroCT window paragraph

Cross-sensor, cross-metric bridge is properly disclaimed. Keep as scope boundary, not a merged number.

---

## Section → claim → artefact (quick index)

- **C3 premise** → within ≪ cross → `stage2.json`, F3
- **C3 shuffle** → order null for *k*-curve → `stage2.shuffle`
- **C4.1** → ORDERING_NEUTRAL → `e4_ordering/phase1_*.json`
- **C4.2** → recency null → `phase2_recency.json`
- **C4.3** → REFERENCE_DILUTION → `phase4_coldstart.json`, `stage2.json` replication para
- **C5** → k=0 description null → `abrg/output/desc_seed/`

---

## Phase 2 gate

**Coherence:** Pass after C5/C2 edits.  
**Traceability:** Pass (all frozen headline numbers match artefacts).  
**Ready for Phase 3** (cross-chapter bridges A/B ↔ C).
