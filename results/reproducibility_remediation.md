# Reproducibility remediation (2026-08-26)

No experiments. No retraining. No score-vector regeneration (Part 3 gated).
Part 0 honesty guard applied: no fabricated version pins.

---

## Part 1 — Missing `reproduce.md` (16 directories)

**Template used:** `abrg/output/androct_2017/supgnn/artifacts/reproduce.md`
(title + fenced CLI + prerequisites). Richer B/C templates exist but are
out of AndroCT convention; AndroCT peers use the short form.

**Placement:** each file written at
`abrg/output/androct_2017/<dir>/reproduce.md` (root next to `SUMMARY.md`;
discovered by `rglob("reproduce.md")`).

| Directory | Written | UNDETERMINED / notes |
|-----------|---------|----------------------|
| `apigraph` | yes | exact original argv; library versions |
| `final_validation` | yes | library versions |
| `glocalkd` | yes | library versions; whether `--skip-nested` |
| `invgraph` | yes | library versions; Stage-4 seed list not in SUMMARY |
| `kernels` | yes | (libraries already in `reproduce_config.json` / SUMMARY) |
| `ladder` | yes | library versions |
| `ocgin` | yes | library versions; sha_list_digest (fingerprint only) |
| `run2` | yes | library versions; sha_list digest; cold vs `--from-cache` first train |
| `run3` | yes | library versions; sha_list digest |
| `run3_5` | yes | library versions; sha_list digest |
| `run4` | yes | library versions; sha_list digest |
| `run5` | yes | library versions; sha_list digest |
| `run6` | yes | **orchestrator CLI** (`run_gae_run6` module ABSENT); parent seeds/digest; library versions — subdir CLIs documented |
| `run8` | yes | library versions; sha_list digest |
| `transitions` | yes | library versions |
| `validation` | yes | library versions; bootstrap RNG beyond split digest |

**Post-check:** experiment dirs with `SUMMARY.md` and no `reproduce.md` = **0**.

Directories with partial UNDETERMINED provenance (not invented): **all 16**
except `kernels` for library pins; `run6` is the strongest UNDETERMINED
(missing orchestrator module).

---

## Part 2 — Missing version pins (21 configs)

### 2a List (unchanged membership)

All 21 paths from `chapter_a/GAPS.md` (glocalkd, run2, run3_5, run5, ladder,
ocgin, arm_b_n8, run4, run3, arm_a_n1, run8, seven `run6/*`, three `*/nb_repro`).

### 2b Evidence search (per-directory)

| Evidence class | Finding |
|----------------|---------|
| pip freeze / poetry.lock / uv.lock in run dirs | **None** |
| conda/env export dated to run | **None** (`chapter_a/environment.yml` exists but is chapter tooling, not per-run) |
| package versions in the 21 configs' SUMMARY | **None** (only `kernels`, not in the 21, records `libraries`) |
| `chapter_a/REPRODUCIBILITY.md` / `requirements.txt` | Versions from **verify-time** (2026-08-25 area), not claimed as run-time for Aug 7–12 experiments |
| Contrasting configs with pins | `kernels` (`libraries`); `ocdev`/`ocgtl`/`supgnn` artifacts (`library_versions`) — **not** in the 21 |

### 2c Evidence-backed pins written

**0 / 21.** No contemporaneous freeze found; Part 0 forbids copying today's venv.

### 2d Unverified marker + lockfile

- Lockfile: `reproducibility/environment-2026-08-26.txt` (pip freeze of current `.venv`, header states post-hoc / not run environment).
- Each of the 21 configs: `"version_provenance": "unverified; see reproducibility/environment-2026-08-26.txt, captured after the run"`.
- **No** `library_versions` / `libraries` keys added.

**Venv vs run dates:** experiment artefacts mtimes ≈ 2026-08-07 … 2026-08-12;
sampled `.venv/lib` file mtimes include **2026-08-26**. The venv has been
modified after the runs → today's freeze must not be presented as the run env.

### 2e Split

| Class | Count |
|-------|------:|
| Evidence-backed pins | **0** |
| Unverified marker + post-hoc lockfile | **21** |

---

## Part 3 — Per-app score vectors (audit only; no regeneration)

### 3a Persistence table (by MASTER experiment family)

