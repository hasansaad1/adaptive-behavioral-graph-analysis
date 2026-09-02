# ContextDroid — sourced specification (thesis Chapter B)

**Document type:** extraction from code and artefacts. Not analysis, not recommendations.

**Written at:** `adaptive-behavioral-graph-analysis/docs/contextdroid_spec.md`  
**Hook inventory:** `adaptive-behavioral-graph-analysis/docs/contextdroid_hooks.csv`  
**Code/artefact source:** sibling repo `$CONTEXTDROID_ROOT (sibling ContextDroid repository)` (cited as `ContextDroid/…` below). ABRG artefacts under `datasets/` and `abrg/output/v2_chapter_b/` are cited where they record what v2 collection produced.

**Date of extraction:** 2026-08-17. **No new collection runs. No pipeline files modified.** File hashes below are of the working-tree files at extraction time.

**Three states used throughout**

| Label | Meaning |
|-------|---------|
| **implemented and exercised** | Code exists and ran on the v2 collection path (original July bulk and/or August extend). |
| **implemented but not exercised** | Code exists; v2 launch/env/export does not use it, or the corpus never produced the corresponding events. |
| **designed but not implemented** | Appears in plan/docs only, or a doc freezes a constant that runtime does not use. |

Where a plan document and the code disagree, both are quoted and labelled **doc-intent** vs **code-behaviour**.

---

## Citation conventions

- `file:function` or `file:line` refer to ContextDroid unless prefixed with `ABRG/`.
- v2 “exercised” for corpus-wide hook fire/non-fire is taken from `ABRG/abrg/output/v2_chapter_b/SUMMARY.md` (388 indexed sessions; fire set computed on usable traces as recorded there). Original-168 identity fields are from `ContextDroid/abrg/output/v2_extend/identity_check/REPORT.md`.
- `UNDETERMINED` names the search that failed.

---

## 1 — Purpose and design rationale

### 1.1 Problem statement in the project’s own words

**README (current working tree)** — `ContextDroid/README.md:1-4`:

> This repository contains a reproducible dynamic-analysis pipeline for Android APKs.  
> It installs apps on an emulator, runs deterministic + monkey-driven interaction, captures Frida and strace telemetry, and emits dataset-ready CSV/JSON artifacts.

**README scope (what it claims to include / exclude)** — `ContextDroid/README.md:6-16`:

> Included: Dynamic behavior extraction code; Frida hooks; Manifest-based benign APK download workflow; Reproducibility metadata outputs.  
> Not included: APK binaries; Private/internal datasets; Credentials/secrets.

**Methodology (doc-intent, still monkey-worded)** — `ContextDroid/docs/methodology.md:3-7,10-16`:

> This repository contains only the dynamic dataset-production pipeline for Android APK behavior capture. It intentionally excludes static feature extraction, graph-building stages, and private/internal assets.  
> Protocol constants frozen for the LLM-first methodology are documented in `docs/protocol_constants.md`.  
> High-Level Procedure step 4: “Run deterministic stimulation followed by monkey-driven UI events.”

**README also names an LLM path** — `ContextDroid/README.md:62-67`:

> LLM-only mode (Phase 1 primary path):  
> `ARM_MODE=llm OLLAMA_MODEL=llama3.2 … run_dynamic_dataset.sh … 120`

**Disagreement (doc-intent vs v2 code-behaviour):** README opening sentence and `docs/methodology.md` step 4 still describe monkey-driven interaction. v2 collection invoked `--arm llm` (`ContextDroid/extraction_pipeline/bulk_apk_sessions.sh:175`) with duration 420 s (`ContextDroid/extraction_pipeline/run_bulk_llm_benign_v2.sh:7`, metadata `duration_sec=420` in identity_check `REPORT.md`). Monkey remains a **pre-simulation warmup** inside `_run_pre_simulation_setup` (`analyze_apk.py:1158-1180`), not the timed stimulation arm.

### 1.2 What it was built to replace or improve on

**Doc-intent (protocol freeze):** `ContextDroid/docs/protocol_constants.md:13-18`:

> `llm_only`: primary mode; runs only the LLM stimulation arm.  
> `llm_plus_monkey`: optional mode; runs LLM plus Monkey baseline.  
> Comparison analysis is optional and post-collection.

**Code-behaviour (v2):** bulk scripts set `--arm llm` only. `ENABLE_COMPARISON` / `llm_plus_monkey` exist on `run_dynamic_dataset.sh` (`README.md:69-73`) — **implemented but not exercised** for v2.

**Stated reasoning for LLM-first (protocol doc):** `ContextDroid/docs/protocol_constants.md:7` titles the freeze “LLM-first methodology”. The same file still freezes session duration **120 s** (`protocol_constants.md:22`), which v2 did not use (see §5).

**Remediation plan (doc-intent, collector quality, not Monkey replacement):** `ContextDroid/docs/remediation_plan.md:4-13` states the governing principle *“Instrument before you fix. Fix before you multiply”* and attributes three incidents to “optimizing something no metric could see” (`advance_goal` success on engine skips; `direct_action_ratio` blind to explore; candidate emptiness hidden behind `interactive_element_count`).

### 1.3 Recorded design decisions, including reversals

**No `DECISION_LOG` in ContextDroid.** Searched `ContextDroid/**/DECISION_LOG*` — 0 files. ABRG `DECISION_LOG.md` records ABRG experiment campaigns, not ContextDroid collector design.

**Git history in this ContextDroid clone:** `git log --oneline` returns a single commit `4d2cdb1 Split llm_agent monolith into package and harden refactor wiring.` Reversed decisions are therefore taken from docs vs code, not from a multi-commit history. **UNDETERMINED** as git-blame narrative.

| Decision | Doc-intent | Code-behaviour | v2 |
|----------|------------|----------------|----|
| Timed duration 120 s | `protocol_constants.md:22`; `protocol_config.py:21` `SESSION_DURATION_SEC = 120` | CLI `--duration` default 180 (`analyze_apk.py:1782`); v2 wrapper default 420 (`run_bulk_llm_benign_v2.sh:7`) | **exercised 420 s** |
| `protocol_config.py` is config-only | File docstring `protocol_config.py:1-5` | Several constants **are** imported into the agent (`llm_agent/config.py:18-31` imports `LLM_TEMPERATURE`, `SESSION_TIMEOUT_MULTIPLIER`, `ACTION_HISTORY_WINDOW`, …) | mixed: temperature 0.0 and 3× wall timeout **exercised**; 120 s duration **not** |
| Snapshot restore every session | fairness protocol “Cold start” (`protocol_constants.md:25`) | `_restore_snapshot` (`analyze_apk.py:835-855`); v2 extend `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` (`launch.sh:15`). If skip is set and `sys.boot_completed==1`, function **returns True without loading a snapshot** (`analyze_apk.py:838-842`). Identity report still records `snapshot_restored=true` (`identity_check/REPORT.md:69`) | metadata flag ≠ snapshot load |
| Dedicated explore **scroll** action | Step 6 plan (`docs/remediation_plan.md` scroll residual; `docs/step6_part_a_scroll_residual.md`) | Step 6 PART A **defers scroll** (`step6_part_a_scroll_residual.md:16`: “Recommendation: defer Step 6 scroll”). Planner action space includes `swipe`, not `scroll` (`config.py:300`) | swipe **exercised**; dedicated `scroll` **not implemented** as planner type |
| Flailing rules merged | Step 0 plan (`remediation_plan.md:30-56`) | `quality_rules.detect_suspect_flailing` exists and is imported by v2 `curate_v2_reference.py` / `run_round_robin.reference_gate_for_dir` | **implemented and exercised** as the reference-tier flail gate |
| Explore candidate logging | Step 1 INSTRUMENT (`remediation_plan.md:77+`) | `session.py` writes `explore_candidate_counts` on BFS explore steps (`session.py:1014-1049`) | **implemented and exercised** (present in packaged `*_llm_actions.jsonl`) |
| Nav-first pipeline | env `CONTEXTDROID_LLM_NAV_FIRST_PIPELINE` default True (`config.py:128-129`) | Explore is **deterministic BFS**, not LLM (`session.py:1027-1031` `prompt_hash="bfs_navigation_phase"`) | **implemented and exercised** |
| Host Frida vs Docker | README: Docker optional “recommended on macOS” (`README.md:38`) | v2 `FRIDA_USE_DOCKER=0` (`collection_v2.env:14`); metadata `frida_mode=host` (`identity_check/REPORT.md:70`) | host **exercised**; Docker **not exercised** for v2 |
| Network sink / malware AVD | `SAFETY.md`, `docs/malware_corpus_safety_plan.md` | v2 launch does not start sink (`launch.sh` has no `network_sink.sh`; Chapter B `SAFETY.md`) | **implemented but not exercised** for v2 |

### 1.4 Scope boundaries the project set for itself

From `README.md:6-16` and `docs/methodology.md:3-5` (doc-intent, still current):

- **Does:** dynamic capture (install, stimulate, Frida, strace, metadata, index).
- **Does not (stated):** static feature extraction; graph-building stages; shipping APK binaries; private datasets; credentials.

