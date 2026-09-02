# Chapter A — AndroCT 2017 reconstruction / one-class / supervision audit

This directory is a **read-only consolidation** of `abrg/output/androct_2017/`.
It does not re-run experiments and does not modify run outputs.

## Claims ↔ tables / figures

| Claim | Table / figure | MASTER row(s) |
|---|---|---|
| Eligible corpus n, mapped rate, medians | T1_corpus | (corpus_cache, not an AUC row) |
| Trivial floors across T22 / API-1000 / invocation | T2_floors, F6_granularity | method=`trivial_floor` |
| Seven families trained vs untrained vs size floor | T3_method_sweep, F2_trained_vs_untrained | family detectors |
| Rung 1 / rung 2 pooled OOF / random-group / rung 3 | T4_supervision_ladder, F1_ladder | ladder HGB; OCPool |
| M1/M2/M3 and WL ablations | T5_message_passing, F5_message_passing | supgnn; WL_* |
| D0–D5 one-class and supervised + raw control | T6_deviation_readout | ocdev/devread |
| TPR at FPR 0.001/0.01/0.05/0.10, wild precision | T7_operating_points, F3_roc_headlines | check2_operating |
| D1 per-node ablation | F4_d1_node_ablation | check3_d1_volume |
| What each headline survived | T8_validation | bias / nested / holdout / shuffle |
| Headline set | MASTER_RESULTS.csv `is_headline=True` | HEADLINE_JUSTIFICATION.txt |

## Reproduce all numbers (required gate)

Reload every MASTER AUC + EXTRA scalars from frozen artifacts (6 dp):

```bash
.venv/bin/python -m abrg.reproduce_chapter_a_numbers verify
# or: jupyter nbconvert --execute chapter_a/reproduce/00_all_numbers.ipynb
```

Per-experiment notebooks live under `chapter_a/reproduce/by_experiment/<exp>/`.
See `chapter_a/reproduce/README.md` and `INDEX.json`.

**Full CLI re-train** (optional / expensive):

- GAE family: `python -m abrg.validate_reproduce --run-dir abrg/output/androct_2017/<run>`
- Other modules: `CLI_RERUN_REGISTRY` in `abrg/reproduce_chapter_a_numbers.py`

## Catalog rebuild + table/figure verify

```bash
.venv/bin/python chapter_a/scripts/verify_all.py
```

This rebuilds tables/figures/notebooks from saved artifacts, reloads every MASTER
AUC from its artifact, executes notebooks headlessly, and diffs regenerated
tables/figures against the copies under `chapter_a/`.

Wall time is recorded in `REPRODUCIBILITY.md`.

## Layout

```
chapter_a/
  MANIFEST.csv
  MASTER_RESULTS.csv
  EXTRA_NUMBERS.csv
  reproduce/           # number-verify notebooks + INDEX
  tables/  T1–T8 .csv and .tex
  figures/ F1–F6 .pdf and .svg
  notebooks/ 01–06
  scripts/
  REPRODUCIBILITY.md
  GAPS.md
  environment.yml
  requirements.txt
```
