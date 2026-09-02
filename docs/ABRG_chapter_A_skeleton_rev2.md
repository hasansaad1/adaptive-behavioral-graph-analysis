# Chapter A — skeleton, revision 2

**Revised 13 August 2026.** Supersedes revision 1. Changes marked **[NEW]** or
**[FIXED]**. Every number traceable to `chapter_a/MASTER_RESULTS.csv` (103/103
verified).

---

## Examiner-level review of revision 1

| Gap | Severity | Fix |
|---|---|---|
| **No related work section** | **High** — a thesis chapter cannot position its contribution without one | New §A.3 |
| **Contributions never stated explicitly** | **High** — examiners look for this first | New §A.1.3 |
| **RQ → answer loop never closed** | Medium | New §A.9 table |
| **No discussion section** — chapter is report, not argument | Medium | New §A.8 |
| **No positioning against published numbers** | Medium — "is 0.80 good?" has no answer | New §A.8.1 |
| API-level granularity work barely represented | Medium | New §A.6.4 |
| adj_only 0.959 vs one-class 0.545 only implicit | Medium — this is one of the sharpest findings | Promoted to §A.6.3 |
| Input-centroid caveat (0.777 / 0.568 / 0.575) missing | Medium | Added §A.6.5 |
| One-class baseline table absent | Low | Added §A.6.3 |
| GLocalKD explainability null missing | Low | Added §A.6.3 |
| Figures not mapped to sections | Low | Inline throughout |
| D3 seed ambiguity unresolved | Low | Fixed in §A.6.5 |
| S1_norm status inconsistent | Low | Fixed — reported, not headline |
| Page budget absent | Low | Added below |

**Page budget (~45–55 pages):** A.1 framing 3 · A.2 corpus 8 · A.3 related work 6 ·
A.4 method 5 · A.5 protocol 2 · A.6 results 16 · A.7 artefacts 3 · A.8 discussion 5 ·
A.9 conclusions 2 · A.10 threats 3.

---

# A.1 Framing

## A.1.1 Problem and design

Zero-day Android malware; benign-only training as a design commitment rather than a
concession. ABRG in one paragraph: per-app reference graph, static seeding, dynamic
refinement, deviation as the detection signal, explainability grounded in *where* the
graph deviated.

## A.1.2 The exercise matrix — state this early

No single corpus can test the whole design. This is why the thesis has more than one
chapter.

| Design element | Chapter A (AndroCT) | Chapters B/C (v2) |
|---|---|---|
| δ temporal edge filter | unavailable — no timestamps | available |
| Recency edge channel | unavailable | available |
| Per-app cross-session refinement | unavailable — 1 trace/app | available |
| Malware evaluation | available | unavailable — no malware |

## A.1.3 **[NEW]** Contributions of this chapter

State them numbered, ordered by defensibility. Examiners look for this page.

1. A controlled measurement that **message passing reduces classification performance
   under full supervision** on behavioural malware graphs — M1 − M2 negative in all
   three poolings, replicated across two splits.
2. A **quantified supervision ladder** on identical tensors, pricing the cost of
   unseen behavioural groups (0.127) and of abandoning malware labels entirely
   (0.048), with a random-group control establishing that the holdout is meaningful.
3. A mechanical diagnosis that **the deviation vector carries the signal and the
   scalar destroys it** — 0.638 → 0.9624 from the same benign-only GAE.
4. A **direct empirical counter-example** to a published remedy for autoencoder
   anomaly reconstruction (Cai et al. 2024).
5. Evidence across **seven method families** that trained and untrained graph models
   are statistically indistinguishable on this representation.
6. The separation of **edge count from edge pattern**: topology carries measurable
   signal (WL structure-only 0.6268) that message passing does not extract.
7. A **corpus-validation record** — seven artefacts identified and corrected, two of
   which had already produced headline numbers.

## A.1.4 Research questions

