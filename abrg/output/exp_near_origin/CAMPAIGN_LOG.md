# Campaign: exp_near_origin

**Origin champion:** `exp_adaptive_ratio/w35_h64_weighted` — 0.5588 / 0.6398 / ratio **1.145**

## exp_near_origin/wd1e5_weighted — 2026-08-04
- Axis: GAE weight_decay 0→1e-5 @ w35 h64 e300 edge_weight=on
- ratio: 1.217 vs 1.145 (Δ +0.072); train_med 0.5617 vs 0.5588; test_med 0.6836 vs 0.6398
- Skeptic: regress (both medians worse, test much more; keep weight_decay=0)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: pattern like wd=1e-4; N 567/161 snaps, 32/8 apps
- Next: hold weight_decay=0; batch 1 closed — champion unchanged

## exp_near_origin/e280_weighted — 2026-08-04
- Axis: GAE epochs 300→280 @ w35 h64 edge_weight=on
- ratio: 1.204 vs 1.145 (Δ +0.059); train_med 0.5603 vs 0.5588; test_med 0.6747 vs 0.6398
- Skeptic: regress (test worse, train flat; keep epochs=300)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: early stop does not help; N 567/161 snaps, 32/8 apps
- Next: keep epochs=300

## exp_near_origin/w34_h64_weighted — 2026-08-04
- Axis: window_sec 35→34 @ h=64 edge_weight=on epochs=300
- ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5934 vs 0.5588; test_med 0.7417 vs 0.6398
- Skeptic: regress (both medians worse; keep window=35)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: densification below 35 s regresses; N 574/163 snaps, 32/8 apps
- Next: keep window=35

## exp_near_origin/w36_h64_weighted — 2026-08-04
- Axis: window_sec 35→36 @ h=64 edge_weight=on epochs=300
- ratio: 0.971 vs 1.145 (Δ −0.174); train_med 0.9460 vs 0.5588; test_med 0.9189 vs 0.6398
- Skeptic: **invalid** (false win — ratio down but both medians much worse; corpus 567/161→550/159)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: reject as improve despite lower ratio; keep window=35
- Next: do not adopt w36

## exp_near_origin/finalsnap_weighted — 2026-08-04
- Axis: snapshots on→off (final graph per session only) @ w35 h64 edge_weight=on
- ratio: 0.815 vs 1.145 (Δ −0.330); train_med 0.6928 vs 0.5588; test_med 0.5646 vs 0.6398
- Skeptic: invalid (n 92/24 vs champion 567/161 — incomparable corpus unit; train worse)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: one final graph/session vs multi-window trajectory; keep snapshots=on
- Next: campaign close — champion unchanged

## exp_near_origin/lam005_weighted — 2026-08-04
- Axis: lambda_rec 0.01→0.005 @ w35 h64 edge_weight=on (replaced planned w32 probe)
- ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5626 vs 0.5588; test_med 0.7032 vs 0.6398
- Skeptic: regress (test worse; keep λ=0.01)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: w32_h64 skipped after w34/w36 settled window peak at 35 s; N 567/161 unchanged
- Next: campaign closed — champion unchanged

## exp_near_origin/k7_weighted — 2026-08-04
- Axis: K_BURST 5→7 @ w35 h64 e300 edge_weight=on δ=5
- ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5592 vs 0.5588; test_med 0.6990 vs 0.6398
- Skeptic: regress (test worse, train flat; keep k=5)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: N unchanged 567/161 snaps, 32/8 apps
- Next: keep k=5

## exp_near_origin/delta7_weighted — 2026-08-04
- Axis: DELTA_SEC 5→7 @ w35 h64 e300 edge_weight=on k=5
- ratio: 1.000 vs 1.145 (Δ −0.145); train_med 0.5569 vs 0.5588; test_med 0.5569 vs 0.6398
- Skeptic: **invalid** (n 612/140 vs origin 567/161; eligibility/split shifted; sticky median train==test)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: gae_eligible 728→752; not comparable to origin
- Next: keep δ=5; do not promote

## exp_near_origin/k3_weighted — 2026-08-04
- Axis: K_BURST 5→3 @ w35 h64 e300 edge_weight=on δ=5
- ratio: 0.936 vs 1.145 (Δ −0.209); train_med 0.5991 vs 0.5588; test_med 0.5607 vs 0.6398
- Skeptic: **invalid** (false-ish win — ratio down but train_med worse; keep k=5)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: N unchanged 567/161 snaps, 32/8 apps
- Next: keep k=5

## exp_near_origin/edge_wrec_weighted — 2026-08-04
- Axis: edge_weight_channel w_cum→w_rec @ w35 h64 e300 k=5 δ=5 edge_weight=on
- ratio: 1.000 vs 1.145 (Δ −0.145); train_med 0.5584 vs 0.5588; test_med 0.5584 vs 0.6398
- Skeptic: **improve (provisional)** — train held, test_med clearly better; sticky-median caveat (train==test)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: N unchanged 567/161; candidate channel=w_rec; champion path not rewritten until loops 9–10
- Next: provisional w_rec pin for remaining loops; await finalsnap + w32
