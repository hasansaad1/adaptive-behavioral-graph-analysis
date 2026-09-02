# ABRG — Contributions and citation strategy

**Compiled 12 August 2026.** Companion to `ABRG_literature_synthesis_2026-08-12.md`
and the session handoff. This document answers two questions: *what does this thesis
contribute that is not already published*, and *which open questions are answered by
citation rather than by running another experiment*.

---

## Part 1 — What the thesis contributes

Ordered by defensibility, not by how interesting they sound.

### 1. Message passing measurably destroys signal under full supervision

| Mode | AUC |
|---|---|
| M2 — identical GIN, **empty** edge_index | **0.9000** |
| M1 — same GIN, edges as built | 0.8838 |
| M3 — edges, node features replaced by constant | 0.5903 |

M1 − M2 is negative in all three pooling variants: mean −0.0162, add −0.0285,
max −0.0121.

Over-smoothing is widely theorised (Li, Han & Wu 2018; Oono & Suzuki 2020) and the
1-WL expressiveness bound is established (Xu et al. 2019), but the cost has not been
*measured* on behavioural malware graphs with everything except the edge set held
fixed. Giving a supervised GIN access to the graph structure makes it worse than the
same network with no graph at all.

This is the strongest claim in the thesis because it is a controlled, single-axis
measurement under full supervision — it cannot be dismissed as an artefact of the
unsupervised objective.

### 2. A quantified supervision ladder on identical tensors

| Rung | Assumption | AUC |
|---|---|---|
| 1 — supervised, random split | seen behavioural groups | 0.9746 |
| 2 — supervised, behavioural-group holdout | **unseen groups** | **0.8492** (weighted 0.8606) |
| 3 — benign-only one-class | no malware at all | 0.7544 (raw 0.7765) |

Two priced gaps: **0.127** is the cost of unseen behavioural groups, **0.095** the
additional cost of abandoning malware labels entirely.

Supported by two controls that make the ladder interpretable rather than decorative:
- **Random-group control 0.9864** — shuffled groups score essentially as high as a
  random split, so behavioural-group holdout is measurably harder and the grouping
  carries meaning.
- **Volume diagnostics** — between/within variance ratio 1.899 on volume-stripped
  structural features vs 0.0257 on `mapped_event_count`; fold AUC vs fold median
  mapped events ρ = 0.058, p = 0.76. The clusters are behavioural groups, not
  trace-length strata.

Nobody has priced the benign-only guarantee for Android behavioural graphs. This
turns an inconvenient constraint into a measured trade-off curve.

*Caveat to report, not bury:* per-fold std is 0.1636 across 30 folds, and 21 of 30
folds clear their own mapped-event floor. Lead with the size-weighted and pooled
out-of-fold figures, show the per-fold distribution.

### 3. The deviation vector works — the scalar was the failure

| Readout | AUC |
|---|---|
| D0 — summed reconstruction error (the standard formulation) | 0.638 |
| D3 — per-node deviation profile, supervised readout | **0.9624** |
| raw-input control (same classifier, raw tensors) | 0.9746 |

Same GAE, same benign-only training, same split. The entire performance loss came
from collapsing the deviation *vector* into a single scalar and thresholding it.

This is a specific mechanical diagnosis of why reconstruction-based anomaly detection
failed in this setting, and it partially vindicates the ABRG design: the deviation
signal exists and is rich; the aggregation step destroyed it.

*Honest boundary:* D3 does not beat the raw-input control (0.9624 vs 0.9746), so the
GAE is a near-lossless but non-additive transform. Report both numbers adjacent.
Shuffled-label control 0.5035; checkpoint reload reproduced its AUC exactly.

### 4. A counter-example to a published remedy

Cai et al. (2024) argue that constraining the autoencoder latent space to a
sufficiently low dimension prevents the "identical shortcut" by which autoencoders
reconstruct anomalies as readily as normal data.

Run 5 swept hidden dimension at α = 0.2:

| h | AUC |
|---|---|
| 2 | **0.568** |
| 8 | 0.638 |
| 64 | 0.638 |

Node feature dimension is 10, so h = 2 is a genuine 5× compression and h = 64 an
expansion. The most constrained latent performed *worst*, and a real bottleneck (h=8)
merely tied the expansion (h=64). The proposed remedy did not hold here.

