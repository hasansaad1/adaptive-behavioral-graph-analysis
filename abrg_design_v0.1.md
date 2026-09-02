# ABRG v0.1 — Adaptive Behavioral Reference Graph
## Design Document

**Status:** Provisional design for first implementation round.
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
        act_v,          # total activity count, log-scaled                            (dynamic)
        sess_v,         # fraction of sessions in which category was active           (dynamic)
        rec_v ]         # recency-channel summary: Σ w_rec over incident edges        (dynamic)
```

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
  w_cum   : float,   # cumulative observation count — NEVER decays (retention channel)
  w_rec   : float,   # exponentially decayed activity weight (recency channel)
  t_first : ts,      # first observation — temporal attribution anchor (F12 graph-level)
  t_last  : ts,      # most recent observation
  n_sess  : int,     # number of distinct sessions edge was observed in
  epoch   : int,     # app version epoch at t_first
}
```

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

### 2.5 Motif layer — [PROVISIONAL]

**Explicit temporal motifs stored as first-class objects** (your call: detection logic lives in the
graph object, not in ad-hoc queries).

- Motif = ordered sequence of directed edges, length L ∈ {2, 3}, all events within `δ_motif = 10 s`.
- Mined from benign sessions → reference motif set `M_ref`, each with count, n_sess, t_first.
- Detection-time: a session's observed motif either ∈ M_ref (update stats) or ∉ M_ref (novel-motif flag).

This is the **F14 flow mechanism**: `contacts → network_open → network_send` is judged as a flow,
not as three individually-permitted actions.

**Known limitation (documented, not solved):** motifs bounded by δ_motif structurally cannot
capture flows split across weeks. Long-range linkage = `w_cum`/`t_first` retention (graph) +
detection layer (CUSUM over session scores). The graph **retains**; the detection layer **connects**.

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
OUTPUT: graph G = (V, E, M_ref), all-static, zero dynamic observations

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
  M_ref ← ∅                                  # no motifs yet
  G.version_epoch ← 0
  return G
```

The graph is *meaningful but edge-empty* at this point: DOMINANT can reconstruct node attributes
(attribute channel) before any structure exists; the structural channel phases in as edges arrive.

### 3.2 UPDATE — one behavioral session (F2, F7)

```
ALGORITHM UpdateGraph(G, session_trace, t_now)
INPUT : G, time-ordered events [(api, args, ts)...] from Frida/strace, session time t_now
OUTPUT: updated G   (only called for sessions accepted as benign — see §3.4)

  # -- 0. decay pass: recency channel only -------------------------------
  for each edge e in G.E:
      e.w_rec ← e.w_rec · exp(−λ · (t_now − e.t_last))     # w_cum untouched

  # -- 1. map raw events to category stream ------------------------------
  S ← [(cat(api), ts) for (api, args, ts) in session_trace]

  # -- 2. edge formation: sliding (k, δ) window --------------------------
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
              e.w_cum  ← e.w_cum + 1
              e.w_rec  ← e.w_rec + 1
              e.t_last ← t_v

  # -- 3. per-session bookkeeping ----------------------------------------
  for each edge touched this session:  e.n_sess ← e.n_sess + 1
  for each node active this session:   v.sess  ← recompute fraction

  # -- 4. motif mining (explicit, stored) --------------------------------
  for each ordered window w ⊆ S with |w| ∈ {2,3} and span(w) ≤ δ_motif:
      m ← edge-sequence signature of w
      if m ∈ G.M_ref: G.M_ref[m].count++ ; G.M_ref[m].n_sess update
      else:           G.M_ref[m] ← { count:1, n_sess:1, t_first:t_now }

  # -- 5. node recency summaries ------------------------------------------
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

### 3.4 STABILITY check — F6 gate

