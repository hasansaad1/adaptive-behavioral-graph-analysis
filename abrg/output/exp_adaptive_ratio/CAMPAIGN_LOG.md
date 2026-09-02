# Campaign: exp_adaptive_ratio

## exp_adaptive_ratio/w35_h64_wd1e4_weighted — 2026-08-04
- Axis: GAE weight_decay 0→1e-4 @ w35 h64 e300 edge_weight=on
- ratio: 1.203 vs 1.145 (Δ +0.058); train_med 0.5708 vs 0.5588; test_med 0.6865 vs 0.6398
- Skeptic: regress (both medians worse; keep weight_decay=0)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w35_h64_weighted; test much worse (+0.047), train worse (+0.012) → genuine regress; mild L2 does not help at champion pin; N 567/161 snaps, 32/8 apps
- Next: **campaign closed** — locked pins w35 h64 e300 lr=0.01 edge_weight=on wd=0; champion w35_h64_weighted ratio 1.145

## exp_adaptive_ratio/w35_h64_e320_weighted — 2026-08-04
- Axis: GAE epochs 300→320 @ w35 h64 edge_weight=on
- ratio: 1.250 vs 1.145 (Δ +0.105); train_med 0.5600 vs 0.5588; test_med 0.7000 vs 0.6398
- Skeptic: regress (overfit)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w35_h64_weighted; test much worse (+0.060), mild train↑; classic overfit matching w30 e450/e600 (ratio 1.250); keep epochs=300; N 567/161 snaps, 32/8 apps
- Next: stop epoch probing (hold e300 @ w35 h64 weighted)

## exp_adaptive_ratio/w35_h48_weighted — 2026-08-04
- Axis: GAE hidden 64→48 @ w35 edge_weight=on epochs=300
- ratio: 1.203 vs 1.145 (Δ +0.058); train_med 0.5677 vs 0.5588; test_med 0.6828 vs 0.6398
- Skeptic: regress
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w35_h64_weighted; both medians worse (test much more) → genuine regress; capacity peak at h64 confirmed at w35; keep hidden=64; N 567/161 snaps, 32/8 apps
- Next: hold hidden=64 @ w35 weighted e300; stop capacity probing below h64

## exp_adaptive_ratio/w35_h64_unweighted — 2026-08-04
- Axis: encoder edge_weight_in_encoder on→off @ w35 h64 e300
- ratio: 1.234 vs 1.145 (Δ +0.089); train_med 0.5573 vs 0.5588; test_med 0.6877 vs 0.6398
- Skeptic: regress
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w35_h64_weighted; test much worse, ratio up; train flat-to-slightly-better → genuine regress; keep edge_weight=on @ w35 h64 e300; N 567/161 snaps, 32/8 apps
- Next: keep edge_weight=on @ w35 h64 e300; next axis via experiment-designer

## exp_adaptive_ratio/w40_h64_weighted — 2026-08-04
- Axis: window_sec 35→40 @ h=64 edge_weight=on epochs=300
- ratio: 1.222 vs 1.145 (Δ +0.077); train_med 0.5730 vs 0.5588; test_med 0.7004 vs 0.6398
- Skeptic: regress
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w35_h64_weighted; both medians worse (test much more) → genuine regress; peak window at 35 s; stop coarsening; N 528/152 snaps, 32/8 apps
- Next: hold window=35 @ h64 weighted e300; stop window probing at h64

## exp_adaptive_ratio/w35_h64_weighted — 2026-08-04
- Axis: window_sec 30→35 @ h=64 edge_weight=on epochs=300
- ratio: 1.145 vs 1.158 (Δ −0.013); train_med 0.5588 vs 0.5614; test_med 0.6398 vs 0.6500
- Skeptic: improve
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; both medians improved (test more) → genuine improve; new champion candidate; mild coarsening helps at h64; adopt window=35 pin; N 567/161 snaps, 32/8 apps
- Next: hold window=35 @ h64 weighted e300; stop window probing unless designer proposes bounded follow-up

## exp_adaptive_ratio/w25_h64_weighted — 2026-08-04
- Axis: window_sec 30→25 @ h=64 edge_weight=on epochs=300
- ratio: 1.250 vs 1.158 (Δ +0.092); train_med 0.5596 vs 0.5614; test_med 0.6995 vs 0.6500
- Skeptic: regress (overfit)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; densification below 30 s overfits at h64; densification win was at lower capacity; N 672/185 snaps, 32/8 apps
- Next: keep window=30 @ h64 weighted e300; stop sub-30 window probing at h64

## exp_adaptive_ratio/w30_h64_e450_weighted — 2026-08-04
- Axis: epochs 300→450 @ window_sec=30 h=64 edge_weight=on
- ratio: 1.250 vs 1.158 (Δ +0.092); train_med 0.5578 vs 0.5614; test_med 0.6973 vs 0.6500
- Skeptic: regress (overfit)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; same pathology as w30_e600_weighted (train ↓ slightly, test ↑, ratio 1.250); keep epochs=300; N 605/173 snaps, 32/8 apps
- Next: stop epoch probing (hold e300 @ w30 h64 weighted)

## exp_adaptive_ratio/w15_weighted — 2026-08-04
- Axis: window_sec 60→15
- ratio: 1.250 vs 1.20 (Δ +0.050); train_med 0.5638 vs 0.5842; test_med 0.7047 vs 0.7010
- Skeptic: regress (overfit)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30 marginal improve — further densification overfit
- Next: stop shortening; try w45 band test

