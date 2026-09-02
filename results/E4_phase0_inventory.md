# E4 Phase 0 — v2_extended inventory and viability

**MEASUREMENT ONLY.** No model, no scoring, no AUC. Benign corpus — nothing here is a detection result. Report and STOP.

> **Sample-size note:** **26** apps clear ≥8 sessions (barely above the ~20 threshold). Max usable sessions/app is 9, so a 6/2 split consumes nearly the whole trace. Carry n=26 in every E4 caption.

## Viability verdict (read first)

| Decision | Verdict | Detail |
|---|---|---|
| **SPLIT VIABILITY** | **VIABLE** | n apps with ≥8 sessions = **26** |
| **RECENCY MEANINGFUL** | **MARGINAL** | median gap 4.86 h — hours-scale separation |
| **TIME-WINDOWING** | **MARGINAL** | best empty-mapped W=120s at median empty-mapped=0.000, but median zero-edge (k=5) fraction still 0.500 ≥ 0.50 — windows often contain events without cross-category edges |

Artifacts: `abrg/output/v2_extended/e4_phase0/`

## 0a — Corpus inventory

| Quantity | n |
|---|---:|
| Total sessions exported | 388 |
| Usable sessions (`reference_tier_pass`) | 342 |
| Failed / non-pass sessions | 46 |
| Apps in index | 59 |
| Apps with ≥1 usable session | 59 |
| Graph-eligible sessions (`gae_eligible`) | 288 |
| Graph-eligible apps | 40 |

Sessions per app (usable): min=1, median=7, IQR=5, max=9.

### Full histogram (usable sessions per app)

| n_sessions | n_apps |
|---:|---:|
| 1 | 2 |
| 2 | 1 |
| 3 | 21 |
| 5 | 2 |
| 6 | 2 |
| 7 | 5 |
| 8 | 16 |
| 9 | 10 |

Per-app table: `abrg/output/v2_extended/e4_phase0/sessions_per_app.csv`

## 0b — Split eligibility (6 ref / 2 test)

| Threshold | n apps |
|---|---:|
| ≥6 sessions | **33** |
| ≥8 sessions (required for 6/2) | **26** |
| ≥10 sessions | **0** |
| ≥15 sessions | **0** |

Apps with ≥8: `abrg/output/v2_extended/e4_phase0/inventory.json` → `0b.apps_ge_8` (26 ids).

## 0c — Per-session graph density

### Export-time topology (`sessions_index.jsonl`)

Mapped events/session: min=1.0, p25=26.8, median=84.0, p75=254.0, max=1941.0.
Edges/graph: median=2.0, IQR=5.0 (sum=1384.0, mean=4.05, frac_zero=0.158).
Active nodes/graph: median=3.0, IQR=2.0.
_Export-time build_session_graph topology fields on sessions_index; differs from Chapter B Run2 update_graph_sequence (med edges 2 vs 5)._

### Chapter B Run2 (AndroCT-aligned `update_graph_sequence`)
Edges: median=5.0, IQR=8.0 (n=342). Path: `abrg/output/v2_chapter_b/run2_comparison/v2_per_session.csv`

### Cross-check vs earlier v2 (~579 edges / ~728 snapshots)

- Cited figure: **NOT FOUND in persisted artifacts (see W_selection.md)**.
- Closest persisted: `norm_ab_v2` total_snapshots=731, gae_eligible_snapshots=565, GAE edge sum=2888.0, mean edges/snap=5.11, median=3.00.
- v2_extended export-time edges/session mean=4.05 vs norm_ab_v2 GAE edges/snap mean=5.11 (Δ=-1.06; different unit: whole session vs 60s window).
- Original v2 trainable window edges: median=2.0, mean=4.56 (n_trainable=634).
- v2_extended whole-session edge sum=1384.0 over n=342 usable sessions (export-time).

## 0d — Inter-session timing

Elapsed wall-clock between consecutive usable sessions (same app): median=4.86h, IQR=8.10h, p10=7.6min, p90=29.09d, min=7.4min, max=32.64d (n_gaps=283).
Apps with all usable sessions on a **single calendar day**: **22** / 59; **multi-day**: **37**.

**Recency reading:** median gap 4.86 h — hours-scale separation. Verdict: **MARGINAL**.
Gaps CSV: `abrg/output/v2_extended/e4_phase0/inter_session_gaps.csv`

## 0e — Vocabulary comparability

- Mapped kept-set equals **22-node `GRAPH_CATEGORY_UNIVERSE`**: True (scanned 342 usable sessions).
- Dropped hook categories observed: `{'lifecycle': 1652, 'reflection': 827700, 'navigation': 226}`
- Unknown outside taxonomy: `[]`

Same 22-node GRAPH_CATEGORY_UNIVERSE labels as AndroCT. Sensor differs: ContextDroid Frida hooks (hook_apis.js v3) emit category at capture time; AndroCT/DroidFax maps Soot callee strings post hoc via api_category_map. Event semantics (what fires a 'network' or 'ipc_intents' event) are instrumentation-specific — label set matches, generative process does not. E4 stats share the node vocabulary with E0/E2 but are NOT interchangeable as samples from the same observation process.

## 0f — Intra-session event timing (NEW)

Intra-session timing requires reading events.jsonl timestamps (not in sessions_index). Zero-edge under k=5 requires in-memory update_graph_sequence on each time-window's mapped category stream — no corpus graph rebuild; measurement-only.

- Session duration: median=460.9s, IQR=15.3s (n=342).
- Mapped events / minute: median=11.03, IQR=29.21.
- Inter-mapped-event gap: median=7.0ms, IQR=34.0ms, p90=1125.0ms, max=256698.0ms.
- Idle fraction of session wall-clock (share of 1s bins with no mapped event): median=0.959, IQR=0.057.

### Candidate time windows

| W | med windows/sess | med frac zero mapped | med frac one mapped | med frac zero edges (k=5) |
|---:|---:|---:|---:|---:|
| 10s | 47.0 | 0.723 | 0.043 | 0.935 |
| 35s | 14.0 | 0.462 | 0.071 | 0.786 |
| 60s | 8.0 | 0.250 | 0.125 | 0.625 |
| 120s | 4.0 | 0.000 | 0.000 | 0.500 |

Best empty-mapped median: W=120s → 0.000.
Per-session timing: `abrg/output/v2_extended/e4_phase0/session_timing.csv`

## Stop

Phase 0 complete. **Do not proceed to E4 Phase 1** from this report alone — human review of the three viability verdicts first.

---

Generated 2026-08-21T21:13:40.246924+00:00. Machine-readable: `abrg/output/v2_extended/e4_phase0/inventory.json`.
