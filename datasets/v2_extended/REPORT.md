# v2_extended export — REPORT

## 1. Sessions exported

| batch | pass | fail | total |
|-------|-----:|-----:|------:|
| original | 168 | 0 | 168 |
| canary | 2 | 1 | 3 |
| extend | 172 | 45 | 217 |
| **all** | **342** | **46** | **388** |

Analysis set `sessions/`: 342. Flagged `sessions_failed_reference/`: 46.

## 2. Apps covered and per-app session counts

| n_apps_export | 59 |
| n_gae40 | 40 |
| gae40_fell_out | [] |
| gae40_count_distribution | `{'7': 3, '8': 18, '9': 19}` |

| app_id | n_sessions |
|--------|----------:|
| InfinityLoop1309.NewPipeEnhanced | 9 |
| ac.robinson.mediaphone | 9 |
| ai.susi | 9 |
| anonvpn.anon_next.android | 9 |
| app.comaps.fdroid | 9 |
| app.fedilab.castlab | 9 |
| app.fedilab.mobilizon | 9 |
| app.fedilab.nitterizeme | 9 |
| app.fedilab.nitterizemelite | 9 |
| app.ladefuchs.android | 9 |
| app.michaelwuensch.bitbanana | 9 |
| app.organicmaps | 9 |
| app.prav.client | 9 |
| app.tice.TICE.production | 9 |
| app.tujice.jergasColombia | 9 |
| app.udderance | 9 |
| at.linuxtage.Eventfahrplan | 9 |
| au.com.wallaceit.reddinator | 9 |
| barilyuk.batterytemperature | 9 |
| be.digitalia.fosdem | 8 |
| be.mygod.vpnhotspot_foss | 8 |
| biz.binarysolutions.mindfulnessmeditation | 8 |
| biz.binarysolutions.vatcalculator | 8 |
| bluepie.ad_silence | 8 |
| bus.chio.wishmaster | 8 |
| ca.chancehorizon.paseo | 8 |
| ca.farrelltonsolar.classic | 8 |
| ca.rmen.android.frenchcalendar | 8 |
| ca.rmen.android.scrumchatter | 8 |
| ca.rmen.nounours | 8 |
| cat.jordihernandez.cinecat | 8 |
| cc.kafuu.bilidownload | 8 |
| cf.playhi.freezeyou | 8 |
| ch.joshuah.bibleverseapp | 8 |
| ch.mydoli.focal | 8 |
| cityfreqs.com.pilfershushjammer | 8 |
| cl.coders.faketraveler | 8 |
| at.mikenet.serbianlatintocyrillic | 7 |
| ch.abertschi.waterme.water_me | 7 |
| ch.hgdev.toposuite | 7 |
| a2dp.Vol | 3 |
| agrigolo.opendrummer | 3 |
| app.alextran.immich | 3 |
| app.crescentcash.src | 3 |
| app.hypostats | 3 |
| app.notesr | 3 |
| app.pachli | 3 |
| at.manuelbichler.octalsuntime | 3 |
| at.tomtasche.reader | 3 |
| biz.binarysolutions.stress | 3 |
| br.odb.knights | 3 |
| btools.routingapp | 3 |
| buet.rafi.dictionary | 3 |
| ca.andries.portknocker | 3 |
| ca.momi.lift | 3 |
| ca.ramzan.delist | 3 |
| ademar.bitac | 2 |
| be.humanoids.webthingify | 1 |
| ch.bubendorf.locusaddon.gsakdatabase | 1 |

## 3. Inter-session transitions (sessions − 1)

