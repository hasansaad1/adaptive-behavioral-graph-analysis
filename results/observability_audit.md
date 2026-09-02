# ABRG observability audit — 22-node universe

Generated: 2026-08-22T14:31:54.637936+00:00

**Effective universe (PRODUCIBLE):** AndroCT **18/22**; v2_extended **15/22**.

---

## Part 1 — Occupancy tables

Coordinate = mapped-event `act_count` per category (graph tensor `act_v_frac × n_mapped`).
1b distinct values are on **D1 train-benign** deviation profiles (562 apps).

CSV: `results/observability_androct.csv`, `results/observability_v2_extended.csv`.

### AndroCT (graph-eligible, n=2403)

| category | frac_nonzero_benign | frac_nonzero_malware | n_distinct_train_benign_d1 | median_act_count_nonzero_overall | total_mapped_events |
| --- | --- | --- | --- | --- | --- |
| clipboard | 0.0 | 0.0 | 4 | 0.0 | 0 |
| sms | 0.0 | 0.0 | 6 | 0.0 | 0 |
| telephony | 0.001422475106685633 | 0.0 | 6 | 8.99999988079071 | 9 |
| camera | 0.005689900426742532 | 0.0 | 12 | 1.5000000419095159 | 12 |
| audio | 0.005689900426742532 | 0.000588235294117647 | 10 | 27.999999288469553 | 23633 |
| dynamic_code_loading | 0.0 | 0.0058823529411764705 | 3 | 1.49999996565748 | 57 |
| accounts | 0.012802275960170697 | 0.0017647058823529412 | 17 | 7.999999945051968 | 85 |
| location | 0.02418207681365576 | 0.009411764705882352 | 26 | 14.000000398606062 | 1167 |
| content_access | 0.07396870554765292 | 0.00411764705882353 | 59 | 7.999999877574737 | 1235 |
| notifications | 0.021337126600284494 | 0.03058823529411765 | 18 | 1.0000000123400241 | 331 |
| media | 0.034139402560455195 | 0.1011764705882353 | 30 | 2.000000048428774 | 3858 |
| database | 0.17780938833570412 | 0.06588235294117648 | 95 | 20.0 | 34571 |
| device_info | 0.16500711237553342 | 0.14352941176470588 | 101 | 4.000000098603778 | 12366 |
| process | 0.30014224751066854 | 0.3135294117647059 | 175 | 6.9999999245628715 | 23237 |
| network | 0.3314366998577525 | 0.3058823529411765 | 204 | 119.00000405311584 | 212618 |
| webview | 0.28591749644381226 | 0.37941176470588234 | 171 | 514.0000163838267 | 485435 |
| storage | 0.46088193456614507 | 0.4047058823529412 | 265 | 12.000000038184226 | 31981 |
| crypto | 0.5746799431009957 | 0.7170588235294117 | 309 | 108.00000268220901 | 1982341 |
| ipc_intents | 0.6856330014224751 | 0.7211764705882353 | 413 | 51.0000019017607 | 189555 |
| package_manager | 0.7425320056899004 | 0.7023529411764706 | 405 | 48.00000087637454 | 157174 |
| file_io | 0.635846372688478 | 0.7741176470588236 | 378 | 121.0000034943223 | 850284 |
| native_code | 0.7709815078236131 | 0.8541176470588235 | 436 | 75.99999916926026 | 711833 |

### v2_extended (reference-tier sessions)

| category | frac_nonzero_sessions | n_distinct_nonzero_session_counts | median_count_nonzero_sessions | total_mapped_events |
| --- | --- | --- | --- | --- |
| accounts | 0.0 | 0 | 0.0 | 0 |
| clipboard | 0.0 | 0 | 0.0 | 0 |
| device_info | 0.0 | 0 | 0.0 | 0 |
| dynamic_code_loading | 0.0 | 0 | 0.0 | 0 |
| media | 0.0 | 0 | 0.0 | 0 |
| sms | 0.0 | 0 | 0.0 | 0 |
| telephony | 0.0 | 0 | 0.0 | 0 |
| camera | 0.008771929824561403 | 1 | 1.0 | 3 |
| package_manager | 0.023391812865497075 | 1 | 1.0 | 8 |
| location | 0.02631578947368421 | 3 | 14.0 | 136 |
| process | 0.02631578947368421 | 7 | 419.0 | 3357 |
| audio | 0.04678362573099415 | 4 | 7.0 | 82 |
| notifications | 0.049707602339181284 | 8 | 36.0 | 494 |
| content_access | 0.07017543859649122 | 21 | 145.0 | 7622 |
| webview | 0.0847953216374269 | 12 | 16.0 | 595 |
| native_code | 0.14912280701754385 | 8 | 3.0 | 164 |
| database | 0.16374269005847952 | 22 | 27.0 | 3105 |
| crypto | 0.17251461988304093 | 28 | 88.0 | 9911 |
| network | 0.1871345029239766 | 17 | 5.0 | 1261 |
| ipc_intents | 0.34502923976608185 | 28 | 9.0 | 1851 |
| file_io | 0.7660818713450293 | 43 | 5.0 | 9720 |
| storage | 0.8216374269005848 | 99 | 39.0 | 44457 |