```
ALGORITHM IsStable(G, history, W=last 5 sessions)
  r_edge  ← (#new edges  discovered in W) / (#sessions in W)
  r_motif ← (#new motifs discovered in W) / (#sessions in W)
  conf(e) ← min(e.w_cum / 30, 1.0)            # Markov stability heuristic, ~30 obs/edge
  coverage ← fraction of edges with conf(e) ≥ 0.8, over edges with w_rec > 0 (active subgraph)

  return (r_edge < ε_e) AND (r_motif < ε_m) AND (coverage ≥ c_min)
```

ε_e, ε_m, c_min have **no literature precedent for per-app behavioral graphs** — calibrating them
on the F-Droid corpus (experiment E1) is the empirical cold-start study claimed as a thesis
contribution. Until IsStable returns true, sessions are reference-building; after, deviation
scoring is considered calibrated. The update-vs-score decision policy during the unstable phase
is part of E1's design.

### 3.5 SCORE — deviation of a new session (sketch; detection layer is downstream work)

```
ALGORITHM ScoreSession(G, session_trace)
  G' ← copy(G);  UpdateGraph(G', session_trace)        # shadow update, not committed

  # signal 1 — attribute reconstruction error (DOMINANT attr channel)
  # signal 2 — structural reconstruction error (DOMINANT struct channel)
  X  ← node feature matrix from G'                     # §2.1 vectors
  A  ← w_cum-normalized adjacency of G'
  (err_attr[v], err_struct[v]) ← DOMINANT(A, X)        # per node

  # signal 3 — novel-motif flag (F14 flow anomaly)
  novel ← { m observed in session : m ∉ G.M_ref }

  # amplification (relative, source-weighted)
  score(u→v) ← base(u→v) · (1 + α·s_u)
  session_score ← aggregate( β·err_attr + (1−β)·err_struct , novel, amplified edges )

  if session accepted as benign-consistent: commit UpdateGraph(G, ...)
  return session_score, per-node errors, novel
```

The three signals — attr error, struct error, novel-motif — are the **provisional F11 taxonomy**
until the dedicated F11 literature phase refines it. CUSUM over session_score sequence gives
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

---

## 5. First experiments — what validates or kills v0.1

| ID | Experiment | Validates | Kills design if |
|---|---|---|---|
| E1 | Convergence curves: new-edge / new-motif rate vs session count, across F-Droid apps | F6 criterion, ε_e/ε_m calibration, cold-start contribution | no convergence trend exists for most apps |
| E2 | (w_cum, w_rec) scatter across real traces | dual-channel temporal model (§2.4) | established/dormant/new regions don't separate |
| E3 | Sensitivity of edge & motif counts to k, δ, δ_motif | edge/motif formation rules | counts unstable across reasonable ranges |
| E4 | DOMINANT reconstruction-error variance across benign sessions of the same app | acceptable-deviation floor (F14), FP baseline | benign variance ≥ anomalous deviation |

**Order matters: E2 first or parallel with E1.** If the dual-channel separation fails, the
temporal model — the foundation of this design — is rethought before anything else is built.

---

## 6. Requirement coverage map

| Req | Status in v0.1 |
|---|---|
| F1 | BuildInitialGraph — static-only init ✓ |
| F2 | UpdateGraph — events → edges/weights/motifs ✓ |
| F3 | Two layers, shared node universe interface ✓ |
| F4 | Per-app G, fixed universe but per-app attributes/edges ✓ |
| F5 | Node universe exists at t=0 with static attributes ✓ |
| F6 | IsStable gate; ε calibration = E1 (open empirical) ◐ |
| F7 | Dual-weight channels + motif layer; validated by E2 ◐ |
| F8 | ReseedStatic policy ✓ ; probation window D1 ◐ |
| F10 | Category nodes + named motifs preserve semantic identity ✓ |
| F11 | Provisional 3-signal taxonomy; literature phase pending ◐ |
| F12 | t_first/t_last (graph) + CUSUM (detection layer) ◐ |
| F13 | N≈40 nodes, sparse E, L≤3 motifs — laptop-tractable ✓ |
| F14 | Boundary violation signal + motif flow anomaly ✓ ; category norms D2 ◐ |
