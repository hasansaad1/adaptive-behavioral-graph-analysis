# Chapter A number reproduction

Every §A.5/A.6 number that lives in `MASTER_RESULTS.csv` or `EXTRA_NUMBERS.csv` can be re-checked from frozen artifacts.

## Fast path (required)

```bash
.venv/bin/python -m abrg.reproduce_chapter_a_numbers verify
# or execute chapter_a/reproduce/00_all_numbers.ipynb
```

## Per-experiment notebooks

| experiment | notebook | n rows |
|---|---|---|
| `apigraph` | `chapter_a/reproduce/by_experiment/apigraph/reproduce_numbers.ipynb` | 5 |
| `devread` | `chapter_a/reproduce/by_experiment/devread/reproduce_numbers.ipynb` | 18 |
| `final_validate` | `chapter_a/reproduce/by_experiment/final_validate/reproduce_numbers.ipynb` | 2 |
| `glocalkd` | `chapter_a/reproduce/by_experiment/glocalkd/reproduce_numbers.ipynb` | 2 |
| `invgraph` | `chapter_a/reproduce/by_experiment/invgraph/reproduce_numbers.ipynb` | 6 |
| `kernels` | `chapter_a/reproduce/by_experiment/kernels/reproduce_numbers.ipynb` | 3 |
| `ladder` | `chapter_a/reproduce/by_experiment/ladder/reproduce_numbers.ipynb` | 7 |
| `ocdev` | `chapter_a/reproduce/by_experiment/ocdev/reproduce_numbers.ipynb` | 14 |
| `ocdev_validate` | `chapter_a/reproduce/by_experiment/ocdev_validate/reproduce_numbers.ipynb` | 4 |
| `ocgin` | `chapter_a/reproduce/by_experiment/ocgin/reproduce_numbers.ipynb` | 2 |
| `ocgtl` | `chapter_a/reproduce/by_experiment/ocgtl/reproduce_numbers.ipynb` | 2 |
| `run3` | `chapter_a/reproduce/by_experiment/run3/reproduce_numbers.ipynb` | 7 |
| `run8` | `chapter_a/reproduce/by_experiment/run8/reproduce_numbers.ipynb` | 2 |
| `supgnn` | `chapter_a/reproduce/by_experiment/supgnn/reproduce_numbers.ipynb` | 27 |
| `validation` | `chapter_a/reproduce/by_experiment/validation/reproduce_numbers.ipynb` | 3 |

## Full CLI re-run (optional / expensive)

- GAE family (`run2`–`run8`, arms, `run6/*`): `python -m abrg.validate_reproduce --run-dir abrg/output/androct_2017/<run>`
- Other modules: see `CLI_RERUN_REGISTRY` in `abrg/reproduce_chapter_a_numbers.py` and each experiment's `CHAPTER_A_REPRODUCE.json`.

