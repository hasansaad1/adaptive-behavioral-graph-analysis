# Campaign: exp_window_sec

## exp_window_sec/w120_weighted — 2026-08-04
- Axis: processing window length 60s → 120s
- ratio: 1.0704 vs 1.20 (Δ −0.1296); train_med 0.6541 vs 0.5842; test_med 0.7001 vs 0.7010
- Skeptic: invalid (dead-end; false ratio win via train_med ↑)
- Process: process_incomplete (no validate_reproduce)
- Research: abrg/output/exp_window_sec/w120_weighted/RESEARCH_NOTE.md
- Next: stop

## exp_window_sec/w30_weighted — 2026-08-04
- Axis: processing window length 60s → 30s
- ratio: 1.187 vs 1.20 (Δ −0.013); train_med 0.5854 vs 0.5842; test_med 0.6948 vs 0.7010
- Skeptic: improve (marginal/weak; not false win; opposite of w120)
- Reproduce: ok (validate_reproduce --mode cli)
- Next: stop / await next axis
