# v2_extended corpus — README (receiving repo)

This export is the ContextDroid **v2-extended** behavioural corpus for ABRG Chapter C
convergence and recency analysis. It packages Frida event traces with timestamps and
session metadata under a fixed layout; it does not include APKs, emulators, or
collection code. Sessions that failed reference-tier gates are included separately so
exclusions remain auditable.

## Layout

```
export/v2_extended/
  README.md
  PROVENANCE.md
  OVERRIDE.md
  EXPORT_SET.json
  REPORT.md
  MANIFEST.csv
  verify_export.py
  sessions_index.jsonl
  sessions/<app_id>/<session_id>__<batch>/
    metadata.json
    events.jsonl
  sessions_failed_reference/<app_id>/<session_id>__<batch>/
    metadata.json
    events.jsonl
```

Directory names use `session_id__batch` because the same `session_id` string can recur
across batches (same APK sample-id prefix). Metadata still carries the raw `session_id`.

- `sessions/` — analysis set: original 168 reference-tier + new slots that **passed**
  reference-tier gates (342 sessions).
- `sessions_failed_reference/` — new slots that **failed** reference-tier gates (46).
- `sessions_index.jsonl` — one JSON object per exported session (pass and fail).

## File schema

### `metadata.json` (per session)

| field | type | meaning |
|-------|------|---------|
| `app_id` | string | Android package name |
| `session_id` | string | Stable session id (may repeat across batches) |
| `export_dir_name` | string | `{session_id}__{batch}` |
| `session_index_within_app` | int | 1-based order by start time across all exported sessions of that app |
| `batch` | string | `original` \| `canary` \| `extend` |
| `start_timestamp` / `end_timestamp` | ISO-8601 Z | Session wall clock |
| `wall_duration_s` | float | Observed elapsed seconds |
| `reference_tier_pass` | bool | Same gates as the original 168 |
| `failure_reason` | string\|null | Null if pass |
| `event_counts.total` / `.mapped` / `.mapped_rate` | | Mapped = GRAPH_CATEGORY_UNIVERSE keep-set |
| `active_categories` | string[] | Set of mapped categories |
| `hooks_fired` | string[] | Set of API names among kept events |
| `n_active_nodes` / `n_edges` | int | ABRG `build_session_graph` at export time on unchanged traces |
| `gae_eligible` | bool | `n_active_nodes ≥ 2` and `n_edges ≥ 1` |

### `events.jsonl` (per session)

Verbatim Frida JSONL. Event records:

```json
{"type":"event","timestamp":1786660414821,"api":"hook_loaded","category":"lifecycle","args":{...}}
```

Non-JSON Frida stderr lines (e.g. `Failed to attach: process not found`) may appear;
they are preserved. Parseable `type==event` timestamps are present and monotonic.

### Worked example

`sessions/app.organicmaps/4862fbeed029_llm_s1__canary/metadata.json`:

```json
{
  "app_id": "app.organicmaps",
  "session_id": "4862fbeed029_llm_s1",
  "export_dir_name": "4862fbeed029_llm_s1__canary",
  "session_index_within_app": 4,
  "batch": "canary",
  "reference_tier_pass": true,
  "failure_reason": null,
  "event_counts": {"total": 1329, "mapped": 125, "mapped_rate": 0.09405568096313018},
  "active_categories": ["crypto", "file_io", "native_code", "network", "storage"],
  "n_active_nodes": 5,
  "n_edges": 5
}
```

## Counts and eligibility

| set | n |
|-----|--:|
| Total exported | 388 |
| Original reference-tier | 168 |
| Canary | 3 |
| Extend | 217 |
| Reference-tier pass (analysis set) | 342 |
| Reference-tier fail (flagged dir) | 46 |

- Apps in export: **59**. Extension covered the **40** GAE-eligible apps
  (`n_active ≥ 2` and `n_edges ≥ 1` on ≥1 original session).
- GAE-40 session-count distribution: `{7: 3, 8: 18, 9: 19}`.
- **No GAE-40 app fell out of eligibility** after extension.

## What is NOT included

- APKs; emulator / AVD / system images; collection pipeline; frida-server binary; LLM weights.

## Known limitations

- Extension: 40 GAE apps; original reference: 59 apps / 168 sessions.
- Benign only — no malware.
- Original-batch graph medians ~3 active nodes / ~3 edges (GAE set).
- Frida-server July identity UNRECOVERABLE — see `OVERRIDE.md` / `PROVENANCE.md`.
- Non-JSON attach-error lines in many Frida logs.

## What this corpus can and cannot answer

- **Can:** within-app convergence and recency with ordered, timestamped traces.
- **Cannot:** detection AUC — no malware class.

## Verify after transfer

```bash
python3 verify_export.py
```
