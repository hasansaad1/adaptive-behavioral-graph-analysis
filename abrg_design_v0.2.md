# ABRG v0.2 — Adaptive Behavioral Reference Graph
## Design Document

**Status:** Provisional design. **v0.2 corrects two things from v0.1:**
1. **Processing model** — the "learn-until-stable, then detect" two-phase gate (old §3.4 `IsStable`)
   is replaced by **windowed cumulative processing** with an explicit train/score mode. `IsStable`
   is demoted from a gate to a diagnostic. (See §3.4, §3.6.)
2. **What the autoencoder consumes** — made explicit: the **cumulative graph** (your decision:
   cumulative over incremental). The recency channel runs **alongside** to catch recent-small
   anomalies the cumulative view dilutes.

> **OPEN / DEFERRED — cumulative-growth handling (D7).** A cumulative graph only grows, so raw
> weights drift upward over a long run. *How* to handle this — **normalization**, periodic
> **snapshot/reset**, bounded history, or something else — is **NOT decided in v0.2**. It is the
> same parked discussion as the "reset to a previous snapshot" idea. The spec specifies the input is
> the **cumulative graph**; it does **not** commit to a growth-handling mechanism. Normalization
> appears below only as the leading *candidate*, never as a settled choice.

> **NORMALIZATION REVISION (v0.2.1) — [SETTLED].** Count-based features leak session length: raw
> event counts and cumulative edge weights grow with how long/busy a session ran, not with what the
> app characteristically does. Two runs of the same app that differ only in length would otherwise
> produce differently-scaled graphs. **The fix — scale-invariant features fed to the autoencoder:**
> 1. **Edges → transition probability.** The **raw `w_cum` is still stored** (never decays — the
>    memory channel, needed for the kill-switch experiment E2/M3, temporal attribution, and analysis).
>    The **autoencoder consumes a normalized transition probability** derived from it: out of source
>    node *u*, the weight to *v* as a fraction of all outgoing weight from *u* (a transition
>    probability). This is local (self-contained per source node), so unrelated activity elsewhere in
>    the graph does not move it — deviation stays local to where it happens.
> 2. **Node `act_v` → fraction of total events** on that node, not a raw (log-scaled) count.
> 3. **Terminal nodes** (no outgoing edges): normalized outgoing weight is **0** (defined rule, no
>    division-by-zero / NaN).
> 4. **`w_rec`** — left as-is for now (it decays, so it is semi-bounded), **but range-check it across
>    the reference graphs before final training**; it can still stack large (observed `rec` ≈ 118 on a
>    busy node) and may need the same treatment.
> 5. **`sess_v`, static slots** — already bounded (∈ [0,1] or fixed scale); unchanged.
>
> **Stored vs. fed — the load-bearing distinction:** the graph **STORES raw** `w_cum` (and raw
> counts); the **TENSOR fed to the GAE carries the NORMALIZED** transition-probability / fraction
> features. Raw persists as data and semantics; normalized is the model input. This keeps the
> dual-weight memory contribution fully intact for M3 while giving the GAE a scale-invariant,
> naturally-bounded object to reconstruct. Note this is **feature normalization** (scale-invariance
> of what the app does), *not* the deferred D7 structural growth-handling above — the cumulative
> graph is still the input; only the feature representation fed to the model is normalized.

**Pilot scope (what is actually being built now):** **directed edges + dual weights (`w_cum`,
`w_rec`) + autoencoder on the cumulative graph.** **Motifs are DEFERRED FOR PILOT** (§2.5) — not
mined, not stored, not in the graph; two unbuilt algorithms (mining + integration) to design
together later. Directed edges already carry pairwise flow. Static-layer attributes depend on
Androguard being joined to the (currently dynamic-only) corpus.

**Purpose:** Lock enough decisions to start producing numbers. Every decision is tagged:

