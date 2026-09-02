# Chapter B — v2 corpus provenance and AndroCT representation comparison

Isolated module. Does **not** modify `abrg/output/androct_2017/`, `chapter_a/`,
`abrg/chapter_c/`, or any AndroCT module. Outputs only under
`abrg/output/v2_chapter_b/`.

Descriptive only. v2 is benign. No detector, no AUC, no supervised probe.

## Corpus

`datasets/v2_extended/` — Frida sessions (original + canary + extend). Run
`python3 datasets/v2_extended/verify_export.py` first (must exit 0).

## Graph builders (read-only imports)

| Use | Module |
|-----|--------|
| Run 1 old-vs-new topology | `abrg.corpus.build_session_graph` (export-time timed path) |
| Run 2 v2 vs AndroCT | `abrg.androct.graph_build.update_graph_sequence` (k-burst, no time) |
| Mapper | `abrg.trace.load_frida_trace` |
| AndroCT parse / inventory stats | `abrg.androct.parse.parse_androct_text_stream`, `abrg.androct.inventory._summarize_dist` / `_mann_whitney_u` / `_percentile` |

## Unit alignment

AndroCT: one whole-trace graph per app. v2: report **per-session** and **per-app
pooled**. Pooling = concatenate mapped category streams in
`session_index_within_app` order, then one `update_graph_sequence`. Not a
merge of per-session graphs.

## Run

```bash
python3 datasets/v2_extended/verify_export.py
python -m abrg.chapter_b
```

## Outputs

```
abrg/output/v2_chapter_b/
  run1_corpus/
  run2_comparison/
  PROVENANCE.md
  SAFETY.md
  SUMMARY.md
  figures/
  artifacts/
```