RQ1 Does the representation carry malware signal at all?
RQ2 Does benign-only reconstruction detect malware?
RQ3 Is failure attributable to the objective, the architecture, or the representation?
RQ4 Does graph topology contribute, and can message passing extract it?
RQ5 What does the benign-only guarantee cost?
RQ6 Where in the deviation signal does the information sit?
RQ7 Is any of it deployable?

---

# A.2 Corpus

*(Unchanged from revision 1 — reproduced in outline.)*

**A.2.1 Selection: sensor symmetry as the deciding axis.** Five options collapse to
three. Mixed-sensor is worst for ABRG specifically because sparsity dominates
reconstruction error and sensor differences change sparsity — the confound aligns with
the label. The falsification test: AndroCT ships benign traces, so anyone can score
them against a ContextDroid-trained GAE. Why AndroCT over CICMalDroid/KronoDroid:
callee signatures carry Java API identity, so mapping is a lookup, not an invention.

**A.2.2 Four validation gates.** Year overlap (archive filenames unreliable; 2019 pair
was 2016 benign / 2011 malware). Parser (`_CALL_RE` rejecting `<init>`/`<clinit>`,
dropping 14.0% benign / 39.0% malware — asymmetric and label-aligned; categories
firing 20/17 → 21/18). Benign naming collapse (1,648/2,256 package-named; 172
resolved, 145 ambiguous, 1,331 unresolvable). Eligibility floor (≥320 excluded 58.5%
benign vs 27% malware and manufactured the baseline).

**A.2.3 Population and attrition.** 2256 → 764 → 763 → 713 → 703 benign;
1742 → 1700 malware. **Zero-mapped exclusion asymmetric: 6.6% benign vs 2.2%
malware — report it.** Inventory table. `sms` genuinely dead in both classes. 96%
empty-category rate is correct behaviour.

**A.2.4 Ethics and data handling.** No malware binaries for trace evaluation; ~1,700
APKs for static seeding, Androguard parsing only, no execution. Licence terms and
faculty-sponsor condition.

*Figure F6 (granularity floors) is introduced later but its 22-node column belongs
conceptually here.*

---

# A.3 **[NEW]** Related work

Six pages. Without this the chapter cannot claim novelty.

## A.3.1 Graph-level anomaly detection

OCGIN and the performance-flip characterisation (Zhao & Akoglu); OCGTL and the
hypersphere-collapse guarantee (Qiu et al., IJCAI 2022); GLocalKD random-teacher
distillation (Ma et al., WSDM 2022); OCPool as the edge-free baseline; UB-GOLD as the
unifying benchmark; the TKDE 2025 survey. **Report the published OCGIN band (≈50–62
AUC across benchmarks) — it is what makes this chapter's numbers interpretable.**

## A.3.2 Reconstruction-based anomaly detection and its critique

Bouman & Heskes (2025) on autoencoder unreliability; the identical-shortcut
explanation (You et al. 2022; Lu et al. 2023; Bercea et al. 2023); **Cai et al. 2024's
low-dimensional-latent remedy, which §A.6.2 counter-examples**; MemAE (Gong et al.
2019) as a remedy not attempted, with the reason; Serrà et al. (ICLR 2020) on input
complexity confounding likelihood-based scores — the general form of the density
confound handled in §A.7.

## A.3.3 Android malware detection with graphs

MsDroid (2-hop subgraphs around *sensitive* APIs); MamaDroid (Markov chains over
abstracted call transitions into a conventional classifier); MalScan (centrality
computed directly); GDroid; ANAKIN; SeGDroid; S-FCSG. **State the pattern explicitly:
every high-performing method either pre-filters to a small subgraph or computes
structural features directly — none runs message passing over a large graph of mostly
uninformative nodes.** S-FCSG states the mechanism in this chapter's own terms:
nonsensical nodes cause informative node features to drift toward uninformative ones
during propagation.

**Address MamaDroid directly.** It is the closest published relative of this design,
it uses transitions as features rather than topology, and it works. §A.6.3's `adj_only`
supervised result at 0.9593 independently rediscovers this. Raise it before a reviewer
does.