From `docs/methodology.md:36-38` (doc-intent): malware only in isolated environments; legal rights for redistribution.

From ABRG graph pipeline (downstream, not ContextDroid): graph construction lives in ABRG (`abrg/registry.py`, `abrg.androct.graph_build`). ContextDroid `evaluate_corpus.py` evaluates “behavioral-graph readiness” but does not build the ABRG GAE graphs.

---

## 2 — Pipeline architecture

### 2.1 End-to-end stages (APK → trace)

**Entry (v2 original):** `ContextDroid/extraction_pipeline/run_bulk_llm_benign_v2.sh` sources `collection_v2.env` and execs `run_bulk_llm_dataset_resumable.sh` with APK root and duration (`run_bulk_llm_benign_v2.sh:20-22`).

**Entry (v2 extend):** `ContextDroid/abrg/output/v2_extend/collection/launch.sh` → `run_round_robin.py`.

**Per-APK analysis entry:** `extraction_pipeline/analyze_apk.py:analyze_apk` (`analyze_apk.py:1221`).

| Stage | Module | v2 |
|-------|--------|----|
| Env / AVD name / Frida docker off / explore floor | `collection_v2.env` | **exercised** |
| Optional emulator ensure | `ensure_emulator.sh` (called from bulk wrappers; not re-read here line-by-line) | original/extend launch set `AVD_NAME=abrg_benign` |
| Device identity | `safety/device_guard.py:assert_device_identity_hard` called from `analyze_apk.py:1337-1343` | **exercised** (failure would be `failed_device_guard`; 0 such in Chapter B exit census) |
| Snapshot / skip-load | `analyze_apk.py:_restore_snapshot` | skip-load **exercised** on extend (`launch.sh:15`); original metadata `snapshot_restored=true` with skip-on-already-booted possible (`identity_check/REPORT.md:69`) |
| Isolate other packages | `llm_agent/device.py:isolate_emulator_state` (`analyze_apk.py:1331-1336`) | **exercised** unless `CONTEXTDROID_ISOLATE_EMULATOR` disabled (default on) |
| Install APK | `adb install -r` (`analyze_apk.py:1344`) | **exercised** |
| `pm clear` | `adb shell pm clear` (`analyze_apk.py:1349-1352`) | **exercised**; original 168 `pm_clear_rc=0` |
| Launch + stability | `ensure_app_running` (`analyze_apk.py:1355`) | **exercised** |
| App context (LLM) | `build_app_context` (`analyze_apk.py:1361`) | **exercised** (LLM arm) |
| Pre-simulation setup | `_run_pre_simulation_setup` (`analyze_apk.py:1133`, called `1361-1364`) | **exercised** when `arm==llm` or `fairness_protocol` |
| Re-launch before Frida | `force_launch_activity` (`analyze_apk.py:1369`) | **exercised** |
| Frida attach | `attach_frida_or_fail` (`analyze_apk.py:1372`) | **exercised** |
| Optional strace | `analyze_apk.py:1392-1418` | implemented; skip recorded in metadata `strace_enabled` / `strace_skip_reason` |
| Timed stimulation | `run_llm_agent_session` (`llm_agent/session.py:142`, called `analyze_apk.py:1587`) | **exercised** (LLM arm) |
| Frida health/reattach during session | `_frida_healthcheck_and_reattach` (`analyze_apk.py:1518`) as `healthcheck_cb` | **exercised**; 2 sessions `failed_frida_reattach` (Chapter B SUMMARY) |
| Uninstall + write metadata | `analyze_apk.py:1673`, `1692+` | **exercised** |
| Reference-tier gate (post) | `experiments/datasets/curate_v2_reference.py:_reference_gate`; extend `run_round_robin.py:reference_gate_for_dir` | **exercised** |
| Export to ABRG | `ContextDroid/export/v2_extended/_build_export.py` copies Frida JSONL + metadata only | **exercised** |

**Monkey arm** (`arm==monkey`): implemented in `analyze_apk.py` (monkey process paths exist in the same function). v2 bulk uses `--arm llm` — **implemented but not exercised** as the timed arm.

### 2.2 One session, control flow (LLM arm, names)

1. `analyze_apk` (`analyze_apk.py:1221`) — create `*_frida.jsonl`, `*_monkey.log`, `*_strace.log`, `*_dynamic_metadata.json`.
2. `_ensure_ollama_server` if `arm==llm` (`analyze_apk.py:1318-1319`).
3. `_restore_snapshot` (`835`) if llm or fairness.
4. `ensure_frida_server_running` (`1325`).
5. `isolate_emulator_state` (`device.py:70`) if isolate env not disabled.
6. `assert_device_identity_hard` (`device_guard.py:239`).
7. `adb install -r` (`1344`); `adb shell pm clear` (`1349`).
8. `ensure_app_running` (`1355`).
9. `build_app_context`; `_run_pre_simulation_setup` (`1133`): `_grant_declared_permissions` (`1122`) → `_resolve_setup_dialogs` → warmup `monkey` (`1158`) → dialogs again → `uiautomator dump` verified start XML (`1186`).
10. `force_launch_activity` (`1369`).
11. `attach_frida_or_fail` (`467`) → `_start_frida_process` (`767`) → `wait_for_frida_attach` (`429`) until `hook_loaded`.
12. `start_device_count_watchdog` (`analyze_apk.py:1581`).
13. `run_llm_agent_session` (`session.py:142`):
    - Ollama `/api/show` for model info (`session.py:192-215`).
    - Optional `_plan_ux_goals` if `_USE_GOAL_PLAN` and not nav-first (`226-233`).
    - Loop (`session.py:330`): elapsed vs `duration_sec`; wall vs `max_runtime`.
    - Each iteration: `dump_clean_screen` (`screen.py:195`); explore vs execute vs primary_ux.
    - Explore (nav-first): `choose_explore_action` (`explore_policy.py:466`) — **no LLM**.
    - Execute/primary: `_build_prompt` / `_build_primary_ux_prompt` (`prompts.py:274`, `454`) → `_ollama_generate_with_retries` (`planner.py:58`) → `_parse_actions_list` (`planner.py:256`) → `_execute_action` (`actions.py:758`).
    - Write `{package}_llm_actions.jsonl`.
14. `finally`: terminate frida/strace/monkey; `adb pull` strace; `adb uninstall` (`analyze_apk.py:1673`); write metadata (`1692+`).

### 2.3 Artefacts: where written, format

Written under the per-session `output_dir` by `analyze_apk` / `run_llm_agent_session`:

| Artefact | Path pattern | Format | v2 export? |
|----------|--------------|--------|------------|
| Raw Frida trace | `{pkg}_frida.jsonl` | JSONL: `type`, `timestamp`, `api`, `category`, `args` (`hook_apis.js:21-28`) | yes → `events.jsonl` (`_build_export.py:299`) |
| Dynamic metadata | `{pkg}_dynamic_metadata.json` | JSON (`analyze_apk.py:1692+`) | yes → `metadata.json` (subset/reshape) |
| LLM actions | `{pkg}_llm_actions.jsonl` | JSONL (`session.py:152`, `1024-1063`, `1754-1798`) | **no** (`_build_export.py` copies only Frida + metadata) |
| UX plan | `{pkg}_llm_ux_plan.json` | JSON | no |
| Navigation artifact | `{pkg}_llm_navigation.json` (written `session.py:1926-1933`) | JSON | no |
| Human UX report | `{pkg}_human_ux_report.json` (`session.py:1935`) | JSON | no |
| Audit / step trace | paths in `llm_session_info` (`analyze_apk.py:1272-1284`) | JSONL if enabled | no |
| Guard timing | `{pkg}_guard_timing.jsonl` (`analyze_apk.py:1317`) | JSONL | no |
| Verified start dump | `{pkg}_verified_start.xml` (`analyze_apk.py:1192`) | XML | no |
| Monkey log | `{pkg}_monkey.log` | text (warmup / unused timed monkey) | no |
| strace | `{pkg}_strace.log` pulled from `/data/local/tmp/strace_{pkg}.log` | text | no |

Collection trees: `ContextDroid/logs/bulk_llm_benign_v2/` (original), `ContextDroid/logs/v2_extend_collection/` (extend). `ContextDroid/.gitignore:31` ignores `logs/` (except ledger). Packaged original actions also exist in `ABRG/datasets/v2/sessions/*/*_llm_actions.jsonl`.

### 2.4 Optional / configurable stages and v2 selection

