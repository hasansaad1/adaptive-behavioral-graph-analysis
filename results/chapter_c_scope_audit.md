# Chapter C scope audit + E4 relocation

Date: 2026-08-22. Audit and move only — no experiments, no re-runs.

---

## CHECK 1 — Convergence 1.28 / 38.32 [BLOCKING]

### Verdict: **ARTIFACT FOUND — Chapter C may cite it**

### 1a. Persisted artifact

| Field | Value |
|-------|-------|
| Path (human) | `abrg/output/v2_chapter_c/SUMMARY.md` (Stage 2 — Cross-app control) |
| Path (machine) | `abrg/output/v2_chapter_c/artifacts/stage2.json` → `cross_app` |
| within_app median | **1.2831416802452953** (SUMMARY rounds to 1.28314) |
| within IQR | [0.14115182493519912, 15.173454849282518], **n = 240** |
| cross_app median | **38.3165** (JSON: same band; SUMMARY 38.3165) |
| cross IQR | [15.114807007915823, 86.23015984316189], **n = 9350** |
| Mann–Whitney U | **354425.0**, alternative `within_lt_cross` |
| **p** | **1.0195951462519772e-73** (≈ 1e-73) |

Also echoed in Stage 3 variant `both` and the Stage 3 summary table row (λ=0.01): within 1.28314, cross 38.3165, separation 37.0333.

### 1b. What statistic is it?

| Aspect | Detail |
|--------|--------|
| Statistic | **`frobenius_combined`**: Euclidean / Frobenius norm on the concatenated node-feature and adjacency blocks of shares-not-counts session tensors (`abrg/chapter_c/tensorize.py` `distances`) |
| Not | MSE, reconstruction error, or AUC |
| Reference | `equal_mean_normalised_session_tensors` — equal-weight arithmetic mean of session vectors 1..k (within) or full other-app mean (cross) |
| Channel | `both` (w_cum + w_rec adjacency blocks) |
| n apps (Stage 2 convergence set) | **35** (`n_apps: 35` in SUMMARY) |
| n within pairs | **240** held-out e(R_k, S_{k+1}) |
| n cross pairs | **9350** (every session of A vs full-app mean of every B≠A) |
| Test | **Mann–Whitney U**, one-sided within < cross |
| Corpus / builder | **v2_extended**; session graphs via Chapter C timed builder → tensorise; runner `abrg/chapter_c/converge.py` `run_cross_app_control` |
| Pipeline status | **Has been run to completion**; outputs persisted under `abrg/output/v2_chapter_c/` (`SUMMARY.md`, `artifacts/stage2.json`, `stage3.json`, `reproduce_config.json`) |

### 1c. Not applicable (artifact exists)

`converge.py` computes reference convergence curves, shuffled-order controls, cross-app control, and Stage 3/4 recency/cold-start variants. It has completed; do not re-run for this task.

### 1d. Reconciliation vs E4 self/cross ratio (72×–411×)

| | Chapter C Stage 2 | E4 Phase 4 |
|--|-------------------|------------|
| Artifact | `v2_chapter_c/…/stage2.json` | `v2_extended/e4_ordering/phase4_coldstart.json` |
| Metric | `frobenius_combined` on independently tensorised session graphs | pooled median **L2 combined** deviation under `update_graph_sequence` |
| Self / within | median **1.28314** (n=240) | d_self medians **0.008143 → 0.042989** (k=1..7) |
| Cross | median **38.3165** (n=9350) | d_cross ≈ **3.1122** (stable across k) |
| Ratio form | ~30× median separation (38.32/1.28) | **72×–411×** on the k-curve |
| n apps | 35 (convergence set) | **26** (≥8 sessions) |
| Claim | pooled within ≪ cross (MW p≈1e-73) | REFERENCE_DILUTION; k=1 minimum |

**Same qualitative question, different statistics.** `phase4_coldstart.json` already notes: *"Chapter C pooled within vs cross (frobenius_combined) ≈ 1.28 vs 38.32; E4 reports L2 combined d at each k on the same 22-node tensors."* They **must not** be presented as one result. Chapter C now states both and the distinction (`sec:c-within-cross`, `sec:c-coldstart`).