## A.3.4 GNN expressiveness and over-smoothing

Li, Han & Wu (2018) over-smoothing; Oono & Suzuki (2020); Xu et al. (2019) on the 1-WL
bound; Corso et al. (2020) on single-aggregator sub-1-WL limits. **Note the receptive
field of a 4-layer GIN saturates in ~2 layers on a 22-node graph** — over-smoothing
that takes 5–6 layers on large sparse graphs happens immediately here.

## A.3.5 Evaluation methodology

TESSERACT (Pendlebury et al. 2019) on temporal and spatial bias; the OOD
generalisation-gap benchmark; concept-drift work (CADE, Transcending TRANSCEND,
LAMDA). **This is the literature that makes §A.6.5's ladder standard practice rather
than improvisation.**

## A.3.6 Questions closed by citation rather than experiment

- **Graph transformers:** HiGraph (499K apps, 2012–2022) found hierarchical CFG/FCG
  modelling beat both flat-graph GNNs and GraphGPS under matched dimensions, and
  localised the malware signal to CFG-level cyclomatic complexity rather than
  aggregate FCG metrics. **Independent corroboration of §A.6.4's structural null at a
  scale this thesis cannot match**, and their remedy — hierarchy — is structurally
  unavailable to dynamic traces.
- **Graph rewiring:** a 2025 survey reports curvature-based gains are highly sensitive
  to hyperparameters and often arise from favourable configurations rather than
  consistent improvement over the original topology.
- **Memory-augmented autoencoders:** reduce reconstruction ability substantially, add
  complexity, and do not address the measured collinearity mechanism.

---

# A.4 Method

*(Unchanged.)* 22-node fixed universe; node feature dim 10 with static/dynamic fusion
(0 all-zero static vectors across 2,403 apps); k=5 proximity edges; `w_cum` only;
shares-not-counts normalisation; 220 + 484 = 704 tensor; GAE with GCNConv encoder.

**The δ measurement.** δ is a filter, not a feature — the rule can only remove edges
and gap duration is never written into the graph. v2 retention 0.8266 overall,
stratified Q1 0.33 → Q4 0.88; fitted **0.968 at 5k events, 1.0 at 10k**. Negligible at
AndroCT densities. *(`0 edges only in k+δ` is definitionally guaranteed — a sanity
check, not a finding.)*

---

# A.5 Experimental protocol

Split, digest, benign-only training. Metric as `max(auc, 1−auc)` with direction —
**and an explicit note that per-fold floor-AUC averaging can hide direction flips**,
which §A.6.5 quantifies. Trivial floors table. Controls inventory. Nested bootstrap
where feature selection is part of the model.

---

# A.6 Results

## A.6.1 The representation carries the signal (RQ1)

Supervised probe table (HGB 0.9762 / 0.957 / 0.9593; LR 0.9085 / 0.931 / 0.855).
Diagnostic only. Crypto/file_io ablation against notifications and process controls —
signal is distributed, the ceiling is not ad-library composition.

## A.6.2 Benign-only reconstruction fails, with a measured mechanism (RQ2)

Six-intervention table. Geometry: malware pairwise cosine 0.462 vs benign 0.325, and
**1 PCA component to 90% variance vs 2–3**.

**[NEW] Run 8 detail:** embedding-space scoring produced the first non-inverted GAE
result (0.6834) but **an untrained encoder of identical architecture scored 0.7591**,
and embedding scores were *more* density-coupled than reconstruction error
(mean |ρ| 0.4435 vs 0.2572). Training did not merely fail to help.

Three negatives to keep: windowing (Arm B 0.601/0.621 — the "adaptive" claim tested
and failed on this corpus); whitening (0.560 — targeted the measured mechanism and
made it worse, so collinearity is a correlate not a cause); **h=2 at 0.568, a direct
counter-example to Cai et al. 2024.**

## A.6.3 Seven method families (RQ3)