---

## Part 2 — Classification

### AndroCT

- **clipboard** → `STIMULUS_LIMITED`: ClipboardManager mapped; 1/2231 benign fires under random Monkey — API producible but stimulus rarely reaches copy/paste flows.
- **sms** → `PERMISSION_GATED`: 0/2231 benign and 0/1736 malware fire (androct_graph_cache); SmsManager mapped; Monkey grants no dangerous permissions.
- **telephony** → `PERMISSION_GATED`: Near-zero fire rate; TelephonyManager/call APIs require runtime permissions Monkey does not grant; 1/N benign fires is stimulus noise.
- **camera** → `PRODUCIBLE`: Observed act_count>0 on 0.17% of eligible apps.
- **audio** → `PRODUCIBLE`: Observed act_count>0 on 0.21% of eligible apps.
- **dynamic_code_loading** → `STIMULUS_LIMITED`: DexClassLoader/instrumentation APIs mapped; 4/2231 benign fires — producible in principle, rare under Monkey.
- **accounts** → `PRODUCIBLE`: Observed act_count>0 on 0.50% of eligible apps.
- **location** → `PRODUCIBLE`: Observed act_count>0 on 1.37% of eligible apps.
- **content_access** → `PRODUCIBLE`: Observed act_count>0 on 2.46% of eligible apps.
- **notifications** → `PRODUCIBLE`: Observed act_count>0 on 2.79% of eligible apps.
- **media** → `PRODUCIBLE`: Observed act_count>0 on 8.16% of eligible apps.
- **database** → `PRODUCIBLE`: Observed act_count>0 on 9.86% of eligible apps.
- **device_info** → `PRODUCIBLE`: Observed act_count>0 on 14.98% of eligible apps.
- **process** → `PRODUCIBLE`: Observed act_count>0 on 30.96% of eligible apps.
- **network** → `PRODUCIBLE`: Observed act_count>0 on 31.34% of eligible apps.
- **webview** → `PRODUCIBLE`: Observed act_count>0 on 35.21% of eligible apps.
- **storage** → `PRODUCIBLE`: Observed act_count>0 on 42.11% of eligible apps.
- **crypto** → `PRODUCIBLE`: Observed act_count>0 on 67.54% of eligible apps.
- **ipc_intents** → `PRODUCIBLE`: Observed act_count>0 on 71.08% of eligible apps.
- **package_manager** → `PRODUCIBLE`: Observed act_count>0 on 71.41% of eligible apps.
- **file_io** → `PRODUCIBLE`: Observed act_count>0 on 73.37% of eligible apps.
- **native_code** → `PRODUCIBLE`: Observed act_count>0 on 82.98% of eligible apps.

**Effective universe size: 18/22**

### v2_extended

