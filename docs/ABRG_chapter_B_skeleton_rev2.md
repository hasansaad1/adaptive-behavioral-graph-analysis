# Chapter B — skeleton, revision 2

**ContextDroid: BFS-first navigation with LLM task execution, and the v2 corpus**

Revised 17 August 2026 against `docs/contextdroid_spec.md`. Supersedes revision 1.
Changes marked **[REV]** where revision 1 was wrong.

---

## What revision 1 got wrong

| Rev 1 claim | Correction | Source |
|---|---|---|
| "LLM-guided exploration" | Explore is **deterministic BFS** (`prompt_hash=bfs_navigation_phase`), ~6,446 of ~8,700 original steps. LLM drives execute and primary-UX phases only. | spec §4.5, §1.3 |
| No Monkey involved | Monkey runs as a **10-event warmup**, seed 42, outside the timed loop | spec §2.2 step 9 |
| Sessions independent | Independent **of that package's app data** when `pm clear` succeeds; device state, other packages, and accounts persist | spec §5.3 |
| Sessions are repeated samples | `SESSION_MODE_SCHEDULE=identical,identical,varied`; identical-mode sessions share `agent_seed` | spec §5.5 — **open question below** |
| Screens-per-session unrecoverable | Recoverable from collection `*_llm_actions.jsonl` via `screen_hash`; absent from the export only | spec §9.4 |
| Session duration unspecified | 420 s configured, median observed wall 460.7 s | spec §5.1 |

**Open question blocking §B.3.2 and Chapter C:** if two of every three sessions share
`agent_seed`, they are near-replicates rather than independent samples. Needs the
identical-vs-varied census and within-app pairwise distance split by mode.

**Page budget (~30–36):** B.1 3 · B.2 10 · B.3 6 · B.4 8 · B.5 2 · B.6 3 · B.7 3.

---

# B.1 Framing

## B.1.1 The stimulus problem

Dynamic analysis is bounded by what the exercised app does. Random input maximises
event volume, not behavioural relevance. DL-Droid reports 97.8% from dynamic features
alone under state-based input generation — a stimulus result, not a model result.

Chapter A's corpus is 600 s of Monkey per app. Every negative result there is
conditional on a stimulus policy chosen by someone else.

## B.1.2 What this chapter does

1. Specifies **ContextDroid**: a dynamic-analysis pipeline combining deterministic
   BFS navigation with LLM-driven task execution (§B.2).
2. Characterises the **v2 corpus** it produced: 40 graph-eligible apps, 342 usable
   sessions, median 8 per app (§B.3).
3. **Compares** the resulting representation against AndroCT on identical metrics
   (§B.4).

No detector, no AUC. v2 is benign-only.

## B.1.3 Contributions

1. **ContextDroid**, specified end to end: 58-hook Java-layer instrumentation, a
   two-phase stimulation policy (BFS navigation then LLM task execution), a session
   protocol with per-session `pm clear`, and an eight-conjunct reference-tier quality
   gate (§B.2).
2. **A measured stimulus-quality result**: mapped-event rate **0.204** versus AndroCT's
   **0.026** (p = 9.19e-14, Cliff δ = 0.568, large), with statistically
   indistinguishable absolute mapped-event counts (p = 0.15) from roughly a quarter of
   the raw events (§B.4.2).
3. **A measured coverage cost**: active nodes 2 vs 6, edges 2 vs 16, both large
   effects. Signal density and behavioural breadth trade against each other under this
   policy (§B.4.2).
4. **The δ measurement Chapter A defers**: retention 0.838 overall, strongly stratified
   (Q1 0.273 → Q4 0.905), fitted asymptote **0.941** (§B.5).
5. **Retirement of a Chapter A threat**: `sms` is dead in v2 and in both AndroCT
   classes, under unrelated stimulus policies — and the ContextDroid action space
   contains no SMS-capable action, so the cause is identified rather than inferred
   (§B.4.3, §B.6.2).
6. **A quality-gate design** whose defect classes are documented: metric/no-op
   pathologies, explore-blind ratios, and weakened flailing rules that would have
   admitted 12 sessions (§B.2.6, §B.6.3).

## B.1.4 Questions

- B-Q1 What does two-phase guided stimulus change about trace composition?
- B-Q2 Does it change the graph representation, and how?
- B-Q3 Are Chapter A's structural findings artefacts of corpus age or stimulus policy?
- B-Q4 What does the temporal edge filter δ cost?

---

# B.2 ContextDroid **[REV — substantially rewritten]**