Small and specific, but it is a direct empirical counter-example to a named published
fix — exactly the kind of result that makes a negative-result paper citable rather
than merely honest. Currently unreported in the results narrative; promote it.

### 5. Untrained beats trained across six method families

| Family | Trained | Untrained / no-training |
|---|---|---|
| GAE reconstruction | 0.638 | input centroid 0.777 |
| GAE embedding distance (Run 8) | 0.683 | random-init 0.759 |
| OCGIN one-class | 0.566 | random-init 0.654 |
| GLocalKD distillation | 0.5594 (T22 mean, Table A.7) | untrained predictor 0.6650 |

Table A.7 pairing: T22 / pool=mean / loss=full / score=s_graph / 5 seeds.
Alternate (not in Table A.7): T22 max-pool gives trained 0.5791 / untrained ~0.672.
| Graph kernels | WL_h3 0.6726 | (no training stage) |
| Pooling | — | OCPool_mean **0.7765** |

Random-init or no-training baselines win in five of six families. Any single instance
is a curiosity; six independent architectures converging on the same relationship is
a finding about what benign-only GNN training does to this representation.

Corroborating context: OCPool is a published baseline that ignores edges entirely and
is reported to do well on several benchmarks. Independently rediscovering this and
then measuring it across six families is the contribution.

### 6. Structure carries signal that message passing cannot reach

| Measurement | AUC |
|---|---|
| WL_h3 kernel, structure only (features constant) | **0.6268** |
| WL_h3 kernel, edges removed | **0.5000** (exactly chance) |
| Supervised GIN, structure only (M3) | 0.5903 |
| `edge_count` floor, 22-node | 0.5267 |
| `edge_count` floor, API-1000 and B_docfreq | 0.5013 |
| `edge_count` floor, 22-category invocation edges | 0.5056 |

The edge-count floors measure how *many* edges — a scalar — and sit at chance
everywhere. The WL ablation measures edge *pattern*, and it is decisively above
chance at 0.6268, collapsing to exactly 0.5000 when edges are removed.

So topology is informative. A kernel reads it; a GNN does not (0.5903 supervised,
below the kernel). The correct claim is not "structure carries no signal" but
"structure carries signal that message passing cannot extract" — a sharper statement
that required both measurements to establish.

*Also established:* the null holds across two granularities (22-category, 1000-API)
and two edge definitions (k=5 sequence proximity, true caller→callee invocation),
with drop-rate symmetry verified for the invocation variant (either-unmapped class
gap 0.0012).

### 7. Methodological contribution — a corpus-validation record

Four defects found and corrected, each of which would have silently invalidated
results:

| Defect | Effect | How caught |
|---|---|---|
| `_CALL_RE` rejected `<init>` / `<clinit>` | dropped 14.0% of benign and 39.0% of malware lines — **asymmetric and label-aligned**; 3.6M mapped events recovered; `dynamic_code_loading` resurrected | raw-text grep before the mapper, staged pipeline trace |
| ≥320 mapped-event eligibility floor | excluded 58.5% benign vs 27% malware, flipped floor directions, drove `active_categories` from 0.501 to 0.680 — the arms competed against a baseline the selection rule created | recomputing floors pre- and post-exclusion |
| OOV-rate residualization fitted on the eval set | inflated the headline from 0.7544 to 0.8141; out-of-sample coefficient had the **opposite sign** (+0.449 vs −2.236), R² collapsed 0.053 → 0.002 | refitting on train-benign only |
| Vocabulary selection excluded from the CI | naive CI [0.771, 0.851] vs nested [0.699, 0.800] — roughly a third too narrow | nested bootstrap resampling apps and rebuilding the vocabulary |

Plus one artefact caught before it became a result: the V2 invocation-edge floor of
0.7338 restated a 99.99% malware edge-drop rate rather than measuring topology,
confirmed by V3's ancestor projection recovering edges and the floor falling to
0.5070.

This is a reusable account of how graph-based malware evaluations go wrong. Most
theses do not produce one because most do not look.

### What the thesis does **not** find

No benign-only method beats the trivial size floors by a comfortable margin. Best is
OCPool_mean at 0.7765 raw / 0.7544 residualized, against a mapped-event floor of
0.7025, with the nested CI lower bound at 0.699 sitting essentially *on* that floor.