- **accounts** → `UNDETERMINED`: 0/N sessions; AccountManager hooks exist; spec marks non-firing UNDETERMINED (AVD account state unknown, B4).
- **clipboard** → `STIMULUS_LIMITED`: Frida hook exists (hook_category_summary n_hooks=1) but 0/N sessions fire; planner has no clipboard action; random/LLM traversal rarely triggers ClipboardManager.
- **device_info** → `UNDETERMINED`: 0/N sessions; Build/Telephony identifier hooks exist; emulator may return null identifiers — spec UNDETERMINED (B4).
- **dynamic_code_loading** → `STIMULUS_LIMITED`: Hooks present but planner excludes dex-loading actions; 0/N sessions fire under guided traversal (B4 unreachable-by-construction list).
- **media** → `UNDETERMINED`: 0/N sessions; MediaPlayer/codec hooks exist; media hardware/codec path UNDETERMINED on AVD (B4).
- **sms** → `HARDWARE_ABSENT`: 0/N sessions; AVD has no cellular radio/SIM; planner action frozenset excludes SMS actions (B4 §category fire).
- **telephony** → `HARDWARE_ABSENT`: 0/N sessions; no incoming/outgoing call stack on emulator AVD; planner excludes telephony actions.
- **camera** → `PRODUCIBLE`: Observed on 3/342 sessions.
- **package_manager** → `PRODUCIBLE`: Observed on 8/342 sessions.
- **location** → `PRODUCIBLE`: Observed on 9/342 sessions.
- **process** → `PRODUCIBLE`: Observed on 9/342 sessions.
- **audio** → `PRODUCIBLE`: Observed on 16/342 sessions.
- **notifications** → `PRODUCIBLE`: Observed on 17/342 sessions.
- **content_access** → `PRODUCIBLE`: Observed on 24/342 sessions.
- **webview** → `PRODUCIBLE`: Observed on 29/342 sessions.
- **native_code** → `PRODUCIBLE`: Observed on 51/342 sessions.
- **database** → `PRODUCIBLE`: Observed on 56/342 sessions.
- **crypto** → `PRODUCIBLE`: Observed on 59/342 sessions.
- **network** → `PRODUCIBLE`: Observed on 64/342 sessions.
- **ipc_intents** → `PRODUCIBLE`: Observed on 118/342 sessions.
- **file_io** → `PRODUCIBLE`: Observed on 262/342 sessions.
- **storage** → `PRODUCIBLE`: Observed on 281/342 sessions.

**Effective universe size: 15/22**

---

## Part 3 — KS hypothesis

**Verdict: PARTIAL**

Exceptions (high KS despite PRODUCIBLE bucket): `audio` KS=0.801, `content_access` KS=0.714. Uniformity failure is not exclusively non-producibility; sparse PRODUCIBLE coordinates (audio, content_access) also depart strongly from U(0,1).

### 3a — KS vs occupancy (AndroCT, D-2 Phase 1c)

| category | bucket | occupancy | ks_statistic |
| --- | --- | --- | --- |
| clipboard | STIMULUS_LIMITED | 0.0 | 0.851063829787234 |
| sms | PERMISSION_GATED | 0.0 | 0.9361324212992707 |
| telephony | PERMISSION_GATED | 0.0004161464835622139 | 0.728695060655304 |
| camera | PRODUCIBLE | 0.0016645859342488557 | 0.6128894095713189 |
| audio | PRODUCIBLE | 0.0020807324178110697 | 0.8011035108272552 |
| dynamic_code_loading | STIMULUS_LIMITED | 0.004161464835622139 | 0.6879432624113475 |
| accounts | PRODUCIBLE | 0.004993757802746567 | 0.4254059433379943 |
| location | PRODUCIBLE | 0.01373283395755306 | 0.5828199992441707 |
| content_access | PRODUCIBLE | 0.02455264253017062 | 0.7142965118476248 |
| notifications | PRODUCIBLE | 0.027881814398668332 | 0.6396457679855889 |
| media | PRODUCIBLE | 0.08156471077819392 | 0.6092488316138216 |
| database | PRODUCIBLE | 0.0986267166042447 | 0.6875023619666679 |
| device_info | PRODUCIBLE | 0.149812734082397 | 0.43896048272300114 |
| process | PRODUCIBLE | 0.3096129837702871 | 0.5684844362143029 |
| network | PRODUCIBLE | 0.31335830212234705 | 0.46367610193618275 |
| webview | PRODUCIBLE | 0.352059925093633 | 0.36955015557487114 |
| storage | PRODUCIBLE | 0.4211402413649605 | 0.3464973608959097 |
| crypto | PRODUCIBLE | 0.6754057428214731 | 0.37490394668883764 |
| ipc_intents | PRODUCIBLE | 0.7107781939242613 | 0.13739717571772292 |
| package_manager | PRODUCIBLE | 0.714107365792759 | 0.13331569731554616 |
| file_io | PRODUCIBLE | 0.7336662505201831 | 0.10694985072370666 |
| native_code | PRODUCIBLE | 0.8297960882230545 | 0.08539611755665572 |

### 3b — Mean KS by bucket
- `PERMISSION_GATED`: 0.8324 (n=2)
- `PRODUCIBLE`: 0.4499 (n=18)
- `STIMULUS_LIMITED`: 0.7695 (n=2)
- Spearman(occupancy, KS): ρ=-0.9071, p=5.87e-09

---

## Part 4 — Impact on existing results

### 4a — D1 per-node ablation