Trained-vs-untrained table. **Paired deltas with Wilcoxon, not best-of** — the honest
claim is *indistinguishable*, not *untrained wins*.

**[NEW] Classical one-class baselines**, same tensors, same split:

| Method | AUC |
|---|---|
| Centroid Euclidean | 0.777 |
| Isolation Forest | 0.650 |
| kNN k=1 / k=5 / k=20 | 0.640 / 0.633 / 0.607 |
| Mahalanobis (Ledoit–Wolf) | 0.613 |
| One-class SVM (RBF) | 0.603 |

**[NEW] The sharpest single contrast in the chapter — promote it:**

> Supervised HGB reads **0.9593** from the flattened adjacency alone. Eight
> unsupervised one-class detectors across five dimensionality reductions cap at
> **0.545** on the same matrix. The structural signal exists and is
> **label-dependent** — discriminative transitions occupy a handful of the 484 cells,
> and unsupervised scoring has no mechanism to localise them.

Two collapse findings: OCGIN_orig hypersphere collapse 5/5 seeds; **OCGTL encoder
agreement collapse** (cos ≈0.9999) on T22 at K=4 and K=6 with score-floor fraction 0.0
— *not* the OCGIN signature, and **T1K did not collapse at all**, consistent with a
22-node graph saturating a 4-layer receptive field. **State the reimplementation
caveat** (AGPL reference not vendored; GTL interpreted as within-graph).

**[NEW] GLocalKD explainability null:** per-node deviation differences between classes
sit in the fourth decimal place (+0.000961, −0.000922) with alternating signs down the
ranking. The node-level deviation map the design promised is not present at measurable
magnitude under the method built to produce it.

Performance-flip diagnostic: sums 1.083 and 1.335 against a published signature of ≈1.

## A.6.4 **[NEW/EXPANDED]** Granularity and edge definition (RQ4, part 1)

The structural null must be shown to hold beyond one representation.

**API-level vocabulary.** 50,331 distinct callees; vocabulary built **from train-benign
only** (integrity constraint — ranking over both classes leaks labels). Three selection
rules (TF-IDF, document frequency, raw frequency) × four sizes (100/300/500/1000).

**The OOV confound and its resolution.** Coverage at K=1000: train benign 0.719, test
benign 0.688, **test malware 0.444**. Because the vocabulary is benign-derived, the
OOV rate is itself a floor (0.7269 under TF-IDF) and contaminates every score on that
representation. B_docfreq selected as the vocabulary whose OOV floor sits closest to
chance (0.6249).

**Structural floors do not move.** `edge_count` and `density`: 0.5116 / 0.5092 /
0.5074 / 0.5126 across K — flat, and slightly *below* the 22-node 0.5267.
`active_nodes` rises to 0.6055, but that is the same OOV effect.

**Invocation edges.** AndroCT lines are `caller -> callee`, so true call structure is
available and was tested. Two variants:
- **API-vocabulary invocation (V2) produced 0.7338 and was an artefact** — median drop
  rate 0.9487 benign / **0.9999 malware**, because 68.7% of callers are app-package
  code absent from a callee-derived vocabulary. V3 ancestor projection recovered edges
  and the floor fell to 0.5070.
- **22-category invocation, both endpoints through the mapper**, gives symmetric
  coverage (either-unmapped class gap **0.0012**) and floors of **0.5056** (no
  self-loops) / 0.5080 (with). Real call structure, balanced coverage, still chance.

**Figure F6** carries this: structural floors across 22-node, API-1000, and invocation.

## A.6.5 Topology carries signal message passing cannot extract (RQ4, part 2)

Supervised GIN ablation table (M1 0.8838 / M2 0.9000 / M3 0.5903; deltas −0.0162,
−0.0285, −0.0121; −0.0150 weighted under holdout). **Figure F5.**

