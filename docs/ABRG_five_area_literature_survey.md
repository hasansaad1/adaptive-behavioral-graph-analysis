# ABRG — Five-area literature survey

**Compiled 12 August 2026.** Papers 2022+ unless a foundational reference is required
for context. Organised by the five requested areas.

**Provenance warning.** Entries marked ◆ were read at abstract or full-text level.
Unmarked entries were identified through reference lists, citation contexts, and
survey coverage — they are real papers and correctly attributed, but the notes are
thinner and you must verify before citing. Do not cite anything here without opening
it yourself.

---

# AREA 1 — AI models and GNNs

## 1a. The expressiveness / over-smoothing problem (most relevant to your M1 − M2 result)

**◆ 1. Neural Graph Pattern Machine** (arXiv 2501.18739, 2025)
Argues message passing has documented limits: restricted expressiveness,
over-smoothing, over-squashing, inability to model long-range dependencies. Notes
that expressive-GNN fixes tend to emphasise long-range structure at the expense of
local information, and lack interpretability about what graph knowledge is learned.
*Why it works:* learns patterns directly rather than through neighbourhood
aggregation.

**◆ 2. Xu et al., How Powerful Are GNNs?** (ICLR 2019 — foundational)
GNN expressive power is upper-bounded by the 1-Weisfeiler-Leman test. GIN is
constructed to reach that bound. **This is the ceiling your GIN hit.**

**◆ 3. Corso et al., Principal Neighbourhood Aggregation** (NeurIPS 2020)
No GNN using a *single* aggregation function reaches 1-WL expressiveness when the
neighbourhood multiset has uncountable support. *Implication for you:* your
single-aggregator readout was provably sub-1-WL.

**◆ 4. Chen et al. 2020; Garg et al. 2020; Zhang et al. 2024**
MPNNs cannot detect or count stars, conjoint cycles, or k-cliques.

**◆ 5. Li, Han & Wu 2018** (foundational) — origin of over-smoothing: repeated
propagation drives node embeddings toward convergence.

**◆ 6. Oono & Suzuki 2020** — formal treatment of asymptotic feature collapse.

**◆ 7. Deep Scattering Transforms for over-smoothing/over-squashing**
(arXiv 2407.06988, 2024)
Notes the double bind precisely: few message-passing steps limit expressivity, many
steps make connected nodes indistinguishable. Extends over-smoothing analysis to
directed graphs via a directed symmetrically normalised Laplacian.
*Relevant:* your graphs are directed.

**◆ 8. Persistent Gaussian Perturbations Prevent Oversmoothing in Recurrent GNNs**
(arXiv 2607.28185, 2026)
Injects Gaussian noise after each propagation step; proves the hidden representations
form a geometrically ergodic Markov chain with non-vanishing stationary Dirichlet
energy. *Why it works:* noise prevents contraction to a fixed point.
**Notes that Graphormer and GraphGPS do not provide theoretical guarantees against
asymptotic feature collapse** — useful counterweight to "just use a transformer."

**◆ 9. Dual Mamba for Node-Specific Representation Learning** (arXiv 2511.06756)
Selective state-space modelling against over-smoothing. Surveys the standard fixes:
decoupling propagation from transformation (Chen et al. 2020), limiting neighbourhood
range, random edge dropping, attention.

**10. GraphCON — Graph-Coupled Oscillator Networks** (Rusch et al., ICML 2022)
Second-order oscillatory dynamics that empirically stabilise deep propagation.

**11. Rusch, Bronstein & Mishra, A Survey on Oversmoothing in GNNs** (2023)
The reference survey. Cite for the phenomenon rather than a primary source.

## 1b. Graph transformers

**◆ 12. Graphormer** (Ying et al., NeurIPS 2021) — "Do Transformers Really Perform
Badly for Graph Representation?" Centrality, spatial, and edge encodings injected into
attention.

**◆ 13. GraphGPS** (Rampášek et al., NeurIPS 2022) — modular recipe combining local
message passing with global attention plus positional/structural encodings.
**This is the one HiGraph tested on Android malware graphs and found did not beat
hierarchical modelling.**

**◆ 14. Plain Transformers Can Be Powerful Graph Learners** (arXiv 2504.12588, 2025)
Lists the three MPNN limitations (over-smoothing, over-squashing/under-reaching,
1-WL bound) and the three response directions (graph transformers, higher-order GNNs,
subgraph GNNs). Notes attention is structure-invariant and senses no structural
information inherently — positional/structural encoding is doing the work.

**◆ 15. Graph External Attention Enhanced Transformer** (arXiv 2405.21061, ICML 2024)
Linear-complexity external attention. Also EGT (Hussain et al. 2022), which introduces
an edge channel into attention with SVD-based positional encoding.

