# Campaign summary: exp_near_origin (10-loop close)

**North star:** test/train median reconstruction-error ratio under the **stochastic** scorer (`normalized_v021`). Lower ratio is better only when train and test medians improve or hold on a **comparable** corpus (same n snaps/apps).

**Parent champion entering campaign:** `exp_adaptive_ratio/w35_h64_weighted` — 0.5588 / 0.6398 / ratio **1.145** (n 567/161).

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

**Locked pins after campaign:** window=35 s, hidden=64, epochs=300, lr=0.01, weight_decay=0, k_burst=5, delta_sec=5, lambda_rec=0.01, edge_weight_channel=**w_cum**, edge_weight=on, snapshots=on, seed=42, stochastic scorer, primary=normalized_v021.

### edge_wrec provisional (not promoted)

Loop 8 (`edge_wrec_weighted`) reported 0.5584 / 0.5584 / **1.000** with n 567/161 unchanged, train held, test_med clearly below champion (0.5584 vs 0.6398), and reproduce validated. Confound-skeptic labeled this **improve provisional** only: train_med==test_med exactly suggests sticky-median / near-zero BCE saturation, so the ratio=1.0 is not trusted for promotion. Loops 9–10 did not corroborate a channel switch. **Champion path and pins stay at w_cum** until a follow-up campaign re-tests w_rec with explicit median diagnostics.

---

## All 10 loops

Baseline for all loops: origin champion (ratio **1.145**, n 567/161) unless noted.

| # | run_id | verdict | train / test / ratio | n (tr/te) | notes |
|---|--------|---------|----------------------|-----------|-------|
| 1 | w36_h64_weighted | **invalid** | 0.9460 / 0.9189 / 0.971 | 550/159 | false win — both medians much worse |
| 2 | w34_h64_weighted | regress | 0.5934 / 0.7417 / 1.250 | 574/163 | densification below 35 s |
| 3 | e280_weighted | regress | 0.5603 / 0.6747 / 1.204 | 567/161 | keep epochs=300 |
| 4 | wd1e5_weighted | regress | 0.5617 / 0.6836 / 1.217 | 567/161 | keep weight_decay=0 |
| 5 | k7_weighted | regress | 0.5592 / 0.6990 / 1.250 | 567/161 | keep k_burst=5 |
| 6 | delta7_weighted | **invalid** | 0.5569 / 0.5569 / 1.000 | 612/140 | δ changed eligibility / split composition |
| 7 | k3_weighted | **invalid** | 0.5991 / 0.5607 / 0.936 | 567/161 | ratio down but train_med worse |
| 8 | edge_wrec_weighted | **improve provisional** | 0.5584 / 0.5584 / 1.000 | 567/161 | sticky median; not promoted |
| 9 | finalsnap_weighted | **invalid** | 0.6928 / 0.5646 / 0.815 | 92/24 | final-only vs trajectory — incomparable |
| 10 | lam005_weighted | regress | 0.5626 / 0.7032 / 1.250 | 567/161 | replaced skipped w32; keep λ=0.01 |

**Score:** 0 promoted improve, 1 improve provisional (not adopted), 5 regress, 4 invalid.

Loop 10 substituted **lam005_weighted** for the queued **w32_h64_weighted** probe after loops 1–2 settled the window peak at 35 s.

---

## Locked pins after campaign

Same as origin champion (see above). No pin changes adopted from this campaign.

| Pin | Value |
|-----|-------|
| window_sec | 35 |
| hidden | 64 |
| epochs | 300 |
| lr | 0.01 |
| weight_decay | 0 |
| k_burst | 5 |
| delta_sec | 5 |
| lambda_rec | 0.01 |
| edge_weight_channel | w_cum |
| edge_weight_in_encoder | on |
| snapshots | on |
| seed | 42 |
| scorer | stochastic (normalized_v021) |

---

## Dead-end axes (this campaign)

- **Window fine-tune:** w34, w36 at h64 (peak stays 35 s; w32 not run)
- **Train mild probes:** e280, wd=1e-5, λ_rec=0.005
- **Edge formation:** k=7 regress; k=3 false-ish ratio; δ=7 changes corpus composition
- **Snapshot mode:** final-only graphs (incomparable n)
- **Edge channel:** w_rec — provisional ratio gain only; sticky median blocks promotion

Do not re-probe without new hypothesis. Parent dead ends (h≠64, lr≠0.01, e>300, w∈{15,25,40}, unweighted, wd=1e-4) still apply.

---

## Conclusion

Ten single-axis loops near the adaptive-ratio champion found **no honest promoted improve**. Window 35 s, full multi-window snapshots, k=5, δ=5, λ=0.01, and w_cum edge channel remain locked. The only intriguing signal — w_rec with ratio 1.0 and lower test median — is withheld as **provisional** pending median-saturation analysis. Primary reconstruction benchmark stays `exp_adaptive_ratio/w35_h64_weighted` at ratio **1.145**.