| Knob | Default in code | v2 selection |
|------|-----------------|--------------|
| `--arm` | parser; `DEFAULT_ARM="unknown"` in `protocol_config.py:59` then coerced | **llm** (`bulk_apk_sessions.sh:175`) |
| `--duration` | 180 (`analyze_apk.py:1782`) | **420** (`run_bulk_llm_benign_v2.sh:7`) |
| `--strict-clean-start` / `--fairness-protocol` | flags on bulk (`bulk_apk_sessions.sh:180-181`) | **on** |
| `FRIDA_USE_DOCKER` | README recommends Docker | **0** (`collection_v2.env:14`) |
| `CONTEXTDROID_SKIP_SNAPSHOT_LOAD` | unset → try `emu avd snapshot load default_boot` (`analyze_apk.py:846`) | extend **1** (`launch.sh:15`); original logs also show skip when already booted (`identity_check/REPORT.md:69`) |
| `SESSIONS_PER_APP` | 3 (`collection_v2.env:10`) | **3** |
| `SESSION_MODE_SCHEDULE` | `identical,identical,varied` (`collection_v2.env:11`) | **exercised** |
| `CONTEXTDROID_LLM_EXPLORE_UNTIL_SEC_FLOOR` | 120 (`collection_v2.env:21`) | **120** |
| `CONTEXTDROID_LLM_EXPLORE_RATIO` | env 0.35 vs code default 0.30 (`config.py:130` vs `collection_v2.env:22`) | **0.35** |
| `CONTEXTDROID_LLM_EXECUTE_ENGINE_ONLY` | 0 (`collection_v2.env:17`) | **0** (LLM execute path enabled; engine routes still appear in logs) |
| `CONTEXTDROID_LLM_NAV_FIRST_PIPELINE` | default True (`config.py:129`) | **exercised** (BFS explore hashes in jsonl) |
| Network sink / `avd_session.sh` | malware-tier | **not** on v2 launch path |
| Timed Monkey arm | implemented | **not** v2 |

---

## 3 — Instrumentation

### 3.1 Hook script identity

| Field | Value | Source |
|-------|-------|--------|
| Path | `ContextDroid/frida_scripts/hook_apis.js` | `analyze_apk.py:1242` |
| SHA256 (working tree, matches original 168) | `3192c7d6f618bb455588a7db7b26b20ccb9028af22cf1d8d8f0db99c28009ffc` | `file_sha256` written to metadata (`analyze_apk.py:1712`); identity_check `REPORT.md:43`; re-hashed 2026-08-17 |
| Line count | 856 | `wc`/read; identity_check `REPORT.md:44` |
| Version tag | `"3"` in `logEvent("hook_loaded", … version: "3")` | `hook_apis.js:50` |
| Git blob during July collection | **UNDETERMINED** | identity_check: file untracked; `git ls-files` empty for this path (`REPORT.md:45`) |

### 3.2 Full hook inventory

Table: `docs/contextdroid_hooks.csv` (63 rows).

- Distinct API **names** emitted: **62**. Direct `logEvent("…")` string literals in `hook_apis.js` = **58** (identity_check `REPORT.md:47` uses this count). Four further names are passed through `logContentUriEvent` (`hook_apis.js:234-239`) and then `logEvent(api, "content_access", …)`: `ContentResolver.query`, `.insert`, `.update`, `.delete`. Those four **did fire** in v2 (`SUMMARY.md` fired list).
- Extra CSV row: `Context.startActivity` is logged twice with categories `ipc_intents` and `navigation` (`hook_apis.js:696-697`).
- Overloads that share an API name (`ContentResolver.query` bundle+legacy, `TelephonyManager.getCallState`, `MediaPlayer.setDataSource`, `NotificationManager.notify`, `Context.sendBroadcast`) are one inventory name.

Fire/non-fire: `ABRG/abrg/output/v2_chapter_b/SUMMARY.md:132-134` (reports `hooked_set_n=58` from the literal-`logEvent` set; fired 40 + never 22 on the corpus API set including ContentResolver). CSV `fired_in_v2_corpus` follows the SUMMARY fired/never lists plus ContentResolver as fired.

### 3.3 Category taxonomy vs 22-node graph universe

**Hook layer (25)** — `hook_apis.js` categories; listed as `CATEGORY_UNIVERSE` in `evaluate_corpus.py:18-44` and `ABRG/abrg/registry.py:6-32`:

`accounts, audio, camera, clipboard, content_access, crypto, database, device_info, dynamic_code_loading, file_io, ipc_intents, lifecycle, location, media, native_code, navigation, network, notifications, package_manager, process, reflection, sms, storage, telephony, webview`.

**Graph nodes (22)** — `ABRG/abrg/registry.py:35-58` `GRAPH_CATEGORY_UNIVERSE`; same drop set `NON_GRAPH_HOOK_CATEGORIES` (`registry.py:61-65`): `lifecycle`, `reflection`, `navigation`.

**Present in hooks, absent from graph nodes:** `lifecycle`, `reflection`, `navigation`.  
**Present in graph, absent from hooks:** none (assert `registry.py:_assert_category_universes`).  
**Logged twice:** `Context.startActivity` → `ipc_intents` (kept) and `navigation` (dropped from graphs) (`hook_apis.js:696-697`).  
**Framework APIs excluded from “meaningful 22cat”:** `hook_loaded`, `Method.invoke` (`curate_v2_reference.py` `FRAMEWORK_APIS` via `_count_meaningful_22cat:136-149`; `evaluate_corpus.py:46-49`).

Legacy label `contacts` is listed in ABRG `DROPPED_CATEGORIES` (`registry.py:68-71`) as mapping to `content_access` in v3 — **not** a current `logEvent` category in `hook_apis.js`.

### 3.4 Per-event fields (hook layer)

`logEvent` (`hook_apis.js:21-28`):

| Field | Type (JS) | Notes |
|-------|-----------|--------|
| `type` | string | `"event"` |
| `timestamp` | number | `Date.now()` (ms) |
| `api` | string | hook name |
| `category` | string | taxonomy above |
| `args` | object | per-hook; `{}` if omitted |

`logStatus` (`hook_apis.js:11-18`): `type="status"`, `timestamp`, `status`, `name`, `message`.

`safeHook` swallows install errors (comment at `hook_apis.js:7`: “Intentionally swallow to avoid breaking app flow”).

### 3.5 Timestamps

- **Hook events:** `Date.now()` in the Frida JS runtime (`hook_apis.js:14,24`) — milliseconds since Unix epoch as implemented by the JS engine on device/client; resolution **milliseconds**.
- **LLM action log:** `ts_epoch_ms: int(time.time() * 1000)` (`session.py:1026`, `1756`) — host Python wall clock, ms.
- **Session metadata:** `started_at_epoch_ms` (`analyze_apk.py:1697`).

Clock domain for Frida vs host action log is **not synchronized in code**. **UNDETERMINED** whether Frida `Date.now()` is device or Frida-client JS; searched `hook_apis.js` and `analyze_apk.py` `_start_frida_process` — no extra timestamp injection on the JSON the script emits.

### 3.6 Frida attach

**Mode:** attach, not spawn, unless `spawn_attach=True` (`attach_frida_or_fail:482`, `504-505`). Default modes `_frida_attach_modes`: `("pid", "name")` (`analyze_apk.py:761-764`). Spawn is `-f package` (`784-787`) — **implemented but not exercised** on the default `analyze_apk` call (`1372` does not pass `spawn_attach=True`).

**Host client (v2):** `frida -U … -l hook_apis.js -q -t <cli_timeout>` (`analyze_apk.py:816-831`). Docker path `should_use_docker_frida()` (`793-813`) — **not v2**.

**Success criterion:** `wait_for_frida_attach` (`429`) until log slice indicates attach (`hook_loaded`) or timeout (`FRIDA_ATTACH_TIMEOUT_SEC` default 12 host / 20 docker, `486`) or process exit.

**Retry:** `FRIDA_ATTACH_ATTEMPTS` default 3 (`488`); on retry, `ensure_frida_server_running(..., force_restart=True)` (`500`). Failure raises `AnalysisFailure("failed_frida_attach", …)` (`560`).

**Mid-session:** `_frida_healthcheck_and_reattach` (`1518-1568`) calls `_frida_perform_reattach` on liveness failure. v2 env `FRIDA_EVENTS_STALE_SEC=30`, `FRIDA_ATTACH_GRACE_SEC=30` (`collection_v2.env:27-28`). Chapter B: 2 sessions `analysis_exit_code=12` `failed_frida_reattach`.

**Early instrumentation:** spawn (`-f`) would start before `onCreate`; default is attach to already-running PID after `ensure_app_running` — **not** early-spawn for v2.

### 3.7 Deliberate non-capture

From code (not inferred from “typical Frida practice”):

- `emitJson` / `safeHook` swallow exceptions so hooks do not crash the app (`hook_apis.js:3-8`).
- Graph pipeline later drops `lifecycle` / `reflection` / `navigation` and framework APIs (ABRG `registry.py:61-71`; curation `_count_meaningful_22cat`).
- No screenshot / `screencap` in `llm_agent/` (searched `screencap|screenshot` — 0 hits). UI observation is uiautomator XML only (`screen.py:dump_clean_screen`).
- Hook `args` are summaries (paths, URIs, algorithms), not full payloads (e.g. `Cipher.doFinal` logs algorithm/size-style fields at `hook_apis.js:494-497` — not ciphertext dumps beyond what that hook writes).

**UNDETERMINED:** a written policy of “we do not hook X because privacy” — searched `hook_apis.js` comments and `docs/methodology.md`; no such list beyond swallow-on-error.

