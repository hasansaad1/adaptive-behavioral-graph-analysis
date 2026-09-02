# Shallow GLAD: graph kernels / embeddings + one-class detectors

Additive package. Does **not** modify `abrg/graph/`, `apigraph/`, `transitions/`,
`invgraph/`, `models/`, `ocgin/`, `validate/`, mapper, or parser.

## Why

Trained deep GLAD underperformed untrained baselines on AndroCT 2017. OCPool
discards edges. This is the first method here that uses graph structure **without**
message passing.

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/kernels/` |
| Outputs | `abrg/output/androct_2017/kernels/` |
| CLI | `python -m abrg.kernels` |
| Split | digest `6129eb13d6a4…` (562/141/1700) asserted |

## Representations

| Tag | Source | Shape |
|-----|--------|-------|
| T22 | run2 `corpus_cache` (run 3 tensors) | `x` (22, 10) |
| T1K | B_docfreq K=1000 vocab + cached sequences → tensors | `x` (1000, 25) |

T1K tensors are materialized from frozen `vocab_B_docfreq_K1000.csv` (no re-ranking)
and cached under `kernels/embeddings/t1k_tensors.pt`.

## Stage 1 — unsupervised

| Method | Library |
|--------|---------|
| FGSD, NetLSD | Native ports (karateclub unavailable on CPython 3.14) |
| Graph2Vec, GL2Vec | WL tokens + TF-IDF + TruncatedSVD (gensim/karateclub unavailable) |
| WL / Propagation / ShortestPath | GraKeL (`grakel`); SP skipped on T1K |

**Fit discipline:** any fitted parameters use **train-benign only**. Kernels:
train×train Gram for fit; eval×train for scoring (never eval×eval).

**WL labels:** T22 = category identity (node index); T1K = argmax of 22-category
one-hot in features. Degree-label variant reported for all kernels.

## Stage 2 — one-class (train-benign fit)

Embeddings: OCSVM RBF ν=0.1 (standardized), IsolationForest(200), centroid E/C,
kNN {1,5,20}, LOF novelty=True. Seeds {42..46} where stochastic.

Kernels: OCSVM `kernel='precomputed'` ν=0.1; kNN in kernel distance {1,5,20}.

## Gate

(a) mapped-events size floor **0.7025** · (b) OCPool_mean raw **0.7765**.
Anything not clearing (a) is not a result.

## Ablation / nested CI

Winner only: edges-removed vs as-built; constant features (structure only);
nested bootstrap B=200 over train-benign refits.

## Output layout

```
abrg/output/androct_2017/kernels/
  embeddings/   vectors, Gram matrices, build times, failures
  detectors/    full grid per seed
  ablation/     edge / feature deltas
  bootstrap/    nested CI
  SUMMARY.md
  reproduce_config.json
```