State this plainly. It is the honest boundary of the work, and it is the finding — not
the absence of one.

---

## Part 2 — Questions answered by citation, not by experiment

Three open questions can be closed with published evidence. Putting them in related
work as *considered and rejected with a reason* reads considerably stronger than
silence, and it pre-empts the corresponding defence questions.

### "Why didn't you try a graph transformer?"

**HiGraph** (arXiv 2509.02113, 2025) — 499K Android applications, 200M+ nested CFGs
and 499K FCGs spanning 2012–2022, with a cross-anchor concept-drift protocol over
433,488 test apps across ten years.

Two findings do the work:

1. Hierarchical CFG/FCG modelling outperformed **both** flat-graph GNNs **and
   GraphGPS** — a current graph transformer — under matched feature and hidden
   dimensions.
2. The discriminative malware signal localises to **CFG-level cyclomatic complexity
   rather than aggregate FCG metrics**.

The second point is independent corroboration of this thesis's structural null at a
scale it cannot match: aggregate graph-level metrics do not carry the malware signal.

Their remedy is *hierarchy* — nesting control-flow graphs inside function-call graphs
— not a better GNN architecture. A dynamic behavioural trace has no CFG level
available, so that remedy is structurally unavailable to ABRG. This is a clean
limitation statement rather than an omission.

### "Why didn't you try graph rewiring?"

Rewiring (curvature-based SDRF, spectral, diffusion-based DIGL, DIFFWIRE, random
regular superposition as in GRASS) modifies connectivity to relieve over-squashing and
over-smoothing, and is the obvious response to a message-passing failure.

A 2025 survey of rewiring for over-squashing and over-smoothing reports that
curvature-based benefits are highly sensitive to both training and rewiring
hyperparameters and vary across graphs, and that reported state-of-the-art gains often
arise from favourable hyperparameter configurations rather than from consistent
improvement over the original topology (Tori et al. 2025, cited therein).

Rejecting this with a published sensitivity warning is stronger than either running it
or ignoring it.

### "Why didn't you address anomaly reconstruction with a memory module?"

Gong et al. (2019) propose MemAE to limit out-of-bounds reconstruction. The critique
literature notes it reduces reconstruction ability substantially and adds considerable
training and optimisation complexity. It also does not address the mechanism measured
here — malware near-collinearity, 1 PCA component to 90% variance vs 2–3 for benign.

One sentence in related work: a remedy not attempted, with the reason.

---

## Part 3 — The framing sentence

> The ABRG representation carries strong malware signal — supervised classification
> reaches 0.976, and per-node deviation profiles from a benign-only GAE reach 0.9624.
> Benign-only anomaly detection recovers 0.7544, against a trivial floor of 0.7025.
> Across six method families, two graph granularities and two edge definitions, no
> trained GNN outperformed an untrained or edge-free baseline, and a supervised GIN
> scored *lower* with edges than without them. Behavioural graph topology carries
> measurable signal that message passing does not extract, and the cost of the
> benign-only guarantee — 0.095 AUC against unseen-group supervision, 0.22 against
> random-split supervision — is quantified on identical tensors.

---

## Key numbers, for quick reference

```
supervised HGB, random split            0.9762  (full) / 0.9593 (adj_only)
supervised GIN M2 (no edges)            0.9000
supervised GIN M1 (with edges)          0.8838      <- M1 - M2 = -0.0162
deviation profile D3 + HGB              0.9624
raw-input control                       0.9746
supervised, behavioural holdout         0.8492  (weighted 0.8606)
random-group control                    0.9864
OCPool_mean raw                         0.7765      nested CI [0.699, 0.800]
OCPool_mean residualized (train-fit)    0.7544
input centroid                          0.777
random-init GAE embedding               0.759
WL_h3 kernel                            0.6726
WL_h3 structure-only                    0.6268
WL_h3 edges-removed                     0.5000
GAE reconstruction (D0 scalar)          0.638
OCGIN_plus                              0.566
GAE h=2 (Cai et al. counter-example)    0.568
size floor, mapped_event_count          0.7025
edge_count floors (all variants)        0.5013 - 0.5267
```

Corpus: AndroCT 2017, 764 benign / 1742 malware, same-sensor, no timestamps.
Split digest `6129eb13d6a4…` — 562 train benign / 141 test benign / 1700 test malware.