- **[SETTLED]** — follows from closed requirements (F1–F5, F13, two-layer F3/F8 resolution)
- **[PROVISIONAL]** — a call made on an open question; contestable; includes the evidence that would overturn it
- **[DEFERRED]** — explicitly not decided yet

---

## 1. Architecture — [SETTLED]

Two layers over **one shared node universe**:

| Layer | Source | Content | Update policy |
|---|---|---|---|
| Static layer | Androguard on APK | Node attributes: declared capabilities, permission gating, component reachability | **Reseeded** on every app version |
| Dynamic layer | Frida + strace traces | Edges (transitions), edge weights, motif set | **Persists** across app versions |

**The interface between layers is the shared node set.** Every dynamic event maps to a node in the fixed universe. If a dynamic event maps to a node whose static attributes say *not declared / not reachable*, that mismatch is itself a first-class signal (capability boundary violation → F14).

The exploitable post-update window (F8) is acknowledged: after a static reseed, the dynamic reference is calibrated to the old boundary. Mitigation hooks exist in the schema (version epoch tags, §2.3) but the probation scoring policy is **[DEFERRED]**.

---

## 2. Graph schema

### 2.1 Nodes — [PROVISIONAL]

**Fixed universe of behavioral category nodes, identical for every app.** N ≈ 25–40.

Categories follow the Frida hook taxonomy: `network`, `crypto`, `sms_telephony`, `location`, `contacts`, `file_io`, `camera`, `audio`, `accounts`, `dyncode` (dynamic code loading), `ipc_intents`, `process`, `ui`, `storage_content`, `device_id`, `sensors`, `clipboard`, `notifications`, ...

Every node exists for every app from t=0 (cold start by construction, F5). What differs per app: attributes and edges.

**Node attribute vector** `x_v` (concatenation):

```
x_v = [ s_v,            # sensitivity score ∈ [0,1], from Android protection levels   (static)
        declared_v,     # capability declared in manifest/DEX {0,1}                   (static)
        gate_v,         # one-hot/multi-hot of gating permissions' protection levels  (static)
        reach_v,        # count of components from which category is reachable        (static)
        epoch_v,        # app version epoch of last static reseed                     (static)
        act_v,          # activity on this node — see normalization note below        (dynamic)
        sess_v,         # fraction of sessions in which category was active           (dynamic)
        rec_v ]         # recency-channel summary: Σ w_rec over incident edges        (dynamic)
```

> **Normalization (v0.2.1):** `act_v` **stored** raw (count) but **fed to the GAE as a fraction of
> total events** on that node (scale-invariant). `sess_v` already ∈ [0,1]. `rec_v` fed as-is for now
> (range-check before final training). Static slots already bounded. See the NORMALIZATION REVISION
> banner at the top for the full rule and the stored-vs-fed distinction.

**Rejected alternatives:** API-method-level nodes (sparsity kills DOMINANT reconstruction early); heterogeneous node types (requires per-type decoders, delays first numbers). Components and permissions are **attributes, not nodes**.

**Overturned by:** poor benign/anomalous separation traceable to category coarseness → fallback is a two-tier schema (promote ~10 high-sensitivity API methods to nodes), then heterogeneous as last resort.

### 2.2 Edges — [PROVISIONAL]

**Directed category→category transition edges.**

Edge u→v forms/updates when an event in category v follows an event in category u within **both**:
- `k = 5` events (sequence proximity), and
- `δ = 5` seconds (wall-clock proximity).

The conjunction handles bursts (k constrains when events flood) and idle gaps (δ constrains across pauses). Both tunable; sensitivity analysis is experiment E3.

### 2.3 Edge record — [PROVISIONAL]

```
E[u][v] = {
  w_cum   : float,   # cumulative observation count — NEVER decays (retention channel) — STORED RAW
  w_rec   : float,   # exponentially decayed activity weight (recency channel)
  t_first : ts,      # first observation — temporal attribution anchor (F12 graph-level)
  t_last  : ts,      # most recent observation
  n_sess  : int,     # number of distinct sessions edge was observed in
  epoch   : int,     # app version epoch at t_first
}
```

