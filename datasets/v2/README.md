# Dataset v2 — ContextDroid Reference Tier (bulk_llm_benign_v2)

**Repo version:** `v2` · see [`VERSION.json`](VERSION.json) and [`../CURRENT`](../CURRENT)

Packaged: 2026-07-20T14:27:51Z

## What this bundle is

**Reference-tier** sessions from ContextDroid `bulk_llm_benign_v2` (hook_apis.js **v3**, 420s sessions, 
3 sessions/app with identical/identical/varied seeds). Curation uses the v2 reference gate 
(sim success, faithfulness FAITHFUL/PARTIAL, explore engagement, meaningful 22-category Frida, 
not flailing). **Separate generation from v1** — never pool v1 and v2 in evaluation.

## Counts

- **Sessions:** 168 (59 distinct apps; up to 3 sessions/app)
- **FAITHFUL:** 162
- **PARTIAL:** 6
- **Source pool:** bulk_llm_benign_v2 analyze-success (594 at curation time; 197/284 apps completed)
- **Artifact files copied:** 1848 (+ 168 SESSION_INDEX.json)
- **Hook script:** hook_apis.js v3 (25 categories in trace; graph uses 22 excluding lifecycle/reflection/navigation)

## Layout

Archive (original export): [`archive/working_dataset_v2.zip`](archive/working_dataset_v2.zip)

```
datasets/v2/
  VERSION.json
  README.md
  working_dataset.csv
  working_dataset_manifest.json
  sessions/
    <session_id>__<package>/
      SESSION_INDEX.json
      <package>_frida.jsonl
      ... (11 more artifact files)
  archive/
    working_dataset_v2.zip
```

## File glossary (per session folder)

- **`*_dynamic_metadata.json`** — Session run metadata: package, timing, Frida/strace paths, simulation status, UX gates, app context.
- **`*_llm_actions.jsonl`** — Agent action log (one JSON per step): taps, swipes, backs, pipeline phase, screen hashes, app_state.
- **`*_frida.jsonl`** — Frida hook trace (JSONL): timestamped API events with category, api, args.
- **`*_frida.csv`** — Frida trace as CSV (relative_time, category, api, args_str) — same session as .jsonl.
- **`*_frida.quality.json`** — Frida attach/quality summary for the session.
- **`*_strace.log`** — Optional strace syscall log (if enabled for the run).
- **`*_llm_ux_plan.json`** — Post-explore UX goals, screen digest, semantic navigation graph summary.
- **`*_llm_navigation_artifact.json`** — BFS navigation graph: screens, transitions, tab targets visited in explore.
- **`*_human_ux_report.json`** — Pipeline UX quality checks (screen diversity, direct-action ratio, etc.).
- **`*_verified_start.xml`** — Accessibility hierarchy dump at verified session start (pre-agent).
- **`*_monkey.log`** — Warmup/monkey log if pre-setup used random input.

## Frida trace format (hook_apis.js v3)

- JSONL lines: `{"type":"event","timestamp":<ms>,"api":"...","category":"...","args":{...}}`
- Optional `type:"status"` / `hook_ok` lines retained
- `hook_loaded` event with `version:"3"`
- 25 hook categories in trace (full CATEGORY_UNIVERSE); lifecycle/reflection/navigation included in raw trace

## `working_dataset.csv` columns

| Column | Meaning |
|--------|---------|
| `package` | Android package name |
| `session_id` | `{apk_sha256_prefix12}_llm_sN` |
| `faithfulness_verdict` | `FAITHFUL` or `PARTIAL` |
| `artifact_dir` | Path relative to `datasets/v2/` → `sessions/<session_id>__<package>` |
| `frida_trace_path` | `{package}_frida.jsonl` (relative to session folder) |
| `agent_log_path` | `{package}_llm_actions.jsonl` |
| `dynamic_metadata_path` | `{package}_dynamic_metadata.json` |
| `meaningful_event_count` | Frida quality meaningful count (excl. reflection/lifecycle/unknown) |
| `coverage_gap` | Judge note on unvisited flows |

## App list (168 sessions)