## B.2.1 Design rationale and honest scope

State the design intent (LLM-first stimulation, `protocol_constants.md`), then state
what v2 actually ran. **Report the doc/code divergences rather than presenting the
docs as the system:**

- README and `methodology.md` still describe monkey-driven interaction; v2 ran
  `--arm llm` at 420 s.
- `protocol_constants.md` freezes 120 s; v2 used 420 s.
- The governing remediation principle, quoted: *"Instrument before you fix. Fix before
  you multiply."*

## B.2.2 Instrumentation

- **Hook script**: `frida_scripts/hook_apis.js`, SHA256 `3192c7d6…`, 856 lines, version
  tag `"3"`, identical across all 168 original sessions.
- **58 hook names** by direct `logEvent`; 62 distinct API names emitted (four
  ContentResolver names pass through `logContentUriEvent`). **Full inventory table**
  from `docs/contextdroid_hooks.csv`.
- **Taxonomy**: 25 hook categories; graph universe is 22. Dropped: `lifecycle`,
  `reflection`, `navigation`. `Context.startActivity` is logged twice — `ipc_intents`
  (kept) and `navigation` (dropped).
- **Event record**: `type`, `timestamp`, `api`, `category`, `args`.
- **[REV] Two unsynchronised clock domains.** Frida events use `Date.now()` in the JS
  runtime; action logs use host `time.time()`. δ operates on Frida timestamps and is
  internally consistent; cross-referencing actions to events would not be. State this.
- **Attach, not spawn.** Attach to a running PID after `ensure_app_running`; spawn
  (`-f`) is implemented but unused. Consequence: pre-`onCreate` behaviour is not
  observed. Three attempts, 12 s timeout; mid-session health-check and reattach;
  2 sessions failed with `failed_frida_reattach`.
- `safeHook` swallows install errors so hooks cannot crash the app — a deliberate
  coverage/robustness trade.

## B.2.3 **[REV]** Stimulation: two phases, not one

**This is the section revision 1 got wrong. Lead with the architecture.**

**Warmup (untimed).** Permission pre-grant via `pm grant`, dialog resolution, then
**10 Monkey events, seed 42**, then dialog resolution again, then a verified-start
uiautomator dump. Outside the timed loop and outside the Frida attach.

**Phase 1 — BFS navigation (deterministic).** `choose_explore_action`, no LLM.
Candidate buckets: nav / tab / expand / other, with recovery actions
(`bfs_return_to_hub`, `bfs_avoid_back_loop`). Budget: `min(duration × 0.35,
duration − reserve)` floored at 120 s, clamped to `[25, duration−30]`.

**Phase 2 — LLM task execution.** Ollama llama3.2, temperature 0.0, seeded when
`agent_seed` is set. Prompt families: execute/UX-goal and primary-UX.

**Phase split — report the measured numbers.** ~6,446 of ~8,700 original steps carry
`bfs_navigation_phase`. **Report steps and mapped events per phase**, because this
determines how much of §B.4.2's result is attributable to systematic traversal versus
semantic planning. Do not claim the LLM produced a result that BFS produced.

### The observation

**uiautomator XML, not screenshots** (no `screencap` anywhere in `llm_agent/`).
`dump_clean_screen` → normalised elements (enabled, and clickable/long-clickable/
focusable-text-entry) with `package, resource_id, content_desc, text, class_name,
bounds, clickable` → token-trimmed → hashed. Injected as `CLEAN_SCREEN_ELEMENTS`.

Prompts are hashed, not stored, so the rendered observation for a given step is not
recoverable. State this.

### The action space

Six types: `tap, input, back, wait, advance_goal, swipe`. Invalid types degrade to
`wait` with `planner_contract_invalid_action_type`.

**[REV] `advance_goal` performs no device I/O and returns success.** The remediation
record identifies this as a metric pathology; the fix was to the metrics that consumed
it, not to the action. Report it — it bears on how session quality is measured.

**Absent by construction**: permission grants in the timed loop (pre-granted via
`pm grant`), credential flows, purchases, `long_press`, named `scroll`, intent
injection. **This is the code-level explanation for the dead categories in §B.4.3.**

Note the internal inconsistency worth one line: the explore prompt template lists
`tap|input|back|wait`, omitting `swipe` and `advance_goal`, while the planner frozenset
includes them.

## B.2.4 Session protocol