> **Normalization (v0.2.1) — [SETTLED]:** `w_cum` is **stored raw** here (it is the memory channel:
> never decays; needed for E2/M3 kill-switch, `t_first` attribution, and analysis). The **autoencoder
> does not consume raw `w_cum`** — it consumes a **normalized transition probability**: out of source
> node *u*, edge *u→v*'s weight as a fraction of the total outgoing weight from *u*. Terminal nodes
> (no outgoing edges) → 0. This makes the model input scale-invariant to session length and
> naturally bounded, while raw `w_cum` remains available in the graph. See the top-of-doc
> NORMALIZATION REVISION banner.

### 2.4 Dual-weight temporal model — [PROVISIONAL — key design move]

This replaces pure decay (the C14 recommendation) because F7 invalidated it: multi-stage malware
means old patterns must not fade; yet "established" vs "newly appearing" must stay distinguishable.

| State | w_cum | w_rec | Interpretation |
|---|---|---|---|
| Established + active | high | high | Core behavior |
| Established + dormant | high | ~0 | Old pattern, currently quiet — **retained** |
| **Newly appearing** | **low** | **high** | **Anomaly-relevant state** |
| Absent | 0 | 0 | Never observed |

Phase-one of a multi-stage attack stays fully present in `w_cum` (+ `t_first`) when phase two
activates weeks later. λ (decay rate of `w_rec`) is no longer a single point of failure: a bad λ
blurs the recency channel but cannot erase history.

**Overturned by:** experiment E2 — if (w_cum, w_rec) scatter across real traces does not separate
into these regions, the temporal model is rethought before anything is built on top.

### 2.5 Motif layer — [DEFERRED FOR PILOT]

> **PILOT SCOPE: motifs are OUT.** Not mined, not stored, not in the graph. The pilot runs on
> **directed edges + dual weights + autoencoder** only. Directed edges already carry pairwise flow
> (`A→B` ≠ `B→A`) — the cheap majority of what motifs would add. Motifs are deferred because they
> are **two unbuilt algorithms**, to be designed together later, not bolted on:
> 1. **Mining** — how to efficiently find recurring ordered edge-sequences in an event stream.
> 2. **Integration** — how a found motif feeds the graph / autoencoder (Options A/B/C below).
> The design thinking below is preserved for that future work; none of it is implemented in the pilot.

**(Future) Temporal motifs stored as a parallel reference set `M_ref`** — *alongside* the node/edge
graph, not inside the edge structure.

- Motif = ordered sequence of directed edges, length L ∈ {2, 3}, all events within `δ_motif = 10 s`.
- `M_ref` is a dictionary: signature → `{count, n_sess, t_first}`. Mined from benign windows.
- Detection-time: an observed motif either ∈ M_ref (update stats) or ∉ M_ref (**novel-motif flag**).

This is the **F14 flow mechanism**: `contacts → network_open → network_send` is judged as a flow,
not as three individually-permitted actions.

#### How motifs reach the autoencoder — three options

By default motifs are a **separate signal** and do **not** enter the autoencoder. If/when motif
information should inform the learned representation, these are the integration paths:

| Option | What it does | Cost | Status |
|---|---|---|---|
| **A — separate flag** | Autoencoder reconstructs node/edge graph only. Motifs checked by lookup → novel-motif flag is a 3rd detection signal *beside* reconstruction error. | None — simplest. GNN and motifs disconnected. | **first option when motifs return** |
| **B — motifs as features** | No structural change. Encode motif participation into existing vectors: per-node "count/strength of reference motifs this node participates in"; per-edge "is this edge part of a known motif, motif frequency". Autoencoder now *sees* motifs through the feature matrix and can raise error when motif participation is off. | Feature-engineering only; graph stays a standard attributed graph. | **documented integration path** |
| **C — motifs as graph elements** | Promote each frequent motif to its own node (edges to constituent categories) or a hyperedge. Motif becomes structure the autoencoder reconstructs. Most expressive. | Breaks fixed-node-universe; hyperedges need a non-standard GNN. | **[DEFERRED] v0.3+** |