| app_id | sessions | transitions |
|--------|---------:|------------:|
| InfinityLoop1309.NewPipeEnhanced | 9 | 8 |
| a2dp.Vol | 3 | 2 |
| ac.robinson.mediaphone | 9 | 8 |
| ademar.bitac | 2 | 1 |
| agrigolo.opendrummer | 3 | 2 |
| ai.susi | 9 | 8 |
| anonvpn.anon_next.android | 9 | 8 |
| app.alextran.immich | 3 | 2 |
| app.comaps.fdroid | 9 | 8 |
| app.crescentcash.src | 3 | 2 |
| app.fedilab.castlab | 9 | 8 |
| app.fedilab.mobilizon | 9 | 8 |
| app.fedilab.nitterizeme | 9 | 8 |
| app.fedilab.nitterizemelite | 9 | 8 |
| app.hypostats | 3 | 2 |
| app.ladefuchs.android | 9 | 8 |
| app.michaelwuensch.bitbanana | 9 | 8 |
| app.notesr | 3 | 2 |
| app.organicmaps | 9 | 8 |
| app.pachli | 3 | 2 |
| app.prav.client | 9 | 8 |
| app.tice.TICE.production | 9 | 8 |
| app.tujice.jergasColombia | 9 | 8 |
| app.udderance | 9 | 8 |
| at.linuxtage.Eventfahrplan | 9 | 8 |
| at.manuelbichler.octalsuntime | 3 | 2 |
| at.mikenet.serbianlatintocyrillic | 7 | 6 |
| at.tomtasche.reader | 3 | 2 |
| au.com.wallaceit.reddinator | 9 | 8 |
| barilyuk.batterytemperature | 9 | 8 |
| be.digitalia.fosdem | 8 | 7 |
| be.humanoids.webthingify | 1 | 0 |
| be.mygod.vpnhotspot_foss | 8 | 7 |
| biz.binarysolutions.mindfulnessmeditation | 8 | 7 |
| biz.binarysolutions.stress | 3 | 2 |
| biz.binarysolutions.vatcalculator | 8 | 7 |
| bluepie.ad_silence | 8 | 7 |
| br.odb.knights | 3 | 2 |
| btools.routingapp | 3 | 2 |
| buet.rafi.dictionary | 3 | 2 |
| bus.chio.wishmaster | 8 | 7 |
| ca.andries.portknocker | 3 | 2 |
| ca.chancehorizon.paseo | 8 | 7 |
| ca.farrelltonsolar.classic | 8 | 7 |
| ca.momi.lift | 3 | 2 |
| ca.ramzan.delist | 3 | 2 |
| ca.rmen.android.frenchcalendar | 8 | 7 |
| ca.rmen.android.scrumchatter | 8 | 7 |
| ca.rmen.nounours | 8 | 7 |
| cat.jordihernandez.cinecat | 8 | 7 |
| cc.kafuu.bilidownload | 8 | 7 |
| cf.playhi.freezeyou | 8 | 7 |
| ch.abertschi.waterme.water_me | 7 | 6 |
| ch.bubendorf.locusaddon.gsakdatabase | 1 | 0 |
| ch.hgdev.toposuite | 7 | 6 |
| ch.joshuah.bibleverseapp | 8 | 7 |
| ch.mydoli.focal | 8 | 7 |
| cityfreqs.com.pilfershushjammer | 8 | 7 |
| cl.coders.faketraveler | 8 | 7 |

## 4. Sessions excluded from export

| excluded | 0 |

## 5. UNRECOVERABLE provenance fields

1. Frida client version (July)
2. Frida server version / binary SHA (July) — override in OVERRIDE.md
3. Emulator system image identity (July)
4. Emulator AVD name (July session metadata)
5. LLM planner model digest (July)
6. Prompt template SHA256 as frozen July artefact
7. adb / platform-tools version (July)
8. Python / collection-path pip pins (July)
9. Host OS (July)
10. Hook git commit during July collection

## 6. verify_export.py exit code

| exit_code | 0 |


## 7. Verify command after transfer

```bash
python3 verify_export.py
```

## Reference-tier failures (sessions_failed_reference/)

| count | 46 |

