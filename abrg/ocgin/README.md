# OCGIN on AndroCT 2017

Deep one-class graph-level anomaly detection (Zhao & Akoglu, OCGIN / OCGIN†).
Additive package under `abrg/ocgin/`. Does **not** modify GAE, graph builder, mapper, or parser.

## Why

Reconstruction GAE (Runs 3–8) is a node-level reconstruction objective applied to a
graph-level AD task. OCGIN maps benign graphs near a fixed center θ in embedding space
and scores by distance. This run tests whether the AndroCT failure is the **objective
family** rather than the representation.

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/ocgin/` |
| Outputs | `abrg/output/androct_2017/ocgin/` |
| CLI | `python -m abrg.ocgin` |
| Tensors | Read-only `run2/corpus_cache` (same as Runs 3–8); identity asserted vs Run3 |

## Architecture

Shared:
- 4× `GINConv`, each with a **two-layer MLP (bias=False)**
- Node hidden dim **32**
- Per-layer readout: two-layer MLP (bias=False) then pool
- Hierarchical graph vector = concat of 4 layer readouts → **128-dim**
- No bounded activation on the final embedding

Variants:
- **OCGIN_orig**: mean pooling + `BatchNorm1d`
- **OCGIN_plus**: add pooling + `GraphNorm` (OCGIN†)

### Edge weights

PyG `GINConv.forward(x, edge_index, size=None)` does **not** accept `edge_weight` or
`edge_attr`. AndroCT `w_cum` edge weights are **not** passed into the encoder
(topology-only). This is stated here explicitly (not silently dropped without notice).

## Objective and collapse guards

\[
L = \mathrm{mean}_G \| f(G) - \theta \|^2
\]

- θ = mean embedding of an **untrained** forward pass over all train graphs, then **frozen**
- No bias in GIN/readout MLPs
- Collapse diagnostics every run (train/test_benign/test_malware):
  - per-dim embedding variance + mean across dims
  - mean/std of \(\|f(G)-\theta\|\)
  - fraction of embeddings within \(10^{-3}\) of θ
- If train mean variance \< \(10^{-6}\): **COLLAPSE DETECTED** (AUC not presented as a result)

## Training

- epochs 300, lr 0.01, wd 0, Adam
- Benign-only train (562 apps), seed pins matching Runs 3–8
- Seeds `{42,43,44,45,46}` → mean±std
- No tuning on test

## Scoring

Anomaly score = \(\|f(G)-\theta\|^2\).

## Baselines (same harness)

1. **OCPool** — pool raw `[22×10]` features (add/mean/max), fit OCSVM (RBF, ν=0.1)
2. **RANDOM-INIT OCGIN** — same architecture, no training; θ from untrained pass
3. Reference rows only (not re-run): GAE 0.638, Run8 emb 0.683 / rand 0.759, centroid 0.777, HGB 0.976

## Performance-flip diagnostic

- Variant A: train benign, malware = anomaly (thesis method)
- Variant B (**diagnostic only**): train 562 malware (seed=42), benign = anomaly  
  Report raw AUC for A and B and A+B. Variant B is never a proposed detector.

## Reproduce

```bash
cd /path/to/adaptive-behavioral-graph-analysis
source .venv/bin/activate
python -m abrg.ocgin
# artifacts → abrg/output/androct_2017/ocgin/
```

Requires existing `abrg/output/androct_2017/run2/corpus_cache/` and Run3 `comparison.json`
for the tensor-identity gate.
