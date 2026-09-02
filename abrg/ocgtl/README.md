# OCGTL — one-class graph transformation learning

Additive module `abrg/ocgtl/`. Does not modify graph builders, GAE, OCGIN, ladder,
supgnn, or existing tensor caches.

## Reference vs reimplementation

**Reimplemented from the paper** (Qiu, Kloft, Mandt, Rudolph, IJCAI 2022).

The Bosch reference at
https://github.com/boschresearch/GraphLevel-AnomalyDetection is **AGPL-3.0**, so it
was **not vendored** into this tree. The implementation was cross-checked against
commit `7b2295d477f2ef48cd270c137710bae0445b5481` (recorded in
`reproduce_config.json`) and written independently.

If a local `abrg/ocgtl/_ref/` checkout exists, it is for inspection only and must
not be imported.

## Ambiguities flagged

1. **GTL negatives:** user brief said “other graphs in the batch”; paper Eqn (2) and
   the reference use **within-graph** competition among the K views. We follow the
   paper/reference.
2. **Temperature τ:** paper leaves τ unspecified; reference uses `1.0`. We use `1.0`.
3. **Learning rate:** user suggested 0.01; paper/config default is **0.001**. We use
   **0.001** (paper default). Epochs=300 and batch=64 follow the user brief (paper
   config used 500 / 128).
4. **Scheduler / early stopping:** paper config uses StepLR + Patience; user brief
   did not. We use plain Adam, no scheduler, no early stopping on test.
5. **Centre:** paper and reference treat θ as a **trainable** `Parameter` (normal
   init). K=1 OCC ablation freezes θ from an untrained forward mean (OCGIN-style).

## Architecture

- K encoders total: 1 reference + (K−1) transforms. Sweep K ∈ {4, 6}.
- Each encoder: 4× GINConv, hidden=32, ReLU, GraphNorm, **add** hierarchical readout
  (OCGIN_plus combination). Graph embedding dim = **128**.
- **No bias** in any MLP/readout; **no bounded** final activation.

## Loss (exact)

```
L_OCGTL = L_OCC + L_GTL   # equal weight; paper Eqn (1); not tuned on test

L_OCC(G) = sum_{k=1}^{K-1} ||f_k(G) - θ||_2

L_GTL(G) = sum_{k=1}^{K-1} [log C_k - log c_k]
c_k = exp(sim(f_k, f_ref)/τ)
C_k = sum_{j≠k} exp(sim(f_k, f_j)/τ)   # j over all K views
sim = cosine; τ = 1.0
```

Anomaly score at test = `L_OCGTL` (higher = more anomalous).

## Training

Benign-only. Adam, lr=0.001, wd=0, epochs=300, batch=64. Seeds {42..46}.

## CLI

```bash
python -m abrg.ocgtl --pilot          # time one (T22,K=4,seed=42,Split-A)
python -m abrg.ocgtl --reps T22
python -m abrg.ocgtl --resume --skip-split-b
```

## Output

`abrg/output/androct_2017/ocgtl/` — see SUMMARY.md (degeneracy first, then gates).
