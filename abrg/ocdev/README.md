# ocdev — one-class readout on deviation profiles + support-novelty scoring

Additive module. Does not modify graph builders, GAE, ladder, devread, or tensors.

## Part A

Load saved `devread` deviation profiles D0–D5 (T22). Fit one-class detectors on the
**562 train-benign profiles only**. Detectors: centroid (L2/cosine), Mahalanobis
(Ledoit–Wolf), OCSVM, IsolationForest, kNN {1,5,20}, LOF. PCA on D2/D5.

T1K profiles are **not** saved under devread; dimensionalities are reported and Part A
runs T22 only.

## Part B

Support-novelty scores S1–S4 on transition cells, fit statistics on train-benign only.
Families: T22 proximity, T1K B_docfreq (1000×1000), T22 invocation (no self-loops).

## CLI

```bash
python -m abrg.ocdev                 # Part A then Part B
python -m abrg.ocdev --skip-partB
python -m abrg.ocdev --resume
```

## Output

`abrg/output/androct_2017/ocdev/` — see `SUMMARY.md`.
