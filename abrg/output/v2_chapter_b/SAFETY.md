# Chapter B — SAFETY (v2 benign collection)

Inspected ContextDroid collection and gate scripts. v2 is benign-only.
Malware-tier controls are listed only to mark what this corpus did not use.
File present on disk at inspection time is not the same as verified-at-collection.

## Files inspected

| key | path | present |
|-----|------|:-------:|
| device_guard.py | `extraction_pipeline/safety/device_guard.py` | True |
| device_guard.sh | `scripts/safety/device_guard.sh` | True |
| adb_pinned.sh | `scripts/safety/adb_pinned.sh` | True |
| avd_session.sh | `scripts/safety/avd_session.sh` | True |
| guest_sink_rules.sh | `scripts/safety/guest_sink_rules.sh` | True |
| network_sink.sh | `scripts/safety/network_sink.sh` | True |
| gate_p0.sh | `scripts/safety/gate_p0.sh` | True |
| gate_p1.sh | `scripts/safety/gate_p1.sh` | True |
| gate_p3.sh | `scripts/safety/gate_p3.sh` | True |
| gate_p4.sh | `scripts/safety/gate_p4.sh` | True |
| analyze_apk.py | `extraction_pipeline/analyze_apk.py` | True |
| ensure_emulator.sh | `extraction_pipeline/ensure_emulator.sh` | True |
| collection_v2.env | `extraction_pipeline/collection_v2.env` | True |
| run_bulk_llm_benign_v2.sh | `extraction_pipeline/run_bulk_llm_benign_v2.sh` | True |
| launch_extend.sh | `abrg/output/v2_extend/collection/launch.sh` | True |
| isolate | `extraction_pipeline/llm_agent/device.py` | True |
| SAFETY.md | `SAFETY.md` | True |
| malware_plan | `docs/malware_corpus_safety_plan.md` | True |

## Network containment

| item | implemented in code | used by v2 benign collection | verified for this corpus |
|------|---------------------|------------------------------|--------------------------|
| Guest iptables sink (`guest_sink_rules.sh`, chain `ABRG_SINK`) | yes (file present) | no — `avd_session.sh` / `network_sink.sh` are malware-tier; `run_bulk_llm_benign_v2.sh` and `v2_extend/collection/launch.sh` do not invoke them | not verified for v2 |
| Host network sink (`network_sink.sh`) | yes | no (malware Gate P4 / `avd_session.sh` refuses malware AVD without Gate A) | not verified for v2 |
| `gate_p4.sh` | yes | malware-tier gate | not run as a v2 collection preflight in `launch.sh` or `run_bulk_llm_benign_v2.sh` |
| Host `pfctl` egress backstop | sketch only (`host_pf_backstop_sketch.sh`) | no | ContextDroid `SAFETY.md` records it as not automated |

v2 launch/env files set AVD `abrg_benign`, `FRIDA_USE_DOCKER=0`, `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1`. They do not start the sink.

## AVD isolation

| item | implemented in code | v2 original (July) | v2 extend (August) |
|------|---------------------|--------------------|--------------------|
| `isolate_emulator_state` (home keyevent + `am force-stop` other `-3` packages) | `analyze_apk.py` calls it when `CONTEXTDROID_ISOLATE_EMULATOR` is not disabled | call is in current `analyze_apk.py`; July invocation not separately logged in export metadata | same code path |
| `pm clear` after install | `analyze_apk.py` | recorded in identity_check as `pm_clear_rc=0` on original 168 | extend launch uses same analyzer |
| Snapshot restore vs skip | `_restore_snapshot`; skip when `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` | identity_check: `snapshot_restored=true`; some starts logged `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` | `launch.sh` exports `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1`, `EMULATOR_NO_SNAPSHOT_LOAD=1`, `EMULATOR_SAVE_SNAPSHOT=0` |
| `-wipe-data` per sample | malware path (`scripts/corpus/run_sample.py` / `avd_session.sh`) | not used | not used |
| Headless emulator flags | `ensure_emulator.sh`: `-no-snapshot-load -no-snapshot-save`; `-no-window` when `EMULATOR_SHOW_WINDOW!=1` | `collection_v2.env` does not set `EMULATOR_SHOW_WINDOW`; `run_bulk_llm_benign_v2.sh` defaults it to 0 | `launch.sh` sets `EMULATOR_SHOW_WINDOW=0` |
| Stop malware AVD before collection | `launch.sh` kills serials whose `emu avd name` is `abrg_mw` | not in `run_bulk_llm_benign_v2.sh` | implemented in extend `launch.sh` |
| Reboot every N apps | `collection_v2.env` `BULK_EMULATOR_REBOOT_EVERY_N=5` | env present | env sourced by `launch.sh` |

## Device guard

| item | implemented in code | verified |
|------|---------------------|----------|
| `assert_device_identity_hard` immediately before `adb install` | yes, `analyze_apk.py` | implemented; export metadata does not record guard pass/fail. `analysis_status=failed_device_guard` would appear if it fired; Chapter B exit-code table is the check |
| Device-count watchdog during LLM session | `start_device_count_watchdog` in `analyze_apk.py` LLM arm | implemented in current analyzer |
| `ensure_emulator.sh` `hard-prelaunch` | yes, if `device_guard.sh` exists | implemented now; whether July `ensure_emulator.sh` already called it is not in session artefacts |
| `scripts/safety/adb_pinned.sh` on every adb call | file present; used by malware `avd_session` / corpus runner | v2 bulk scripts invoke `analyze_apk.py` with host `adb`, not `adb_pinned.sh` |
| `gate_p3.sh` (two-emulator fail-closed, wipe isolation) | yes | malware/harness gate; not invoked by v2 bulk/extend launch scripts |
| `CONTEXTDROID_DEVICE_GUARD_DISABLE` | bypass exists in `device_guard.py` | not set in `collection_v2.env` or extend `launch.sh` |

## Storage

| item | implemented in code | v2 corpus |
|------|---------------------|-----------|
| Encrypted malware vault (`vault.sh`, `/Volumes/ABRG_MW`) | yes (malware tier) | not used; v2 APKs are benign under ContextDroid `data/apks/benign/` |
| `precommit_no_samples.sh` / `gate_p0.sh` | yes | repo hygiene for APK commits; not a runtime collection control |
| Export excludes APKs | `datasets/v2_extended/README.md` | events + metadata only |
| Session logs on disk | Frida JSONL + dynamic metadata | packaged into `datasets/v2_extended/sessions/` |

## Specified in plan documents but not verified as running for v2

- Network sink + guest iptables + `gate_p4` (plan Phase 4; malware AVD `abrg_mw`).
- `-wipe-data` + fresh boot per sample (malware reset; ContextDroid `SAFETY.md` A2).
- `adb_pinned.sh` as the only adb path (malware session).
- Host pf backstop (documented as not automated).
- `config_snapshot.json` for original July runs: identity_check REPORT.md states it was **not** emitted under `logs/bulk_llm_benign_v2/`.

## What v2 launch scripts actually set (extend `launch.sh`)

```
CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1
FRIDA_USE_DOCKER=0
AVD_NAME=abrg_benign
ANDROID_SERIAL=emulator-5554
EMULATOR_SHOW_WINDOW=0
EMULATOR_GPU=swiftshader_indirect
EMULATOR_NO_SNAPSHOT_LOAD=1
EMULATOR_SAVE_SNAPSHOT=0
BULK_EMULATOR_WATCHDOG=1
```