WL ablation table (as-built 0.6730, structure-only 0.6268, edges-removed exactly
0.5000). The claim: not "structure carries no signal" but "structure carries signal
message passing cannot extract" — a kernel reads 0.6268 where a supervised GIN manages
0.5903.

## A.6.6 The supervision ladder (RQ5)

Three rungs with **pooled out-of-fold** as the carried figure (0.848861, not the
per-fold floor mean 0.849185), the 3/30 flip count, and the 0.0118 inflation.
**Do not report LR's behavioural number** — 9/30 folds flipped, inflation 0.195.
Random-group control 0.9864 with 0/30 flips. Volume diagnostics (between/within 1.899
structural vs 0.0257 on event count; fold AUC vs fold volume ρ = 0.058, p = 0.76).
**Figure F1.**

**Split-B is meaningless for benign-only methods** — train-benign fit identical across
all 30 folds. Report the divergence (weighted 0.8083 vs pooled OOF 0.5178) and why.

## A.6.7 The deviation vector works; the scalar was the failure (RQ6)

D0 0.638 → **D3 0.9624** vs raw-input control 0.9746. Shuffled-label 0.5035.
**[FIXED] Carry the seed-mean 0.9624 as the headline and note the seed-42 figure
(0.9614) as the ROC/operating-point source.** Do not present both as headline.

### The benign-only headline

**D1 centroid Euclidean, 0.8004, nested CI [0.757, 0.815].** What it survived: bias
−0.0028 with the point inside its interval; six volume ρ ≤ 0.33 and residualisation
changing nothing (R² 0.000029); AUC stable across volume terciles; **benign-group
holdout pooled OOF 0.7889 [0.764, 0.814], 0/5 folds flipped**.

**[NEW] Contextualise against the input centroid.** The raw-tensor centroid reaches
0.777, and per-node ablation drops it to 0.568 when `ipc_intents` is zeroed — but the
`ipc_intents` share *alone* scores only 0.575. **The contribution is relational, not
univariate**; an earlier reading of that result as "a univariate detector in disguise"
was tested and withdrawn.

**The concentration finding, stated as interpretability.** D1 drops to 0.5914 when
`ipc_intents` is zeroed; the next node contributes 0.0025. But `ipc_intents` raw share
scores 0.575 benign-higher while its **reconstruction error scores 0.793
malware-higher**. The deviation signal is worth +0.22 AUC over the raw quantity *and
corrects the direction*. This is the ABRG premise demonstrated on the node that carries
it. **Figure F4.**

**Also report:** Mahalanobis inverted on 5/5 benign-holdout folds (0.242) — covariance
on a cluster-reduced benign set is unstable; centroid is robust.

**[FIXED] S1_norm status.** Support-novelty scoring on API-level transitions reaches
0.8226 raw, but the bootstrap mean is 0.7867 (bias −0.0359, point outside its own
interval) and **shuffled support still returns 0.6594 ± 0.005 across 20 seeds**. It is
reported as a result with its control adjacent, **not as a headline**, and its
granularity dependence is a finding: support novelty is at chance on 22 nodes (0.545)
because a universal node set makes "unseen" nearly empty.

## A.6.8 Deployability (RQ7)

TPR-at-FPR table. **Figure F3** with the 1% FPR line marked. State the base-rate
inversion and give precision at a 1% wild base rate.

---

# A.7 Artefacts caught before they became results

Seven-row table. Own section, not footnotes.

---

# A.8 **[NEW]** Discussion

The chapter currently reports; it must also argue.

## A.8.1 Positioning against published work

| Reference point | AUC |
|---|---|
| Published OCGIN band across GLAD benchmarks | ≈0.50–0.62 |
| This work, OCGIN on AndroCT | 0.566 |
| This work, best benign-only (D1) | 0.8004 |
| This work, supervised ceiling | 0.9762 |

**The benign-only result sits above the published deep-GLAD band; the negative results
reproduce it.** Neither fact is visible without this comparison, and an examiner will
ask "is 0.80 good?"

## A.8.2 Why message passing hurts here