**Decision:** Option A for the pilot (motif = separate flag). **Option B is the committed path** to
feed motifs *into* the autoencoder when needed — it does so via the feature matrix, so it is a
feature change, not an architecture change. Option C only if A/B prove insufficient.

**Known limitation (documented, not solved):** motifs bounded by δ_motif structurally cannot
capture flows split across weeks. Long-range linkage = `w_cum`/`t_first` retention (graph) +
recency channel + detection layer. The graph **retains**; recency + detection layer **connect**.

### 2.6 Sensitivity & amplification — [PROVISIONAL]

- `s_v` derived from Android permission protection levels (normal → 0.2, dangerous → 0.7,
  signature/privileged → 0.9; category-critical overrides e.g. `dyncode` → 0.9).
  Source is the platform security model — not hand-written malware rules; survives the
  "where do amplification weights come from" challenge.
- Applied **at scoring time, not stored in the graph**: anomaly contribution of edge u→v is
  multiplied by `(1 + α·s_u)` — source-weighted (information flows originate at sources).
- **Relative to reference:** a backup app's `file_io → network` pattern is normalized by its own
  reference; only deviation from the expected conditional pattern is amplified.
- α ablatable; α = 0 recovers unamplified scoring.

---

## 3. Pseudo-algorithms

### 3.1 BUILD — cold start from static analysis (F1, F5)

```
ALGORITHM BuildInitialGraph(apk)
INPUT : apk file
OUTPUT: graph G = (V, E), all-static, zero dynamic observations   # M_ref deferred, §2.5

  static_report ← Androguard(apk)            # permissions, API refs, components, intents

  V ← fixed category universe                # identical for every app
  for each v in V:
      s_v       ← sensitivity(protection_level(v), category_override(v))
      declared_v← 1 if static_report shows any API of category v referenced, else 0
      gate_v    ← protection levels of permissions gating v
      reach_v   ← #components from which v-APIs are reachable (call-graph walk)
      epoch_v   ← 0
      act_v, sess_v, rec_v ← 0, 0, 0

  E ← ∅                                      # no behavioral edges yet
  # M_ref ← ∅                                # [DEFERRED FOR PILOT — motifs out, see §2.5]
  G.version_epoch ← 0
  return G
```

The graph is *meaningful but edge-empty* at this point: DOMINANT can reconstruct node attributes
(attribute channel) before any structure exists; the structural channel phases in as edges arrive.

### 3.2 UPDATE — one window of behavior (F2, F7)

**Processing unit is a WINDOW** (a bundle of events over a time period), not a whole session and not
a single event. A session is processed as a *sequence of windows*; each window calls UpdateGraph
once, then emits the current graph state (§3.6). `t_now` is the window boundary time.

