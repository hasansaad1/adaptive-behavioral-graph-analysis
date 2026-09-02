# Reproduce validation audit

Total: 53 | ok: 51 | fail: 2 | pending: 0

| run_id | kind | frozen headline | status | diff (if fail) |
|---|---|---|---|---|
| `androct_2017/arm_a_n1` | androct_auc | auc_floor=0.5157 dir=benign_higher_score | ok |  |
| `androct_2017/arm_b_n8` | androct_auc | auc_floor=0.5168 dir=benign_higher_score | ok |  |
| `androct_2017/ocgin` | androct_auc | auc_floor=0.5912 dir=benign_higher_score | fail | CLI exit 1 (Run3 corpus path not supplied by bare validate argv) |
| `androct_2017/run2` | androct_auc | auc_floor=0.5381 dir=benign_higher_score | ok |  |
| `androct_2017/run3` | androct_auc | auc_floor=0.6161 dir=benign_higher_score | ok |  |
| `androct_2017/run3_5` | androct_auc | auc_floor=0.9762 dir=malware_higher_score | ok |  |
| `androct_2017/run4` | androct_auc | auc_floor=0.6379 dir=benign_higher_score | ok |  |
| `androct_2017/run5` | androct_auc | auc_floor=0.6379 dir=benign_higher_score | ok |  |
| `androct_2017/run6/centroid_node_ablation` | androct_auc | auc_floor=0.7769 dir=malware_higher_score | ok |  |
| `androct_2017/run6/ipc_scalar_probes` | androct_auc | auc_floor=0.5755 dir=benign_higher_score | ok |  |
| `androct_2017/run6/oneclass_baselines` | androct_auc | auc_floor=0.7769 dir=malware_higher_score | ok |  |
| `androct_2017/run6/part1_ablation` | androct_auc | auc_floor=0.9762 dir=malware_higher_score | ok |  |
| `androct_2017/run6/part2_geometry` | androct_auc | auc_floor=0.7769 dir=malware_higher_score | ok |  |
| `androct_2017/run6/part3_armB` | androct_auc | auc_floor=0.6012 dir=benign_higher_score | ok |  |
| `androct_2017/run6/whiten_h8_a02` | androct_auc | auc_floor=0.5600 dir=benign_higher_score | ok |  |
| `androct_2017/run8` | androct_auc | auc_floor=0.6834 dir=malware_higher_score | ok |  |
| `desc_seed` | desc_seed | self_cross_auc=0.501 within_prior=0.952 | ok |  |
| `exp_adaptive_ratio/w15_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_adaptive_ratio/w25_h64_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_adaptive_ratio/w30_e600_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_adaptive_ratio/w30_h128_weighted` | ratio | ratio=1.2000 | ok |  |
| `exp_adaptive_ratio/w30_h32_weighted` | ratio | ratio=1.1798 | ok |  |
| `exp_adaptive_ratio/w30_h64_e450_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_adaptive_ratio/w30_h64_lr005_weighted` | ratio | ratio=1.2153 | ok |  |
| `exp_adaptive_ratio/w30_h64_lr02_weighted` | ratio | ratio=1.1933 | ok |  |
| `exp_adaptive_ratio/w30_h64_weighted` | ratio | ratio=1.1577 | ok |  |
| `exp_adaptive_ratio/w30_h96_weighted` | ratio | ratio=0.3178 | ok |  |
| `exp_adaptive_ratio/w30_unweighted` | ratio | ratio=1.1969 | ok |  |
| `exp_adaptive_ratio/w35_h48_weighted` | ratio | ratio=1.2026 | ok |  |
| `exp_adaptive_ratio/w35_h64_e320_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_adaptive_ratio/w35_h64_unweighted` | ratio | ratio=1.2341 | ok |  |
| `exp_adaptive_ratio/w35_h64_wd1e4_weighted` | ratio | ratio=1.2028 | ok |  |
| `exp_adaptive_ratio/w35_h64_weighted` | ratio | ratio=1.1450 | ok |  |
| `exp_adaptive_ratio/w40_h64_weighted` | ratio | ratio=1.2222 | ok |  |
| `exp_adaptive_ratio/w45_weighted` | ratio | ratio=1.2000 | ok |  |
| `exp_drop_inactive/w35_h64_drop7` | ratio | ratio=0.9888 | ok |  |
| `exp_epochs/e600_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_near_origin/delta7_weighted` | ratio | ratio=1.0000 | ok |  |
| `exp_near_origin/e280_weighted` | ratio | ratio=1.2042 | ok |  |
| `exp_near_origin/edge_wrec_weighted` | ratio | ratio=1.0000 | ok |  |
| `exp_near_origin/finalsnap_weighted` | ratio | ratio=0.8149 | ok |  |
| `exp_near_origin/k3_weighted` | ratio | ratio=0.9358 | ok |  |
| `exp_near_origin/k7_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_near_origin/lam005_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_near_origin/w34_h64_weighted` | ratio | ratio=1.2500 | ok |  |
| `exp_near_origin/w36_h64_weighted` | ratio | ratio=0.9714 | ok |  |
| `exp_near_origin/wd1e5_weighted` | ratio | ratio=1.2170 | ok |  |
| `exp_window_sec/w120_weighted` | ratio | ratio=1.0704 | fail | Δtrain_med=-0.0905, Δtest_med=-0.0275, Δratio=+0.1230 |
| `exp_window_sec/w30_weighted` | ratio | ratio=1.1868 | ok |  |
| `negative_control_v2` | negative_control |  | ok |  |
| `negative_control_v2_weighted` | negative_control |  | ok |  |
| `norm_ab_v2` | ratio | ratio=1.2857 | ok |  |
| `norm_ab_v2_weighted` | ratio | ratio=1.2000 | ok |  |