---

## 4 — Exploration policy

This is the stimulation contribution. v2 uses **nav-first**: explore is a deterministic policy; execute/primary_ux may call the LLM.

### 4.1 Planner runtime

| Item | Value | Source | v2 |
|------|-------|--------|----|
| Runtime | Ollama HTTP `POST {endpoint}/api/generate` | `planner.py:_ollama_generate:40-56` | **exercised** |
| Body | `model`, `prompt`, `stream: False`, `options` | same | |
| Options | `{temperature: _LLM_TEMPERATURE_RUNTIME}` plus optional `seed` if `CONTEXTDROID_LLM_AGENT_SEED` parses as int | `config.py:_ollama_generate_options:135-142` | temperature **0.0** in original jsonl (`identity_check/REPORT.md:60`); seed when identical sessions set agent_seed |
| Temperature default | `LLM_TEMPERATURE = 0.0` (`protocol_config.py:35`); overridable `CONTEXTDROID_LLM_TEMPERATURE` (`config.py:67`) | | **0.0 exercised** |
| Model name | CLI/`OLLAMA_MODEL`; metadata `planner_model=llama3.2` | identity_check `REPORT.md:58` | **llama3.2** |
| Model digest | **UNRECOVERABLE** | `/api/show` stored as `planner_model_info: {"model":"llama3.2"}` when `_SLIM_ACTION_LOG` (`session.py:1760-1763`); identity_check `REPORT.md:59` | |
| Decode params besides temperature/seed | none in `_ollama_generate_options` | | |
| Timeout | `_OLLAMA_GENERATE_TIMEOUT_SEC` | `planner.py:53` | |
| Retries | `OLLAMA_GENERATE_RETRIES` with exponential backoff (`planner.py:66-73`) | | |
| Where it runs | Host process of `analyze_apk` / agent, talking to `OLLAMA_ENDPOINT` (default documented `http://127.0.0.1:11434` in README) | | **exercised** |

Explore-phase steps with `prompt_hash="bfs_navigation_phase"` **do not call Ollama** (`session.py:1027-1031`).

### 4.2 Observation (what is shown)

**Construction:** `dump_clean_screen` (`screen.py:195-246`):

1. `adb shell uiautomator dump /sdcard/window_dump.xml`
2. `adb shell cat` that file
3. `_normalized_elements(raw_xml)` (`screen.py:53-71`): enabled + (clickable or long-clickable or focusable text-entry); fields `package, resource_id, content_desc, text, class_name, bounds, clickable`
4. `_token_trim_elements` (token budget)
5. `_screen_hash(elements)`

**Not shown:** screenshots (no `screencap` in `llm_agent/`).

**Inserted into LLM prompts** as `CLEAN_SCREEN_ELEMENTS` JSON (`prompts.py:269-270`, `423`, `501-502`), plus `APP_CONTEXT`, `RECENT_STEP_SUMMARY`, `RECENT_ACTIONS_JSON`, navigation digest / `APP_STATE` depending on phase.

**Rendered prompt is hashed, not stored in `*_llm_actions.jsonl`.** Hash: `hashlib.sha256(prompt.encode("utf-8")).hexdigest()` (`session.py:1223`). Field `"prompt"` is absent from packaged jsonl (checked `cl.coders.faketraveler` s1).

**Real example (original packaged session, not v2_extended export):**  
`ABRG/datasets/v2/sessions/fb32bae7e64d_llm_s1__cl.coders.faketraveler/cl.coders.faketraveler_llm_actions.jsonl`

- Step 1 (explore, BFS — planner not shown a prompt): `pipeline_phase=explore`, `prompt_hash=bfs_navigation_phase`, `interactive_element_count=13`, `screen_hash=1178cddcbeeb548f6370184ff4356c1862f5dc4a1f641781552edf78eee09c70`, `parsed_action={"action_type":"tap","target_resource_id":"cl.coders.faketraveler:id/button_settings","x":927,"y":331,"reason":"bfs_graph_uncovered_tab"}`, `app_state.screen_role=text_entry`, `explore_candidate_counts={nav_cands:2, other_cands:7, expand_cands:7, tab_cands:3, skipped_interactive:4}`.
- Step 34 (execute): `prompt_hash=3cbf94eca95ee0ff2dd76a3ee9b3b7d49272a28013964c8104288b8948ac9258`, `temperature=0.0`, `ux_goal_active="Tap button settings"`, `raw_response` begins `{"actions":[{"action_type":"tap",…,"reason":"engine_route_tap_goal_nav"}]}`. Full `CLEAN_SCREEN_ELEMENTS` array **not** in this jsonl row.

**UNDETERMINED:** exact `CLEAN_SCREEN_ELEMENTS` JSON for that step — would require a stored prompt or XML dump; `{pkg}_verified_start.xml` is pre-session only. Searched jsonl keys: no `elements` list on execute rows.

### 4.3 Action space

**Planner-allowed types** — `config.py:300`:

```text
_ACTION_TYPES_PLANNER = frozenset({"tap", "input", "back", "wait", "advance_goal", "swipe"})
```

Invalid types become `wait` with `reason=planner_contract_invalid_action_type` (`planner.py:200-229`).

**Execution** — `actions.py:_execute_action:758-825`:

| Type | Parameters | Device execution |
|------|------------|------------------|
| `advance_goal` | none required | **no device I/O**; returns `(True, "advance_goal")` (`760-761`) |
| `back` | none | `adb shell input keyevent 4` (`762-764`) |
| `input` | `text` required; optional `target_resource_id` / `target_content_desc` / `x,y`; `submit_search` | optional focus tap `_tap_from_action`; optional field clear; `adb shell input text <escaped>` (`765-799`); optional IME submit keyevents |
| `tap` | `target_resource_id` / `target_content_desc` / `x,y` | `_tap_from_action` → `adb shell input tap` |
| `swipe` | `x1,y1,x2,y2` (defaults 540,1650 → 540,750); optional `duration_ms` | `adb shell input swipe …` (`804-823`) |
| anything else (incl. missing type) | — | `time.sleep(0.5)` and success `"wait"` (`824-825`) |

**Judge-only types** (not in planner set): `evaluate_faithfulness.py:41` `INTERACTIVE_TYPES` includes `scroll, long_press, type, fill`. **designed/legacy in judge; not planner-emittable.**

**Not in `_ACTION_TYPES_PLANNER` (confirmed by the frozenset, not assumed):** `grant_permission`, `purchase`, `login`, `type_password`, `long_press`, `scroll` (as a named action), `keyevent` except via `back` and input-submit helpers.

Permission **pre-grant** is outside the planner: `pm grant` in `_grant_declared_permissions` (`analyze_apk.py:1122-1130`). Runtime permission UI packages are treated as foreign by default (`config.py:313-327` `_FOREGROUND_DIALOG_PACKAGES`), with explore `_dialog_policy_action` (`explore_policy.py:484`).

### 4.4 Prompt templates

**Path:** `ContextDroid/extraction_pipeline/llm_agent/prompts.py`  
**SHA256 (working tree 2026-08-17):** `379632c225f4316855b100db9ed43396950987a8e6276f69c81f6f2a435058ae`  
**Lines:** 504  

**July frozen file SHA:** **UNRECOVERABLE** (`identity_check/REPORT.md:61`). Observed per-step `prompt_hash` is SHA of the **rendered** string or the label `bfs_navigation_phase` (`REPORT.md:62`).

There is no separate `.txt` template file. Three builders:

#### Explore LLM template (`prompts.py:_build_explore_prompt:218-272`)

Used if explore called the LLM. Under nav-first v2, explore is BFS; this template is **implemented**; **UNDETERMINED** how often (if ever) v2 explore steps used it vs BFS (original jsonl `prompt_hash` modes: `bfs_navigation_phase` 6446 vs remaining SHA hashes — `identity_check/REPORT.md:62`).

Verbatim construction (`prompts.py:249-272`):

```
PHASE=APP_NAVIGATION (coverage first). Build a mental map of the app — maximize DISTINCT screens.
Return JSON ONLY: {"actions":[{...}, ...]} with 1–{batch_limit} actions per response. The runner executes ALL listed actions IN ORDER before asking you again — no LLM between them.
NAVIGATION_BAR_PRIORITY: Explore primary navigation thoroughly BEFORE unrelated scrolling.
- If NAVIGATION_TARGETS_DETECTED lists tabs/chips/bar items, spend MOST of each batch tapping distinct destinations there until each has been tried at least once across recent turns (breadth-first).
- After opening a destination from the nav strip, press BACK when stuck so you can return and tap the next nav target.
- Include drawer/menu opener taps when visible; open drawer once then tap each drawer destination.
- Horizontal tab strips at top count as navigation — cycle through tabs similarly.
[+ detected vs no-match extra bullet]
Also explore non-nav surfaces (lists, settings, FAB/search) AFTER nav breadth is progressing.
Each action uses fields action_type(tap|input|back|wait), target_resource_id, target_content_desc, x, y, text, submit_search, reason.
Avoid repeating ineffective taps (see RECENT_STEP_SUMMARY). Stay inside the app under test.
{stagnation fragment}
NAVIGATION_TARGETS_DETECTED:
{nav_targets}
DISCOVERED_SCREENS (hash → hints):
{navigation_digest_text}
APP_CONTEXT:
{json app_context}
RECENT_STEP_SUMMARY:
{summary}
RECENT_ACTIONS_JSON:
{json hist}
CLEAN_SCREEN_ELEMENTS:
{json elements}
```