| # | package | session_id | verdict | meaningful_events | sim_status |
|---|---------|------------|---------|-------------------|------------|
| 1 | `a2dp.Vol` | `f67ef52502fa_llm_s1` | FAITHFUL | 2 |  |
| 2 | `a2dp.Vol` | `f67ef52502fa_llm_s2` | FAITHFUL | 2 |  |
| 3 | `a2dp.Vol` | `f67ef52502fa_llm_s3` | FAITHFUL | 2 |  |
| 4 | `ac.robinson.mediaphone` | `497e019dc8a1_llm_s1` | FAITHFUL | 784 |  |
| 5 | `ac.robinson.mediaphone` | `497e019dc8a1_llm_s2` | FAITHFUL | 760 |  |
| 6 | `ac.robinson.mediaphone` | `497e019dc8a1_llm_s3` | FAITHFUL | 1034 |  |
| 7 | `ademar.bitac` | `3f8f31a5b92b_llm_s1` | FAITHFUL | 32 |  |
| 8 | `ademar.bitac` | `3f8f31a5b92b_llm_s2` | FAITHFUL | 32 |  |
| 9 | `agrigolo.opendrummer` | `9347877bc340_llm_s1` | FAITHFUL | 2 |  |
| 10 | `agrigolo.opendrummer` | `9347877bc340_llm_s2` | FAITHFUL | 2 |  |
| 11 | `agrigolo.opendrummer` | `9347877bc340_llm_s3` | FAITHFUL | 2 |  |
| 12 | `ai.susi` | `6f8510108099_llm_s1` | FAITHFUL | 401 |  |
| 13 | `ai.susi` | `6f8510108099_llm_s2` | FAITHFUL | 408 |  |
| 14 | `ai.susi` | `6f8510108099_llm_s3` | FAITHFUL | 421 |  |
| 15 | `anonvpn.anon_next.android` | `2f4839ccdb6e_llm_s1` | FAITHFUL | 24 |  |
| 16 | `anonvpn.anon_next.android` | `2f4839ccdb6e_llm_s2` | FAITHFUL | 21 |  |
| 17 | `anonvpn.anon_next.android` | `2f4839ccdb6e_llm_s3` | FAITHFUL | 23 |  |
| 18 | `app.alextran.immich` | `efcaf058dff9_llm_s1` | FAITHFUL | 13 |  |
| 19 | `app.alextran.immich` | `efcaf058dff9_llm_s2` | FAITHFUL | 13 |  |
| 20 | `app.alextran.immich` | `efcaf058dff9_llm_s3` | FAITHFUL | 13 |  |
| 21 | `app.comaps.fdroid` | `47d583fd8b06_llm_s1` | FAITHFUL | 160 |  |
| 22 | `app.comaps.fdroid` | `47d583fd8b06_llm_s2` | FAITHFUL | 148 |  |
| 23 | `app.comaps.fdroid` | `47d583fd8b06_llm_s3` | FAITHFUL | 157 |  |
| 24 | `app.crescentcash.src` | `a02b64c18d0e_llm_s1` | FAITHFUL | 6 |  |
| 25 | `app.crescentcash.src` | `a02b64c18d0e_llm_s2` | FAITHFUL | 6 |  |
| 26 | `app.crescentcash.src` | `a02b64c18d0e_llm_s3` | FAITHFUL | 6 |  |
| 27 | `app.fedilab.castlab` | `5719f3b34f71_llm_s1` | FAITHFUL | 69 |  |
| 28 | `app.fedilab.castlab` | `5719f3b34f71_llm_s2` | FAITHFUL | 92 |  |
| 29 | `app.fedilab.castlab` | `5719f3b34f71_llm_s3` | FAITHFUL | 79 |  |
| 30 | `app.fedilab.mobilizon` | `9b7a3d5efee6_llm_s1` | FAITHFUL | 127 |  |
| 31 | `app.fedilab.mobilizon` | `9b7a3d5efee6_llm_s2` | FAITHFUL | 127 |  |
| 32 | `app.fedilab.mobilizon` | `9b7a3d5efee6_llm_s3` | FAITHFUL | 127 |  |
| 33 | `app.fedilab.nitterizeme` | `bcf251559ee4_llm_s1` | FAITHFUL | 199 |  |
| 34 | `app.fedilab.nitterizeme` | `bcf251559ee4_llm_s2` | FAITHFUL | 228 |  |
| 35 | `app.fedilab.nitterizeme` | `bcf251559ee4_llm_s3` | FAITHFUL | 168 |  |
| 36 | `app.fedilab.nitterizemelite` | `30ae40611f5f_llm_s1` | FAITHFUL | 199 |  |
| 37 | `app.fedilab.nitterizemelite` | `30ae40611f5f_llm_s2` | FAITHFUL | 199 |  |
| 38 | `app.fedilab.nitterizemelite` | `30ae40611f5f_llm_s3` | FAITHFUL | 199 |  |
| 39 | `app.hypostats` | `56ba09e3fd7c_llm_s1` | FAITHFUL | 2 |  |
| 40 | `app.hypostats` | `56ba09e3fd7c_llm_s2` | FAITHFUL | 2 |  |
| 41 | `app.hypostats` | `56ba09e3fd7c_llm_s3` | FAITHFUL | 2 |  |
| 42 | `app.ladefuchs.android` | `0f0dc4577a45_llm_s1` | FAITHFUL | 106 |  |
| 43 | `app.ladefuchs.android` | `0f0dc4577a45_llm_s2` | FAITHFUL | 101 |  |
| 44 | `app.ladefuchs.android` | `0f0dc4577a45_llm_s3` | FAITHFUL | 113 |  |
| 45 | `app.michaelwuensch.bitbanana` | `36bdbc1733f0_llm_s1` | FAITHFUL | 1941 |  |
| 46 | `app.michaelwuensch.bitbanana` | `36bdbc1733f0_llm_s2` | FAITHFUL | 1941 |  |
| 47 | `app.michaelwuensch.bitbanana` | `36bdbc1733f0_llm_s3` | FAITHFUL | 1941 |  |
| 48 | `app.notesr` | `3d3afadebd74_llm_s1` | FAITHFUL | 2 |  |
| 49 | `app.notesr` | `3d3afadebd74_llm_s2` | FAITHFUL | 1 |  |
| 50 | `app.notesr` | `3d3afadebd74_llm_s3` | FAITHFUL | 2 |  |
| 51 | `app.organicmaps` | `4862fbeed029_llm_s1` | FAITHFUL | 145 |  |
| 52 | `app.organicmaps` | `4862fbeed029_llm_s2` | FAITHFUL | 142 |  |
| 53 | `app.organicmaps` | `4862fbeed029_llm_s3` | FAITHFUL | 142 |  |
| 54 | `app.pachli` | `6187300de1fe_llm_s1` | PARTIAL | 12 |  |
| 55 | `app.pachli` | `6187300de1fe_llm_s2` | PARTIAL | 12 |  |
| 56 | `app.pachli` | `6187300de1fe_llm_s3` | PARTIAL | 12 |  |
| 57 | `app.prav.client` | `e4a6cdb972a2_llm_s1` | FAITHFUL | 254 |  |
| 58 | `app.prav.client` | `e4a6cdb972a2_llm_s2` | FAITHFUL | 254 |  |
| 59 | `app.prav.client` | `e4a6cdb972a2_llm_s3` | FAITHFUL | 254 |  |
| 60 | `app.tice.TICE.production` | `648d8ddb49f4_llm_s1` | FAITHFUL | 833 |  |
| 61 | `app.tice.TICE.production` | `648d8ddb49f4_llm_s2` | FAITHFUL | 781 |  |
| 62 | `app.tice.TICE.production` | `648d8ddb49f4_llm_s3` | FAITHFUL | 892 |  |
| 63 | `app.tujice.jergasColombia` | `ef6177e39b1d_llm_s1` | FAITHFUL | 11 |  |
| 64 | `app.tujice.jergasColombia` | `ef6177e39b1d_llm_s2` | FAITHFUL | 11 |  |
| 65 | `app.tujice.jergasColombia` | `ef6177e39b1d_llm_s3` | FAITHFUL | 12 |  |
| 66 | `app.udderance` | `2074fc55fb78_llm_s1` | FAITHFUL | 170 |  |
| 67 | `app.udderance` | `2074fc55fb78_llm_s2` | FAITHFUL | 169 |  |
| 68 | `app.udderance` | `2074fc55fb78_llm_s3` | FAITHFUL | 170 |  |
| 69 | `at.linuxtage.Eventfahrplan` | `84bca8b5903c_llm_s1` | FAITHFUL | 49 |  |
| 70 | `at.linuxtage.Eventfahrplan` | `84bca8b5903c_llm_s2` | FAITHFUL | 49 |  |
| 71 | `at.linuxtage.Eventfahrplan` | `84bca8b5903c_llm_s3` | FAITHFUL | 49 |  |
| 72 | `at.manuelbichler.octalsuntime` | `fe47baf78790_llm_s1` | PARTIAL | 48 |  |
| 73 | `at.manuelbichler.octalsuntime` | `fe47baf78790_llm_s2` | PARTIAL | 48 |  |
| 74 | `at.manuelbichler.octalsuntime` | `fe47baf78790_llm_s3` | PARTIAL | 48 |  |
| 75 | `at.mikenet.serbianlatintocyrillic` | `4b633ea030db_llm_s3` | FAITHFUL | 34 |  |
| 76 | `at.tomtasche.reader` | `407b766fceb3_llm_s1` | FAITHFUL | 3 |  |
| 77 | `at.tomtasche.reader` | `407b766fceb3_llm_s2` | FAITHFUL | 3 |  |
| 78 | `at.tomtasche.reader` | `407b766fceb3_llm_s3` | FAITHFUL | 3 |  |
| 79 | `au.com.wallaceit.reddinator` | `c3751de467a1_llm_s1` | FAITHFUL | 45 |  |
| 80 | `au.com.wallaceit.reddinator` | `c3751de467a1_llm_s2` | FAITHFUL | 46 |  |
| 81 | `au.com.wallaceit.reddinator` | `c3751de467a1_llm_s3` | FAITHFUL | 47 |  |
| 82 | `barilyuk.batterytemperature` | `75dd71ae0f0a_llm_s1` | FAITHFUL | 692 |  |
| 83 | `barilyuk.batterytemperature` | `75dd71ae0f0a_llm_s2` | FAITHFUL | 696 |  |
| 84 | `barilyuk.batterytemperature` | `75dd71ae0f0a_llm_s3` | FAITHFUL | 703 |  |
| 85 | `be.digitalia.fosdem` | `37b1a8bb28b9_llm_s1` | FAITHFUL | 46 |  |
| 86 | `be.digitalia.fosdem` | `37b1a8bb28b9_llm_s2` | FAITHFUL | 56 |  |
| 87 | `be.digitalia.fosdem` | `37b1a8bb28b9_llm_s3` | FAITHFUL | 44 |  |
| 88 | `be.humanoids.webthingify` | `4bb0adc701ab_llm_s1` | FAITHFUL | 7 |  |
| 89 | `be.mygod.vpnhotspot_foss` | `a72518537ed0_llm_s1` | FAITHFUL | 1674 |  |
| 90 | `be.mygod.vpnhotspot_foss` | `a72518537ed0_llm_s2` | FAITHFUL | 1691 |  |
| 91 | `be.mygod.vpnhotspot_foss` | `a72518537ed0_llm_s3` | FAITHFUL | 1657 |  |
| 92 | `biz.binarysolutions.mindfulnessmeditation` | `fba1483a8a4d_llm_s1` | FAITHFUL | 10 |  |
| 93 | `biz.binarysolutions.mindfulnessmeditation` | `fba1483a8a4d_llm_s2` | FAITHFUL | 10 |  |
| 94 | `biz.binarysolutions.mindfulnessmeditation` | `fba1483a8a4d_llm_s3` | FAITHFUL | 10 |  |
| 95 | `biz.binarysolutions.stress` | `a79d40377e87_llm_s1` | FAITHFUL | 4 |  |
| 96 | `biz.binarysolutions.stress` | `a79d40377e87_llm_s2` | FAITHFUL | 4 |  |
| 97 | `biz.binarysolutions.stress` | `a79d40377e87_llm_s3` | FAITHFUL | 4 |  |
| 98 | `biz.binarysolutions.vatcalculator` | `bec3b8076c0f_llm_s1` | FAITHFUL | 10 |  |
| 99 | `biz.binarysolutions.vatcalculator` | `bec3b8076c0f_llm_s2` | FAITHFUL | 10 |  |
| 100 | `biz.binarysolutions.vatcalculator` | `bec3b8076c0f_llm_s3` | FAITHFUL | 10 |  |
| 101 | `bluepie.ad_silence` | `c134927f92ec_llm_s1` | FAITHFUL | 15 |  |
| 102 | `bluepie.ad_silence` | `c134927f92ec_llm_s2` | FAITHFUL | 17 |  |
| 103 | `bluepie.ad_silence` | `c134927f92ec_llm_s3` | FAITHFUL | 15 |  |
| 104 | `br.odb.knights` | `12a4c95ef388_llm_s1` | FAITHFUL | 388 |  |
| 105 | `br.odb.knights` | `12a4c95ef388_llm_s2` | FAITHFUL | 388 |  |
| 106 | `br.odb.knights` | `12a4c95ef388_llm_s3` | FAITHFUL | 388 |  |
| 107 | `btools.routingapp` | `ef0f40be1b94_llm_s1` | FAITHFUL | 71 |  |
| 108 | `btools.routingapp` | `ef0f40be1b94_llm_s2` | FAITHFUL | 72 |  |
| 109 | `btools.routingapp` | `ef0f40be1b94_llm_s3` | FAITHFUL | 68 |  |
| 110 | `buet.rafi.dictionary` | `33f4266b15fd_llm_s1` | FAITHFUL | 5 |  |
| 111 | `buet.rafi.dictionary` | `33f4266b15fd_llm_s2` | FAITHFUL | 5 |  |
| 112 | `buet.rafi.dictionary` | `33f4266b15fd_llm_s3` | FAITHFUL | 5 |  |
| 113 | `bus.chio.wishmaster` | `39f811f07c23_llm_s1` | FAITHFUL | 52 |  |
| 114 | `bus.chio.wishmaster` | `39f811f07c23_llm_s2` | FAITHFUL | 52 |  |
| 115 | `bus.chio.wishmaster` | `39f811f07c23_llm_s3` | FAITHFUL | 52 |  |
| 116 | `ca.andries.portknocker` | `f54d6d05f299_llm_s1` | FAITHFUL | 4 |  |
| 117 | `ca.andries.portknocker` | `f54d6d05f299_llm_s2` | FAITHFUL | 4 |  |
| 118 | `ca.andries.portknocker` | `f54d6d05f299_llm_s3` | FAITHFUL | 4 |  |
| 119 | `ca.chancehorizon.paseo` | `e271584cf787_llm_s1` | FAITHFUL | 115 |  |
| 120 | `ca.chancehorizon.paseo` | `e271584cf787_llm_s2` | FAITHFUL | 109 |  |
| 121 | `ca.chancehorizon.paseo` | `e271584cf787_llm_s3` | FAITHFUL | 125 |  |
| 122 | `ca.farrelltonsolar.classic` | `2d767cdb301f_llm_s1` | FAITHFUL | 134 |  |
| 123 | `ca.farrelltonsolar.classic` | `2d767cdb301f_llm_s2` | FAITHFUL | 138 |  |
| 124 | `ca.farrelltonsolar.classic` | `2d767cdb301f_llm_s3` | FAITHFUL | 130 |  |
| 125 | `ca.momi.lift` | `59ee61acbb1b_llm_s1` | FAITHFUL | 6 |  |
| 126 | `ca.momi.lift` | `59ee61acbb1b_llm_s2` | FAITHFUL | 6 |  |
| 127 | `ca.momi.lift` | `59ee61acbb1b_llm_s3` | FAITHFUL | 6 |  |
| 128 | `ca.ramzan.delist` | `12d9ef307c03_llm_s1` | FAITHFUL | 8 |  |
| 129 | `ca.ramzan.delist` | `12d9ef307c03_llm_s2` | FAITHFUL | 8 |  |
| 130 | `ca.ramzan.delist` | `12d9ef307c03_llm_s3` | FAITHFUL | 8 |  |
| 131 | `ca.rmen.android.frenchcalendar` | `5e76f97d0425_llm_s1` | FAITHFUL | 95 |  |
| 132 | `ca.rmen.android.frenchcalendar` | `5e76f97d0425_llm_s2` | FAITHFUL | 104 |  |
| 133 | `ca.rmen.android.frenchcalendar` | `5e76f97d0425_llm_s3` | FAITHFUL | 103 |  |
| 134 | `ca.rmen.android.scrumchatter` | `7603ad0544fe_llm_s1` | FAITHFUL | 151 |  |
| 135 | `ca.rmen.android.scrumchatter` | `7603ad0544fe_llm_s2` | FAITHFUL | 187 |  |
| 136 | `ca.rmen.android.scrumchatter` | `7603ad0544fe_llm_s3` | FAITHFUL | 186 |  |
| 137 | `ca.rmen.nounours` | `0e7da7b17b63_llm_s1` | FAITHFUL | 474 |  |
| 138 | `ca.rmen.nounours` | `0e7da7b17b63_llm_s2` | FAITHFUL | 661 |  |
| 139 | `ca.rmen.nounours` | `0e7da7b17b63_llm_s3` | FAITHFUL | 498 |  |
| 140 | `cat.jordihernandez.cinecat` | `24e9101cdb34_llm_s1` | FAITHFUL | 42 |  |
| 141 | `cat.jordihernandez.cinecat` | `24e9101cdb34_llm_s2` | FAITHFUL | 42 |  |
| 142 | `cat.jordihernandez.cinecat` | `24e9101cdb34_llm_s3` | FAITHFUL | 42 |  |
| 143 | `cc.kafuu.bilidownload` | `64de55f0293d_llm_s1` | FAITHFUL | 8 |  |
| 144 | `cc.kafuu.bilidownload` | `64de55f0293d_llm_s2` | FAITHFUL | 8 |  |
| 145 | `cc.kafuu.bilidownload` | `64de55f0293d_llm_s3` | FAITHFUL | 8 |  |
| 146 | `cf.playhi.freezeyou` | `86b80fef253c_llm_s1` | FAITHFUL | 267 |  |
| 147 | `cf.playhi.freezeyou` | `86b80fef253c_llm_s2` | FAITHFUL | 267 |  |
| 148 | `cf.playhi.freezeyou` | `86b80fef253c_llm_s3` | FAITHFUL | 267 |  |
| 149 | `ch.abertschi.waterme.water_me` | `d42d78005adb_llm_s1` | FAITHFUL | 12 |  |
| 150 | `ch.abertschi.waterme.water_me` | `d42d78005adb_llm_s3` | FAITHFUL | 12 |  |
| 151 | `ch.bubendorf.locusaddon.gsakdatabase` | `3eae0c6f3334_llm_s1` | FAITHFUL | 183 |  |
| 152 | `ch.hgdev.toposuite` | `05e3f19e2717_llm_s1` | FAITHFUL | 229 |  |
| 153 | `ch.hgdev.toposuite` | `05e3f19e2717_llm_s3` | FAITHFUL | 229 |  |
| 154 | `ch.joshuah.bibleverseapp` | `18aff8885c8c_llm_s1` | FAITHFUL | 74 |  |
| 155 | `ch.joshuah.bibleverseapp` | `18aff8885c8c_llm_s2` | FAITHFUL | 74 |  |
| 156 | `ch.joshuah.bibleverseapp` | `18aff8885c8c_llm_s3` | FAITHFUL | 80 |  |
| 157 | `ch.mydoli.focal` | `bbf18ac3b134_llm_s1` | FAITHFUL | 59 |  |
| 158 | `ch.mydoli.focal` | `bbf18ac3b134_llm_s2` | FAITHFUL | 59 |  |
| 159 | `ch.mydoli.focal` | `bbf18ac3b134_llm_s3` | FAITHFUL | 59 |  |
| 160 | `cityfreqs.com.pilfershushjammer` | `c7c04de887f3_llm_s1` | FAITHFUL | 29 |  |
| 161 | `cityfreqs.com.pilfershushjammer` | `c7c04de887f3_llm_s2` | FAITHFUL | 29 |  |
| 162 | `cityfreqs.com.pilfershushjammer` | `c7c04de887f3_llm_s3` | FAITHFUL | 29 |  |
| 163 | `cl.coders.faketraveler` | `fb32bae7e64d_llm_s1` | FAITHFUL | 577 |  |
| 164 | `cl.coders.faketraveler` | `fb32bae7e64d_llm_s2` | FAITHFUL | 577 |  |
| 165 | `cl.coders.faketraveler` | `fb32bae7e64d_llm_s3` | FAITHFUL | 577 |  |
| 166 | `InfinityLoop1309.NewPipeEnhanced` | `b77ab89fd70e_llm_s1` | FAITHFUL | 388 |  |
| 167 | `InfinityLoop1309.NewPipeEnhanced` | `b77ab89fd70e_llm_s2` | FAITHFUL | 1329 |  |
| 168 | `InfinityLoop1309.NewPipeEnhanced` | `b77ab89fd70e_llm_s3` | FAITHFUL | 360 |  |