**◆ 16. A Theory for Compressibility of Graph Transformers** (arXiv 2411.13028)
Important nuance: **the rank-collapse problem is not unique to message passing** —
attention mechanisms suffer similarly (Dong et al. 2021). Also notes lower-rank
embeddings are not always bad; pooling methods deliberately merge similar nodes.

## 1c. Graph foundation models and LLM+graph (context, low direct relevance)

**◆ 17. Graph Foundation Models: Concepts, Opportunities and Challenges**
(arXiv 2310.11829 → TPAMI 47(6):5023–5044, 2025)

**◆ 18. Graph Foundation Models: Challenges, Methods, and Open Questions** (KDD 2025)

**19. Mao et al., Position: Graph Foundation Models Are Already Here** (ICML 2024)

**20. Liu et al., Towards Graph Foundation Models: A Survey and Beyond** (2024)

**◆ 21. A Survey of Large Language Models for Graphs** (KDD 2024, arXiv 2405.08011)
Covers OpenGraph (LLM-generated nodes/edges with Gibbs sampling and tree-of-prompt),
LLM-GNN (LLMs as annotators producing labels with confidence scores).

**22. Jin et al., Large Language Models on Graphs: A Comprehensive Survey** (TKDE 2024)

**23. Fatemi, Halcrow & Perozzi, Talk Like a Graph** (ICLR 2024) — how to encode graphs
for LLM consumption.

**24. One for All** (Liu et al., ICLR 2024) — one graph model for all classification tasks.

**25. GraphPrompt** (WWW 2023); **All in One** (KDD 2023) — prompt-based unification of
pre-training and downstream graph tasks.

**26. A Survey on Self-Supervised Graph Foundation Models** (arXiv 2403.16137)

**27. LLM as GNN: Graph Vocabulary Learning** (arXiv 2503.03313, 2025)

**28. AnomalyGFM: Graph Foundation Model for Zero/Few-shot Anomaly Detection**
(Qiao, Niu, Chen & Pang, 2025) — **worth a look**; graph foundation models applied
directly to anomaly detection.

**29. Billion-Scale Graph Foundation Models** (arXiv 2602.04768)

**30. GNN Applications Across Domains** (arXiv 2606.27202) — broad application survey.

### Area 1 conclusions

- Your M1 − M2 = −0.0162 has three independent theoretical explanations, all
  established: over-smoothing, the 1-WL bound, and single-aggregator sub-1-WL limits.
