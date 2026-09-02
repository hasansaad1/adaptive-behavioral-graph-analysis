# Adaptive behavioural graph analysis

Modelling, evaluation, and reproducibility artefacts for an MSc thesis on
Android malware detection from dynamic behavioural graphs.

The submitted thesis PDF is [`thesis.pdf`](thesis.pdf).

## What reproduces from a fresh clone

| Scope | Fresh clone? | Notes |
|-------|--------------|-------|
| Chapters B and C (v2 Frida corpus) | **Mostly yes** | `datasets/v2` and `datasets/v2_extended` session captures are included. Outputs under `abrg/output/v2_chapter_b`, `v2_chapter_c`, `v2_extended`, `desc_seed`, and `norm_ab_v2` are included. |
| Chapter A (AndroCT 2017) | **No** | AndroCT terms prohibit redistribution. The 936 MB Zenodo inputs and ~20 GB of derived outputs under `abrg/output/androct_2017/` are absent from this repository. Fifteen of the fifty-one passing validate reports live in that tree and cannot be re-verified without obtaining AndroCT separately (see Data terms). |
| `desc_seed` | **Validate only** | Scores against frozen llama3.2 predictions. Predictions are **not** regenerated: Ollama output is not reproducible across versions even at temperature 0 (see `abrg/output/desc_seed/reproduce_config.json`). |

## Validate harness

`abrg.batch_validate_reproduce` walks every `abrg/output/**/reproduce_config.json`
(skipping `nb_repro/` scratch dirs). For each run whose
`validate_reproduce_report.json` is missing or not fully `ok`, it re-runs the
frozen CLI (`python -m abrg.validate_reproduce --run-dir … --mode cli`) and
compares metrics against the frozen expected values within tolerance. Runs that
already pass are skipped.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/python -m abrg.batch_validate_reproduce
```

**Current status: 51 of 53 reports pass.** See
[`abrg/output/REPRODUCE_STATUS.md`](abrg/output/REPRODUCE_STATUS.md).

Failures:

1. `exp_window_sec/w120_weighted` — re-run ratio diverges from frozen medians
   (Δratio ≈ +0.123).
2. `androct_2017/ocgin` — `python -m abrg.ocgin` exits 1 under the bare validate
   argv because the module requires the AndroCT Run3 shared corpus layout
   (`abrg.ocgin.data.assert_run3_tensor_identity`). That corpus is not
   redistributed here.

Per-run notebooks: `abrg/output/**/reproduce.ipynb`. Chapter A number reload
(without full retrain): `python -m abrg.reproduce_chapter_a_numbers verify`
(requires local AndroCT artefacts).

## Repository layout

| Path | Role |
|------|------|
| `abrg/` | Python package: graph construction, GAE pilots, Chapter B/C runners, validate harness |
| `abrg/output/` | Frozen experiment outputs, `reproduce_config.json`, validate reports |
| `chapter_a/` | Chapter A consolidation: `MASTER_RESULTS.csv`, tables, figures, reproduce notebooks |
| `datasets/` | `CURRENT` → `v2`; Frida session captures (`v2`, `v2_extended`); AndroCT inventory only |
| `docs/` | Specs and literature notes (including ContextDroid collection protocol) |
| `notebooks/` | Pilot notebooks and reproduce index |
| `results/` | Experiment write-ups cited by the thesis |
| `reproducibility/` | Post-hoc environment snapshot (see disclaimer in the file) |
| `android_malware_pipeline/` | Frida collection helpers (no APKs in git) |
| `thesis.pdf` | Submitted thesis PDF |
| `requirements.txt` | Default Python dependencies for modelling / validate |

LaTeX sources are not published; they remain local under `thesis/` (gitignored).

## Dependencies

Default install: `pip install -r requirements.txt` (Python **3.14.3**).

Pinned modelling stack: numpy **2.5.0**, scipy **1.18.0**, scikit-learn **1.9.0**,
torch **2.12.1**, networkx **3.6.1**, grakel **0.1.8**.

Other requirement files (not replaced):

- `abrg/requirements-pilot.txt` / `abrg/requirements-notebook.txt` — ABRG pilots + Jupyter
- `chapter_a/requirements.txt` + `chapter_a/environment.yml` — Chapter A conda env
- `android_malware_pipeline/requirements.txt` — Frida collection
- `reproducibility/environment-2026-08-26.txt` — full `.venv` freeze; **does not claim**
  to be the environment of the original AndroCT training runs

## ContextDroid dependency

Chapter B documents the collection protocol implemented in a **separate** repository:

- <https://github.com/hasansaad1/ContextDroid>

Protocol evidence cited in the thesis (scripts, env files, hooks) lives there, not here.
`abrg/chapter_b/config.py` resolves that tree via the `CONTEXTDROID_ROOT` environment
variable (default: sibling directory `../ContextDroid` next to this repository).

```bash
export CONTEXTDROID_ROOT=/path/to/ContextDroid
```

## Data terms

| Data | In this repo? | Terms |
|------|---------------|-------|
| Code / scripts | yes | MIT (`LICENSE`) |
| `datasets/v2`, `datasets/v2_extended` | yes | Author-collected Frida sessions for this thesis |
| F-Droid app descriptions (`abrg/output/desc_seed/metadata/`) | yes | Upstream [F-Droid index-v2](https://f-droid.org/repo/index-v2.json) is **AGPL-3.0**; provenance recorded in `desc_seed/reproduce_config.json` |
| AndroCT 2017 raw traces | **no** | Zenodo [4470320](https://zenodo.org/records/4470320); CC-BY-4.0 **plus** author conditions: faculty sponsor, **no redistribution**, no commercial use, cite Li, Fu & Cai (MSR 2021). See `datasets/androct_2017/README.md`. |
| `abrg/output/androct_2017/` derived outputs | **no** | Same AndroCT constraints; ~20 GB local-only |

APKs are not committed. AndroZoo credentials (if used for APK fetch) stay in
`.androzoo_api_key` / `ANDROZOO_API_KEY` and are gitignored.

## Licence

Source code: MIT — see [`LICENSE`](LICENSE).

Dataset and metadata terms are **not** MIT; see Data terms above.
