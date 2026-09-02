# Invocation-graph representation (AndroCT 2017)

Additive package under `abrg/invgraph/`. Does **not** modify `abrg/graph/`,
`abrg/apigraph/`, `abrg/models/`, `abrg/ocgin/`, mapper, or parser. Imports
read-only.

## Why

Prior graphs used **sequence-proximity** edges (k=5). Edge floors stayed near
chance (22-node 0.5267; API / B_docfreq ≈ 0.5013). AndroCT lines are real
`<caller> -> <callee>` invocations; the caller side was discarded. This run
holds nodes/features fixed (B_docfreq K=1000) and varies **only** the edge
definition.

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/invgraph/` |
| Outputs | `abrg/output/androct_2017/invgraph/` |
| CLI | `python -m abrg.invgraph` |
| Split | Digest must start with `6129eb13d6a4` (562/141/1700) |
| Vocab | Reused verbatim: `apigraph/vocab_control/vocab_B_docfreq_K1000.csv` |

## Caller discard (prior pipelines)

- `abrg/apigraph/extract.py` :: `_iter_call_lines` — yields only `m.group(2)`
- `abrg/androct/run2_corpus.py` / `run_gae_run2.py` — categorize callee only

The full parser (`abrg/androct/parse.py`) already retains both endpoints in
`CallEvent`; downstream graph builders dropped the caller.

## ICC decision

`[ Intent sent ]` / `[ Intent received ]` blocks do **not** yield
`(caller, callee)` method pairs (`callee=None` in the parser). **Excluded**
from invocation edges. Only soot `<caller> -> <callee>` lines are used.

## Variants (same nodes + features; edge axis only)

| Variant | Edges |
|---------|--------|
| `V1_proximity` | k=5 callee-sequence proximity (control; must match B_docfreq edge ≈ 0.5013) |
| `V2_invocation` | caller→callee when **both** in vocabulary |
| `V3_invocation_projected` | V2 + when caller OOV, nearest in-vocab ancestor within lookback **32** |

Node features (dim **25**): activity share, active flag, first-occurrence,
22-category one-hot. `w_cum` + shares-not-counts.

## Gate

If V2/V3 `edge_count` and `density` stay ~0.50–0.53 → **STOP** (no Stage 4).
If either reaches ≥ 0.60 → **PASS** and train on the best V2/V3 variant.

## Reproduce

```bash
python -m abrg.invgraph
```
