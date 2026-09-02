# Chapter C — per-app reference, cold-start dilution, and recency (v2-extended)

Isolated module. Does **not** modify `abrg/output/androct_2017/`, `chapter_a/`,
or any AndroCT module. Outputs only under `abrg/output/v2_chapter_c/`.

## Corpus

`datasets/v2_extended/` — 40 GAE-eligible apps (extended), benign only, timestamped.
No malware; no AUC.

## Graph builder (required note)

| Path | Module | δ | recency |
|------|--------|---|---------|
| AndroCT tensors | `abrg.androct.graph_build.update_graph_sequence` | no | asserted empty |
| Chapter C / v2 export metrics | `abrg.graph.update_graph` | k∧δ | `w_rec` + `λ_rec` |

Chapter C uses **`abrg.graph.update_graph`** (same 22-node universe, static seeding,
shares-not-counts `graph_to_tensors`) because the AndroCT sequence builder cannot
exercise δ or recency. Export-time `graph_metrics` used the same timed path via
`build_session_graph`.

Pins: `k_burst=5`, `delta_sec=5`, `lambda_rec=0.01` (`abrg.config.LAMBDA_REC`),
`window_sec=60` multi-window cumulative (final snapshot per session).

## Reference combination

`R_k` = equal-weight mean of per-session **normalised** dense tensors (sessions 1…k
ordered by start time). Justification: equal session weight; distances on
shares-not-counts scale; Stage-3 channel variants differ only in adjacency
channel (`w_cum` / `w_rec` / concat both).

Held-out error `e(R_k, S_{k+1})` = Frobenius / cosine distance on the flattened
tensor (node block + adjacency block), not GAE reconstruction (no labels / no
malware train).

## Run

```bash
.venv/bin/python -m abrg.chapter_c
```

## Outputs

```
abrg/output/v2_chapter_c/
  SUMMARY.md
  reproduce.md
  reproduce_config.json
  figures/*.svg
  tensors/<app_id>/{session_vectors,references}.npz
  artifacts/*.json
```