```
ALGORITHM UpdateGraph(G, window_trace, t_now)
INPUT : G, time-ordered events [(api, args, ts)...] in this window, window boundary t_now
OUTPUT: updated G   (cumulative — w_cum only grows; w_rec decays)

  # -- 0. decay pass: recency channel only -------------------------------
  for each edge e in G.E:
      e.w_rec ← e.w_rec · exp(−λ · (t_now − e.t_last))     # w_cum NEVER decays (retention)

  # -- 1. map raw events to category stream ------------------------------
  S ← [(cat(api), ts) for (api, args, ts) in window_trace]

  # -- 2. edge formation: sliding (k, δ) window --------------------------
  #   NOTE: (k, δ) is the EDGE-formation window ("what counts as a transition").
  #   This is a DIFFERENT, smaller time scale than the PROCESSING window above.
  #   Keep the two separate; conflating them is a known footgun.
  for i in 1..len(S):
      (u, t_u) ← S[i]
      G.V[u].act ← G.V[u].act + 1
      for j in i+1 .. min(i+k, len(S)):
          (v, t_v) ← S[j]
          if t_v − t_u > δ: break
          if u ≠ v:
              if (u→v) ∉ G.E:
                  G.E[u→v] ← new edge { w_cum:0, w_rec:0, t_first:t_v,
                                         n_sess:0, epoch:G.version_epoch }
              e ← G.E[u→v]
              e.w_cum  ← e.w_cum + 1        # cumulative — grows forever (memory)
              e.w_rec  ← e.w_rec + 1        # recency — bounded by decay
              e.t_last ← t_v

  # -- 3. per-window bookkeeping -----------------------------------------
  for each edge touched this window:  e.n_sess ← e.n_sess + 1   # (n_sess = #windows here)
  for each node active this window:   v.sess  ← recompute fraction

  # -- 4. motif mining ----------------------------------------------------
  #   [DEFERRED FOR PILOT — NOT IMPLEMENTED] see §2.5. Pilot does edges only.
  #   (future) for each ordered window w ⊆ S with |w| ∈ {2,3} and span(w) ≤ δ_motif:
  #               m ← edge-sequence signature of w
  #               update G.M_ref[m]  {count, n_sess, t_first}

  # -- 5. node recency summaries -----------------------------------------
  for each v: v.rec ← Σ_{e incident to v} e.w_rec
  return G
```

### 3.3 RESEED — app version update (F8)

```
ALGORITHM ReseedStatic(G, new_apk)
  static_report ← Androguard(new_apk)
  G.version_epoch ← G.version_epoch + 1
  for each v in G.V:
      recompute s_v, declared_v, gate_v, reach_v from static_report
      v.epoch ← G.version_epoch
  # dynamic layer (E, M_ref) PERSISTS untouched
  # edges keep their original epoch tag → post-update probation hook [DEFERRED]
  return G
```

### 3.4 STABILITY — F6 — [v0.2: DIAGNOSTIC, NOT A GATE]

**Changed in v0.2.** v0.1 used `IsStable` as a *gate*: reference-building while unstable, detection
only after stable. That was wrong — it means detection is OFF during the learning period, so malware
appearing before convergence is missed. **v0.2 removes the gate.** Detection vs. learning is a *mode*
(§3.6), not a phase the graph forces.

`IsStable` survives only as a **diagnostic**: it answers "has benign accumulation been well-sampled
for this app?" — useful for knowing whether the training reference is representative, NOT for
switching detection on/off.

```
DIAGNOSTIC IsStable(G, history, W=last 5 windows)
  r_edge  ← (#new edges  discovered in W) / (#windows in W)
  r_motif ← (#new motifs discovered in W) / (#windows in W)   # [pilot: 0, motifs deferred §2.5]
  conf(e) ← min(e.w_cum / 30, 1.0)            # Markov stability heuristic
  coverage ← fraction of edges with conf(e) ≥ 0.8, over active subgraph (w_rec > 0)
  return (r_edge < ε_e) AND (r_motif < ε_m) AND (coverage ≥ c_min)   # "well-sampled?", not "detect now?"
```

ε_e, ε_m, c_min calibration on F-Droid (E1) remains the cold-start study. For a stationary benign
app the cumulative graph's *shape* should converge to something stable even as raw weights climb
(all weights rising together is the stationary case). **How that stable shape is read off the
growing graph — normalization, snapshotting, or otherwise — is the deferred growth-handling question
(D7).** This diagnostic measures shape convergence regardless of which mechanism is chosen.

### 3.5 SCORE — deviation of one window (reconstruction of the cumulative graph)

