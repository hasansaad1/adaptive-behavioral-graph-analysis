# Research index: exp_adaptive_ratio

Campaign north star: test/train median reconstruction-error ratio under stochastic scorer; pins dataset=v2, seed=42, edge_weight=on unless stated as axis.

## exp_adaptive_ratio/w35_h64_wd1e4_weighted — 2026-08-04
- Question: At the campaign-best weighted w35 h64 e300 pin, does adding GAE weight_decay=1e-4 improve stochastic recon ratio via regularization, or does wd=0 remain optimal?
- Axis: GAE weight_decay 0 → 1e-4 @ w35 h64 e300 edge_weight=on
- Ratio: 1.203 vs 1.145 baseline (Δ +0.058); train_med 0.5708 vs 0.5588; test_med 0.6865 vs 0.6398
- Skeptic: regress (both medians worse, test much more; keep weight_decay=0 @ w35 h64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w35_h64_wd1e4_weighted/RESEARCH_NOTE.md`
- Path (context): w35 h64 wd=0 1.145 (champion) → w35 wd=1e-4 1.203 (regress); final loop 12/12 — campaign closed

## exp_adaptive_ratio/w35_h64_e320_weighted — 2026-08-04
- Question: At the campaign-best weighted w35 h64 e300 pin, does raising GAE epochs from 300 to 320 improve stochastic recon ratio, or reproduce the w30 e450/e600 overfit pathology?
- Axis: GAE epochs 300 → 320 @ w35 h64 edge_weight=on
- Ratio: 1.250 vs 1.145 baseline (Δ +0.105); train_med 0.5600 vs 0.5588; test_med 0.7000 vs 0.6398
- Skeptic: regress (overfit: test ↑ much more than train; keep epochs=300 @ w35 h64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w35_h64_e320_weighted/RESEARCH_NOTE.md`
- Path (context): w35 h64 e300 1.145 (champion) → w35 e320 1.250 (regress); epoch overfit confirmed at w35 mirroring w30 e450/e600

## exp_adaptive_ratio/w35_h48_weighted — 2026-08-04
- Question: At the campaign-best weighted w35 h64 e300 pin, does reducing GAE hidden capacity from 64 to 48 improve stochastic recon ratio (less overfit), or does h64 remain the capacity sweet spot at w35?
- Axis: GAE hidden 64 → 48 @ w35 edge_weight=on epochs=300
- Ratio: 1.203 vs 1.145 baseline (Δ +0.058); train_med 0.5677 vs 0.5588; test_med 0.6828 vs 0.6398
- Skeptic: regress (both medians worse, test much more; keep hidden=64 @ w35) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w35_h48_weighted/RESEARCH_NOTE.md`
- Path (context): w35 h64 1.145 (champion) → w35 h48 1.203 (regress); capacity peak stable at h64 across w30/w35

## exp_adaptive_ratio/w35_h64_unweighted — 2026-08-04
- Question: At the campaign-best weighted w35 h64 e300 pin, does turning encoder edge weights off improve (or preserve) stochastic recon ratio, as tested at w30?
- Axis: encoder edge_weight_in_encoder on → off @ w35 h64 e300
- Ratio: 1.234 vs 1.145 baseline (Δ +0.089); train_med 0.5573 vs 0.5588; test_med 0.6877 vs 0.6398
- Skeptic: regress (test much worse, ratio up; keep edge_weight=on @ w35 h64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w35_h64_unweighted/RESEARCH_NOTE.md`
- Path (context): w35 weighted 1.145 (champion) → w35 unweighted 1.234 (regress); extends w30_unweighted finding to h64

## exp_adaptive_ratio/w40_h64_weighted — 2026-08-04
- Question: At the campaign-best weighted w35 h64 e300 pin, does further coarsening the window from 35 s to 40 s continue the w35 improve, or has the window surface peaked?
- Axis: window_sec 35 → 40 @ h=64 edge_weight=on epochs=300
- Ratio: 1.222 vs 1.145 baseline (Δ +0.077); train_med 0.5730 vs 0.5588; test_med 0.7004 vs 0.6398
- Skeptic: regress (both medians worse, test much more; peak at w35; stop coarsening; hold window=35 at h64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w40_h64_weighted/RESEARCH_NOTE.md`
- Path (context): w25 1.250 (regress) → w35 1.145 (improve/champion) → w40 1.222 (regress); window sweet spot at 35 s at h64

## exp_adaptive_ratio/w35_h64_weighted — 2026-08-04
- Question: At the campaign-best weighted w30 h64 e300 pin, does mild coarsening the window from 30 s to 35 s improve stochastic recon ratio, complementing the sub-30 regress at h64?
- Axis: window_sec 30 → 35 @ h=64 edge_weight=on epochs=300
- Ratio: 1.145 vs 1.158 baseline (Δ −0.013); train_med 0.5588 vs 0.5614; test_med 0.6398 vs 0.6500
- Skeptic: improve (both medians down, test more; new champion; adopt window=35 at h64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w35_h64_weighted/RESEARCH_NOTE.md`
- Path (context): w30 h64 1.158 (prior best) → w25 1.250 (regress) → w35 1.145 (improve); window sweet spot above 30 s at h64

## exp_adaptive_ratio/w25_h64_weighted — 2026-08-04
- Question: At the campaign-best weighted w30 h64 e300 pin, does further densifying the window from 30 s to 25 s improve stochastic recon ratio, or reproduce the sub-30 overfit seen at lower capacity?
- Axis: window_sec 30 → 25 @ h=64 edge_weight=on epochs=300
- Ratio: 1.250 vs 1.158 baseline (Δ +0.092); train_med 0.5596 vs 0.5614; test_med 0.6995 vs 0.6500
- Skeptic: regress (overfit: train ↓ slightly, test ↑, ratio ↑; densification win was at lower capacity; keep window=30 at h64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w25_h64_weighted/RESEARCH_NOTE.md`

## exp_adaptive_ratio/w30_h64_e450_weighted — 2026-08-04
- Question: At the campaign-best weighted w30 h64 e300 pin, does raising GAE epochs from 300 to 450 improve stochastic recon ratio, or reproduce the e600 overfit pathology?
- Axis: epochs 300 → 450 @ window_sec=30 h=64 edge_weight=on
- Ratio: 1.250 vs 1.158 baseline (Δ +0.092); train_med 0.5578 vs 0.5614; test_med 0.6973 vs 0.6500
- Skeptic: regress (overfit: train ↓ slightly, test ↑, ratio ↑; same pathology as e600; keep epochs=300) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h64_e450_weighted/RESEARCH_NOTE.md`
- Path (context): h64 e300 1.158 (best) → e450 1.250 (regress) / e600@h16 1.250 (regress); stop epoch probing

## exp_adaptive_ratio/w15_weighted — 2026-08-04
- Question: Does further densifying the multi-window cumulative processing window from 60 s to 15 s improve train→test recon generalization after w30’s marginal improve?
- Axis: processing window length 60 s → 15 s
- Ratio: 1.250 vs 1.20 baseline (Δ +0.050); train_med 0.5638 vs 0.5842; test_med 0.7047 vs 0.7010
- Skeptic: regress (overfit: train ↓, test ↑ slightly, ratio ↑) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w15_weighted/RESEARCH_NOTE.md`

## exp_adaptive_ratio/w45_weighted — 2026-08-04
- Question: Does an intermediate 45 s window (between 60 s pin and w30’s marginal improve) change train→test recon ratio, or is the surface flat near the pin?
- Axis: processing window length 60 s → 45 s
- Ratio: 1.200 vs 1.20 baseline (Δ ≈0); train_med 0.5854 vs 0.5842; test_med 0.7025 vs 0.7010
- Skeptic: neutral (flat vs pin; interpolates w30 1.187 and baseline 1.20) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w45_weighted/RESEARCH_NOTE.md`

## exp_adaptive_ratio/w30_unweighted — 2026-08-04
- Question: At the ~30 s densification sweet spot, does turning encoder edge weights off improve (or preserve) stochastic recon ratio vs weighted w30?
- Axis: encoder edge_weight_in_encoder on → off @ window_sec=30
- Ratio: 1.197 vs 1.187 baseline (Δ +0.010); train_med 0.5814 vs 0.5854; test_med 0.6959 vs 0.6948
- Skeptic: regress (keep edge_weight=on at w30) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_unweighted/RESEARCH_NOTE.md`

## exp_adaptive_ratio/w30_e600_weighted — 2026-08-04
- Question: At weighted window_sec=30, does doubling GAE epochs from 300 to 600 improve stochastic recon ratio without a train-only win?
- Axis: epochs 300 → 600 @ window_sec=30 edge_weight=on
- Ratio: 1.250 vs 1.187 baseline (Δ +0.063); train_med 0.5599 vs 0.5854; test_med 0.6998 vs 0.6948
- Skeptic: regress (overfit: train ↓, test ~flat, ratio ↑; keep epochs=300 at w30) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_e600_weighted/RESEARCH_NOTE.md`

## exp_adaptive_ratio/w30_h32_weighted — 2026-08-04
- Question: At weighted window_sec=30 e300, does doubling GAE hidden capacity from 16 to 32 improve stochastic recon ratio without a train-only win?
- Axis: GAE hidden 16 → 32 @ window_sec=30 edge_weight=on epochs=300
- Ratio: 1.180 vs 1.187 baseline (Δ ≈ −0.007); train_med 0.5867 vs 0.5854; test_med 0.6922 vs 0.6948
- Skeptic: improve (marginal; new campaign best capacity pin) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h32_weighted/RESEARCH_NOTE.md`

## exp_adaptive_ratio/w30_h64_weighted — 2026-08-04
- Question: At weighted window_sec=30 e300, does doubling GAE hidden capacity again from 32 to 64 improve stochastic recon ratio without a train-only win?
- Axis: GAE hidden 32 → 64 @ window_sec=30 edge_weight=on epochs=300
- Ratio: 1.158 vs 1.180 baseline (Δ −0.022); train_med 0.5614 vs 0.5867; test_med 0.6500 vs 0.6922
- Skeptic: improve (campaign best; both medians down, test more) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h64_weighted/RESEARCH_NOTE.md`
- Path (context): w60 weighted 1.20 → w30 1.187 → h32 1.180 → h64 1.158

## exp_adaptive_ratio/w30_h64_lr005_weighted — 2026-08-04
- Question: At the campaign-best weighted w30 h64 e300 pin, does halving GAE learning rate from 0.01 to 0.005 improve stochastic recon ratio, or does slower optimization underfit within 300 epochs?
- Axis: GAE lr 0.01 → 0.005 @ window_sec=30 h=64 edge_weight=on epochs=300
- Ratio: 1.215 vs 1.158 baseline (Δ +0.057); train_med 0.5934 vs 0.5614; test_med 0.7211 vs 0.6500
- Skeptic: regress (both medians worse, ratio worse; keep lr=0.01) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h64_lr005_weighted/RESEARCH_NOTE.md`
- Path (context): h64 lr=0.01 1.158 (best) → lr=0.005 1.215 (regress/underfit)

## exp_adaptive_ratio/w30_h128_weighted — 2026-08-04
- Question: At weighted window_sec=30 e300, does doubling GAE hidden capacity again from 64 to 128 improve stochastic recon ratio, or has capacity saturated at h=64?
- Axis: GAE hidden 64 → 128 @ window_sec=30 edge_weight=on epochs=300
- Ratio: 1.200 vs 1.158 baseline (Δ +0.042); train_med 0.5857 vs 0.5614; test_med 0.7029 vs 0.6500
- Skeptic: regress (both medians worse, ratio worse; keep hidden=64) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h128_weighted/RESEARCH_NOTE.md`
- Path (context): h64 1.158 (best) → h128 1.200 (regress); capacity ceiling at h=64

## exp_adaptive_ratio/w30_h64_lr02_weighted — 2026-08-04
- Question: At the campaign-best weighted w30 h64 e300 pin, does doubling GAE learning rate from 0.01 to 0.02 improve stochastic recon ratio, or does faster optimization overshoot/destabilize within 300 epochs?
- Axis: GAE lr 0.01 → 0.02 @ window_sec=30 h=64 edge_weight=on epochs=300
- Ratio: 1.193 vs 1.158 baseline (Δ +0.035); train_med 0.5837 vs 0.5614; test_med 0.6966 vs 0.6500
- Skeptic: regress (both medians worse, ratio worse; keep lr=0.01) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h64_lr02_weighted/RESEARCH_NOTE.md`
- Path (context): h64 lr=0.01 1.158 (best) → lr=0.005 1.215 (underfit) / lr=0.02 1.193 (overshoot); stop lr probing

## exp_adaptive_ratio/w30_h96_weighted — 2026-08-04
- Question: At weighted window_sec=30 e300, does intermediate GAE hidden capacity (64→96) improve stochastic recon ratio, or is h=64 already the capacity peak?
- Axis: GAE hidden 64 → 96 @ window_sec=30 edge_weight=on epochs=300
- Ratio: 0.318 vs 1.158 baseline (Δ −0.840); train_med 2.2091 vs 0.5614; test_med 0.7021 vs 0.6500
- Skeptic: invalid (false ratio win — train collapsed; ratio alone meaningless) | Process: process_valid (reproduce ok)
- Note: `abrg/output/exp_adaptive_ratio/w30_h96_weighted/RESEARCH_NOTE.md`
- Path (context): h64 1.158 (best) → h96 0.318 (invalid/pathological) → h128 1.200 (regress); capacity peak at h=64