Note: this explore template’s `action_type` list **omits `swipe` and `advance_goal`** (`prompts.py:255`), while `_ACTION_TYPES_PLANNER` includes them (`config.py:300`).

#### Execute / UX-goal template (`prompts.py:_build_prompt:274-424`)

When `ux_goals` is set (nav-first post-explore), rules include (`prompts.py:375-410`):

```
You are an Android UI agent.
Fields: action_type(tap|input|back|wait|advance_goal|swipe), target_resource_id, target_content_desc, x, y, text, reason, submit_search (optional bool).
swipe: x1,y1,x2,y2 (vertical list browse: y1 below y2 on screen), optional duration_ms.
… [input/ADB/search/ALLOWED_TARGET_RESOURCE_IDS / GOAL_STATUS rules] …
Stay inside the app under test; do not open browsers or external apps.
```

Plus `ACTIVE UX GOAL`, `APP_STATE`, `APP_CONTEXT`, `RECENT_*`, `CLEAN_SCREEN_ELEMENTS` (`412-423`). Full function text is `prompts.py:274-424`.

Non-goal branch (`prompts.py:425+`) lists `action_type(tap|input|back|wait)` without `swipe`/`advance_goal` in that sentence — **code**.

#### Primary UX template (`prompts.py:_build_primary_ux_prompt:454-504`)

```
PHASE=PRIMARY_APP_UX (remaining session time). Checklist goals are paused or finished — you already explored the app shell; now mimic typical sustained use (scroll/browse, revisit main tabs, short tasks).
Return JSON ONLY: {"actions":[{...}, ...]} with 1–{batch_limit} actions per response (executed in order).
PRIMARY_UX_MISSION (follow this closely):
{primary_mission}
PRIMARY_MICRO_INTENT (this turn's concrete user-like intent):
{json primary_micro_intent}
Actions: action_type one of tap|input|back|wait|swipe. Prefer swipe for scrolling feeds/lists.
swipe fields: x1,y1,x2,y2 pixel coordinates (portrait phone). …
Avoid advance_goal — there is no goal index here. …
{stagnation}
DISCOVERED_SCREENS / APP_CONTEXT / APP_STATE / RECENT_* / CLEAN_SCREEN_ELEMENTS
```

Additional planner prompt: `_plan_primary_app_ux` (`prompts.py:36-50`) for mission text; fallback `_DEFAULT_PRIMARY_UX_TEXT` (`config.py:234-237`).

### 4.5 Control loop

**Outer loop:** `session.py:330-336` — break when `elapsed >= duration_sec` or wall `>= max_runtime` (`duration_sec * SESSION_TIMEOUT_MULTIPLIER` default 3, `session.py:162`, `protocol_config.py:24`).

**Per step:** dump screen → choose phase (`exploring_phase = nav-first and elapsed < explore_until_sec`, `session.py:679`) → pick action (BFS `choose_explore_action` or LLM parse) → `_execute_action` → dump after (audit/settle) → append jsonl → `sleep(0.8)` (`session.py:1901`).

**Progress (code, not narrative):**

- Screen hash change (`last_hash` / `stagnant` in `session.py:157-158`).
- `_execution_counts_as_ux_progress` (`audit.py`, used in primary micro-intent `prompts.py:90-95`).
- Explore candidate buckets / nav graph in `ExploreState` (`session.py:238-240`).
- `advance_goal` increments goal index (engine).
- C0 gate later counts named functional explore taps / new functional explore hashes (`evaluate_faithfulness.py:217-221`).

**No-op / failed action:**

- Failed tap: `action_success=false`; `fallback_rid_missing` in `_tap_from_action` (`actions.py:749`).
- Unparseable LLM: `_planner_contract_failure` → `wait` + `planner_contract_*` (`planner.py:200-207`).
- Repetition guard: replace with `back` or `wait` `reason=repetition_guard` (`session.py:1534-1546`).
- Invisible target: replace with `wait` `planner_target_not_visible` (`session.py:1500-1503`).
- Empty execute: `advance_goal` `engine_empty_state_blocked_goal` (`session.py:1523-1526`).
- Consecutive Ollama failures: `partial:{PARTIAL_OLLAMA_UNAVAILABLE}` (`session.py:1903-1905`).

**Explore engine (v2 nav-first):** `explore_policy.py:choose_explore_action:466` — candidate buckets (nav / tab / expand / other) then recovery (`bfs_return_to_hub`, `bfs_avoid_back_loop`, `explore_policy.py:460-463`). Logged `execution_kind` / `explore_tier_index` / `explore_candidate_counts`.

### 4.6 Step budget, timeout, termination

- **No `max_steps` in metadata** (`identity_check/REPORT.md:63`). Observed original-168 steps/session median 52 (`REPORT.md:64`).
- **Duration:** CLI `duration_sec` (v2 420).
- **Wall timeout:** `3 × duration` unless `timeout_sec` passed (`session.py:162`).
- **Explore budget:** `_explore_until_seconds` (`config.py:240-262`): `min(duration*ratio, duration-reserve)` then floor `CONTEXTDROID_LLM_EXPLORE_UNTIL_SEC_FLOOR` (v2 120) capped by execute reserve (`max(90, 0.52*duration)` unless env). Return clamped to `[25, duration-30]`.
- **Handoff / quality statuses** that end or flag the session include `partial:timeout`, `partial:bad_handoff`, `partial:no_goal_progress`, `partial:ux_quality_gate`, `flag:webview_dominant` (written through `analyze_apk` / session status fields; Chapter B census `SUMMARY.md:255-259`).

### 4.7 Fallback / heuristic when planner fails

| Condition | Behaviour | Site |
|-----------|-----------|------|
| No JSON / bad types | `wait` + `planner_contract_*` | `planner.py:200-277` |
| Ollama exception after retries | counted in `ollama_fail_steps`; abort after `OLLAMA_DEAD_AFTER_CONSECUTIVE_STEPS` | `session.py:1903` |
| Primary UX parse failure | `_primary_ux_controller_action` if contract failure (`session.py:1548-1554`) | |
| Primary mission plan fail | `_DEFAULT_PRIMARY_UX_TEXT` | `prompts.py:53-55` |
| Explore | BFS engine, not LLM | `session.py:1027-1031` |
| Execute `CONTEXTDROID_LLM_EXECUTE_ENGINE_ONLY=1` | engine-only execute | env default **0** for v2 (`collection_v2.env:17`) — **implemented but not the v2 default** |

### 4.8 State tracked across steps

In `run_llm_agent_session` (`session.py:154-241` and loop): `actions` history; `stagnant` / `last_hash`; `exploration_digest`; `nav_visited_counts`; `nav_transitions`; `ExploreState` / `nav_graph`; `ux_goals` / `ux_goal_idx`; `goal_blocked_turns`; `root_screen_hash` / handoff; `seen_hashes` (audit); `failed_once`; `last_failed_signature`; primary-UX micro-intent; `bfs_expand_stall_by_screen`.

**Not persisted to the next session of the same app:** in-memory only. Next session is a new `analyze_apk` process after uninstall (see §5).

---

## 5 — Session protocol

### 5.1 Duration

| Item | Value | Source |
|------|-------|--------|
| Doc freeze | 120 s | `protocol_constants.md:22`; `protocol_config.py:21` — **designed (Phase 0); not v2** |
| CLI default | 180 s | `analyze_apk.py:1782` |
| v2 configured | 420 s | `run_bulk_llm_benign_v2.sh:7`; metadata `duration_sec` ×168 (`identity_check/REPORT.md:56`) |
| Enforcement | `elapsed = time.time() - simulation_started`; `if elapsed >= duration_sec: break` | `session.py:331-333`; inner `1412-1413` |
| Observed wall (includes setup) | original median `elapsed_sec` 460.721 | `identity_check/REPORT.md:57` |

Pre-simulation warmup is **outside** the timed LLM loop (runs before `run_llm_agent_session`).

### 5.2 Device state between sessions — actual call sequence

For each `analyze_apk` invocation (LLM + fairness), in order:

1. `_restore_snapshot` (`analyze_apk.py:1321`): either `emu avd snapshot load default_boot` (`846`) **or**, if `CONTEXTDROID_SKIP_SNAPSHOT_LOAD` in `{1,true,yes}` and `getprop sys.boot_completed == 1`, **return True without load** (`837-842`).
2. `ensure_frida_server_running(..., force_restart=snapshot_restored)` (`1325-1326`).
3. `isolate_emulator_state`: `input keyevent 3` (HOME), then `am force-stop` every third-party package except the target (`device.py:70-94`). Target package may not be installed yet.
4. `assert_device_identity_hard` (`1337`).
5. `adb install -r {apk}` (`1344`).
6. `adb shell pm clear {package}` (`1349`).
7. … session …
8. `adb uninstall {package}` (`1673`).

