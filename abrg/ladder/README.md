# Supervision ladder (`abrg/ladder`)

Additive experiment measuring the cost of supervision level on identical T22 tensors.

## Isolation

- New module only; read-only imports from corpus cache, Run 3 split, Run 3.5 vectorization.
- No edits to `graph/`, `apigraph/`, `transitions/`, `invgraph/`, `kernels/`, `glocalkd/`,
  `models/`, `ocgin/`, `validate/`, mapper, or parser.

## Pins

| Pin | Value |
|-----|-------|
| Dataset | AndroCT 2017 v2 eligible population |
| Benign split | app-level 80/20, seed=42, digest `6129eb13d6a4…` |
| Tensors | T22 `(22, 10)` from `run2/corpus_cache` |
| Rung 1 split | stratified both-class 80/20 (Run 3.5 harness) |
| Rung 2 benign | fixed GAE train/test benign (562 / 141) |
| Models | LogisticRegression + HistGradientBoosting |
| Modes | `full`, `node_only`, `adj_only` (704 / 220 / 484 dims) |
| HGB seeds | 42–46 |

## Stages

1. **Grouping** — Route A: VT/AVClass availability check (no fabrication). Route B:
   malware-only Ward + KMeans on standardized 704-dim vectors; k via max silhouette
   over {5, 10, 15, 20, 30}.
2. **Rung 1** — random stratified split; must reproduce HGB full ≈0.976 and adj_only
   ≈0.959 within 0.01.
3. **Rung 2** — leave-one-cluster-out (Ward); benign fixed; per-fold floors + leakage cosine.
4. **Control** — random-group holdout (same cluster sizes, seed=42).
5. **Rung 3** — reference rows only (OCPool_mean 0.7765 / R2 0.7544).

## CLI

```bash
python -m abrg.ladder
python -m abrg.ladder --skip-rung2   # grouping + harness only
```

## Output

```text
abrg/output/androct_2017/ladder/
  grouping/
  rung1/
  rung2/
  control/
  SUMMARY.md
  reproduce_config.json
```

Numbers and tables only in `SUMMARY.md`; no conclusions.