Three converging explanations: over-smoothing on a graph where a 4-layer receptive
field saturates in two hops; the 1-WL bound with an identical initial colouring across
every graph (fixed universe, categorical identity); single-aggregator sub-1-WL limits.
The WL kernel reading structure better than the supervised GIN is consistent with the
pooling/aggregation pipeline, not the topology, being lossy.

## A.8.3 Why unsupervised scoring cannot reach the structural signal

Supervised 0.9593 on adjacency vs unsupervised 0.545. Density-based scoring sums
across 484 dimensions; discriminative transitions occupy a few. Labels localise;
distance metrics dilute. This is the general form of the input-complexity confound
(Serrà et al. 2020).

## A.8.4 What the design got right and what it did not

Right: fixed universe (comparability), shares normalisation (length invariance),
static/dynamic fusion, deviation over raw magnitude (+0.22 AUC on `ipc_intents`).
Not right: the scalar readout; message passing as the extraction mechanism; the
assumption that a universal node set is compatible with support-based novelty.

## A.8.5 The honest boundary

No benign-only method beats the trivial size floors by a comfortable margin. Best is
0.8004 against a mapped-event floor of 0.7025, at 0.24% TPR at 1% FPR. **State this
plainly. It is the finding, not the absence of one.**

---

# A.9 **[NEW]** Conclusions, with RQ closure

| RQ | Answer | Evidence |
|---|---|---|
| 1 Signal present? | Yes, strongly | 0.9762 supervised; 0.9593 adjacency alone |
| 2 Benign-only reconstruction? | No — inverted, below floor | 0.638, six interventions |
| 3 Objective, architecture, or representation? | **Objective and readout** | 0.638 → 0.9624 same model; seven families indistinguishable trained vs untrained |
| 4 Topology? | Carries signal; message passing cannot extract it | WL 0.6268 vs edges-removed 0.5000; M1 − M2 negative |
| 5 Cost of the guarantee? | 0.127 unseen groups, 0.048 no labels | Ladder with random-group control |
| 6 Where is the signal? | In the vector, not the scalar; concentrated in `ipc_intents` | D0 0.638 → D3 0.9624; ablation Δ 0.2090 |
| 7 Deployable? | No | 0.24% TPR at 1% FPR |

**Open questions leading out:** generality beyond one corpus (→ B); whether
state-based stimulus changes the picture; whether per-app refinement converges (→ C);
whether the univariate concentration is corpus-specific.

---

# A.10 Threats to validity

*(As revision 1, plus:)* **[NEW]** vocabulary selection is part of the model, so
naive CIs understate uncertainty by roughly a third — nested bootstrap used throughout
for those configurations. **[NEW]** AUC verification is catalogue-reload rather than
from-scores recompute for rows where score vectors were not persisted.

---

# Reproducibility statement

103/103 verified, 6 notebooks, `verify_all.py` exit 0 in 12.1 s. `GAPS.md` records 16
directories without reproduce scripts, 21 configs missing library pins, OCGTL Split-B
aborted, GLocalKD nested bootstrap abandoned at B=20, V2 invocation marked
`complete_but_artifact`. Five superseded numbers retained and flagged.

---

# Do not drop under deadline

1. §A.3 related work — without it there is no novelty claim
2. §A.1.3 contributions — examiners look for this page first
3. §A.6.8 operating points — otherwise the chapter never says whether it works
4. §A.7 artefacts caught — the corpus-validation contribution made visible
5. The `ipc_intents` 0.575-vs-0.793 comparison — without it D1 reads as degenerate
6. Paired deltas + Wilcoxon, not best-of
7. Pooled OOF for rung 2, with the 3/30 flip count
8. The OCGTL reimplementation caveat
9. Windowing and whitening negatives
10. The zero-mapped exclusion asymmetry (6.6% vs 2.2%)
11. §A.8.1 positioning table — answers "is 0.80 good?"
12. §A.6.3 adj_only 0.9593 vs one-class 0.545