## exp_adaptive_ratio/w45_weighted — 2026-08-04
- Axis: window_sec 60→45
- ratio: 1.200 vs 1.20 (Δ ≈0); train_med 0.5854 vs 0.5842; test_med 0.7025 vs 0.7010
- Skeptic: neutral
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: flat vs 60s weighted baseline; interpolates w30 (1.187) and pin 1.20; sweet spot looks localized near ~30s; N 495/140 snaps, 32/8 apps
- Next: stop further window probing unless new design; prefer non-window axis via experiment-designer

## exp_adaptive_ratio/w30_unweighted — 2026-08-04
- Axis: encoder edge_weight_in_encoder on→off @ window_sec=30
- ratio: 1.197 vs 1.187 (Δ +0.010); train_med 0.5814; test_med 0.6959
- Skeptic: regress
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs exp_window_sec/w30_weighted; unweighted worse at 30s sweet spot; keep edge_weight=on at w30; N 605/173 snaps, 32/8 apps
- Next: next axis via experiment-designer (hold edge_weight=on @ w30 pin)

## exp_adaptive_ratio/w30_e600_weighted — 2026-08-04
- Axis: epochs 300→600 @ window_sec=30 edge_weight=on
- ratio: 1.250 vs 1.187 (Δ +0.063); train_med 0.5599; test_med 0.6998
- Skeptic: regress (overfit)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs exp_window_sec/w30_weighted; train fit improved, test flat → overfit; keep epochs=300 at w30 pin; N 605/173 snaps, 32/8 apps
- Next: none (hold epochs=300 at w30; next axis via experiment-designer)

## exp_adaptive_ratio/w30_h32_weighted — 2026-08-04
- Axis: GAE hidden 16→32 @ window_sec=30 edge_weight=on epochs=300
- ratio: 1.180 vs 1.187 (Δ ≈−0.007); train_med 0.5867; test_med 0.6922
- Skeptic: improve (marginal)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs exp_window_sec/w30_weighted (h16); new best capacity pin; N 605/173 snaps, 32/8 apps
- Next: next axis via experiment-designer (hold h=32 @ w30 weighted e300, or probe further capacity as its own run)

## exp_adaptive_ratio/w30_h64_weighted — 2026-08-04
- Axis: GAE hidden 32→64 @ window_sec=30 edge_weight=on epochs=300
- ratio: 1.158 vs 1.180 (Δ −0.022); train_med 0.5614; test_med 0.6500
- Skeptic: improve
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h32_weighted; new campaign best; both medians improved (test more); N 605/173 snaps, 32/8 apps; path w60 1.20 → w30 1.187 → h32 1.180 → h64 1.158; final loop of 6
- Next: stop (hold h=64 @ w30 weighted e300)

## exp_adaptive_ratio/w30_h64_lr005_weighted — 2026-08-04
- Axis: GAE lr 0.01→0.005 @ window_sec=30 h=64 edge_weight=on epochs=300
- ratio: 1.215 vs 1.158 (Δ +0.057); train_med 0.5934 vs 0.5614; test_med 0.7211 vs 0.6500
- Skeptic: regress (both medians worse, ratio worse; underfit at 300ep)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; slower lr underfits; keep lr=0.01; N 605/173 snaps, 32/8 apps
- Next: stop (hold lr=0.01 @ w30 h64 weighted e300)

## exp_adaptive_ratio/w30_h128_weighted — 2026-08-04
- Axis: GAE hidden 64→128 @ window_sec=30 edge_weight=on epochs=300
- ratio: 1.200 vs 1.158 (Δ +0.042); train_med 0.5857 vs 0.5614; test_med 0.7029 vs 0.6500
- Skeptic: regress (both medians worse, ratio worse)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; capacity ceiling at h64; N 605/173 snaps, 32/8 apps
- Next: stop (hold h=64 @ w30 weighted e300)

## exp_adaptive_ratio/w30_h64_lr02_weighted — 2026-08-04
- Axis: GAE lr 0.01→0.02 @ window_sec=30 h=64 edge_weight=on epochs=300
- ratio: 1.193 vs 1.158 (Δ +0.035); train_med 0.5837 vs 0.5614; test_med 0.6966 vs 0.6500
- Skeptic: regress (both medians worse, ratio worse)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; faster lr overshoots/destabilizes at 300ep; lr=0.01 sweet spot (0.005 and 0.02 both worse); N 605/173 snaps, 32/8 apps
- Next: stop lr probing (hold lr=0.01 @ w30 h64 weighted e300)

## exp_adaptive_ratio/w30_h96_weighted — 2026-08-04
- Axis: GAE hidden 64→96 @ window_sec=30 edge_weight=on epochs=300
- ratio: 0.318 vs 1.158 (Δ −0.840); train_med 2.2091 vs 0.5614; test_med 0.7021 vs 0.6500
- Skeptic: invalid (false ratio win — train collapsed; ratio alone meaningless)
- Graph audit: landed
- Reproduce: ok
- Process: process_valid
- Research: RESEARCH_NOTE.md
- Notes: vs w30_h64_weighted; pathological training collapse at h96 (train_med +294%, test +8%); capacity peak at h64; N 605/173 snaps, 32/8 apps
- Next: stop (hold h=64 @ w30 weighted e300; do not adopt h96)