Per-session sequence, in order: snapshot restore (or skip) → frida-server ensure →
`isolate_emulator_state` (HOME + force-stop other third-party packages) → device guard
→ `install -r` → `pm clear` → launch → warmup → force-launch → Frida attach → timed
session → uninstall → metadata.

**[REV] Independence, stated precisely.** Sessions are independent **of that package's
app data** when `pm clear` succeeds (all 168 original: `pm_clear_rc=0`). They are not
AVD resets. Persisting across sessions: emulator userdata, other installed packages,
device-level accounts, external-storage files not owned by the cleared package.

**This is the mechanism behind Chapter C's convergence result** and belongs here, in
the protocol, not retrofitted there.

**Provenance caveat**: `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` on the extension batch means
`_restore_snapshot` can return True — and metadata record `snapshot_restored=true` —
**without loading a snapshot**. Report this.

## B.2.5 **[OPEN]** Session mode schedule

`SESSIONS_PER_APP=3`, `SESSION_MODE_SCHEDULE=identical,identical,varied`, with
`agent_seed` shared across identical-mode sessions of an app.

**Report the census**: how many usable sessions are identical-mode versus varied, and
within-app pairwise graph distance split by mode. If identical-mode sessions are
near-replicates, they are not independent observations, and Chapter C's convergence
analysis must say so.

**Do not write this section until that measurement exists.**

## B.2.6 Quality gates

Eight conjuncts: `analyze_ok ∧ sim==success ∧ faith ∈ {FAITHFUL, PARTIAL} ∧ c0_pass ∧
meaningful_22 > 0 ∧ ¬flail ∧ ¬auth_gated ∧ ¬network_degraded`.

- **C0**: ≥3 named functional explore taps **or** ≥2 functional explore screen hashes.
- **meaningful_22**: Frida events in the 22-node universe, excluding `hook_loaded` and
  `Method.invoke`.
- **Flailing**, six sub-rules: `mechanical_majority`, `explore_back_wait_dominant`,
  `dominant_screen`, `same_element_cycle`, `low_all_phase_direct_ratio`, plus
  no-actions cases. Give thresholds.

**A gate that was weakened and restored**: an earlier `_flailing_new` dropped
`same_element_cycle` and guarded `dominant_screen`, which would have admitted 12
flailing sessions. Merged back into a single `detect_suspect_flailing`. Report it —
this is the same class of finding as Chapter A's §A.7.

## B.2.7 Safety posture

Three states, per control. **Report plainly that v2 is a benign corpus and the
malware-tier controls did not run:**

| Control | Implemented | Exercised for v2 |
|---|---|---|
| Device guard (hard assert, watchdog) | yes | **yes** — 0 `failed_device_guard` in 388 |
| AVD isolation, force-stop others | yes | yes |
| `pm clear` per session | yes | yes |
| Network sink + guest iptables DNAT | yes | **no** |
| `gate_p4` preflight | yes | **no** |
| `-wipe-data` | yes | **no** |
| `adb_pinned.sh` | yes | **no** |
| Encrypted vault | yes | **no** |
| Host `pfctl` backstop | **design only** | no |

Device-guard **pass** is not recorded as a per-session metadata field; only failure
sets a status. State that gap.

## B.2.8 What ContextDroid is not

It did not collect malware. The malware-handling infrastructure exists in code and was
not exercised. Chapter A's malware evaluation uses a public corpus for the
sensor-symmetry reason in §A.2.1.

---

# B.3 The v2 corpus

## B.3.1 Population

388 indexed / **342 usable** / 46 reference-tier failures. Batches: original 168,
canary 2, extend 172. 59 apps with ≥1 usable session; **40 graph-eligible**;
eligibility unchanged by the extension (40 → 40, none in, none out). Per-app counts:
median 8 (19 apps at 9, 18 at 8, 3 at 7).

## B.3.2 The extension and poolability

Original July 12–19 2026; extension August 13–15 2026.

- Wall duration does not differ (p = 0.413).
- Mapped events, total events, active nodes, edges, density **do**, at small effect
  sizes (|δ| 0.16–0.29). Report each with statistic and effect size.
- **Failure concentration**: 46 failures across 13 of 40 extension apps, max 6 per app,
  **4 apps failed every new slot**. Name them; their curves are shortened in Chapter C.
- Fail reasons: `partial:bad_handoff` 14, `partial:ux_quality_gate` 12,
  `partial:no_goal_progress` 7, `webview_dominant` 6, `flailing:dominant_screen` 4,
  `failed_frida_reattach` 2, `flailing:same_element_cycle` 1.

