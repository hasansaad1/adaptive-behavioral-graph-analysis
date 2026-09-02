# exp_near_origin — version table

**Origin champion:** `exp_adaptive_ratio/w35_h64_weighted`  
train_med=0.5588 / test_med=0.6398 / ratio=**1.145**  
Pins: window=35, hidden=64, epochs=300, lr=0.01, edge_weight=on, weight_decay=0, k=5, δ=5, λ=0.01, edge_channel=w_cum, snapshots=on, seed=42, stochastic, primary=normalized_v021.

**Provisional pin (loops 9–10):** edge_channel=**w_rec** from `edge_wrec_weighted` — train held (0.5584), test_med 0.5584 vs origin 0.6398; sticky-median caveat (ratio=1.000). Do not rewrite origin champion path until loops 9–10 finish.

**Rule:** one axis per run; defaults match origin unless the axis column says otherwise. Do not re-probe dead ends (h≠64, lr≠0.01, e>300, w∈{15,25,40}, unweighted, wd=1e-4).

| # | run_id | axis | origin → value | status |
|---|--------|------|----------------|--------|
| 1 | w36_h64_weighted | window_sec | 35→36 | **invalid** (false win; keep w=35) |
| 2 | w34_h64_weighted | window_sec | 35→34 | **regress** (keep w=35) |
| 3 | e280_weighted | epochs | 300→280 | **regress** (keep e=300) |
| 4 | wd1e5_weighted | weight_decay | 0→1e-5 | **regress** (keep wd=0) |
| 5 | k7_weighted | K_BURST | 5→7 | **regress** (keep k=5) |
| 6 | delta7_weighted | DELTA_SEC | 5→7 | **invalid** (corpus shift; keep δ=5) |
| 7 | k3_weighted | K_BURST | 5→3 | **invalid** (false-ish win; keep k=5) |
| 8 | edge_wrec_weighted | edge_weight_channel | w_cum→w_rec | **improve (provisional)** |
| 9 | finalsnap_weighted | snapshots | on→off (final only) | **invalid** (n 92/24 vs 567/161; keep snapshots=on) |
| 10 | lam005_weighted | lambda_rec | 0.01→0.005 | **regress** (keep λ=0.01); *w32_h64 skipped* |

Note: champion A/B raw arm ratio≈1.02 is recorded but **primary stays normalized** (stay near origin policy).

**Champion pin for loops 9–10:** w35 h64 e300 k=5 δ=5; edge_channel=**w_rec** (provisional) unless loops 9–10 invalidate.
