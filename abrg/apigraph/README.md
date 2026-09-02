# API-level graph representation (AndroCT 2017)

Additive package under `abrg/apigraph/`. Does **not** modify `abrg/graph/`,
`abrg/models/`, `abrg/ocgin/`, the 22-node universe, the mapper, or the AndroCT
parser. Imports those modules read-only.

## Why

Structural floors on the 22-node representation sit near chance
(`active_nodes` 0.5164, `edge_count`/`density` 0.5267); only volume separates
classes (`mapped_event_count` 0.7025). This experiment replaces category nodes
with TF-IDF-ranked API callees (fixed vocabulary size K) to test whether the
**representation**, not the objective, is the limiting factor.

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/apigraph/` |
| Outputs | `abrg/output/androct_2017/apigraph/` |
| CLI | `python -m abrg.apigraph` |
| Split | Same Run3 app-level 80/20, seed=42 (562 / 141 / 1700); SHA lists asserted |

## Integrity constraint (vocabulary)

**Node vocabulary is derived exclusively from the 562 train-benign apps.**
Malware and held-out benign are never used to rank or select nodes. This is
asserted in code (`build_vocabularies` key equality + `N==562`) and written to
`vocab/VOCAB_INTEGRITY.txt`.

## Callee normalisation

From each soot method signature: keep `fully.qualified.Class.methodName`.
Drop parameter types and return type. Keep `<init>` / `<clinit>` as method names.

## TF-IDF ranking formula

Over train-benign apps only, each app is a document:

\[
\begin{aligned}
\mathrm{tf}(a,c) &= \frac{\mathrm{count}(c \in a)}{|a|} \\
\mathrm{idf}(c) &= \log\frac{N}{\mathrm{df}(c)} \\
\mathrm{tfidf}(a,c) &= \mathrm{tf}(a,c)\cdot\mathrm{idf}(c) \\
\mathrm{score}(c) &=
  \Bigl(\mathrm{mean}_{a:c\in a}\,\mathrm{tfidf}(a,c)\Bigr)\cdot\mathrm{df}(c)
\end{aligned}
\]

where \(N=562\) and \(\mathrm{df}(c)\) is the number of train-benign apps
containing callee \(c\). Top-K vocabs for \(K\in\{100,300,500,1000\}\).

## Graph construction (per K)

- **Nodes:** fixed K vocabulary entries (identical across apps). OOV calls dropped.
- **Edges:** \(k=5\) sequence proximity (same burst rule as 22-node); `w_cum` only;
  no fabricated timestamps.
- **Normalisation:** shares-not-counts (out-edge shares sum to 1; node activity is
  share of in-vocabulary events).
- **Node features (dim = 25):** activity share, binary active, first-occurrence
  position in \([0,1]\), 22-category one-hot from `categorize_callee`.
- **Static features (dim = 4, global graph attribute):** declared permission count,
  component-count proxy (\(\sum\) category `reach_v`), static feature L2 norm,
  nonzero static category count. Per-node permission mapping was **not** attempted.

## Stage 3 gate

Recompute size/structure floors (`max(auc, 1-auc)`) per K. Compare to 22-node
baselines. **If `active_nodes` and `edge_count` remain ~0.52 for every K → STOP;
do not train.** If any structural floor moves to \(\ge 0.60\), continue to Stage 4
on the K with largest \(\max(\mathrm{active\_nodes},\mathrm{edge\_count})\).

## Stage 4 (conditional)

Supervised probe (LR + HGB, stratified both-class), OCPool (add/mean/max),
GAE dual recon \(\alpha=0.2\), \(h=8\) (Run 5 pins), OCGIN_plus, random-init
controls; seeds `{42..46}`; Spearman vs size/structure covariates.

## Reproduce

```bash
python -m abrg.apigraph
python -m abrg.apigraph.run_vocab_control   # K=1000 A/B/C vocab controls
```

Artifacts: `vocab/`, `graphs/`, `floors/`, `models/` (if gate passes), `SUMMARY.md`,
`vocab_control/` (A/B/C coverage + oov floors + OCPool residual).