**[OPEN]** Fold in the identical/varied mode census from §B.2.5.

## B.3.3 Provenance

Configuration table with **UNRECOVERABLE** marked: July Frida client and server
versions, frida-server binary SHA, emulator system image, July AVD name, planner
digest, July `prompts.py` SHA, Python and pip freeze, adb version.

**The frida-server override**, reproduced: client 17.9.3 installed 2026-04-30, no
upgrade trail through July; Frida enforces client/server compatibility at attach and
July sessions attached; no frida commands in July shell history.

**The canary, with its ambiguity.** Three apps, one new session each. **PASS** under
the pre-declared 0.25×–4× mapped-event band; **FAIL** under existing min–max. State the
band as operative and why: min–max over 2–3 prior sessions is an extremely tight bound
on a corpus with large session-to-session variance. Report both.

---

# B.4 The representation comparison

## B.4.1 Units

AndroCT: one whole-trace graph per app. v2 reports two units, never conflated:
**per-session** (n = 342, Chapter C's unit) and **per-app pooled** (n = 59, compared
against AndroCT). Pooling is concat-then-build: mapped category streams concatenated in
`session_index_within_app` order, then one `update_graph_sequence`. State and justify.

## B.4.2 Trace composition — the headline

Materiality rule declared before the table: p < 0.05 **and** |Cliff δ| ≥ 0.147.

| metric | v2 session | v2 pooled | AndroCT benign | test |
|---|---|---|---|---|
| mapped events | 84 | 372 | 185 | p = 0.15, δ = 0.11 — **not material** |
| total events | 524 | 1703 | 6878 | p = 2.09e-4, δ = −0.282 (small) |
| **mapped rate** | **0.244** | **0.204** | **0.026** | **p = 9.19e-14, δ = 0.568 (large)** |
| active nodes | 3 | 2 | 6 | p = 3.61e-12, δ = −0.527 (large) |
| edges | 5 | 2 | 16 | p = 9.08e-11, δ = −0.493 (large) |
| ≤2 edges | 158/342 | 32/59 | 455/2231 | — |

**Lead with**: mapped-event rate roughly eight times higher; absolute mapped-event
counts statistically indistinguishable from a quarter of the raw volume.

**Cost, in the same paragraph**: sparser on every structural measure, all large
effects. Over half of v2 apps produce ≤2 edges.

**[REV] Attribution.** With the phase split from §B.2.3, state how much of the mapped
volume comes from BFS navigation versus LLM execution. If BFS dominates, the finding is
about systematic traversal, not semantic planning — and that is still a stimulus
result, just a different mechanism.

## B.4.3 Category coverage

Fire rate per category, ranked by difference. Largest gaps (v2 − AndroCT):
`package_manager` −0.735, `native_code` −0.628, `ipc_intents` −0.375;
`storage` +0.209.

Dead in v2: `sms`, `dynamic_code_loading`, `telephony`, `clipboard` (0 apps);
`camera` (1 app).

**[REV] Explain from the action space, not by inference.** No SMS, telephony,
clipboard, or dex-loading action exists in the six-type planner set. These categories
are unreachable by construction, not unreached by chance.

Three interpretation classes:
- **Unreachable by policy** — `sms`, `telephony`, `clipboard`,
  `dynamic_code_loading`. Confirmed from `_ACTION_TYPES_PLANNER`.
- **Platform-gated regardless of policy** — `sms` is also dead in both AndroCT classes
  under a completely different stimulus. Two mechanisms, same outcome (§B.6.2).
- **Incidental under high-volume random input** — `package_manager`, `native_code`
  fire under Monkey and not under guided traversal.

`ipc_intents` at −0.375 needs its own note: it carries Chapter A's entire benign-only
signal (§A.6.7) and fires substantially less here.

## B.4.4 Static features

v2 59/59 resolved, 0 all-zero; AndroCT benign n = 703, 0 all-zero. Per-coordinate and
static-norm distributions for both.

## B.4.5 Event yield

Three candidate explanations and what separates them:

- **Narrower hook coverage**: 22 of 58 never fire. §B.2.2's table plus §9.1's
  per-hook reasons — several are Camera1-vs-Camera2 or overload misses
  (`Cipher.getInstance` silent while `doFinal` fires), not coverage failures.
- **[REV] Fewer surfaces**: now measurable. `screen_hash` in collection
  `*_llm_actions.jsonl` gives distinct screens per session; absent only from the
  export. Report distinct screens per session and its correlation with mapped events.