| app_id | session_id | batch | failure_reason |
|--------|------------|-------|----------------|
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s4 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s5 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s4 | extend | analyze_status:failed_frida_reattach,sim_not_success |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s5 | extend | analyze_status:failed_frida_reattach,sim_not_success |
| app.comaps.fdroid | 47d583fd8b06_llm_s1 | canary | analyze_status:partial:bad_handoff,sim_not_success |
| app.comaps.fdroid | 47d583fd8b06_llm_s9 | extend | flailing:same_element_cycle: screen hash b17834b15c17… dominates (81%) and top named target repeated 41/50 times |
| app.fedilab.castlab | 5719f3b34f71_llm_s5 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| app.fedilab.castlab | 5719f3b34f71_llm_s8 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s4 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s5 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s6 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s7 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s8 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s9 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.ladefuchs.android | 0f0dc4577a45_llm_s4 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| app.ladefuchs.android | 0f0dc4577a45_llm_s5 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| app.ladefuchs.android | 0f0dc4577a45_llm_s6 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.ladefuchs.android | 0f0dc4577a45_llm_s7 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.ladefuchs.android | 0f0dc4577a45_llm_s8 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.ladefuchs.android | 0f0dc4577a45_llm_s9 | extend | analyze_status:partial:ux_quality_gate,sim_not_success |
| app.organicmaps | 4862fbeed029_llm_s7 | extend | analyze_status:partial:bad_handoff,sim_not_success,flailing:same_element_cycle: screen hash 29d9dc4f7967… dominates (89%) and top named target repeated 25/28 times |
| app.organicmaps | 4862fbeed029_llm_s8 | extend | analyze_status:partial:bad_handoff,sim_not_success,flailing:same_element_cycle: screen hash 29d9dc4f7967… dominates (89%) and top named target repeated 24/27 times |
| app.organicmaps | 4862fbeed029_llm_s9 | extend | analyze_status:partial:bad_handoff,sim_not_success,flailing:same_element_cycle: screen hash 29d9dc4f7967… dominates (89%) and top named target repeated 24/27 times |
| app.tice.TICE.production | 648d8ddb49f4_llm_s6 | extend | analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 55/55 times |
| app.tice.TICE.production | 648d8ddb49f4_llm_s7 | extend | analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 56/56 times |
| app.tice.TICE.production | 648d8ddb49f4_llm_s8 | extend | analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 56/56 times |
| app.tice.TICE.production | 648d8ddb49f4_llm_s9 | extend | analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 56/56 times |
| app.udderance | 2074fc55fb78_llm_s4 | extend | analyze_status:flag:webview_dominant |
| app.udderance | 2074fc55fb78_llm_s5 | extend | analyze_status:flag:webview_dominant |
| app.udderance | 2074fc55fb78_llm_s6 | extend | analyze_status:flag:webview_dominant |
| app.udderance | 2074fc55fb78_llm_s7 | extend | analyze_status:flag:webview_dominant |
| app.udderance | 2074fc55fb78_llm_s8 | extend | analyze_status:flag:webview_dominant |
| app.udderance | 2074fc55fb78_llm_s9 | extend | analyze_status:flag:webview_dominant |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s4 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s6 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s4 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s5 | extend | analyze_status:partial:bad_handoff,sim_not_success |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s4 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s5 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s6 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s7 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s8 | extend | analyze_status:partial:no_goal_progress,sim_not_success |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s3 | extend | flailing:dominant_screen: hash e8e86dc0a776… on 12/12 execute+primary steps (100%); named_functional_taps=0 |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s4 | extend | flailing:dominant_screen: hash e8e86dc0a776… on 11/11 execute+primary steps (100%); named_functional_taps=0 |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s6 | extend | flailing:dominant_screen: hash e8e86dc0a776… on 12/12 execute+primary steps (100%); named_functional_taps=0 |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s7 | extend | flailing:dominant_screen: hash e8e86dc0a776… on 11/11 execute+primary steps (100%); named_functional_taps=0 |

## Export size

| total_bytes | 174470556 |
| total_MiB | 166.39 |
| manifest_files | 783 |