- The graph-transformer escape hatch is weaker than it looks — attention suffers rank
  collapse too (#16), transformers lack collapse guarantees (#8), and GraphGPS
  specifically failed on Android malware graphs (HiGraph).
- Graph foundation models are the field's current direction but are irrelevant to a
  22-node fixed-universe graph.

---

# AREA 2 — Malware (general)

## 2a. LLMs for malware analysis — the 2024–2026 wave

**◆ 31. Large Byte Model (LBM)** (CrowdStrike, arXiv 2606.02834, 2026)
Byte-native LLM with a bespoke byte tokenizer and hybrid text+byte embedder, two-phase
training. Reported accuracy ranges from **69% for malware family classification to 98%
for architecture classification**.
*Why it works:* vocabulary expansion lets a language model read raw binaries natively.
*Note the spread* — the easy task is near-solved, the hard one is not.

**◆ 32. LLMs for source-code malware detection** (KIT 2025, IEEE 11205440)
GPT-2, T5, CodeBERT on decompiled .c from PE files. GPT-2 and T5 strongest.
Conclusion emphasised **model selection and dataset quality** over architecture.

**◆ 33. Multi-View Decompilation for LLM-Based Malware Classification**
(arXiv 2606.20436, 2026) — multiple decompiler views as LLM input.

**◆ 34. Leveraging LLMs to Support Malware Analysis from Structured and Semantic
Binary Data** (Springer, 2025)

**35. MalBERT** (Rahali & Akhloufi, SMC 2021) — BERT for malware detection.

**36. SeMalBERT** (J. Inf. Secur. Appl. 80:103690, 2024) — semantic-based extension.

**37. Malware detection using attributed CFG generated by pre-trained language model
with GIN** (COMPSAC 2022) — **directly relevant hybrid**: LM-generated node features
plus GIN over control-flow graphs.

**38. MalGTA: LLM-based guided malware tactical analysis** (J. Supercomputing 81(9), 2025)

**39. Assessing LLMs in malicious code deobfuscation of real-world campaigns**
(Expert Systems with Applications 256:124912, 2024)

**40. AutoMalDesc: Large-Scale Script Analysis for Cyber Threat Research**
(arXiv 2511.13333)

**41. RL4Mal: Representation learning-based malware classification under long-tailed
distribution** (2025) — **relevant if your behavioural clusters are imbalanced.**

**42. Disassembling obfuscated executables with LLM** (arXiv 2407.08924, 2024)

**43. LLM for Software Security: Code Analysis, Malware Analysis, Reverse Engineering**
(arXiv 2504.07137) — survey.

**44. LLMs for Security Operations Centers: A Comprehensive Survey**
(arXiv 2509.10858)

**45. Malware Detection with Artificial Intelligence: A Systematic Literature Review**
(ACM Computing Surveys 56(6), 2024) — the general survey to cite.

## 2b. Adversarial ML and robustness

**◆ 46. Pierazzi, Pendlebury, Cortellazzi & Cavallaro, Intriguing Properties of
Adversarial ML Attacks in the Problem Space** (IEEE S&P 2020, extended 2023)
Formalises problem-space vs feature-space attacks and shows **100% misclassification
on successfully generated apps** under problem-space constraints. Argues ℓp-norm
perturbation measures overestimate defence robustness.
**The canonical citation for why feature-space robustness ≠ real robustness.**

**◆ 47. Evaluating the Robustness of Adversarial Defenses in Malware Detection
Systems** (arXiv 2505.09342, 2025)
Context figure: Kaspersky blocked **33.8 million** mobile malware/adware/riskware
instances, with mobile attacks up ~50% year on year.

**◆ 48. On the Robustness of Malware Detectors to Adversarial Samples**
(SECAI 2024, arXiv 2408.02310) — transferability of adversarial examples across
classifiers.

**◆ 49. PAD: Towards Principled Adversarial Malware Detection Against Evasion Attacks**
(arXiv 2302.11328, TDSC)
Names the **robustness gap**: feature-space adversarial training does not propagate to
the problem space because of "side-effect" features in inverse mapping.

**50. Lucas et al., Adversarial Training for Raw-Binary Malware Classifiers**
(USENIX Security 2023)

**51. Defend Against Adversarial Attacks in Malware Detection Through Attack Space
Management** (Computers & Security 141:103841, 2024)

**52. Reducing the Surface for Adversarial Attacks in Malware Detectors** (Springer 2025)
Reports evasion rate driven to zero for most generators without accuracy loss.

**53. A LLM Approach to Generating Bypass Rules for Malware Evasion in Analysis
Sandbox** (arXiv 2605.21821) — offensive use of LLMs against sandboxes.
**Relevant to your threat model:** sandbox evasion is now LLM-assisted.

**54. Demontis et al., Why Do Adversarial Attacks Transfer?** (USENIX Security 2019)

**55. The Space of Adversarial Strategies** (arXiv 2209.04521, USENIX Security 2023)

### Area 2 conclusions

- The field's centre of gravity has moved to LLMs over decompiled code and raw bytes,
  not graphs. **Your GNN framing is now slightly against the current.**
- #37 (pre-trained LM node features + GIN over CFGs) is the closest published relative
  to a "better features into a GNN" fix. Worth one paragraph in future work.
- Nobody reports strong *unsupervised* results. The LLM work is all supervised or
  few-shot with labels.
- Adversarial-robustness work universally assumes a supervised detector — another
  place where the benign-only framing is unusual rather than wrong.

---

# AREA 3 — Malware on smartphones

## 3a. Evaluation methodology — the most useful cluster for you

**◆ 56. HiGraph** (arXiv 2509.02113, 2025)
499K Android apps, 200M+ nested CFGs, 499K FCGs, 2012–2022; cross-anchor concept-drift
protocol over 433,488 test apps across ten years.
**Two findings:** hierarchical CFG/FCG modelling beat both flat-graph GNNs and
GraphGPS under matched dimensions; and the discriminative signal localises to
**CFG-level cyclomatic complexity rather than aggregate FCG metrics**.
**Your single most important corroborating citation.**

**◆ 57. TESSERACT** (Pendlebury et al., USENIX Security 2019) and **Beyond the
TESSERACT** (arXiv 2506.23814, 2025)
Temporal and spatial bias; random splits inflate reported performance.
**The justification for your random-group control.**

**◆ 58. LAMDA: A Longitudinal Android Malware Benchmark for Concept Drift Analysis**
(arXiv 2505.18551, ICLR 2026)

**◆ 59. Quantifying the Generalization Gap: A New Benchmark for OOD Graph-Based
Android Malware Classification** (arXiv 2508.06734, 2025)
**The framing for your supervision ladder.**

**◆ 60. Empirical Evaluation of Concept Drift in ML-Based Android Malware Detection**
(arXiv 2507.22772, 2025)
Two datasets, nine ML/DL algorithms plus LLMs, across static/dynamic/hybrid/semantic/
image features. Finds drift widespread and materially damaging; **feature type and
data environment matter more than algorithm choice**; balancing helps imbalance but
not drift.
**Directly supports your "representation, not model" conclusion.**

**◆ 61. Combating Concept Drift with Explanatory Detection and Adaptation**
(ACM CCS 2025)

**◆ 62. MADCAT: Combating Malware Detection Under Concept Drift with Test-Time
Adaptation** (arXiv 2505.18734, 2025)

**63. CADE: Detecting and Explaining Concept Drift Samples for Security Applications**
(Yang et al., USENIX Security 2021)

**64. Transcending TRANSCEND: Revisiting Malware Classification in the Presence of
Concept Drift** (Barbero et al., IEEE S&P 2022)

**65. Chen, Ding & Wagner, Continuous Learning for Android Malware Detection**
(USENIX Security 2023)

**66. Kan et al., Investigating Labelless Drift Adaptation for Malware Detection**
(AISec 2021) — **closest published relative to what a benign-only adaptive reference
graph is trying to do.**

**67. MORPH: Towards Automated Concept Drift Adaptation** (NDSS 2024 poster)

**68. BenchMFC: A Benchmark Dataset for Trustworthy Malware Family Classification
Under Concept Drift** (Computers & Security 139:103706, 2024)

**69. Cluster Analysis and Concept Drift Detection in Malware** (arXiv 2502.14135, 2025)
**Methodologically close to your Ward k=30 behavioural clustering.**

**70. KronoDroid** (Guerra-Manzanares et al., Computers & Security 110:102399, 2021)
and **Concept Drift and Cross-Device Behavior** (Computers & Security 120:102757, 2022)

**71. ActDroid: An Active Learning Framework for Android Malware Detection** (2024)

**72. Online Learning-Based Android Malware Detection Using API Call Graphs** (AAAI-SS)
Comparative evaluation of drift detectors (DDM, EDDM, ADWIN, PHT, Hoeffding) against
multiple classifiers.

## 3b. Graph-based Android detection — the methods that work

**◆ 73. MsDroid** (TDSC 2022) — 2-hop subgraphs around *sensitive* APIs, each encoding
code attributes plus domain knowledge, classified by GNN.
*Why it works:* pre-filtering removes uninformative nodes before message passing.

**74. MamaDroid** (NDSS 2017) — Markov chains over package/family-abstracted call
transitions into a conventional classifier.
*Why it works:* transitions as **features**, never as topology. **Closest published
relative to your design, and it avoids the GNN entirely.**

**75. MalScan** — social-network centrality over the FCG.
*Why it works:* structure computed directly, not learned via aggregation.

**76. GDroid** — heterogeneous App-API graph with App-API and API-API edges.
*Why it works:* cross-app structure, not within-app topology.

**77. ANAKIN** — API-node FCG with per-node and per-edge explanations.

**78. SeGDroid: Sensitive Function Call Graph Learning** (Expert Systems with
Applications 235:121125, 2024) — **the sensitive-subgraph idea, published.**

**79. FCG + S-FCSG** (2023) — API-based node features, TF-IDF-inspired API coefficient
ranking, sensitive-function-called subgraph extraction. States explicitly that
**nonsensical nodes cause important node features to drift toward uninformative ones
during propagation**.
**This is the mechanism you measured, published, in your exact domain.**

**80. MaskDroid** (2024) — masked graph reconstruction; stable representations from
reconstructing the whole graph from a node subset.
**The self-supervised objective closest to yours that reportedly works.**

**81. HerTDroid: Influential node filter + heterogeneous graph transformer**
(Applied Sciences 14:3150, 2024)
**Note the two-part design: filter first, then transformer.**

**82. Hypergraph-level classification for Android malware** (2024) — argues binary
edges cannot express one function calling several to produce an effect.

**83. Graph-Augmented Multi-Modal Learning Framework for Robust Android Malware
Detection** (Scientific Reports, 2025)

**84. aCyber: Robustness of Heterogeneous Graph Based Android Malware Detection
Against Adversarial Attacks** (CIKM 2019)

## 3c. Non-graph Android detection (for the baselines chapter)

**85. DL-Droid** (Computers & Security, 2019) — real devices, state-based input
generation. **97.8% with dynamic features only; 99.6% with dynamic + static.**
*Why it works:* enhanced input generation — better stimulus, not a better model.
**Directly relevant to your Monkey limitation.**

**86. DBN-GRU hybrid** (PLoS One 20(5):e0310230, 2025) — DBN for static, GRU for
dynamic. 98.7% accuracy on Drebin (129,013 apps).
*Caveat:* Drebin is 2014 and this is a random split — read against TESSERACT.

**87. MPDroid: Multimodal pre-training with static and dynamic features**
(Computers & Security 150:104262, 2025)

**88. Towards a Robust Android Malware Detection Model Using Explainable Deep
Learning** (2025) — BiLSTM best; SHAP/LIME identify **TCP flags and initial window
parameters** as key. Network-flow features, not behavioural graphs.

**89. Advanced Android Malware Detection through Deep Learning Optimization**
(ETASR 14(3), 2024) — LSTM/NN with hyperparameter tuning.

**90. An Effective Deep Learning Scheme Leveraging Performance Metrics and
Computational Resources** (2024) — CNN, autoencoder, DBN, deep neural decision forest
on Drebin 2014 and TUANDROMD 2021.
**Note: an autoencoder used as a supervised classifier, not for anomaly detection.**

**91. Hybrid Android Malware Detection and Classification Using DNNs**
(Int. J. Computational Intelligence Systems, 2025)

**92. LinRegDroid** (IEEE Access 10:14246, 2022); **SEDMDroid** (IEEE TNSE 8:984, 2020);
**DroidFusion** (IEEE T-Cybernetics 49(2), 2019)

## 3d. LLMs for Android specifically

**93. LAMD: Context-Driven Android Malware Detection and Classification with LLMs**
(Qian, Zheng, He, Yang & Cavallaro, arXiv 2502.13055, 2025)
**From Cavallaro's group — the same lab as TESSERACT. Worth reading.**

**94. Exploring LLMs for Semantic Analysis and Categorization of Android Malware**
(ACSAC Workshops 2024, arXiv 2501.04848)

**95. Evaluating Lightweight Transformers with Local Explainability for Android
Malware Detection** (IEEE Access 2025)

## 3e. Adversarial robustness, Android-specific

**◆ 96. DeepTrust** (arXiv 2510.12310, 2025)
**Won the Robust Android Malware Detection competition at IEEE SaTML 2025**,
outperforming the runner-up by up to 266% under feature-space evasion while keeping
the highest clean detection rate and FPR below 1%.
*Why it works:* maximises divergence between the representations of internal models,
so the decision space becomes unpredictable to an attacker.
**Note the design principle — ensemble diversity, not a better single model.**

**97. ELSA-RAMD** — the Robust Android Malware Detection Benchmark. Enforces
FPR ≤ 1% and uses functionality-preserving attacks. Covers feature-space,
problem-space, and temporal drift.
**A standardised benchmark you could position against in future work.**

**98. Improving Adversarial Robustness in Android Malware Detection by Reducing the
Impact of Spurious Correlations** (arXiv 2408.16025, 2024)
**Directly relevant to your `ipc_intents` and OOV-rate confound work.**

### Area 3 conclusions

- **Every high-performing graph method pre-filters** (MsDroid, SeGDroid, S-FCSG,
  HerTDroid) **or avoids message passing** (MamaDroid, MalScan). Your 22-node
  all-nodes design is the configuration none of them uses.
- DL-Droid's result — 97.8% dynamic-only with *state-based* input generation — points
  at stimulus quality, not model capacity. Your Monkey traces are the weaker input.
- MamaDroid is the uncomfortable comparison: abstracted transitions in a conventional
  classifier, and it works. Your Run 3.5 `adj_only` HGB at 0.959 is essentially the
  same finding rediscovered.
- The concept-drift cluster (#57–72) is where your ladder belongs methodologically.

---

# AREA 4 — Graphs, graph designs, transformations

## 4a. Rewiring

**◆ 99. Graph Rewiring in GNNs to Mitigate Over-Squashing and Over-Smoothing: A Survey**
(arXiv 2411.17429 and 2605.00951)
Taxonomy by structural modification (edge editing, global adjacency reconstruction,
auxiliary-node augmentation) and by rewiring signal (structure, features, learned;
local or global).
**Critical caveat:** curvature-based benefits are highly sensitive to training *and*
rewiring hyperparameters, and reported SOTA gains often come from favourable
hyperparameter configurations rather than consistent improvement over the original
topology (Tori et al. 2025).
**Cite this to justify not running rewiring.**

**100. Alon & Yahav, On the Bottleneck of GNNs** (ICLR 2021) — over-squashing origin.

**101. SDRF — Stochastic Discrete Ricci Flow** (Topping et al., ICLR 2022) —
curvature-based rewiring.

**102. DIGL** (Gasteiger et al., NeurIPS 2019) — diffusion-based preprocessing.

**103. DIFFWIRE** (Arnaiz-Rodríguez et al., LoG 2022) — diffusion and curvature combined.

**104. GTR** (Black et al., ICML 2023) — effective-resistance rewiring via commute time.

**105. FoSR** — first-order spectral rewiring for over-squashing.

**106. Spectral Graph Pruning** (Jamadandi, Rubio-Madrigal & Burkholz, NeurIPS 2024)
**Removing edges as the intervention — closest to your edge ablations.**

**◆ 107. GRASS / Greener GRASS** (ICLR 2025; arXiv 2407.05649)
Relative random walk probabilities encoding, random regular graph superposition,
graph-tailored additive attention. **20.3% MAE reduction on ZINC.**

**◆ 108. Joint Graph Rewiring and Feature Denoising via Spectral Resonance**
(arXiv 2408.07191) — rewiring as *denoising* rather than geometric optimisation.
Notes Dong & Kluger (2023) proposed a graph-noise metric correlating with GCN
performance. **Potentially useful for characterising your graphs.**

**◆ 109. Graph Cascades: Contagion-Based Mesoscopic Rewiring** (arXiv 2606.05046)
Label-free; connects node pairs reinforced by multi-path short walks, prunes weak
edges.

**◆ 110. Rewiring with Positional Encodings** (OpenReview dn3ZkqG2YV, TMLR 2023)
Extends receptive fields to r-hop neighbourhoods via positional encodings plus a
virtual fully-connected node.

**111. DropEdge** (Rong et al., ICLR 2020) — random edge dropping against
over-smoothing.

**112. HDHGR** (Guo et al. 2023); **DHGR** (Bi et al. 2024) — label-guided homophilic
rewiring.

## 4b. Expressiveness — beyond 1-WL

**◆ 113. Rethinking the Expressive Power of GNNs via Graph Biconnectivity**
(ICLR 2023, arXiv 2301.09505) — categorises the escape routes from 1-WL.

**◆ 114. A Complete Expressiveness Hierarchy for Subgraph GNNs via Subgraph WL Tests**
(arXiv 2302.07090, ICML 2023) — all node-based subgraph GNNs fall into six equivalence
classes.

**◆ 115. Beyond Weisfeiler-Lehman: A Quantitative Framework for GNN Expressiveness**
(arXiv 2401.08514, ICLR 2024) — homomorphism-based expressivity, isomorphism-complete,
allows direct model comparison. Notes higher-order GNNs are generally impractical at
scale.

**◆ 116. From Relational Pooling to Subgraph GNNs** (arXiv 2305.04963, ICML 2023) —
k,l-WL framework unifying subgraph GNNs.

**◆ 117. The Expressive Power of Pooling in GNNs** (AAAI 2023)
**Directly relevant: your add/mean/max pooling choice has expressivity consequences.**

**118. GSN — Graph Substructure Networks** (Bouritsas et al., TPAMI 2022) —
substructure isomorphism counts injected as node/edge features.
**Closely related to graph-kernel subgraph-pattern methods (Shervashidze et al. 2011),
which is the family that worked best on your data.**

**119. Nested GNNs** (Zhang & Li, NeurIPS 2021); **ESAN** (Bevilacqua et al., ICLR 2022);
**I²-GNN** (Huang et al. 2023).

**120. k-GNN / k-IGN / k-FGNN** (Morris et al. 2019; Maron et al. 2019) — the k-WL
hierarchy. O(N^k) cost.

**121. Permutation-Invariant Graph Partitioning** (arXiv 2312.08671) — how GNNs capture
structural interactions.

**122. Towards Bridging Generalization and Expressivity of GNNs** (arXiv 2410.10051)
**Important nuance: more expressive ≠ better generalisation.**

**123. FloydNet** (arXiv 2601.19094) — learned DP-style global refinement matching
k-FWL.

## 4c. Graph kernels (the family that performed best for you)

**124. Shervashidze et al., Weisfeiler-Lehman Graph Kernels** (JMLR 2011)

**125. Vishwanathan et al., Graph Kernels** (JMLR) — the survey.

**126. FGSD** (Verma & Zhang, NeurIPS 2017) — family of spectral distances.

**127. Graph2Vec** (2017); **NetLSD** (KDD 2018); **GL2Vec** (2019)

### Area 4 conclusions

- Rewiring is well-developed but the survey's own honesty about hyperparameter
  sensitivity makes it a poor use of your remaining time.
- **#117 (pooling expressiveness) and #106 (spectral pruning) are the two most
  directly relevant to what you measured** and neither requires new experiments to
  cite.
- **#122 is the sharpest point for your discussion:** expressiveness and
  generalisation are different axes. Your GIN was maximally expressive at 1-WL and
  still lost to an edgeless MLP.
- Substructure-counting methods (#118) are the bridge between graph kernels — which
  worked best for you — and GNNs.

---

# AREA 5 — Deviation signals

## 5a. Why reconstruction error fails (your core mechanism)

**◆ 128. Bouman & Heskes, Autoencoders for Anomaly Detection Are Unreliable**
(arXiv 2501.13864 / OpenReview X8XQOLjLX6, 2025)
**Your single most important citation.** Systematic treatment of unwanted anomaly
reconstruction. Surveys the competing explanations:
- **Identical shortcut** — AE learns an identity map reconstructing normal and
  anomalous alike (You et al. 2022; Lu et al. 2023; Bercea et al. 2023)
- **Countered by Cai et al. 2024** — constraining latent dimension sufficiently low
  avoids it. **Your h=2 run (0.568, worst) is a direct counter-example.**
- **Havtorn et al. 2021** — high correlation between low-level features of in- and
  out-of-distribution data
- **Zhou 2022** — OOD data produces smaller neural activations *(untested by you;
  cheap to check)*

**◆ 129. Reconstruction Error-Based Anomaly Detection with Few Outlying Examples**
(arXiv 2305.10464, Neurocomputing 2026)
Trains the AE to actively enlarge the gap between anomalous and normal reconstruction
error. Notes anomalies in the training set worsen the problem substantially.

**130. MemAE** (Gong et al., ICCV 2019) — memory module limiting out-of-bounds
reconstruction. Critique: substantially reduced reconstruction ability, considerable
added complexity.

**131. DAGMM** (Zong et al., ICLR 2018) — notes some anomalies have high reconstruction
loss while others occupy normal latent regions.

**132. A Hierarchically Feature Reconstructed Autoencoder** (arXiv 2405.09148, 2024)
Aggregates **hierarchical feature reconstruction errors into an anomaly map**.
Argues comparing encoder/decoder features across layers beats single-feature or
pixelwise comparison.
**This is your D3 per-node deviation profile idea, in the vision domain.**

**133. ReContrast** (Guo et al., NeurIPS 2023) — global cosine objectives with
stop-gradient to prevent representation collapse.

## 5b. Graph-level anomaly detection

**◆ 134. UB-GOLD: Unifying Unsupervised Graph-Level Anomaly Detection and OOD
Detection: A Benchmark** (arXiv 2406.15523, ICLR 2025)
**35 datasets, four scenarios, 18 GLAD/GLOD methods.**
**The benchmark to position against.** Explicitly excludes methods requiring anomaly
labels for fair comparison.

**135. GLocalKD** (Ma, Pang, Chen & van den Hengel, WSDM 2022) — random-teacher
distillation at graph and node level. *You ran it.*

**136. OCGIN / OCGTL** (Zhao & Akoglu 2021; Qiu et al., IJCAI 2022) — *OCGIN run,
OCGTL not.*

**137. GOOD-D** (Liu, Ding, Liu & Pan, WSDM 2023) — contrastive unsupervised graph OOD.

**138. GraphDE** — generative graph OOD.

**139. AAGOD** (2023) and **GOODAT** (AAAI 2024) — post-hoc, operate on a trained GNN;
GOODAT is test-time.

**140. SIGNET: Towards Self-Interpretable Graph-Level Anomaly Detection**
(Liu et al., NeurIPS 2024)
**Directly relevant to your explainability claim.**

**141. FANFOLD: Graph Normalizing Flows-Driven Asymmetric Network for Unsupervised
GLAD** (arXiv 2407.00383, 2024)

**142. GLADC: Deep Graph-Level Anomaly Detection with Contrastive Learning**
(Scientific Reports 12:19867, 2022)

**143. CVTGAD** — simplified transformer with cross-view attention for unsupervised GLAD.

**144. TUAF: Triple-Unit-Based GLAD with Adaptive Fusion Readout** (DASFAA 2023)

**145. GLADMamba** (2025) — selective state space model for unsupervised GLAD.

**146. DiffGAD: A Diffusion-Based Unsupervised Graph Anomaly Detector** (ICLR 2025)

**147. UniGAD: Unifying Multi-Level Graph Anomaly Detection** (NeurIPS 2024)

**148. DeNoise: Learning Robust Graph Representations for Unsupervised GLAD**
(arXiv 2511.04086, 2025)

**149. Cross-Domain Graph Level Anomaly Detection** (TKDE 2024)

**150. Learning from Graph-Graph Relationship: A New Perspective on GLAD** (TKDE 2025)

**151. Deep Graph Anomaly Detection: A Survey and New Perspectives**
(arXiv 2409.09957, TKDE 2025) — repo: `mala-lab/Awesome-Deep-Graph-Anomaly-Detection`

**152. Ma et al., A Comprehensive Survey on Graph Anomaly Detection with Deep Learning**
(TKDE 2021)

**153. GADBench** (NeurIPS 2023) — supervised graph anomaly detection benchmark.

**154. Deep Into Hypersphere: Robust and Unsupervised Anomaly Discovery in Dynamic
Networks** (IJCAI 2018) — **hypersphere collapse context for your OCGIN failure.**

**155. Imbalanced Graph-Level Anomaly Detection via Counterfactual Augmentation**
(arXiv 2407.11082)

## 5c. OOD detection (transferable scoring ideas)

**156. Yang, Zhou, Li & Liu, Generalized Out-of-Distribution Detection: A Survey**
(arXiv 2110.11334) — the unifying survey.

**157. Ren et al., A Simple Fix to Mahalanobis Distance for Improving Near-OOD
Detection** (2021) — **you ran plain Mahalanobis; the fix is cheap.**

**158. Sun, Ming, Zhu & Li, Out-of-Distribution Detection with Deep Nearest Neighbors**
(ICML 2022) — **you ran kNN; this is the principled version.**

**159. Xiao, Yan & Amit, Likelihood Regret** (NeurIPS 2020) — VAE OOD score.

**160. Serrà et al., Input Complexity and OOD Detection with Likelihood-Based
Generative Models** (ICLR 2020)
**Highly relevant: likelihood is confounded by input complexity — the same shape as
your density/volume confound.**

**161. Denoising Diffusion Models for OOD Detection** (Graham et al., CVPR 2023)

**162. Diffusion-Based Layer-Wise Semantic Reconstruction for Unsupervised OOD
Detection** (arXiv 2411.10701, NeurIPS 2024)

**163. Heng, Thiery & Soh, OOD Detection with a Single Unconditional Diffusion Model**
(NeurIPS 2024)

**164. Denouden et al., Improving Reconstruction Autoencoder OOD Detection with
Mahalanobis Distance** (2018)
**Exactly the hybrid your D3 result suggests: reconstruction plus a distance metric.**

**165. Anomaly Detection for Tabular Data with Internal Contrastive Learning**
(ICLR 2022)

**166. Fascinating Supervisory Signals and Where to Find Them: Deep Anomaly Detection
with Scale Learning** (ICML 2023)

**167. Unmasking the Chameleons: A Benchmark for OOD Detection in Medical Tabular Data**
(2024) — methodologically clean, includes a membership-model check for whether OOD is
even detectable. **That check is a good idea for your setting.**

**168. Salehi et al., A Unified Survey on Anomaly, Novelty, Open-Set, and OOD
Detection** (2021)

**169. Awesome-Out-Of-Distribution-Detection** (ACM CSUR 2025 task-oriented survey +
maintained repo)

### Area 5 conclusions

- **#128 is your anchor citation** and it contains the Cai et al. reference your
  counter-example targets.
- **#132 (hierarchical feature reconstruction into an anomaly map) and #164
  (reconstruction + Mahalanobis) are the two closest published relatives of your D3
  finding.** Both support the claim that the *vector* is the signal and the scalar
  is the failure.
- **#160 (input complexity confounds likelihood) is the general form of the confound
  you spent two days chasing.** Cite it — it makes your OOV and density work look
  principled rather than ad hoc.
- **#134 (UB-GOLD)** is where a future version of this work would be evaluated.
- **#140 (SIGNET)** is the published version of your explainability ambition.

---

# CROSS-CUTTING CONCLUSIONS

**1. Your negative result sits inside the published distribution.**
OCGIN's reported band across benchmarks is 50–62 AUC. Autoencoder AD has a dedicated
2025 paper arguing it is unreliable. Performance flip is named and characterised.

**2. Three of your findings have direct published analogues you can cite as support
rather than presenting unsupported:**
- S-FCSG (#79) — nonsensical nodes drag informative features toward uninformative ones
- HiGraph (#56) — aggregate FCG metrics do not carry the signal
- Input complexity / likelihood confound (#160) — the general form of your density
  confound

**3. One finding is genuinely unreported and contradicts a published remedy:**
Cai et al. 2024's low-dimensional-latent fix, contradicted by your h=2 result.

**4. Two questions are closed by citation, not experiment:**
Graph transformers (HiGraph tested GraphGPS and it lost; also #16 and #8 on attention
rank collapse) and graph rewiring (#99's hyperparameter-sensitivity warning).

**5. The methodological cluster is where your ladder belongs.**
TESSERACT, LAMDA, the generalisation-gap benchmark, and the drift literature give you
the framing that makes rung 1 vs rung 2 vs rung 3 read as standard practice.

**6. The uncomfortable comparison is MamaDroid.**
Abstracted transitions in a conventional classifier, and it works. Your `adj_only`
HGB at 0.959 rediscovers this. Address it directly in related work rather than
letting a reviewer raise it.

**7. What the field is actually doing in 2025–2026:**
LLMs over decompiled code and raw bytes, drift-aware longitudinal evaluation, and
adversarial robustness benchmarks. Graph-based detection is mature but no longer the
frontier. This affects how you position future work, not the validity of the thesis.
