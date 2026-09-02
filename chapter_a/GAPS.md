# Chapter A gaps

Register of what is not independently re-executed or not fully version-pinned.
No numbers were regenerated to close a gap.

## Number verify (closed 2026-08-25)

Every `MASTER_RESULTS.csv` row (104) and `EXTRA_NUMBERS.csv` scalar (25+)
reloads from its artifact via:

```bash
.venv/bin/python -m abrg.reproduce_chapter_a_numbers verify
```

Notebooks: `chapter_a/reproduce/00_all_numbers.ipynb` and
`chapter_a/reproduce/by_experiment/*/reproduce_numbers.ipynb`.

This is **artifact reload**, not full CLI retrain. GAE-family CLI retrain remains
via `abrg.validate_reproduce`. Module CLI retrain is registered but not yet
harness-validated end-to-end for every comparison-module (see
`CLI_RERUN_REGISTRY`).

## 16 experiment dirs with SUMMARY.md and no reproduce.md

**Closed 2026-08-26** (see `results/reproducibility_remediation.md`).
Each of the 16 directories now has a root `reproduce.md` written from on-disk
evidence; several mark fields `UNDETERMINED`. Inventory via
`final_validate` check5 / `rglob("reproduce.md")` now reports zero missing.

Former list (for history):
- `abrg/output/androct_2017/apigraph`
- `abrg/output/androct_2017/final_validation`
- `abrg/output/androct_2017/glocalkd`
- `abrg/output/androct_2017/invgraph`
- `abrg/output/androct_2017/kernels`
- `abrg/output/androct_2017/ladder`
- `abrg/output/androct_2017/ocgin`
- `abrg/output/androct_2017/run2`
- `abrg/output/androct_2017/run3`
- `abrg/output/androct_2017/run3_5`
- `abrg/output/androct_2017/run4`
- `abrg/output/androct_2017/run5`
- `abrg/output/androct_2017/run6`
- `abrg/output/androct_2017/run8`
- `abrg/output/androct_2017/transitions`
- `abrg/output/androct_2017/validation`

Count missing now: 0

## Aborted / abandoned runs

- `ocgtl` Split-B aborted; no checkpoints.
- `glocalkd` nested bootstrap abandoned at B=20.
- `invgraph` V2 complete_but_artifact (99.99% malware edge-drop).

## reproduce_config.json missing library versions

**Status 2026-08-26:** still no evidence-backed run-time pins for the 21
configs below. Each now carries
`"version_provenance": "unverified; see reproducibility/environment-2026-08-26.txt, captured after the run"`.
Versions were **not** copied from today's venv into `library_versions`
(Part 0 honesty guard). Post-hoc lockfile:
`reproducibility/environment-2026-08-26.txt`.

- `abrg/output/androct_2017/glocalkd/reproduce_config.json`
- `abrg/output/androct_2017/run2/reproduce_config.json`
- `abrg/output/androct_2017/run3_5/reproduce_config.json`
- `abrg/output/androct_2017/run5/reproduce_config.json`
- `abrg/output/androct_2017/ladder/reproduce_config.json`
- `abrg/output/androct_2017/ocgin/reproduce_config.json`
- `abrg/output/androct_2017/arm_b_n8/reproduce_config.json`
- `abrg/output/androct_2017/run4/reproduce_config.json`
- `abrg/output/androct_2017/run3/reproduce_config.json`
- `abrg/output/androct_2017/arm_a_n1/reproduce_config.json`
- `abrg/output/androct_2017/run8/reproduce_config.json`
- `abrg/output/androct_2017/run6/centroid_node_ablation/reproduce_config.json`
- `abrg/output/androct_2017/run6/part1_ablation/reproduce_config.json`
- `abrg/output/androct_2017/run6/whiten_h8_a02/reproduce_config.json`
- `abrg/output/androct_2017/run6/ipc_scalar_probes/reproduce_config.json`
- `abrg/output/androct_2017/run6/part3_armB/reproduce_config.json`
- `abrg/output/androct_2017/run6/part2_geometry/reproduce_config.json`
- `abrg/output/androct_2017/run6/oneclass_baselines/reproduce_config.json`
- `abrg/output/androct_2017/arm_a_n1/nb_repro/reproduce_config.json`
- `abrg/output/androct_2017/arm_b_n8/nb_repro/reproduce_config.json`
- `abrg/output/androct_2017/run2/nb_repro/reproduce_config.json`

## Library version disagreements across runs

- (none)

## MASTER rows with missing / unresolvable artifact_path

- (none at inventory time; verify_all.py may add catalog-only rows)

## Figures / tables whose source artifact is missing

- Generated scripts fail rather than invent numbers. See REPRODUCIBILITY.md after verify_all.

## GPU nondeterminism vs headlines

- Headline rows (D1 centroid, OCPool raw/R2, S1 nested mean, D3 HGB, HGB full, mapped floor,
  rung-2 pooled OOF, random-group control, D1 benign-holdout centroid) are sklearn/numpy
  scores or stored JSON scalars. They do not depend on GPU nondeterminism given the artifacts.
- T3 GNN families (OCGIN, GLocalKD, OCGTL, GAE recon) used torch; trained-vs-untrained means
  are catalogued from saved JSONs and were not re-trained here.

## AUC verification mode

- `verify_all.py` reloads the stored `auc_floor` (or documented bootstrap mean) from each row's
  JSON artifact and asserts 6 decimal-place agreement with MASTER_RESULTS.csv.
- Per-app score vectors sufficient to recompute ROC AUC without re-inference are persisted for
  **61/104** catalogue rows (ocdev/devread/ocgtl/supgnn `predictions.csv` families). The other
  **43/104** artefacts store quantile summaries or aggregate AUCs only. Regeneration of missing
  vectors was **not** performed in the 2026-08-26 remediation (author gate).

## Chapter A toolchain not in experiment reproduce_config.json

- matplotlib, pandas, nbformat/nbconvert used to build tables/figures/notebooks are recorded
  in REPRODUCIBILITY.md at verify time; they are not pinned in experiment reproduce_config files.
- kernels `reproduce_config.json` records karateclub and gensim as `unavailable_on_cpython_3.14`.