- Near-zero ablations (Δ<0.01, excl. ipc_intents): **21** nodes
- Of those, non-PRODUCIBLE: **4** → ['sms', 'clipboard', 'dynamic_code_loading', 'telephony']
- ipc_intents drop 0.209 is on a PRODUCIBLE coordinate (real signal).
- network Δ=0.0025 and remaining near-zero drops on PRODUCIBLE coords are measured, not structurally guaranteed (4 structural no-ops).

### 4b — D-2 ladder restricted to PRODUCIBLE

| coords | FISHER floor | HC α₀=1 floor |
|--------|--------------|---------------|
| 22 (ref) | 0.649796 | 0.501489 |
| 18 PRODUCIBLE | 0.673050 | 0.647059 |
| D1 L2 ref | 0.800426 | — |

### 4c — D1 L2 restricted

- Full 22: **0.800426**
- PRODUCIBLE-only: **0.800421**
- Δ: -0.000004

### 4d — E0/E2 self-reference d vectors

- Non-PRODUCIBLE categories (excluded from mask): **4** — clipboard, dynamic_code_loading, sms, telephony
- E0 PREFIX SCALAR MAX node: ref 0.6997 → restricted 0.699796
- E2 NODE_STD MAX node: ref 0.7124 → restricted 0.712829

---

## Part 5 — Proposed text changes (not applied)

### 5a — `thesis/chapter_a/A4_method.tex` (~59-61)

**Before:**
```
Because the node set does not depend on the app, graphs are directly comparable
and can be stacked as tensors of constant shape. Inactive categories remain as
zero-feature, zero-degree nodes rather than being dropped.
```

**After:**
```
Because the node set does not depend on the app, graphs are directly comparable
and can be stacked as tensors of constant shape. Inactive categories remain as
zero-feature, zero-degree nodes rather than being dropped. Comparability across
a structurally unobservable coordinate is vacuous: on AndroCT only 18 of
22 categories are environment-producible under the Monkey protocol; the remainder
are permission-gated or stimulus-limited (\S\ref{sec:observability-audit}).
```

### 5b — `thesis/chapter_a/A10_threats.tex` (after §a10-corpus (~65))

**Before:**
```
(no observability threat entry)
```

**After:**
```
\paragraph{Observability and ambiguous zeros.}
A zero coordinate conflates ``the app did not perform this behaviour'' with
``the environment could not produce observable events for this category.'' The
schema does not distinguish them. AndroCT effective universe: 18/22
PRODUCIBLE; v2\_extended: 15/22. D-2 KS uniformity cross-check:
PARTIAL (\S\ref{sec:observability-audit}).
```

### 5c — `thesis/chapter_b/B3_corpus.tex or B4_comparison.tex` (new threat subsection)

**Before:**
```
(v2 AVD described without effective-universe size)
```

**After:**
```
The v2 AVD has no cellular radio and no SIM; telephony/SMS-class events are
not physically producible. Combined with the planner action frozenset, seven
categories never fire (0/59 apps); effective PRODUCIBLE universe: 15/22.
Occupancy table: \texttt{results/observability\_v2\_extended.csv}.
```

### 5d — `thesis/chapter_a/A6_results.tex` (~627-629)

**Before:**
```
support novelty is granularity-dependent and at chance where every category is
always in vocabulary.
```

**After:**
```
support novelty is granularity-dependent and at chance where every category is
always in vocabulary. The converse also holds: readouts that require a
well-conditioned per-coordinate null fail when some nodes are structurally empty
(permission-gated or hardware-absent), because zeros encode instrumentation
artifacts as well as behaviour.
```

### 5e — `results/D2_higher_criticism.md or future A6_selfref subsection` (§1c uniformity paragraph)

**Before:**
```
Worst departures from uniformity: sms KS=0.936, clipboard KS=0.851 ...
```

**After:**
```
Uniformity failures on sparse coordinates (sms, clipboard, telephony) track
non-producibility under the Monkey emulator protocol, not merely low benign
base rate: KS ranks align with PERMISSION_GATED and STIMULUS_LIMITED buckets
(verdict PARTIAL).
```

### 5f — `thesis/chapter_a/A8_discussion.tex (future work)` (new bullet)

**Before:**
```
(no observability mask)
```

**After:**
```
Future work: per-corpus observability mask $\mathcal{O}_c \subseteq \mathcal{U}$
so that $x_j=0$ when $j\notin \mathcal{O}_c$ is tagged instrumentation-unavailable
rather than behavioural absence. The current ABRG schema has no field for this.
```