- **Lower event density**: v2 mapped/s 0.184 vs AndroCT 0.308. **Caveat the AndroCT
  denominator** — it assumes the stated 600 s protocol; those traces carry no
  wall-clock.

v2 mapped events do not correlate with session wall duration (ρ = 0.074, p = 0.173,
n = 342): more time does not produce more mapped events, which points at the policy
rather than the budget.

---

# B.5 The temporal filter δ, measured

Chapter A forward-references this (§A.4.3).

δ is a conjunctive filter: it can only remove edges; gap duration is never written as
an attribute. Measured on v2, where timestamps exist:

- **Retention 0.838 overall**, strongly stratified by session event count:
  Q1 0.273, Q2 0.446, Q3 0.672, Q4 0.905.
- Fitted `a − b·exp(−c·n)`: **0.941 at 5k, 10k, and 50k** — saturates below 1.0.

**Consequence for Chapter A**: at AndroCT densities the filter would remove ~6% of
candidate edges, roughly uniformly. Its absence is a bounded limitation. **The
asymptote is 0.941, not 1.0** — correct any earlier figure.

---

# B.6 What this says about Chapter A

## B.6.1 Sparsity is not a corpus-age artefact

Chapter A's structural results condition on graphs with median 6 active nodes and 16
edges. A modern corpus, current Android, purpose-built instrumentation, and two-phase
guided stimulation produces **fewer**: 2 and 2. The sparsity driving Chapter A's
reconstruction failure is at least as severe under the better instrument.

This strengthens Chapter A's structural null rather than qualifying it.

## B.6.2 A retired threat, with a mechanism

`sms` is dead in AndroCT benign, AndroCT malware, and v2. Two unrelated stimulus
policies, eight years apart. **And** the ContextDroid action space contains no
SMS-capable action, so for v2 the cause is identified in code rather than inferred.
Consistent with dangerous-permission gating on API 23+ for AndroCT.

## B.6.3 A shared methodological pattern

Chapter A's §A.7 records seven artefacts caught by auditing denominators and
populations. ContextDroid's remediation record contains the same class: metrics that
could not see engine skips, explore-blind ratios, and a weakened flailing rule that
would have admitted 12 sessions. **The governing principle is the project's own:
instrument before you fix.**

## B.6.4 What this chapter cannot say

No malware, so no detection claim transfers. The comparison establishes that the
representation behaves comparably — more extremely — under modern instrumentation. It
does not establish that Chapter A's AUCs would replicate. That needs a
sensor-symmetric malware arm on v2: future work.

---

# B.7 Threats to validity

- **40 apps, benign only.** Case study, not population estimate. Say so in every
  caption.
- **[OPEN] Session-mode replication.** If identical-mode sessions share `agent_seed`,
  two of every three sessions are near-replicates rather than independent samples.
- **One configuration.** One planner model, one temperature, one explore ratio, one
  duration. No ablation over planner, prompt, or phase split.
- **Frida-server provenance gap**; behavioural equivalence substituted via canary,
  which passes one criterion and fails a tighter one.
- **Snapshot flag unreliable** on the extension batch: `snapshot_restored=true` does
  not prove a snapshot load under skip-load.
- **Batch heterogeneity**: five of six metrics differ between batches at small effect
  sizes; pooled regardless in Chapter C.
- **Failure concentration**: 4 apps failed every extension slot.
- **Attach-not-spawn**: behaviour before `onCreate` is unobserved.
- **22 of 58 hooks never fire**; several are overload or API-generation misses rather
  than coverage gaps.
- **Two unsynchronised clock domains** between Frida events and action logs.
- **`advance_goal` returns success without device I/O**; consuming metrics were fixed,
  the action was not.
- **AndroCT rate denominators assumed** (600 s protocol; actual durations unknown).
- **Device-guard pass not recorded** per session.
- **Doc/code divergence**: README and `methodology.md` describe a monkey-driven
  pipeline that is not what produced v2.

---

# Do not drop under deadline

1. §B.2.3's phase split — without it the chapter overclaims the LLM's role
2. §B.4.2's mapped-rate result **and** its cost in the same paragraph
3. §B.4.3's action-space explanation for dead categories
4. §B.2.4's independence statement — Chapter C depends on it
5. §B.5's corrected asymptote (0.941)
6. §B.6.1 — what Chapter A needs from this chapter
7. §B.2.6's weakened-then-restored gate — the §A.7 pattern, repeated
8. §B.2.7's honest three-state safety table