**Not in this sequence:** `emulator -wipe-data`. That flag is malware-tier (`avd_session.sh` / SAFETY docs) — **implemented but not exercised** for v2.

### 5.3 Independence vs continuation (explicit)

**Code that decides it:** `pm clear` after every install (`analyze_apk.py:1349-1352`) plus `uninstall` at end (`1673`) plus re-`install -r` on the next session. Fairness/strict-clean-start **fails** the session if `pm clear` rc ≠ 0 (`1351-1352`).

**Statement:** sessions of the same app are **independent samples of app-private data**, not continuations of SharedPreferences/DB/account state inside that package, **provided `pm clear` succeeded**. Original 168 record `pm_clear_rc=0` (`identity_check/REPORT.md:69`).

**What can persist across sessions (same AVD, no wipe-data):** emulator userdata, third-party packages not force-stopped if isolation skipped, accounts in the **device** account manager, SD card files **not** owned by the cleared package, and any state `pm clear` does not wipe. Isolation force-stops other third-party apps but does not uninstall them (`device.py:80-88`). **UNDETERMINED** from code whether Google accounts on the AVD persist (no `pm clear` on `com.google.android.gms` in this sequence). Searched `analyze_apk.py` / `isolate_emulator_state` for account wipe — none.

**`snapshot_restored=true` in metadata does not by itself prove a snapshot load** when skip-load returns True (`analyze_apk.py:838-842`).

### 5.4 Install / uninstall

- Install: `adb install -r` (`1344`); failure `failed_install`.
- Uninstall: `adb uninstall` in `finally` (`1673`), `check=False` (failure not fatal to metadata write).

### 5.5 Randomisation vs pins

| Item | Fixed or random | Source |
|------|-----------------|--------|
| Dataset / APK set | fixed manifests | collection config `collection_v2` |
| Duration 420, explore floor/ratio, host Frida | fixed | `collection_v2.env` |
| Planner temperature | 0.0 | jsonl / `LLM_TEMPERATURE` |
| Warmup monkey seed | `PRE_ONBOARDING_MONKEY_SEED = 42` | `protocol_config.py:29`; `_run_pre_simulation_setup` `-s 42` (`analyze_apk.py:1168`) |
| Warmup monkey events | 10 | `protocol_config.py:30`; `analyze_apk.py:1177` |
| `agent_seed` / `monkey_seed` | per session; schedule `identical,identical,varied` | metadata / `run_manifest.json` (`identity_check/REPORT.md:66`); identical sessions share seed |
| Ollama `options.seed` | set when `CONTEXTDROID_LLM_AGENT_SEED` is digit | `config.py:137-141` |
| BFS explore | deterministic given UI dump | `explore_policy.py` |
| LLM decode | temperature 0; other sampling params unset | `planner.py:48` |

---

## 6 — Quality gates

### 6.1 Reference-tier criteria (code that applies them)

Function `curate_v2_reference._reference_gate` (`experiments/datasets/curate_v2_reference.py:229-250`):

```text
analyze_ok
AND sim == "success"
AND faith in {FAITHFUL, PARTIAL}
AND c0_pass
AND meaningful_22 > 0
AND not flail
AND not auth_gated
AND not network_degraded
```

Same function imported by extend `run_round_robin.reference_gate_for_dir` (`run_round_robin.py:174-182`).

**Meanings:**

| Conjunct | Threshold / definition | Code |
|----------|------------------------|------|
| `analyze_ok` | index/metadata `analysis_status` success (extend also treats empty status + exit 0) | `run_round_robin.py:196-208`; curate loops `status==success` rows (`curate_v2_reference.py:259`) |
| `sim` | `llm_simulation_status == "success"` | metadata |
| `faith` | `evaluate_session` → `faithfulness` in `{FAITHFUL, PARTIAL}`; judge `JUDGE_VERSION = "faithfulness_v2_phase_aware"` (`evaluate_faithfulness.py:21`) | `curate_v2_reference.py:348-352` |
| `c0_pass` | C0 value `yes`: named functional explore taps ≥ **3** **OR** functional explore screen hashes ≥ **2** | `evaluate_faithfulness.py:44-45, 217-221` |
| `meaningful_22` | count of Frida events whose `category ∈ GRAPH_CATEGORY_UNIVERSE` and `api` not in `{hook_loaded, Method.invoke}` | `_count_meaningful_22cat:136-149` |
| `flail` | `quality_rules.detect_suspect_flailing` | `quality_rules.py:245-318` |
| `auth_gated` | `sim == "failed:skip:login_required"` | `curate_v2_reference.py:366` |
| `network_degraded` | keyword regex on action reasons | `_network_degraded`; `DEGRADED_RE` in `evaluate_faithfulness.py:27-29` |

**Flailing sub-reasons** (`quality_rules.py:245-318`):

| Reason prefix | Rule |
|---------------|------|
| `no agent actions recorded` / `no successful actions` | empty / all failed |
| `mechanical_majority` | ≥50% successful actions in `{back,wait,swipe,scroll}` and named functional taps < 3 (`MECHANICAL_MAJORITY_FRAC=0.50`, `MIN_PURPOSEFUL_NAMED=3`) |
| `explore_back_wait_dominant` | explore back/wait ratio > 0.50 and explore functional taps < 3 |
| `dominant_screen` | execute+primary hash dominance ≥ 0.80 and named < 3 |
| `same_element_cycle` | session hash dominance ≥ 0.80 **and** named ≥ 3 **and** top named target ≥ max(3, 75% of named) |
| `low_all_phase_direct_ratio` | `sim_status==success` and all-phase direct ratio < 0.40 |

Doc-intent restatement (same gates): `ContextDroid/experiment/v2_dataset_bundle/notes.md:30` (eight numbered conjuncts). **Doc vs code:** notes say C0 “≥3 named **effective** functional explore taps OR ≥2 new functional explore screen hashes” — code uses `_named_functional_explore_tap_count` / `_functional_explore_screen_hashes` (`evaluate_faithfulness.py:217-221`), not the word “effective” in the C0 predicate (effectiveness appears in explore instrumentation elsewhere).

### 6.2 What a session must satisfy to be in the **exported analysis set**

`export/v2_extended/README.md:32-34`: `sessions/` = original 168 reference-tier **plus** new slots that **passed** the same gates (342). Failed new slots go to `sessions_failed_reference/` (46). Original failures were not re-exported as fail-tier in that layout (original tree was already curated).

### 6.3 Failure reasons gates / pipeline can emit

**Reference-tier fail reasons (extend census, Chapter B `SUMMARY.md:251`):**  
`partial:bad_handoff` (14), `partial:ux_quality_gate` (12), `partial:no_goal_progress` (7), `webview_dominant` (6), `flailing:dominant_screen` (4), `failed_frida_reattach` (2), `flailing:same_element_cycle` (1).

**`analysis_status` values seen on 388 indexed sessions (`SUMMARY.md:259`):**  
`success` (344), `partial:bad_handoff` (14), `failed_frida_reattach` (2), `partial:no_goal_progress` (7), `partial:ux_quality_gate` (12), `flag:webview_dominant` (9).

**Other `AnalysisFailure` reasons in `analyze_apk.py` (implemented; not all seen in v2 census):** `failed_snapshot_restore`, `failed_install`, `failed_pm_clear`, `failed_app_unstable`, `failed_frida_server`, `failed_frida_attach`, `failed_foreground_mismatch`, `failed_device_guard` (`analyze_apk.py:1654-1656`).

**Faithfulness `HARD_FAIL_STATUSES`:** `failed:partial:agent_stuck`, `failed:skip:login_required` (`evaluate_faithfulness.py:35-38`).

### 6.4 Gate changes during the project

**Doc-intent (Step 0):** `_flailing_new` dropped `same_element_cycle` and `dominant_screen when named ≥ 3`, which would have **admitted** 12 flailing sessions (`remediation_plan.md:37-44`). Merge into `quality_rules.py` restored those rules (`quality_rules.py:291-311` comments cite `coolmicapp`).

**Code now:** single `detect_suspect_flailing` used by curation and `reference_gate_for_dir`.

**Before/after numeric relabel on old corpora (v129/v6)** is stated in the plan (`remediation_plan.md:44, 56-61`) as a **plan acceptance criterion**, not re-verified in this extraction. **UNDETERMINED** whether a leftover `_flailing_new` path still runs anywhere: searched `extraction_pipeline/quality_rules.py` as the cited single source; v2 gate imports that module.

**C0 added in faithfulness_v2_phase_aware** (`evaluate_faithfulness.py:21`, `_judge_c0:217`). Pre-phase-aware judge **UNDETERMINED** from this clone’s git history (single commit).

---

## 7 — Safety controls

### 7.1 Network containment

