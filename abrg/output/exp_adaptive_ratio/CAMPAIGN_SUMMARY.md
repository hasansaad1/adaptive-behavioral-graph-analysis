# Campaign summary: exp_adaptive_ratio (12-loop close)

**North star:** test/train median reconstruction-error ratio under the **stochastic** scorer (`graph_reconstruction_error` / `normalized_v021`). Lower ratio is better only when both train and test medians improve or hold.

**Dataset / split pins (fixed):** v2, seed=42, app-level 80/20 (`test_ratio=0.2`).

---

## Champion (unchanged)

**Run:** `exp_adaptive_ratio/w35_h64_weighted`

| Metric | Value |
|--------|-------|
| train_med | 0.5588 |
| test_med | 0.6398 |
| ratio | **1.145** |
| N | train 567 snaps / 32 apps; test 161 snaps / 8 apps |

**Locked training pins:** window=35 s, hidden=64, epochs=300, lr=0.01, edge_weight=on, weight_decay=0, seed=42, stochastic scorer.

---

## Path to champion (prior work + this campaign)

An earlier six-run window/capacity phase (w60→w30, h16→h32→h64) moved the weighted stochastic ratio from **~1.20** (60 s pin) toward **1.158** at `w30_h64_weighted`. This 12-loop extension refined around that pin:

```text
~1.20 (w60 weighted baseline)
  → w30 densification (~1.187)
  → h32 / h64 capacity (1.180 → 1.158 @ w30 h64)
  → w35 mild coarsening (1.145)  ← champion
```

Loop 7 (`w35_h64`) was the sole **improve** in this 12-loop block; loops 8–12 and all capacity/lr/epoch probes at w30 regressed or were invalid.

---

## This 12-loop table

Baseline for loops 1–6: `w30_h64_weighted` (ratio **1.158**). Baseline for loops 7–12: `w35_h64_weighted` (ratio **1.145**).

| # | run_id | verdict | ratio | notes |
|---|--------|---------|-------|-------|
| 1 | w30_h128_weighted | regress | 1.200 | capacity above h64 worse |
| 2 | w30_h64_lr005_weighted | regress | 1.215 | underfit at lr=0.005 |
| 3 | w30_h64_lr02_weighted | regress | 1.193 | lr overshoot at 0.02 |
| 4 | w30_h96_weighted | **invalid** | 0.318 | train collapse (ratio meaningless) |
| 5 | w30_h64_e450_weighted | regress | 1.250 | epoch overfit |
| 6 | w25_h64_weighted | regress | 1.250 | sub-30 window overfit at h64 |
| 7 | w35_h64_weighted | **improve** | **1.145** | **campaign champion** |
| 8 | w40_h64_weighted | regress | 1.222 | window peak at 35 s |
| 9 | w35_h64_unweighted | regress | 1.234 | keep encoder edge weights |
| 10 | w35_h48_weighted | regress | 1.203 | keep hidden=64 |
| 11 | w35_h64_e320_weighted | regress | 1.250 | keep epochs=300 |
| 12 | w35_h64_wd1e4_weighted | regress | 1.203 | keep weight_decay=0 |

**Score:** 1 improve, 10 regress, 1 invalid, 0 neutral (in this 12-loop block).

---

## Locked pins after campaign

| Pin | Value |
|-----|-------|
| window_sec | 35 |
| hidden | 64 |
| epochs | 300 |
| lr | 0.01 |
| edge_weight_in_encoder | on |
| weight_decay | 0 |
| seed | 42 |
| scorer | stochastic |

---

## Dead-end axes (do not re-probe without new hypothesis)

- **Capacity:** h48, h96, h128 at these windows (h64 is the peak; h96 pathological)
- **Learning rate:** lr≠0.01 (0.005 underfits, 0.02 overshoots)
- **Epochs:** >300 (e320, e450, e600 all ratio 1.250 overfit pattern)
- **Window:** 15, 25, 40 s at h64 (35 s sweet spot; 25/40 regress; 15 overfit earlier phase)
- **Encoder:** unweighted (regresses at w30 and w35)
- **Regularization:** weight_decay=1e-4 (both medians worse vs wd=0)

---

## Artifacts

- Per-run cards: `abrg/output/exp_adaptive_ratio/<run_id>/RUN.md`
- Research notes: `abrg/output/exp_adaptive_ratio/<run_id>/RESEARCH_NOTE.md`
- Chronological log: `abrg/output/exp_adaptive_ratio/CAMPAIGN_LOG.md`
- Research index: `abrg/output/exp_adaptive_ratio/RESEARCH_INDEX.md`
- Champion comparison: `abrg/output/exp_adaptive_ratio/w35_h64_weighted/comparison.json`

All 12 loops in this block completed with `process_valid` and reproduce validation **ok**.
