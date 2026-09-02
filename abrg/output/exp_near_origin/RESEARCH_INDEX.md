# Research index: exp_near_origin

Campaign north star: test/train median reconstruction-error ratio under stochastic scorer; origin champion = `exp_adaptive_ratio/w35_h64_weighted` (1.145).

## exp_near_origin/wd1e5_weighted — 2026-08-04
- Question: At origin pin, does very mild weight_decay=1e-5 improve ratio vs wd=0?
- Axis: weight_decay 0 → 1e-5 @ w35 h64 e300 edge_weight=on
- Ratio: 1.217 vs 1.145 (Δ +0.072); train_med 0.5617; test_med 0.6836
- Skeptic: regress (keep weight_decay=0) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/wd1e5_weighted/RESEARCH_NOTE.md`

## exp_near_origin/e280_weighted — 2026-08-04
- Question: Does stopping at epoch 280 vs 300 improve ratio at origin pin?
- Axis: epochs 300 → 280 @ w35 h64 edge_weight=on
- Ratio: 1.204 vs 1.145 (Δ +0.059); train_med 0.5603; test_med 0.6747
- Skeptic: regress (keep epochs=300) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/e280_weighted/RESEARCH_NOTE.md`

## exp_near_origin/w34_h64_weighted — 2026-08-04
- Question: Does −1 s window densification (35→34) beat origin at h64?
- Axis: window_sec 35 → 34 @ h=64 edge_weight=on epochs=300
- Ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5934; test_med 0.7417
- Skeptic: regress (keep window=35) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/w34_h64_weighted/RESEARCH_NOTE.md`

## exp_near_origin/w36_h64_weighted — 2026-08-04
- Question: Does +1 s coarsening (35→36) beat origin at h64?
- Axis: window_sec 35 → 36 @ h=64 edge_weight=on epochs=300
- Ratio: 0.971 vs 1.145 (Δ −0.174); train_med 0.9460; test_med 0.9189
- Skeptic: **invalid** (false win; keep window=35) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/w36_h64_weighted/RESEARCH_NOTE.md`

## exp_near_origin/finalsnap_weighted — 2026-08-04
- Question: Does final-session-only graphing beat multi-window snapshots at origin?
- Axis: snapshots on → off (final only) @ w35 h64 edge_weight=on
- Ratio: 0.815 vs 1.145 (Δ −0.330); train_med 0.6928; test_med 0.5646; n 92/24
- Skeptic: invalid (incomparable n; keep snapshots=on) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/finalsnap_weighted/RESEARCH_NOTE.md`

## exp_near_origin/lam005_weighted — 2026-08-04
- Question: Does lower λ_rec (0.005 vs 0.01) improve ratio at origin pin?
- Axis: lambda_rec 0.01 → 0.005 @ w35 h64 edge_weight=on
- Ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5626; test_med 0.7032
- Skeptic: regress (keep λ=0.01) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/lam005_weighted/RESEARCH_NOTE.md`

## exp_near_origin/k7_weighted — 2026-08-04
- Question: Does looser burst grouping (k=5→7) improve ratio at origin pin?
- Axis: K_BURST 5 → 7 @ w35 h64 e300 edge_weight=on δ=5
- Ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5592; test_med 0.6990
- Skeptic: regress (keep k=5) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/k7_weighted/RESEARCH_NOTE.md`

## exp_near_origin/delta7_weighted — 2026-08-04
- Question: Does wider temporal delta (δ=5→7) improve ratio at origin pin?
- Axis: DELTA_SEC 5 → 7 @ w35 h64 e300 edge_weight=on k=5
- Ratio: 1.000 vs 1.145 (Δ −0.145); train_med 0.5569; test_med 0.5569; n 612/140
- Skeptic: **invalid** (corpus/split shift; keep δ=5) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/delta7_weighted/RESEARCH_NOTE.md`

## exp_near_origin/k3_weighted — 2026-08-04
- Question: Does tighter burst grouping (k=5→3) improve ratio at origin pin?
- Axis: K_BURST 5 → 3 @ w35 h64 e300 edge_weight=on δ=5
- Ratio: 0.936 vs 1.145 (Δ −0.209); train_med 0.5991; test_med 0.5607
- Skeptic: **invalid** (false-ish win; keep k=5) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/k3_weighted/RESEARCH_NOTE.md`

## exp_near_origin/edge_wrec_weighted — 2026-08-04
- Question: Does w_rec edge-weight channel beat w_cum at origin pin with train held?
- Axis: edge_weight_channel w_cum → w_rec @ w35 h64 e300 k=5 δ=5 edge_weight=on
- Ratio: 1.000 vs 1.145 (Δ −0.145); train_med 0.5584; test_med 0.5584
- Skeptic: **improve (provisional)** sticky-median caveat | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_near_origin/edge_wrec_weighted/RESEARCH_NOTE.md`