**Blocking outcome:** Spine may rest on **both** the persisted Stage 2 within/cross figure **and** the E4 ratio, with explicit non-identity.

---

## CHECK 2 — State-based stimulus [BLOCKING for A.9 forward ref]

### 2a. Artifacts found?

**None.** Repository search (thesis, `results/`, `abrg/output/`) found no controlled comparison of ContextDroid LLM-planned stimulus versus Monkey (or any other stimulus regime) on a shared app population. Mentions of Monkey vs planner appear only as **observability classification** (why categories fail to fire), not as a head-to-head coverage/behaviour experiment.

### 2b. Is a controlled comparison constructible?

**No — not from current data.**

| Obstacle | Detail |
|----------|--------|
| AndroCT | 600s Monkey, Nexus One AVD, Android 6.0, DroidFax; one trace per app; malware labels |
| v2_extended | LLM-planned Frida harness, different AVD, different apps, no malware, multi-session |
| Shared population | **None** — no overlapping app set with both stimuli |
| Confounds if forced | Sensor (DroidFax vs Frida), AVD/hardware, app set, session length, and stimulus would all change together |

A within-corpus stimulus ablation would require **new collection** (same apps, same AVD/sensor, two stimulus arms). That is future work, not Chapter C draftable content.

### 2c. Proposed §A.9 replacement string (DO NOT EDIT chapter_a in this task)

**Before** (`thesis/chapter_a/A9_conclusions.tex` ≈ L86–89):

> What remains untested on AndroCT is deferred, not promised. Generality beyond one public year-matched corpus is Chapter~B. Whether state-based stimulus changes the picture, and whether per-app cross-session refinement converges, are Chapter~C. Whether the `\texttt{ipc\_intents}` concentration is corpus-specific is an open measurement on any later corpus that keeps a comparable node universe.

**After (proposed):**

> What remains untested on AndroCT is deferred, not promised. Generality beyond one public year-matched corpus is Chapter~B. Per-app cross-session self-reference---within versus cross-app session error, ordering, recency, and cold-start dilution---is Chapter~C (\S\ref{sec:c-self-reference}). A controlled comparison of state-based (LLM-planned) stimulus versus Monkey is \emph{not constructible} across AndroCT and v2\_extended: different apps, AVDs, sensors (DroidFax versus Frida), and no shared population; it remains deferred to a future same-harness collection, not to Chapter~C. Whether the `\texttt{ipc\_intents}` concentration is corpus-specific is an open measurement on any later corpus that keeps a comparable node universe.

Also propose retargeting `A10_threats.tex` L127–128 similarly when chapter_a is next edited (stimulus unavailable on AndroCT **and** not answered by C).

---

## CHECK 3 — Chapter C inventory

| Item | Artifact path | Currently in thesis | Move to C? |
|------|---------------|---------------------|------------|
| E4 Phase 0 viability (342/59/40/26; gaps; timing; W=120) | `abrg/output/v2_extended/e4_phase0/inventory.json` | `B8_v2_extended.tex` `sec:b8-viability` | **Stay in B** (corpus characterisation) |
| E4 Phase −1 three-builder provenance | `abrg/output/v2_extended/e4_ordering/provenance.json` | now noted in `sec:b8-viability` | **Stay in B** |
| E4 Phase 1 ORDERING_NEUTRAL | `e4_ordering/phase1_ordering.json`, `diagnostics/phase1_diagnostics.json` | was B8 → **`C1_self_reference.tex` `sec:c-ordering`** | **Moved to C** |
| E4 Phase 2 recency null | `e4_ordering/phase2_recency.json` | was B8 → **`sec:c-recency`** | **Moved to C** |
| E4 Phase 4 + diagnostics REFERENCE_DILUTION / 72×–411× | `phase4_coldstart.json`, `diagnostics/phase4_diagnostics.json` | was B8 → **`sec:c-coldstart`** | **Moved to C** |
| Observability audit v2 15/22 | `results/observability_v2_extended.csv`, `results/observability_audit.md` | `sec:b8-observability` | **Stay in B** |
| Chapter C Stage 2 within/cross 1.28314 / 38.3165 / p≈1e-73 | `abrg/output/v2_chapter_c/SUMMARY.md`, `artifacts/stage2.json` | **now cited in `sec:c-within-cross`** | **C (spine)** |
| E0/E2 window counterpart | AndroCT selfref outputs; `results/d_self_vs_d_cross.md` | `A6_selfref.tex` | **Cross-ref only** (not moved) |

