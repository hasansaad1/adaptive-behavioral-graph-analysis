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
