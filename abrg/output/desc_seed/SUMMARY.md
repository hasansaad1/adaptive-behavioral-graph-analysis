# desc_seed — description-seeded reference at k=0

**Chapter C.** Fifty-three F-Droid apps; llama3.2 predictions are **frozen inputs**
(not regenerated on validate). Ollama output is not guaranteed reproducible across
versions even at temperature 0.

## Population

- Census: 59 v2 apps with ≥1 usable session (`reference_tier_pass`).
- Analysed: **53** (six excluded: five missing from F-Droid index, one empty description).
- Median observed active categories: **2** of 22 (IQR 2; range 1–7).
- Median description length: **738** characters (IQR 589.5).

## Method

- Metadata: F-Droid `index-v2.json`, 2026-08-31T08:25:43Z, AGPL-3.0; name, summary, description only.
- Model: **llama3.2** via Ollama, JSON-schema constrained 22-category probabilities.
- Package name withheld from prompt. Category defs: `abrg/api_category_map.py`.
- Primary decoding: temperature **0.0**, seeds 42–46 (deterministic).
- Stability arm: temperature **0.7**, same seeds.
- Observed: 53×22 binary matrix from `run2_comparison/v2_units.json`; column sums match `category_fire.csv`.

## Results — three framings

### 1. Self versus cross (does description *i* match app *i* better than app *j*?)

| Scorer | AUC |
|--------|-----|
| Cosine (temp 0.0) | 0.501 |
| Cosine (temp 0.7 mean) | 0.515 |
| Mass on observed-active / all 22 | 0.516 |
| Jaccard (pred ≥ 0.5) | 0.507 |
| Mean on active − mean on inactive | 0.538 |
| Population-mean profile baseline | 0.500 |

Ceiling: 34 distinct profiles; 25 apps duplicate another; max attainable AUC **0.979** (ties at 0.5). Observed 0.501 = **51%** of ceiling.

### 2. Within-app ranking (does description rank active categories above inactive?)

| | Descriptions | Prevalence prior |
|---|-------------|------------------|
| Median | 0.725 | **0.952** |
| Mean | 0.706 | 0.943 |
| Min / max | 0.386 / 0.958 | 0.725 / 1.000 |
| Apps > 0.5 | 48/53 | 53/53 |

Median delta −0.24; prior wins on 50/53 apps. Five apps below chance.

### 3. Per-category across apps (constant predictor = 0.5; prior cannot help)

Stable categories (fires / mean pred / AUC):

| Category | Fires | Mean pred | AUC |
|----------|------:|----------:|----:|
| storage | 40 | 0.547 | 0.508 |
| file_io | 39 | 0.483 | **0.420** |
| ipc_intents | 17 | 0.528 | 0.538 |
| crypto | 12 | 0.294 | 0.456 |
| network | 10 | 0.564 | 0.500 |
| database | 8 | 0.482 | 0.517 |
| native_code | 8 | 0.205 | 0.469 |
| webview | 6 | 0.549 | 0.544 |

Spearman ρ = −0.17 (p = 0.23) for per-app (model − prior) vs prior baseline: atypical-app hypothesis rejected.

## Stability arm (temp 0.7)

- Cross-seed SD: 0.162; mean pairwise correlation: 0.503.
- Displacement from temp 0.0: mean |Δ| 0.148; correlation 0.786.
- Parse success: 100% all seeds.

## Mechanism

Descriptions state **purpose**; the 22-category universe records **syscall surfaces**. The model over-scores ubiquitous categories (`storage`, `webview`, `content_access`) from generic prose. Example: offline apps firing `file_io` alone get `file_io` predicted at 0.10 while `webview`/`storage`/`telephony` sit at 0.18–0.22. `file_io` per-category AUC is **0.420** (below chance).

## Stated limits

- v2 is **benign-only**; this measures whether descriptions carry app-specific behavioural information, not detection.
- Tested: llama3.2 zero-shot on 53 apps, median two active categories. Does not establish descriptions are uninformative in general (CHABADA found signal on static API usage at larger scale).
- 25/53 apps share an exact observed profile; no per-app prior can discriminate identical fingerprints.
- Labelled malware under the same harness is the natural next collection (Chapter C threats).

## Artefacts

`reproduce_config.json`, `reproduce.ipynb`, `predictions/seed_{42..46}.json`, `predictions/temp07_seed_{42..46}.json`, `observed/observed_59x22.csv`, `stage2b_report.json`, `scores/self_cross_temp07.json`.

Validate:

```bash
cd REPO_ROOT
.venv/bin/python -m abrg.validate_reproduce --run-dir abrg/output/desc_seed --mode both
```
