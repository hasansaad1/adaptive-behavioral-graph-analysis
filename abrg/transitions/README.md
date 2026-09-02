# Transitions: one-class on adj + 22-category invocation edges

Additive package under `abrg/transitions/`. Does **not** modify `abrg/graph/`,
`abrg/apigraph/`, `abrg/invgraph/`, `abrg/models/`, `abrg/ocgin/`, mapper, or
parser. Imports read-only.

## Isolation

| Item | Path |
|------|------|
| Code | `abrg/transitions/` |
| Outputs | `abrg/output/androct_2017/transitions/` |
| CLI | `python -m abrg.transitions` |
| Split | Digest prefix `6129eb13d6a4` (562/141/1700) |

## Part B (runs first)

One-class detectors on **existing** run-3 proximity tensors (no new graphs).

### Feature sets

| ID | Description | Dim |
|----|-------------|-----|
| F1 | flattened 22×22 transition (`adj_only`) | 484 |
| F2 | flattened 22×10 node features | 220 |
| F3 | full (node + adj) | 704 |
| F4 | per-node out-transition summary | 66 |
| F5 | OCPool-style mean(node) ⊕ F4 | 76 |

**F4 definitions** (per node \(i\), adjacency row \(A[i,:]\)):

- `out_degree_share` = \(\mathrm{nnz}(A[i,j], j\neq i)/(N-1)\)
- `out_entropy` = \(H(\mathrm{normalize}(A[i,:]))\) (0 if empty)
- `max_out_share` = \(\max_j A[i,j]\)

PCA on F1 and F3 at \(n\in\{8,16,32,64\}\), **fit on train-benign only**.

### Detectors (train-benign only)

OCSVM(RBF, ν=0.1) + StandardScaler; IsolationForest(200);
Centroid Euclidean / Cosine; Mahalanobis (Ledoit-Wolf);
kNN mean distance \(k\in\{1,5,20\}\). Seeds `{42..46}` for stochastic detectors.

## Part A

Map **both** caller and callee through `categorize_callee` onto the 22-category
universe. If a side returns multiple categories, add the **cartesian product** of
edges. Node features copied from run-3 tensors (dim 10). Self-loops reported
with/without; **downstream = no self-loops**.

Drop rates (caller / callee / either unmapped) reported per class. Gate requires
edge floors ≥0.60 **and** class-symmetric either-unmapped (±5 points).

## Reproduce

```bash
python -m abrg.transitions
```