```
ALGORITHM ScoreWindow(G, window_trace)
  G' ← copy(G);  UpdateGraph(G', window_trace)         # shadow update, not committed

  # ---- PRIMARY signal: reconstruct the CUMULATIVE graph ----
  X  ← node feature matrix from G'                      # §2.1 vectors (motif features deferred)
  A  ← w_cum adjacency of G'   ◀── GROWTH-HANDLING DEFERRED (D7): raw vs normalized vs snapshot
  #   OPEN: a cumulative graph grows forever, so raw weights drift up over long runs. Whether to
  #   feed RAW w_cum, a NORMALIZED form (row-normalize / proportions), or a snapshotted/bounded
  #   form is the parked growth-handling question (D7). Normalization is the leading CANDIDATE
  #   (it would cancel uniform scale drift) but is NOT committed in v0.2.
  (err_attr[v], err_struct[v]) ← AUTOENCODER(A, X)      # GAE/DOMINANT, per node

  # ---- ALONGSIDE signals: catch what the cumulative view DILUTES -------
  #   a small recent anomaly is a rounding error against a mature cumulative graph,
  #   so the cumulative reconstruction CANNOT be the only signal.
  rec_dev  ← deviation of the RECENCY channel (w_rec) for this window   # "recent ≠ benign-recent"
  # novel  ← { m in window : m ∉ G.M_ref }   # [DEFERRED FOR PILOT — motifs out, §2.5]

  # ---- amplification (relative, source-weighted) ----------------------
  score(u→v) ← base(u→v) · (1 + α·s_u)
  window_score ← aggregate( β·err_attr + (1−β)·err_struct ,  rec_dev ,  amplified edges )
  return window_score, per-node errors, rec_dev
```

**Why more than one signal:** the cumulative reconstruction is strong at "the overall accumulated
profile is a shape benign never takes" and *deliberately weak* at "a small new thing just appeared in
a mature graph" (dilution). The **recency channel (`w_rec`)** covers that weakness — `w_cum` retains
history for multi-stage detection; `w_rec` stays fresh and scale-independent. (When motifs return
post-pilot, the novel-motif flag adds a second scale-independent signal — §2.5.) This is why the
dual-weight design is load-bearing. **Note the open growth-handling question (D7)** — a hard reset of
the cumulative graph is one *candidate* but is in tension with `w_cum`'s purpose (it would discard
the history multi-stage detection relies on), which is exactly why the recency channel exists as a
*soft* continuous refresh; hard snapshots are otherwise reserved for app-version epochs (§3.3). None
of this is resolved in v0.2 — it is parked under D7.

### 3.6 PROCESSING MODEL — [v0.2: NEW] windowed cumulative, train/score mode

The single loop that replaces the v0.1 two-phase gate:

```
for each WINDOW of events (bundle over a time period):
    G ← UpdateGraph(G, window, t_now)        # fold window into cumulative graph
    emit  cumulative G                       # the cumulative graph state
                                             #   (growth-handling — raw/normalized/snapshot — is D7, deferred)

    if mode == TRAIN:   feed emitted graph to autoencoder as a benign example
    if mode == SCORE:   ScoreWindow → reconstruction error + recency dev   # (+ novel-motif when motifs return)
```

Consequences (all [PROVISIONAL]):
- **Training set = the accumulation trajectory.** One session → many cumulative snapshots
  (graph-after-window-1, -2, …). Train on the WHOLE trajectory, not only final-state graphs, so the
  autoencoder learns the benign manifold at every maturity (sparse-early to dense-late).
- **Two distinct time scales** — the *processing window* (how often the graph is snapshotted/scored)
  vs. the *edge window* (k, δ; what counts as a transition). Keep separate. Processing-window size is
  its own experiment (too small → near-identical inputs; too large → bursts get averaged out).
- **`IsStable` is a diagnostic** (§3.4), not a gate. Detection is available at any maturity because
  the autoencoder has been trained across maturities.
