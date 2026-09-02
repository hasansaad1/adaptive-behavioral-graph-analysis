# Research index: exp_window_sec

Campaign north star: test/train median reconstruction-error ratio under stochastic scorer; pins dataset=v2, seed=42, edge_weight=on unless stated as axis.

## exp_window_sec/w120_weighted — 2026-08-04
- Question: Does lengthening the multi-window cumulative processing window from 60 s to 120 s improve train→test recon generalization without worse train fit?
- Axis: processing window length 60 s → 120 s
- Ratio: 1.0704 vs 1.20 baseline (Δ −0.1296); train_med 0.6541 vs 0.5842; test_med 0.7001 vs 0.7010
- Skeptic: invalid (false ratio win via train_med ↑, test flat) | Process: process_incomplete (validate_reproduce not run)
- Note: `abrg/output/exp_window_sec/w120_weighted/RESEARCH_NOTE.md`