| Control | State | Evidence |
|---------|-------|----------|
| Host sink `network_sink.sh` / `network_sink_server.py` | **implemented but not exercised** for v2 | Files under `scripts/safety/`; v2 `run_bulk_llm_benign_v2.sh` and `launch.sh` do not invoke them (read `launch.sh:1-40`; Chapter B `SAFETY.md`) |
| Guest iptables `guest_sink_rules.sh` chain `ABRG_SINK` | **implemented but not exercised** for v2 | `guest_sink_rules.sh:163-178`; Gate P4 `gate_p4.sh:79` |
| DNS DNAT to host sink port | **implemented but not exercised** | `guest_sink_rules.sh:166-167` |
| `gate_p4.sh` | **implemented but not exercised** for v2 | malware preflight `malware_session_preflight.sh`; not in v2 launch |
| Host `pfctl` backstop | **designed but not implemented** as automation | `host_pf_backstop_sketch.sh`; ContextDroid `SAFETY.md` (Chapter B quotes “not automated”) |

v2 launch path (`launch.sh`): `AVD_NAME=abrg_benign`, `FRIDA_USE_DOCKER=0`, `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1`; kills `abrg_mw` if online (`launch.sh:27-36`); **does not start sink**.

### 7.2 AVD isolation

| Item | State | Evidence |
|------|-------|----------|
| Benign AVD name `abrg_benign` | **implemented and exercised** (extend/env); original AVD name **UNRECOVERABLE** from July metadata | `collection_v2.env:6`; `launch.sh:17`; identity_check `REPORT.md:50` |
| SDK 29 | **exercised** (log text) | `Device SDK level: 29` in `logs/bulk_llm_benign_v2/nohup.out` (`REPORT.md:51`) |
| System image hash / Google APIs vs AOSP | **UNRECOVERABLE** | `REPORT.md:52` |
| Snapshot load | skip-load **exercised** on extend; load path **implemented** | `analyze_apk.py:835-846`; `launch.sh:15,21-22` `EMULATOR_NO_SNAPSHOT_LOAD=1` `EMULATOR_SAVE_SNAPSHOT=0` |
| `-wipe-data` | **implemented but not exercised** (malware AVD session) | not in `analyze_apk` sequence |

### 7.3 Device guard

`assert_device_identity_hard` (`device_guard.py:239-268`): exactly one online adb device; optional serial match; `ro.kernel.qemu == 1`; optional AVD name match; optional `ro.build.fingerprint`.

Called in `analyze_apk.py:1337-1343` **before install**. Watchdog `start_device_count_watchdog` during LLM (`analyze_apk.py:1581-1584`); `raise_if_watchdog_failed` in the agent loop (`session.py:338`).

**Per-session recording:** failure sets `analysis_status=failed_device_guard` (`analyze_apk.py:1654-1656`). **Pass is not a dedicated metadata field.** Guard timing JSONL is written (`analyze_apk.py:1317`) but **not** copied into v2_extended export. Chapter B: no `failed_device_guard` in the 388-session status census.

### 7.4 Storage

- Collection traces: `logs/bulk_llm_benign_v2/`, `logs/v2_extend_collection/` — gitignored (`ContextDroid/.gitignore:31`).
- Packaged ABRG: `datasets/v2/`, `datasets/v2_extended/` (events + metadata).
- APKs: `ContextDroid/data/apks/benign` (not in ABRG export).
- Malware encrypted vault: **implemented but not exercised** for v2 (`SAFETY.md` / `network_sink.sh` require vault mount).

Whether those log paths sit outside synced directories / git worktrees: **code** only gitignores `logs/`. **UNDETERMINED** host backup/sync policy. Searched SAFETY.md + `.gitignore`.

### 7.5 Malware-tier controls (plain)

| Control | Implemented? | Exercised for v2? |
|---------|--------------|-------------------|
| `gate_p4` | yes (`scripts/safety/gate_p4.sh`) | **no** |
| `-wipe-data` | yes (AVD session scripts) | **no** |
| `adb_pinned.sh` | yes (`scripts/safety/adb_pinned.sh`) | **no** on v2 launch (`launch.sh` uses `tools/platform-tools/adb` on PATH, not that wrapper) |
| Encrypted vault | yes (sink start requires mount; SAFETY.md) | **no** |

---

## 8 — Remediation history

Source of classes: `docs/remediation_plan.md` (plan) vs modules that now exist (code). Thesis-style classes, not a changelog of every PR.

### 8.1 Classes of defect

| Class | Symptom (plan/code) | How detected | What changed (code now) | Silent quality risk if undetected |
|-------|---------------------|--------------|-------------------------|-----------------------------------|
| Metric / no-op success | `advance_goal` returned success on engine skips (`remediation_plan.md:11`); wait/back counted as progress in older ratios | Inspection of metrics vs session playback (plan incidents 1–3) | `_execute_action` still returns success for `advance_goal` without I/O (`actions.py:760-761`); quality now uses phase-aware named taps / C0 / flailing | **Yes** — reference tier would look cleaner while sessions idle |
| Explore-blind ratio | `direct_action_ratio` ignored explore (`remediation_plan.md:12`) | Judge vs Mensa (`remediation_plan.md:12`) | `quality_rules._all_phase_direct_action_ratio`; C0 explore engagement | **Yes** |
| Duplicate / weakened flailing | `_flailing_new` dropped `same_element_cycle` and guarded `dominant_screen` (`remediation_plan.md:37-44`) | Relabel 46→35 described as a hole | Merged `detect_suspect_flailing` | **Yes** — 12 sessions would enter reference |
| Element model | `clickable` not used; anonymous clickables excluded (Step 2 docs) | Candidate emptiness vs `interactive_element_count` (`remediation_plan.md:13`) | `screen.py:_normalized_elements` includes `clickable` (`screen.py:69`); `_is_visible_and_interactive` (`23-41`) | **Yes** — explore stuck in back/wait with widgets on screen |
| Typing / goal classifier | input goals without EditText (Step 4 doc `docs/step4_typing_goal_fix.md`) | Goal status vs hierarchy | `_screen_has_edittext_for_typing` (`screen.py:248`); `_goal_action_hint` in prompts | **Yes** — failed inputs counted as attempts |
| Explore policy seam | logic inlined in session (Step 5) | Plan SEAM | `explore_policy.py:choose_explore_action` | Process risk more than silent metric |
| Candidate-bucket logging | buckets invisible (Step 1 INSTRUMENT) | Could not see emptiness | `explore_candidate_counts` on explore jsonl | Without logs, emptiness stays hidden |
| `SESSIONS_PER_APP` dead config | plan Step 8 | Config vs actual 1 session | v2 env `SESSIONS_PER_APP=3` (`collection_v2.env:10`) | Coverage / independence design |
| Hook v2→v3 categories | pooling old+new forbidden (plan Step 9) | Identity of hook SHA | v2 metadata single SHA `3192c7d6…` (`REPORT.md:43`) | **Yes** if mixed hook versions pooled |
| Scroll residual | high back/wait on scrollable UIs | Step 6 PART A fresh 90 s runs (`step6_part_a_scroll_residual.md:5-16`) | Scroll **deferred**; anonymous clickables + `swipe` in planner | Plan says cohort resolved without scroll |

### 8.2 Instrumentation vs inspection

- **Instrumentation:** Step 1 candidate counts; `explore_input_effective`; audit JSONL; faithfulness C0 evidence fields.
- **Inspection / offline relabel:** flailing merge examples named in plan (`coolmicapp`, `roadtripradar`, Mensa); Step 6 PART A comparison of logs (`step6_part_a_scroll_residual.md:6`).

### 8.3 Verification after fixes (as recorded)

- Step 6 PART A: “Fresh 90s emulator runs on current code (Steps 0–5)” (`step6_part_a_scroll_residual.md:5`); gate table RESOLVED 21 / STILL-NEEDS-SCROLL 0.
- v2 preflight: `collection_v2.env` header “Step 9 preflight”; `run_bulk_llm_benign_v2.sh:2` “DO NOT run until preflight passes”.
- Identity/canary: `identity_check/REPORT.md` (read-only check, not a collector fix).
- Reference gate scripts: `curate_v2_reference.py`, extend `reference_gate_for_dir`.

**UNDETERMINED:** a single lab notebook listing gate-script exit codes after each numbered remediation step — searched `docs/remediation_plan.md` checkboxes (many still `- [ ]` in the plan file) vs code that clearly landed. Plan file checkboxes are **not** a reliable “done” signal; code presence is.

---

## 9 — Known limitations, from the code

### 9.1 Twenty-two hooks that never fired in v2

From `ABRG/abrg/output/v2_chapter_b/SUMMARY.md:134`. Explanations: **only** where code or project docs state a reason; otherwise **UNDETERMINED** (searched `hook_apis.js` comments, `evaluate_corpus.py:PERM_TO_CATEGORIES`, action space, Step 6 / SAFETY docs).

