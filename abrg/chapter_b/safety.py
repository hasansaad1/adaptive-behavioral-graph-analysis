"""SAFETY.md from collection code and gate scripts (not from plan memory)."""

from __future__ import annotations

from pathlib import Path

from abrg.chapter_b.config import CONTEXTDROID_ROOT, OUTPUT_ROOT


def _exists(rel: str) -> bool:
    return (CONTEXTDROID_ROOT / rel).is_file()


def write_safety_md(path: Path | None = None) -> Path:
    path = path or (OUTPUT_ROOT / "SAFETY.md")
    path.parent.mkdir(parents=True, exist_ok=True)

    files = {
        "device_guard.py": "extraction_pipeline/safety/device_guard.py",
        "device_guard.sh": "scripts/safety/device_guard.sh",
        "adb_pinned.sh": "scripts/safety/adb_pinned.sh",
        "avd_session.sh": "scripts/safety/avd_session.sh",
        "guest_sink_rules.sh": "scripts/safety/guest_sink_rules.sh",
        "network_sink.sh": "scripts/safety/network_sink.sh",
        "gate_p0.sh": "scripts/safety/gate_p0.sh",
        "gate_p1.sh": "scripts/safety/gate_p1.sh",
        "gate_p3.sh": "scripts/safety/gate_p3.sh",
        "gate_p4.sh": "scripts/safety/gate_p4.sh",
        "analyze_apk.py": "extraction_pipeline/analyze_apk.py",
        "ensure_emulator.sh": "extraction_pipeline/ensure_emulator.sh",
        "collection_v2.env": "extraction_pipeline/collection_v2.env",
        "run_bulk_llm_benign_v2.sh": "extraction_pipeline/run_bulk_llm_benign_v2.sh",
        "launch_extend.sh": "abrg/output/v2_extend/collection/launch.sh",
        "isolate": "extraction_pipeline/llm_agent/device.py",
        "SAFETY.md": "SAFETY.md",
        "malware_plan": "docs/malware_corpus_safety_plan.md",
    }
    present = {k: _exists(v) for k, v in files.items()}

    lines: list[str] = []
    lines.append("# Chapter B — SAFETY (v2 benign collection)")
    lines.append("")
    lines.append("Inspected ContextDroid collection and gate scripts. v2 is benign-only.")
    lines.append("Malware-tier controls are listed only to mark what this corpus did not use.")
    lines.append("File present on disk at inspection time is not the same as verified-at-collection.")
    lines.append("")
    lines.append("## Files inspected")
    lines.append("")
    lines.append("| key | path | present |")
    lines.append("|-----|------|:-------:|")
    for k, rel in files.items():
        lines.append(f"| {k} | `{rel}` | {present[k]} |")
    lines.append("")
    lines.append("## Network containment")
    lines.append("")
    lines.append("| item | implemented in code | used by v2 benign collection | verified for this corpus |")
    lines.append("|------|---------------------|------------------------------|--------------------------|")
    lines.append(
        "| Guest iptables sink (`guest_sink_rules.sh`, chain `ABRG_SINK`) | yes (file present) | "
        "no — `avd_session.sh` / `network_sink.sh` are malware-tier; "
        "`run_bulk_llm_benign_v2.sh` and `v2_extend/collection/launch.sh` do not invoke them | "
        "not verified for v2 |"
    )
    lines.append(
        "| Host network sink (`network_sink.sh`) | yes | no (malware Gate P4 / `avd_session.sh` refuses malware AVD without Gate A) | not verified for v2 |"
    )
    lines.append(
        "| `gate_p4.sh` | yes | malware-tier gate | not run as a v2 collection preflight in `launch.sh` or `run_bulk_llm_benign_v2.sh` |"
    )
    lines.append(
        "| Host `pfctl` egress backstop | sketch only (`host_pf_backstop_sketch.sh`) | no | ContextDroid `SAFETY.md` records it as not automated |"
    )
    lines.append("")
    lines.append(
        "v2 launch/env files set AVD `abrg_benign`, `FRIDA_USE_DOCKER=0`, "
        "`CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1`. They do not start the sink."
    )
    lines.append("")
    lines.append("## AVD isolation")
    lines.append("")
    lines.append("| item | implemented in code | v2 original (July) | v2 extend (August) |")
    lines.append("|------|---------------------|--------------------|--------------------|")
    lines.append(
        "| `isolate_emulator_state` (home keyevent + `am force-stop` other `-3` packages) | "
        "`analyze_apk.py` calls it when `CONTEXTDROID_ISOLATE_EMULATOR` is not disabled | "
        "call is in current `analyze_apk.py`; July invocation not separately logged in export metadata | "
        "same code path |"
    )
    lines.append(
        "| `pm clear` after install | `analyze_apk.py` | recorded in identity_check as `pm_clear_rc=0` on original 168 | extend launch uses same analyzer |"
    )
    lines.append(
        "| Snapshot restore vs skip | `_restore_snapshot`; skip when `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` | "
        "identity_check: `snapshot_restored=true`; some starts logged `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1` | "
        "`launch.sh` exports `CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1`, `EMULATOR_NO_SNAPSHOT_LOAD=1`, `EMULATOR_SAVE_SNAPSHOT=0` |"
    )
    lines.append(
        "| `-wipe-data` per sample | malware path (`scripts/corpus/run_sample.py` / `avd_session.sh`) | not used | not used |"
    )
    lines.append(
        "| Headless emulator flags | `ensure_emulator.sh`: `-no-snapshot-load -no-snapshot-save`; `-no-window` when `EMULATOR_SHOW_WINDOW!=1` | "
        "`collection_v2.env` does not set `EMULATOR_SHOW_WINDOW`; `run_bulk_llm_benign_v2.sh` defaults it to 0 | "
        "`launch.sh` sets `EMULATOR_SHOW_WINDOW=0` |"
    )
    lines.append(
        "| Stop malware AVD before collection | `launch.sh` kills serials whose `emu avd name` is `abrg_mw` | not in `run_bulk_llm_benign_v2.sh` | implemented in extend `launch.sh` |"
    )
    lines.append(
        "| Reboot every N apps | `collection_v2.env` `BULK_EMULATOR_REBOOT_EVERY_N=5` | env present | env sourced by `launch.sh` |"
    )
    lines.append("")
    lines.append("## Device guard")
    lines.append("")
    lines.append("| item | implemented in code | verified |")
    lines.append("|------|---------------------|----------|")
    lines.append(
        "| `assert_device_identity_hard` immediately before `adb install` | yes, `analyze_apk.py` | "
        "implemented; export metadata does not record guard pass/fail. "
        "`analysis_status=failed_device_guard` would appear if it fired; Chapter B exit-code table is the check |"
    )
    lines.append(
        "| Device-count watchdog during LLM session | `start_device_count_watchdog` in `analyze_apk.py` LLM arm | implemented in current analyzer |"
    )
    lines.append(
        "| `ensure_emulator.sh` `hard-prelaunch` | yes, if `device_guard.sh` exists | "
        "implemented now; whether July `ensure_emulator.sh` already called it is not in session artefacts |"
    )
    lines.append(
        "| `scripts/safety/adb_pinned.sh` on every adb call | file present; used by malware `avd_session` / corpus runner | "
        "v2 bulk scripts invoke `analyze_apk.py` with host `adb`, not `adb_pinned.sh` |"
    )
    lines.append(
        "| `gate_p3.sh` (two-emulator fail-closed, wipe isolation) | yes | malware/harness gate; not invoked by v2 bulk/extend launch scripts |"
    )
    lines.append(
        "| `CONTEXTDROID_DEVICE_GUARD_DISABLE` | bypass exists in `device_guard.py` | not set in `collection_v2.env` or extend `launch.sh` |"
    )
    lines.append("")
    lines.append("## Storage")
    lines.append("")
    lines.append("| item | implemented in code | v2 corpus |")
    lines.append("|------|---------------------|-----------|")
    lines.append(
        "| Encrypted malware vault (`vault.sh`, `/Volumes/ABRG_MW`) | yes (malware tier) | not used; v2 APKs are benign under ContextDroid `data/apks/benign/` |"
    )
    lines.append(
        "| `precommit_no_samples.sh` / `gate_p0.sh` | yes | repo hygiene for APK commits; not a runtime collection control |"
    )
    lines.append(
        "| Export excludes APKs | `datasets/v2_extended/README.md` | events + metadata only |"
    )
    lines.append(
        "| Session logs on disk | Frida JSONL + dynamic metadata | packaged into `datasets/v2_extended/sessions/` |"
    )
    lines.append("")
    lines.append("## Specified in plan documents but not verified as running for v2")
    lines.append("")
    lines.append("- Network sink + guest iptables + `gate_p4` (plan Phase 4; malware AVD `abrg_mw`).")
    lines.append("- `-wipe-data` + fresh boot per sample (malware reset; ContextDroid `SAFETY.md` A2).")
    lines.append("- `adb_pinned.sh` as the only adb path (malware session).")
    lines.append("- Host pf backstop (documented as not automated).")
    lines.append("- `config_snapshot.json` for original July runs: identity_check REPORT.md states it was **not** emitted under `logs/bulk_llm_benign_v2/`.")
    lines.append("")
    lines.append("## What v2 launch scripts actually set (extend `launch.sh`)")
    lines.append("")
    lines.append("```")
    lines.append("CONTEXTDROID_SKIP_SNAPSHOT_LOAD=1")
    lines.append("FRIDA_USE_DOCKER=0")
    lines.append("AVD_NAME=abrg_benign")
    lines.append("ANDROID_SERIAL=emulator-5554")
    lines.append("EMULATOR_SHOW_WINDOW=0")
    lines.append("EMULATOR_GPU=swiftshader_indirect")
    lines.append("EMULATOR_NO_SNAPSHOT_LOAD=1")
    lines.append("EMULATOR_SAVE_SNAPSHOT=0")
    lines.append("BULK_EMULATOR_WATCHDOG=1")
    lines.append("```")
    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
