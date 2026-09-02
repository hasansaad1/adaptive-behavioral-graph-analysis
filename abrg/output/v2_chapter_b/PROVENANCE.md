# Chapter B — PROVENANCE

Assembled (UTC): 2026-08-17T16:13:58.117973+00:00

Sources: `datasets/v2_extended/PROVENANCE.md`, `OVERRIDE.md`,
`ContextDroid/abrg/output/v2_extend/identity_check/{REPORT,CANARY}.md`.
Live hashes of current files are labelled current; July identity is as recorded.

## Collection configuration

| field | value | status |
|-------|-------|--------|
| hook_script_path | frida_scripts/hook_apis.js | recoverable |
| hook_script_sha256 | 3192c7d6f618bb455588a7db7b26b20ccb9028af22cf1d8d8f0db99c28009ffc | recoverable |
| hook_api_set | 58 API names / 25 categories (22 GRAPH excl. lifecycle, reflection, navigation) | recoverable |
| frida_client_version | UNRECOVERABLE | UNRECOVERABLE |
| frida_client_install_date | 2026-04-30 | override evidence (not a July session field) |
| frida_server_version | UNRECOVERABLE | UNRECOVERABLE |
| emulator_avd_name | UNRECOVERABLE in session metadata | UNRECOVERABLE (July); recoverable (extend/canary launch.sh AVD_NAME=abrg_benign) |
| emulator_system_image | UNRECOVERABLE | UNRECOVERABLE |
| emulator_api_sdk | 29 | recoverable (July run logs) |
| session_duration_setting | 420 s | recoverable |
| llm_planner_model | llama3.2 | recoverable |
| llm_planner_digest | UNRECOVERABLE | UNRECOVERABLE |
| prompt_template_path | extraction_pipeline/llm_agent/prompts.py | path recoverable; July frozen SHA UNRECOVERABLE |
| reset_protocol | snapshot_restored=true + pm clear (not -wipe-data); CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1 when already booted | recoverable |
| action_space | tap, input, back, wait, advance_goal, swipe | recoverable (observed) |
| max_steps | duration-bounded (no fixed max_steps) | recoverable as uncapped |
| adb_platform_tools_version_july |  | UNRECOVERABLE |
| python_pip_pins_july |  | UNRECOVERABLE |
| host_os_july |  | UNRECOVERABLE |
| hook_git_commit_july |  | UNRECOVERABLE |

## UNRECOVERABLE fields

1. Frida client version (July)
2. Frida server version / binary SHA (July) — operator override in OVERRIDE.md
3. Emulator system image identity (July)
4. Emulator AVD name (July session metadata)
5. LLM planner model digest (July)
6. Prompt template SHA256 as frozen July artefact
7. adb / platform-tools version (July)
8. Python / collection-path pip pins (July)
9. Host OS (July)
10. Hook git commit during July collection

## Operator override (frida-server) — verbatim from `datasets/v2_extended/OVERRIDE.md`

```
# Operator override (2026-08-14) — frida-server version only

Copied verbatim from `abrg/output/v2_extend/identity_check/REPORT.md`
(file `OVERRIDE.md` was not present in that directory at export time).

Explicit override of the Stage 1 UNRECOVERABLE gate **for frida-server version**, recorded verbatim:

- client 17.9.3, installed 2026-04-30, no upgrade trail through the July window
- frida enforces client/server version compatibility at attach; July sessions
  attached successfully, so the server was 17.9.3-compatible
- no frida commands in shell history during July
- current `tools/frida-server-android-arm64` strings report 17.9.3; the 2026-08-05
  mtime reflects a file write, not a verified content change

**Remaining HARD gaps (not overridden):** emulator system image identity, LLM planner
model digest, prompt template SHA256 — still UNRECOVERABLE from July artifacts.
```

## Canary verification

Apps: `app.comaps.fdroid`, `app.organicmaps`, `ai.susi` (1 session each).

Two recorded verdicts exist (different criteria):

### Band criteria (`identity_check/CANARY.md`) — mapped in `[0.25×, 4×]` existing median; no novel / no silent-reliable category

# Stage 1d canary evaluation

**Criteria (all three apps must pass all three):**
1. No novel category vs that app’s existing sessions
2. No silent reliable category (fired in all existing sessions)
3. Mapped events in `[0.25×, 4×]` of that app’s existing median

## Per-app table

| app | existing median mapped | band [0.25×, 4×] | canary mapped | C1 no novel | C2 no silent reliable | C3 volume in band | app verdict |
|-----|-----------------------:|------------------:|--------------:|:-----------:|:---------------------:|:-----------------:|:-----------:|
| app.comaps.fdroid | 157 | 39.25–628 | 153 | PASS | PASS | PASS | PASS |
| app.organicmaps | 142 | 35.5–568 | 125 | PASS | PASS | PASS | PASS |
| ai.susi | 408 | 102–1632 | 348 | PASS | PASS | PASS | PASS |

| app | novel categories | silent reliable |
|-----|------------------|-----------------|
| app.comaps.fdroid | — | — |
| app.organicmaps | — | — |
| ai.susi | — | — |

Protocol (all three): `snapshot_restored=true`, `pm_clear_rc=0`, fairness on, hook SHA `3192c7d6…`, AVD `abrg_benign`, not `-wipe-data`.

CANARY PASS

### Min–max range criteria (`identity_check/REPORT.md` §1d)

| app | metric | existing min–max | canary | inside |
|-----|--------|-----------------:|-------:|:------:|
| app.comaps.fdroid | total_events | 576–929 | 606 | YES |
| app.comaps.fdroid | mapped_events | 148–160 | 153 | YES |
| app.comaps.fdroid | mapped_rate | 0.1710–0.2569 | 0.2525 | YES |
| app.comaps.fdroid | active_nodes | 5–5 | 5 | YES |
| app.comaps.fdroid | edges | 7–8 | 6 | NO |
| app.comaps.fdroid | elapsed_sec | 455.9–472.193 | 226.642 | NO |
| app.organicmaps | total_events | 939–1004 | 867 | NO |
| app.organicmaps | mapped_events | 142–145 | 125 | NO |
| app.organicmaps | mapped_rate | 0.1414–0.1544 | 0.1442 | YES |
| app.organicmaps | active_nodes | 5–5 | 5 | YES |
| app.organicmaps | edges | 5–5 | 5 | YES |
| app.organicmaps | elapsed_sec | 448.538–461.21 | 450.983 | YES |
| ai.susi | total_events | 5108–7082 | 5048 | NO |
| ai.susi | mapped_events | 401–421 | 348 | NO |
| ai.susi | mapped_rate | 0.0594–0.0785 | 0.0689 | YES |
| ai.susi | active_nodes | 6–6 | 6 | YES |
| ai.susi | edges | 12–23 | 12 | YES |
| ai.susi | elapsed_sec | 466.348–474.74 | 544.554 | NO |

REPORT.md §1d gate: FAIL — canary metrics outside existing min–max ranges.
CANARY.md / export PROVENANCE.md: CANARY PASS under the 0.25×–4× mapped band.

## Collection date ranges (from session metadata in this run)

| batch | n | start (UTC) | end (UTC) |
|-------|--:|-------------|-----------|
| canary | 3 | 2026-08-13T22:28:42.534000Z | 2026-08-13T22:49:45.128000Z |
| extend | 217 | 2026-08-13T23:17:33.502000Z | 2026-08-15T06:07:05.633000Z |
| original | 168 | 2026-07-12T17:26:14.626000Z | 2026-07-19T07:21:53.932000Z |

