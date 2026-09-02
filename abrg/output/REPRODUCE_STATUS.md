# Reproduce status

Canonical count: **51 of 53** validate reports pass (2 fail). Reconstructed from on-disk `validate_reproduce_report.json` files.

Failures:

- `exp_window_sec/w120_weighted` (ratio): re-run metrics diverge from frozen comparison (Δtrain_med≈−0.0905, Δtest_med≈−0.0275, Δratio≈+0.123). Documented as a window-sec axis run whose frozen numbers no longer match the current pipeline on re-validation.
- `androct_2017/ocgin` (androct_auc): `python -m abrg.ocgin --output-dir <nb_repro>` exits 1. The module requires the AndroCT Run3 shared corpus (`comparison.json` / tensor cache via `abrg.ocgin.data.assert_run3_tensor_identity`); the bare validate CLI invoke does not supply that layout, so the arm is not re-verified by the current harness entry point. Original `SUMMARY.md` / frozen expected AUC remain on disk.

| run_id | kind | headline | notebook | config | validate |
|---|---|---|---|---|---|
| `androct_2017/arm_a_n1` | androct_auc | auc_floor=0.5157 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/arm_b_n8` | androct_auc | auc_floor=0.5168 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/ocgin` | androct_auc | auc_floor=0.5912 dir=benign_higher_score | yes | yes | fail |
| `androct_2017/run2` | androct_auc | auc_floor=0.5381 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run3` | androct_auc | auc_floor=0.6161 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run3_5` | androct_auc | auc_floor=0.9762 dir=malware_higher_score | yes | yes | ok |
| `androct_2017/run4` | androct_auc | auc_floor=0.6379 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run5` | androct_auc | auc_floor=0.6379 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run6/centroid_node_ablation` | androct_auc | auc_floor=0.7769 dir=malware_higher_score | yes | yes | ok |
| `androct_2017/run6/ipc_scalar_probes` | androct_auc | auc_floor=0.5755 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run6/oneclass_baselines` | androct_auc | auc_floor=0.7769 dir=malware_higher_score | yes | yes | ok |
| `androct_2017/run6/part1_ablation` | androct_auc | auc_floor=0.9762 dir=malware_higher_score | yes | yes | ok |
| `androct_2017/run6/part2_geometry` | androct_auc | auc_floor=0.7769 dir=malware_higher_score | yes | yes | ok |
| `androct_2017/run6/part3_armB` | androct_auc | auc_floor=0.6012 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run6/whiten_h8_a02` | androct_auc | auc_floor=0.5600 dir=benign_higher_score | yes | yes | ok |
| `androct_2017/run8` | androct_auc | auc_floor=0.6834 dir=malware_higher_score | yes | yes | ok |
| `desc_seed` | desc_seed | self_cross_auc=0.501 within_prior=0.952 | yes | yes | ok |
| `exp_adaptive_ratio/w15_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_adaptive_ratio/w25_h64_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_adaptive_ratio/w30_e600_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h128_weighted` | ratio | ratio=1.2000 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h32_weighted` | ratio | ratio=1.1798 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h64_e450_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h64_lr005_weighted` | ratio | ratio=1.2153 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h64_lr02_weighted` | ratio | ratio=1.1933 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h64_weighted` | ratio | ratio=1.1577 | yes | yes | ok |
| `exp_adaptive_ratio/w30_h96_weighted` | ratio | ratio=0.3178 | yes | yes | ok |
| `exp_adaptive_ratio/w30_unweighted` | ratio | ratio=1.1969 | yes | yes | ok |
| `exp_adaptive_ratio/w35_h48_weighted` | ratio | ratio=1.2026 | yes | yes | ok |
| `exp_adaptive_ratio/w35_h64_e320_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_adaptive_ratio/w35_h64_unweighted` | ratio | ratio=1.2341 | yes | yes | ok |
| `exp_adaptive_ratio/w35_h64_wd1e4_weighted` | ratio | ratio=1.2028 | yes | yes | ok |
| `exp_adaptive_ratio/w35_h64_weighted` | ratio | ratio=1.1450 | yes | yes | ok |
| `exp_adaptive_ratio/w40_h64_weighted` | ratio | ratio=1.2222 | yes | yes | ok |
| `exp_adaptive_ratio/w45_weighted` | ratio | ratio=1.2000 | yes | yes | ok |
| `exp_drop_inactive/w35_h64_drop7` | ratio | ratio=0.9888 | yes | yes | ok |
| `exp_epochs/e600_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_near_origin/delta7_weighted` | ratio | ratio=1.0000 | yes | yes | ok |
| `exp_near_origin/e280_weighted` | ratio | ratio=1.2042 | yes | yes | ok |
| `exp_near_origin/edge_wrec_weighted` | ratio | ratio=1.0000 | yes | yes | ok |
| `exp_near_origin/finalsnap_weighted` | ratio | ratio=0.8149 | yes | yes | ok |
| `exp_near_origin/k3_weighted` | ratio | ratio=0.9358 | yes | yes | ok |
| `exp_near_origin/k7_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_near_origin/lam005_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_near_origin/w34_h64_weighted` | ratio | ratio=1.2500 | yes | yes | ok |
| `exp_near_origin/w36_h64_weighted` | ratio | ratio=0.9714 | yes | yes | ok |
| `exp_near_origin/wd1e5_weighted` | ratio | ratio=1.2170 | yes | yes | ok |
| `exp_window_sec/w120_weighted` | ratio | ratio=1.0704 | yes | yes | fail |
| `exp_window_sec/w30_weighted` | ratio | ratio=1.1868 | yes | yes | ok |
| `negative_control_v2` | negative_control |  | yes | yes | ok |
| `negative_control_v2_weighted` | negative_control |  | yes | yes | ok |
| `norm_ab_v2` | ratio | ratio=1.2857 | yes | yes | ok |
| `norm_ab_v2_weighted` | ratio | ratio=1.2000 | yes | yes | ok |

## Batch validate pending

```bash
cd REPO_ROOT
.venv/bin/python -m abrg.batch_validate_reproduce
```

Revisits only runs whose report is missing or not fully `ok` (currently the two failures above).
Long-running AndroCT retrains (run2/4/5, arms) may take hours; run overnight.
