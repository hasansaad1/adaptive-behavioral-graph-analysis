# v2_extended — PROVENANCE

Sources: `abrg/output/v2_extend/identity_check/REPORT.md`, `CANARY.md`,
`SUMMARY.md`, collection state, and session metadata. Export is read-only on
session artefacts.

---

## Collection configuration (recoverable vs current)

| field | value | status |
|-------|-------|--------|
| Hook script path | `frida_scripts/hook_apis.js` | recorded on sessions |
| Hook script SHA256 | `3192c7d6f618bb455588a7db7b26b20ccb9028af22cf1d8d8f0db99c28009ffc` | recorded ×168; matches current file |
| Hook API set / categories | 58 API names / 25 categories (22 GRAPH excl. lifecycle, reflection, navigation) | from SHA-matched hook file |
| Frida client version | current `17.9.3` (installed 2026-04-30) | July value **UNRECOVERABLE** |
| Frida client install date | 2026-04-30 | override evidence |
| Frida-server version | current strings `17.9.3`; mtime 2026-08-05 | July binary identity **UNRECOVERABLE**; **operator override** in `OVERRIDE.md` |
| Emulator AVD name | extend/canary: `abrg_benign`; July AVD name | July **UNRECOVERABLE** in session metadata |
| Emulator system image | current: android-29 google_apis arm64-v8a | July image identity **UNRECOVERABLE** |
| Emulator API / SDK | 29 | July run logs |
| Session duration setting | 420 s | recorded |
| LLM planner model name | `llama3.2` | recorded |
| LLM planner digest | | July **UNRECOVERABLE** |
| Prompt template path | `extraction_pipeline/llm_agent/prompts.py` | current SHA256 `379632c225f4316855b100db9ed43396950987a8e6276f69c81f6f2a435058ae` |
| Prompt last-commit date | 2026-06-09 20:34:18 +0200 (`4d2cdb1e…`) | July frozen SHA **UNRECOVERABLE** |
| Reset protocol | `snapshot_restored=true` + `pm clear` (not `-wipe-data`); `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` when already booted | recorded |
| Action space | `tap`, `input`, `back`, `wait`, `advance_goal`, `swipe` | observed |
| Max steps | duration-bounded (no fixed max_steps) | |

### Operator override (frida-server) — verbatim

See `OVERRIDE.md`:

- client 17.9.3, installed 2026-04-30, no upgrade trail through the July window
- frida enforces client/server version compatibility at attach; July sessions
  attached successfully, so the server was 17.9.3-compatible
- no frida commands in shell history during July
- current `tools/frida-server-android-arm64` strings report 17.9.3; the 2026-08-05
  mtime reflects a file write, not a verified content change

---

## Canary verification (Stage 1d)

Apps: `app.comaps.fdroid`, `app.organicmaps`, `ai.susi` (1 session each).

| app | median mapped | band | canary mapped | C1 | C2 | C3 | verdict |
|-----|--------------:|-----:|--------------:|:--:|:--:|:--:|:-------:|
| app.comaps.fdroid | 157 | 39.25–628 | 153 | PASS | PASS | PASS | PASS |
| app.organicmaps | 142 | 35.5–568 | 125 | PASS | PASS | PASS | PASS |
| ai.susi | 408 | 102–1632 | 348 | PASS | PASS | PASS | PASS |

**CANARY PASS** (behavioural criteria). Reference-tier on canary slots: 2 pass / 1 fail
(`app.comaps.fdroid`: `partial:bad_handoff`).

---

## Collection date ranges (by batch)

| batch | n | start (UTC) | end (UTC) |
|-------|--:|-------------|-----------|
| original | 168 | 2026-07-12T17:26:14.626Z | 2026-07-19T07:21:53.932Z |
| canary | 3 | 2026-08-13T22:28:42.534Z | 2026-08-13T22:49:45.128Z |
| extend | 217 | 2026-08-13T23:17:33.502Z | 2026-08-15T06:07:05.633Z |

Hard stop (extend): 2026-08-15T08:00:00+02:00.

---

## Old vs new distribution (`SUMMARY.md`)

| metric | old median | new median | pooled median | Mann-Whitney U | p |
|--------|----------:|----------:|--------------:|---------------:|--:|
| sessions_per_app | 3.0 | 8.0 | 5.0 | 0.0 | 2.07e-16 |
| mapped_events | 127.0 | 103.0 | 111.0 | 13273.0 | 0.545 |
| active_nodes | 3.0 | 3.0 | 3.0 | 13638.5 | 0.283 |
| edges | 3.0 | 2.0 | 3.0 | 13542.0 | 0.349 |

Plain statement: session count rose by design (median 3 → 8). Mapped-event median
127 → 103 and edges median 3 → 2; Mann-Whitney on mapped / nodes / edges does not
reject equality at p < 0.05. Sessions-per-app differs by construction.

---

## Analyze exit codes (extend)

Non-zero extend sessions (2):

| app_id | session_id | exit_status | analysis_status |
|--------|------------|------------:|-----------------|
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s4 | 12 | failed_frida_reattach |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s5 | 12 | failed_frida_reattach |

---

## Timestamps in exported events

- Parseable `type==event` records: timestamp present; monotonic non-decreasing per session.
- 361 / 388 files also contain non-JSON Frida attach-error lines (copied verbatim).

---

## UNRECOVERABLE fields (explicit)

1. Frida client version (July)
2. Frida server version / binary SHA (July) — override in `OVERRIDE.md`
3. Emulator system image identity (July)
4. Emulator AVD name (July session metadata)
5. LLM planner model digest (July)
6. Prompt template SHA256 as frozen July artefact
7. adb / platform-tools version (July)
8. Python / collection-path pip pins (July)
9. Host OS (July)
10. Hook git commit during July collection