| Config / family | MASTER rows | Vectors persisted | Path if yes |
|-----------------|------------:|-------------------|-------------|
| `ocdev` | 14 | YES | `abrg/output/androct_2017/ocdev/artifacts/predictions.csv` (+ profiles under `devread`/`ocdev` for D0–D5) |
| `devread` | 18 | YES | `abrg/output/androct_2017/devread/artifacts/predictions.csv`; `devread/artifacts/profiles/*.npy` |
| `ocgtl` | 2 | YES | `abrg/output/androct_2017/ocgtl/artifacts/predictions.csv` |
| `supgnn` | 27 | YES | `abrg/output/androct_2017/supgnn/artifacts/predictions.csv` |
| `ocdev_validate` | 4 | NO | nested AUC draws only (`nested_aucs__*.npy`), not per-app |
| `ladder` | 7 | NO | fold/aggregate JSON |
| `validation` | 3 | NO | residualisation/bootstrap summaries |
| `apigraph` | 5 | NO | floor/coverage JSON |
| `kernels` | 3 | NO | grid/winner JSON |
| `glocalkd` | 2 | NO | family check JSON; **no** `.pt` checkpoints in tree |
| `ocgin` | 2 | NO | family check JSON; **no** checkpoints in tree |
| `invgraph` | 6 | NO | floor/variant JSON |
| `final_validate` | 2 | NO | check aggregates |
| `run3` | 7 | NO | `floors.json` metrics/CI only (no per-app score lists) |
| `run8` | 2 | NO | `comparison.json` aggregates only |
| **Total YES** | **61** | | |
| **Total NO** | **43** | | |

Also present but **not** in the 104-row MASTER catalogue: `arm_a_n1/per_app_scores.csv`,
`arm_b_n8/per_app_scores.csv`, `selfref/deviations/`, `selfref_e2/window_scores.csv`.

Detector JSON `score_distributions` remain **quantiles only** even when a
parallel `predictions.csv` exists.

### 3b Regenerable without retraining? (NO-vector rows)

| Family | Regenerable without retrain? | Basis |
|--------|------------------------------|-------|
| `run3` / GAE floors | **YES (scoring)** | `gae_androct_run3_model.pt` + `run2/corpus_cache` |
| `run8` | **YES (scoring)** | Run5 checkpoint + corpus cache |
| `ocgtl` (already YES vectors) | scoring via checkpoints | 72 `.pt` under `ocgtl/artifacts/checkpoints/` |
| `supgnn` (already YES) | scoring via checkpoints | many `.pt` under `supgnn/artifacts/checkpoints/` |
| `glocalkd`, `ocgin` | **NO without retrain** | no checkpoints on disk |
| `kernels`, `ladder`, `validation`, `apigraph`, `invgraph` | **partial / sklearn-refit** | tensors/vocab exist; detectors often not checkpointed as torch |
| `ocdev_validate` nested | N/A for per-app | would need outer-loop score storage, not present |
| `final_validate` | N/A | aggregates prior runs |

### 3c Gate

**No regeneration performed.** Author must decide knowingly before any
re-score that could disagree with catalogue AUC.

### 3d Fraction

**61 / 104** catalogue rows could have ROC AUC recomputed today from
persisted per-app score vectors (without re-inference).

---

## Part 4 — A.10.4 before/after

### Before

> Sixteen experiment directories carry SUMMARY.md but no reproduce.md;
> twenty-one reproduce_config.json files omit library version pins (GAPS.md).
> … reloads documented AUC_floor values … rather than recomputing ROC AUC
> from per-app score vectors, which most detector JSONs do not persist
> (quantile summaries only). …

### After

> Every experiment directory that carries a SUMMARY.md now also carries a
> reproduce.md (16/16 previously missing … UNDETERMINED where evidence
> absent). Of twenty-one configs that lacked pins, 0 evidence-backed, 21
> unverified against post-hoc lockfile
> `reproducibility/environment-2026-08-26.txt`. … Per-app score vectors …
> persisted for 61/104 catalogue rows … remaining 43/104 … quantile
> summaries or aggregate AUCs only. Independent verification does not
> re-infer trained torch models …

### Assessment: still a threat, or disclosure?

**Disclosure about verification scope**, not a validity threat to a reported
AUC under the “if false, would a number change?” test. After remediation it
fits better in **§A.7** (process / verification notes) or a short appendix
than under “Threats to validity.” **Not moved** — author decides.

---

## Files touched

- `abrg/output/androct_2017/{16 dirs}/reproduce.md` (created)
- 21× `reproduce_config.json` (`version_provenance` only)
- `reproducibility/environment-2026-08-26.txt` (created)
- `thesis/chapter_a/A10_threats.tex` (reproducibility paragraph)
- `chapter_a/GAPS.md` (status update aligned with remediation)
- `results/reproducibility_remediation.md` (this file)