```

The pilot's signals — attr error, struct error (+ recency deviation) — are the **provisional F11
taxonomy** until the dedicated F11 literature phase refines it (the novel-motif signal joins when
motifs return). CUSUM over the window_score sequence gives
deviation onset (F12 detection-layer); `t_first`/`t_last` give it at graph level.

---

## 4. Deferred decisions — [DEFERRED]

| # | Question | Blocked on |
|---|---|---|
| D1 | Post-update probation scoring policy (the exploitable window) | temporal-block close + E1 data |
| D2 | App-category behavioral norms (F14 part 2) | cross-app corpus structure (F-Droid categories) |
| D3 | Network endpoint identity in the graph | open challenge from discussion; currently only coarse counts on `network` node |
| D4 | F11 deviation-type taxonomy from literature | dedicated F11+F14 research block |
| D5 | Accept/reject policy for committing a session to the reference (poisoning risk) | E4 variance data |
| D6 | **Motif mining + integration algorithms** (find recurring ordered sequences; feed via Option A/B/C, §2.5) | post-pilot; design the two algorithms together, not bolted on |
| D7 | **Cumulative-growth handling** — raw vs normalized vs snapshot/reset vs bounded history for the ever-growing cumulative graph (§3.5). Same parked discussion as the "reset to a previous snapshot" idea. | dedicated temporal-block session; E5 informs but does not decide it |

---

## 5. First experiments — what validates or kills v0.2

| ID | Experiment | Validates | Kills design if |
|---|---|---|---|
| E1 | Convergence curves: new-edge rate vs window count, across F-Droid apps (motif rate when motifs return) | F6 diagnostic, ε calibration, cold-start contribution | no convergence trend exists for most apps |
| E2 | (w_cum, w_rec) scatter across real traces | dual-channel temporal model (§2.4) | established/dormant/new regions don't separate |
| E3 | Sensitivity of edge counts to k, δ (motif params deferred) | edge formation rules | counts unstable across reasonable ranges |
| E4 | Reconstruction-error variance across benign windows of the same app | acceptable-deviation floor (F14), FP baseline | benign variance ≥ anomalous deviation |
| E5 | **[informs D7]** Cumulative-growth behavior: how does the raw cumulative graph's shape vs. scale evolve as w_cum grows? Does a candidate handling (e.g. normalization) keep shape stable? | characterizes the growth problem; provides evidence to *decide* D7 | (does not kill the design — it scopes the deferred growth-handling decision) |

**Order matters: E2 first or parallel with E1.** If the dual-channel separation fails, the
temporal model — the foundation of this design — is rethought before anything else is built.
**E5 is investigative, not a gate** — it characterizes the cumulative-growth problem and tests
candidate handlings (normalization among them) to inform the deferred D7 decision. It does not
assume normalization is the answer.

---

## 6. Requirement coverage map

| Req | Status in v0.2 |
|---|---|
| F1 | BuildInitialGraph — static-only init ✓ |
| F2 | UpdateGraph — events → edges/weights (motif mining deferred) ✓ |
| F3 | Two layers, shared node universe interface ✓ |
| F4 | Per-app G, fixed universe but per-app attributes/edges ✓ |
| F5 | Node universe exists at t=0 with static attributes ✓ |
| F6 | IsStable demoted to diagnostic (§3.4); measures cumulative-graph shape convergence; growth-handling = D7; ε calibration = E1 ◐ |
| F7 | Dual-weight channels (pilot) ✓ ; motif layer deferred (§2.5); validated by E2 ◐ |
| F8 | ReseedStatic policy ✓ ; probation window D1 ◐ |
| F10 | Category nodes preserve semantic identity ✓ ; named motifs deferred post-pilot ◐ |
| F11 | Pilot taxonomy = attr/struct/recency; motif signal + literature phase pending ◐ |
| F12 | t_first/t_last (graph) + CUSUM (detection layer) ◐ |
| F13 | N≈40 nodes, sparse E — laptop-tractable ✓ (motifs out of pilot) |
| F14 | Boundary violation signal ✓ ; flow/motif anomaly deferred (§2.5); category norms D2 ◐ |