| API | Category | Code/docs explanation | Else |
|-----|----------|------------------------|------|
| `SmsManager.sendTextMessage` | sms | Planner cannot emit an SMS action (`_ACTION_TYPES_PLANNER`). `PERM_TO_CATEGORIES` maps `SEND_SMS`→`sms` (`evaluate_corpus.py:70`) — permission proxy only. | No hook comment “requires user SMS UI”. |
| `SmsManager.sendMultipartTextMessage` | sms | same | |
| `Camera.open` | camera | Camera1 API; **Camera2** `CameraManager.openCamera` **did fire**. | Why Camera1 unused: **UNDETERMINED**. |
| `ClipboardManager.setPrimaryClip` | clipboard | No clipboard action in planner set. | |
| `AccountManager.getAccounts` / `getAccountsByType` | accounts | No account-picker action; `GET_ACCOUNTS` in perm map (`evaluate_corpus.py:79`). | Whether AVD has accounts: **UNDETERMINED**. |
| `Cipher.getInstance` | crypto | `Cipher.doFinal` **did fire** — getInstance may be uncalled or hooked overload miss. | **UNDETERMINED**. |
| `DexClassLoader.<init>` / `PathClassLoader.<init>` | dynamic_code_loading | No policy to load dex. | |
| `FileOutputStream.<init>` | file_io | `FileInputStream.<init>` **did fire**. | Why writes unseen: **UNDETERMINED**. |
| `HttpURLConnection.connect` | network | `URL.openConnection` **did fire**; connect() may be skipped by stacks using OkHttp (also fired). | |
| `MediaPlayer.setDataSource` / `prepare` / `start` | media | No media-play action; graph category `media` dead in v2 pooled apps (`SUMMARY.md` category table). | Hardware/codec: **UNDETERMINED**. |
| `PackageManager.getInstalledApplications` | package_manager | `getInstalledPackages` **did fire**. | Overload/API choice: **UNDETERMINED**. |
| `Runtime.load` / `Runtime.loadLibrary` | native_code | `System.loadLibrary` **did fire**. | |
| `TelephonyManager.getDeviceId` / `getSubscriberId` / `getSimSerialNumber` | device_info | Identifier APIs; API 29 device (`REPORT.md:51`). Policy does not request them. | Permission-gated vs emulator null: **UNDETERMINED** (no hook-side permission check). |
| `TelephonyManager.getCallState` | telephony | No call action in planner. | |
| `volley.RequestQueue.add` | network | App-library-specific hook (`Java.use("com.android.volley.RequestQueue")`, `hook_apis.js:843`). | Apps in v2 may not use Volley. |

### 9.2 Actions the policy cannot perform (from the action space)

Confirmed absent from `_ACTION_TYPES_PLANNER` and `_execute_action` branches:

- Named **purchase** / Play Billing.
- Named **credential/login** (can still `input` into a visible EditText; simulation may still `failed:skip:login_required`).
- Named **permission grant** in the timed loop (pre-grant via `pm grant`; dialog packages treated as foreign).
- `long_press`, named `scroll` (use `swipe`), intent injection, `adb shell am start` as a planner action.

### 9.3 Exploration loop — decision/plan record of poor handling

From `docs/remediation_plan.md` incidents (doc): engine `advance_goal` no-ops; explore idle with widgets present; explore-blind metrics. From `docs/step6_part_a_scroll_residual.md`: scrollable cohort was back/wait-dominated **before** Step 2; after, scroll deferred. From prompts themselves: `fallback_rid_missing`, `tap_xy` with unchanged UI, `repetition_guard` (`prompts.py:318-320`).

### 9.4 `llm_actions.jsonl`

**Exists in collection output:** yes. Opened in `session.py:152` `{pkg}_llm_actions.jsonl`. Present under `ContextDroid/logs/bulk_llm_benign_v2/**` and `ABRG/datasets/v2/sessions/**`. Records steps: `step`, `ts_epoch_ms`, `prompt_hash`, `temperature`, `planner_model`, `raw_response`, `parsed_action`, `action_success`, `action_outcome`, `screen_hash`, `pipeline_phase`, `interactive_element_count`, explore bucket counts (explore), `ux_goal_*` (execute), etc. (`session.py:1024-1063`, `1754-1798`).

**Absent from v2_extended export:** `_build_export.py:296-299` writes only `metadata.json` and copies Frida to `events.jsonl`. Export README layout lists those two files only (`export/v2_extended/README.md:21-26`).

**Consequence (as already recorded in Chapter B):** distinct screens/activities per session are **not computable from the export** (`SUMMARY.md:137`). They **are** recoverable from collection `*_llm_actions.jsonl` via `screen_hash` / `unique_screen_hashes_seen` (audit) — **not** from `datasets/v2_extended/`.

---

## 10 — Versions and environment

Sources: identity_check `REPORT.md` (original 168), `collection_v2.env` / `launch.sh` (extend), `requirements.txt`, working-tree hashes. **UNRECOVERABLE** means not in session/run artefacts (identity_check language).

| Component | Value | Evidence bound | v2 state |
|-----------|-------|----------------|----------|
| Python (collection) | **UNRECOVERABLE** | not in metadata / run tree (`REPORT.md:71`) | |
| Python (extend launch shebang) | path `…/adaptive-behavioral-graph-analysis/.venv/bin/python` | `launch.sh:39` | extend only; version string not recorded |
| `requirements.txt` | `frida>=16.0.0`, `frida-tools>=12.0.0`, `pandas>=2.0.0` | `ContextDroid/requirements.txt` | pins lower bounds, not freeze |
| Collection pip freeze | **UNRECOVERABLE** | `REPORT.md:72`; `config_snapshot.py` exists now but was not emitted under `logs/bulk_llm_benign_v2/` (`REPORT.md:79`) | |
| Frida **client** version | **UNRECOVERABLE** in artefacts; operator override note: client 17.9.3 installed 2026-04-30 | `REPORT.md:39, 18-21` | attach succeeded in July |
| Frida **server** version | **UNRECOVERABLE** in artefacts; same override: 17.9.3-compatible | `REPORT.md:40, 18-23` | |
| frida-server binary SHA | **UNRECOVERABLE** | `REPORT.md:41` | |
| Hook SHA256 | `3192c7d6f618bb455588a7db7b26b20ccb9028af22cf1d8d8f0db99c28009ffc` | metadata ×168; rehash 2026-08-17 | **exercised** |
| Hook git commit | **UNRECOVERABLE** | untracked (`REPORT.md:45`) | |
| Androguard | **not in ContextDroid tree** | searched `androguard` in ContextDroid — 0 hits | not on collection path |
| Emulator system image | **UNRECOVERABLE** | `REPORT.md:52` | |
| AVD name (July) | **UNRECOVERABLE** | `REPORT.md:50` | serial `emulator-5554` in logs |
| AVD name (extend) | `abrg_benign` | `launch.sh:17` | **exercised** extend |
| Device SDK | 29 | `nohup.out` (`REPORT.md:51`) | |
| adb path (observed) | `ContextDroid/tools/platform-tools/adb` | `REPORT.md:54` | |
| adb version string | **UNRECOVERABLE** | `REPORT.md:55` | |
| Planner name | `llama3.2` | metadata ×168 | **exercised** |
| Planner digest | **UNRECOVERABLE** | `REPORT.md:59` | |
| Prompt file SHA (July) | **UNRECOVERABLE** | `REPORT.md:61` | working-tree `prompts.py` SHA §4.4 |
| Temperature | 0.0 | jsonl ×9063 steps (`REPORT.md:60`) | |
| OS / Darwin | **UNRECOVERABLE** from session artefacts | not in metadata | this extraction host is darwin (user_info); **not** a collection pin |
| Collection window (original) | 2026-07-12 … 2026-07-19 | `REPORT.md:73` | |
| Extend window | 2026-08-13 … 2026-08-15 | Chapter B `SUMMARY.md` batch table | |

---

## Appendix A — Doc-intent vs code-behaviour (index)

| Topic | Doc-intent | Code-behaviour / v2 |
|-------|------------|---------------------|
| Stimulation | Monkey (`README.md:3`, `methodology.md:14`) | LLM arm + Monkey **warmup only** |
| Duration | 120 s (`protocol_constants.md`) | 420 s |
| `protocol_config.py` inert | docstring | temperature, timeout multiplier, history window **wired** |
| Snapshot every session | cold start | skip-load can report `snapshot_restored=True` without load |
| Scroll action | Step 6 plan | deferred; `swipe` used |
| Explore LLM | explore prompt exists | v2 explore predominantly `bfs_navigation_phase` |
| Network sink | SAFETY.md malware | not on v2 launch |

---

## Appendix B — Files searched when a claim is UNDETERMINED

- `ContextDroid/**/DECISION_LOG*` (0)
- `git log` in this ContextDroid clone (single commit `4d2cdb1`)
- `llm_agent/**` for `screencap|screenshot` (0)
- `hook_apis.js` comments for per-hook “why unused”
- July prompt file SHA, Frida versions, AVD image, Python/pip, Androguard: identity_check `REPORT.md` plus `requirements.txt` / tree grep
- v2_extended export contents vs `*_llm_actions.jsonl`: `_build_export.py`, export README, Chapter B SUMMARY

---

*End of specification.*