---

## ACTION — Relocation record

### Split decision

| Remains in Chapter B | Moves to Chapter C |
|----------------------|--------------------|
| Phase 0 viability / timing / windowing | Phase 1 ordering |
| Phase −1 builder provenance pin | Phase 2 recency |
| v2 observability (15/22, buckets) | Phase 4 cold start + self/cross ratio |
| Pointer to C for design results | Stage 2 within/cross frobenius result (new citation of existing artifact) |
| | Interpretation of adaptive-update / REFERENCE_DILUTION |

Ambiguous sections: **none duplicated**. B points to C; C points back to B viability/observability.

### Files created

| File | Role |
|------|------|
| `thesis/chapter_c/chapter_c.tex` | Top-level chapter input |
| `thesis/chapter_c/C1_self_reference.tex` | Relocated E4 design results + Stage 2 within/cross |
| `thesis/chapter_c/preview_chapter_c.tex` | Standalone compile harness |
| `thesis/chapter_b/preview_b8_only.tex` | Slim B8 compile check |
| `results/chapter_c_scope_audit.md` | This document |

### Files edited

| File | Change |
|------|--------|
| `thesis/chapter_b/B8_v2_extended.tex` | Slimmed to viability + provenance note + observability; points to C |
| `thesis/chapter_b/chapter_b.tex` | Unchanged inputs (still `\input{B8_v2_extended}`) |
| `thesis/chapter_b/B2_contextdroid.tex` | `\ref{sec:b8-coldstart}` → `\ref{sec:c-coldstart}` |
| `thesis/chapter_b/B4_comparison.tex` | Builder audit line points to B8 pin + `sec:c-self-reference` |
| `thesis/chapter_b/preview_chapter_b.tex` | Now includes B8; stubs for C labels |

### Cross-references

| Ref | Resolution |
|-----|------------|
| `sec:c-ordering`, `sec:c-recency`, `sec:c-coldstart`, tables `tab:c-*` | Defined in `C1_self_reference.tex` |
| Compat aliases `sec:b8-ordering`, `sec:b8-recency`, `sec:b8-coldstart`, `tab:b8-*` | Same locations in C — so **Chapter A `\ref`s still resolve** without editing chapter_a |
| `sec:b8-viability`, `sec:b8-observability`, `sec:b8-v2-extended` | Remain in slimmed B8 |
| Chapter A prose still saying “Chapter B” for cold-start | **Not edited** this task; proposed retarget below |

### Chapter A refs — proposed retargets (not applied)

| File | Current | Proposed |
|------|---------|----------|
| `A1_framing.tex` L51–52 | `\S\ref{sec:b8-recency}`, `sec:b8-coldstart`, `sec:b8-ordering` | Same labels still work via compat aliases; optionally `\S\ref{sec:c-recency}` etc. and say Chapter~C |
| `A6_selfref.tex` L88 | `\S\ref{sec:b8-coldstart}` | `\S\ref{sec:c-coldstart}` |
| `A8_discussion.tex` L206, L220 | `(Chapter~B, \S\ref{sec:b8-coldstart})` | `(Chapter~C, \S\ref{sec:c-coldstart})` |
| `A10_threats.tex` L119–122 | `sec:b8-recency` / coldstart / ordering | `sec:c-recency` / `sec:c-coldstart` / `sec:c-ordering` |
| `A9_conclusions.tex` | stimulus + converges → Chapter C | Use Check 2c string above |

Compat aliases mean a combined thesis compile will not show undefined refs for the old `sec:b8-*` design labels; prose still incorrectly attributes them to Chapter B until A is edited.

### Compile status

| Target | Status |
|--------|--------|
| `thesis/chapter_c/preview_chapter_c.tex` | **OK** (`preview_chapter_c.pdf`) — overfull hbox only |
| `thesis/chapter_b/preview_b8_only.tex` | **OK** (`preview_b8_only.pdf`) — overfull hbox only |
| Combined A+B+C book | Not present as a single root; chapter_a not recompiled this task |

No unresolved `\ref` inside the Chapter C preview after two tectonic passes.
