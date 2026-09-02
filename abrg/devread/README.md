# Experiment S2 — devread

Deviation profile plus supervised readout, additive-only.

## Scope

- GAE stage is benign-only and keeps Run-5 pins (`h=8`, `alpha=0.2`, epochs=300, lr=0.01, wd=0, seed=42).
- Readout stage is supervised and uses labels on split partitions.
- This is **not** benign-only end-to-end: only the encoder training is benign-only.

## Data and isolation

- T22 from run-2/run-3 corpus cache (`x=(22,10)`).
- T1K reused for profile dimensionality reporting (`x=(1000,25)`).
- Ladder Ward assignments are reused from:
  `abrg/output/androct_2017/ladder/grouping/route_b_behavioral.json`.

## Profiles

- `D0`: scalar total dual recon error.
- `D1`: per-node feature recon error.
- `D2`: per-cell adjacency recon error (flattened full matrix for T22).
- `D3`: per-node aggregate over D2 (mean,max).
- `D4`: `D1 || D3`.
- `D5`: `D1 || D2`.

## Readout

- Classifiers: `LR_L2`, `LR_L1`, `HGB`.
- Splits:
  - `splitA`: random stratified 80/20 (seed=42).
  - `splitB`: behavioral group holdout using existing ladder Ward groups.
- Controls:
  - raw-input readout (`RAW_full`, `RAW_node_only`, `RAW_adj_only`),
  - random-init GAE profiles,
  - shuffled-label control.

## CLI

```bash
python -m abrg.devread
```

## Output

```text
abrg/output/androct_2017/devread/
  artifacts/
  profiles/
  splitA/
  splitB/
  controls/
  interpret/
  SUMMARY.md
```
