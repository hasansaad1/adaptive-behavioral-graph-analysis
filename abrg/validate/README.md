# Validation of OCPool residual 0.8141

Additive package under `abrg/validate/`. Does **not** modify `abrg/apigraph/`,
`abrg/transitions/`, `abrg/invgraph/`, `abrg/models/`, or existing run outputs.
Imports read-only.

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/validate/` |
| Outputs | `abrg/output/androct_2017/validation/` |
| CLI | `python -m abrg.validate` |
| Split | Digest prefix `6129eb13d6a4` |

## Checks

1. **Residualization** — R0 raw · R1 OLS-on-eval (leaky) · R2 OLS-on-train (honest) ·
   R3 residual distributions + oov extrapolation range. Thesis carries **R2**.
2. **3×3 grid** — `{A_tfidf,B_docfreq,C_rawfreq} × {300,500,1000}`; vocab from
   train-benign only (asserted). OCPool mean/max raw + R2 residual.
3. **Nested bootstrap** — resample train apps → rebuild vocab → refit OCSVM + R2
   OLS → score fixed eval. B=200 (or 100 if runtime >2h). Vocab Jaccard stability.

## Reproduce

```bash
python -m abrg.validate
```
