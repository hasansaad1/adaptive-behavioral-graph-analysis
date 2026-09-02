# Cross-chapter coherence audit (Phase 3)

Date: 2026-09-01. Branch: `submission-work`. No numbers changed in this pass.

## Gate: **Pass** (one attribution fix applied; matrix row expanded)

---

## 3.1 Forward references (Chapter A → C)

| Location | Points to | Verified |
|----------|-----------|----------|
| `A1_framing.tex` exercise matrix row | `sec:c-premise`, `sec:c-ordering`, `sec:c-coldstart`, `sec:c-recency`, `sec:c-desc-seed` | **Y** (row expanded in Phase 3) |
| `A8_discussion.tex` synthesis | Premise `sec:c-premise`; k-curve `sec:c-coldstart` | **Y** |
| `A8_discussion.tex` exchangeability | `sec:c-framing`, `sec:c-premise` | **Y** (prose normalized) |
| `A8_discussion.tex` deployability | `sec:c-premise`, `sec:c-coldstart` | **Y** |
| `A9_conclusions.tex` deferred work | All four C questions + §C.5 k=0 (`sec:c-desc-seed`) | **Y** |
| `A10_threats.tex` design commitments | `sec:c-recency`, `sec:c-premise`, `sec:c-ordering`, `sec:c-coldstart`, `sec:c-threats` | **Y** |
| `A6_selfref.tex` cross-corpus bridge | Frobenius medians → `sec:c-premise`; E4 ratios → `sec:c-coldstart` | **Y** (was wrongly attributed to Chapter B) |

### `sec:c-coldstart` grep in `thesis/chapter_a/`

Every hit is k-curve / $k{=}1$ / dilution specific — **OK**.

---

## 3.2 Chapter B → C

| Bridge | Claim | Verified |
|--------|-------|----------|
| `B2_contextdroid.tex` protocol isolation | Cross-session conditions for C reference analysis; `sec:c-framing` | **Y** |
| `B3_corpus.tex` populations | Stage-2 eligible vs E4 $n{=}26$; defers to `sec:c-method` | **Y** |
| `B3_corpus.tex` poolability | Batch heterogeneity + near-replicates; cited by C6 | **Y** |
| `B7_threats.tex` corpus | 112/342 near-replicates; session nesting; mirrors C6 | **Y** |
| `B8_v2_extended.tex` | Ordering/recency/cold-start deferred to `sec:c-framing`; no duplicate tables | **Y** |
| `B4_comparison.tex` | Session unit $n{=}342$; design runs in `sec:c-framing` | **Y** |
| `B5_delta.tex` | Builder chain to Chapter C session graphs | **Y** |
| `B6_chapter_a.tex` | IPC coordinate; no C ratio claims | **Y** |

---

## 3.3 Chapter C → A/B (reverse bridges)

| Location | Points to | Verified |
|----------|-----------|----------|
| `C1_framing.tex` | AndroCT asymmetry; `sec:a6-selfref-interpret`; `sec:b8-viability`; `tab:a1-matrix` | **Y** |
| `C2_method.tex` | Corpus characterisation `sec:b8-*`, `sec:b3-*`; window object `sec:a6-selfref` | **Y** |
| `C4_not_temporal.tex` | Window exchangeability `sec:a6-selfref-interpret`; `tab:a1-matrix` recency row | **Y** |
| `C5_interpretation.tex` | $D_1$ floor `sec:a6-deviation`; E0/E2 `sec:a6-selfref` | **Y** |
| `C6_threats.tex` | DroidFax vs Frida; `sec:b8-observability`, `sec:b3-poolability`, `sec:b7-corpus` | **Y** |
| `C3_premise.tex` E4 paragraph | AndroCT window counterpart `sec:a6-selfref-e0` | **Y** |

---

## 3.4 Shared vocabulary (spot-check)

| Term | Canonical reading in thesis | Drift? |
|------|----------------------------|--------|
| Message passing | “Does not help” (+ add pooling unanimous) | **No** |
| Cold-start / convergence | `REFERENCE_DILUTION`; convergence withdrawn | **No** (only negated uses remain) |
| `ipc_intents` | Architectural coordinate, not behavioural deviation | **No** |
| Floor interval A8.6 | $D_1$ nested $[0.757, 0.815]$ vs floor bootstrap $[0.6434, 0.7545]$ | **No** |
| OCGIN | `OCGIN_plus` vs OCGIN† band distinguished | **No** |

---

## 3.5 Population discipline (grep spot-check)

| Count | Canonical set | Sample locations | OK? |
|-------|---------------|------------------|-----|
| 2231 | Parsed-non-empty AndroCT benign traces | B6, B7 | **Y** |
| 562 | GAE train-benign graphs | A8, B6, B7 | **Y** |
| 342 | v2 usable sessions (reference tier) | B3, C6, B8 | **Y** |
| 59 | v2 apps with usable sessions | B3, C2 (desc: 59→53) | **Y** |
| 53 | desc-seed analysed apps | C4, C1 | **Y** (six excluded stated) |
| 35 | Stage-2 eligible apps | C2, C3, C6 | **Y** |
| 26 | E4 apps ($\ge 8$ sessions) | C2, C3, B8 | **Y** |
| 40 | v2 graph-eligible apps | C2, B3 | **Y** |

---

## Fixes applied (Phase 3)

1. **`A1_framing.tex`** — exercise-matrix row now cites premise, ordering, cold-start/dilution, and description-seed null.
2. **`A6_selfref.tex`** — corrected attribution: $72\times$--$411\times$ ratios are Chapter C (`sec:c-coldstart`), not Chapter B; Frobenius medians cite `sec:c-premise`.
3. **`A8_discussion.tex`** — normalized cross-session bridge to `(\S\ref{sec:c-framing}, \S\ref{sec:c-premise})`.

---

## Open items (non-blocking)

- `A6_selfref.tex` still uses $38.32$ in comment block vs $38.3$ in prose elsewhere — comment only, no narrative change needed.
- Stage 3 `w_rec`/`w_cum` Frobenius within/cross in `v2_chapter_c/SUMMARY.md` not in thesis body (flagged Phase 2; out of scope for bridge pass).
