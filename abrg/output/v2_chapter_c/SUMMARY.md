# Chapter C — SUMMARY (numbers only)

No malware. No AUC.

## Graph builder note

- AndroCT tensor builder: `abrg.androct.graph_build.update_graph_sequence`
  - properties: `{"assert_recency_unpopulated": true, "delta_filter": false, "k_burst": 5, "timestamps": false, "w_cum": true, "w_rec": false}`
- Chapter C builder: `abrg.graph.update_graph`
  - properties: `{"delta_filter": true, "delta_sec": 5.0, "k_burst": 5, "lambda_rec": 0.01, "processing_windows": "time_sec_cumulative", "timestamps": true, "w_cum": true, "w_rec": true, "window_sec": 60.0}`
- Choice: Chapter C uses abrg.graph.update_graph (same schema / universe / shares-not-counts tensorization as AndroCT) because AndroCT's update_graph_sequence cannot exercise δ or recency. Export-time graph_metrics also used build_session_graph → update_graph. Session graphs are 60s multi-window cumulative finals so λ_rec decay separates w_rec from w_cum.

## Stage 0 — ingest

| field | value |
|-------|------:|
| verify_export exit | 0 |
| sessions in index | 388 |
| usable pass (timestamps OK) | 342 |
| reference-tier failures | 46 |
| batch pass | {'canary': 2, 'extend': 172, 'original': 168} |
| batch fail | {'canary': 1, 'extend': 45} |
| apps with usable sessions | 59 |
| apps with ≥5 usable | 35 |
| gate (≥30 apps with ≥5) | True |
| session_index contiguous | True |
| timestamp exclusions | 0 |
| n_nodes universe | 22 |

### Per-app usable session counts

| app_id | n |
|--------|--:|
| InfinityLoop1309.NewPipeEnhanced | 7 |
| a2dp.Vol | 3 |
| ac.robinson.mediaphone | 9 |
| ademar.bitac | 2 |
| agrigolo.opendrummer | 3 |
| ai.susi | 9 |
| anonvpn.anon_next.android | 7 |
| app.alextran.immich | 3 |
| app.comaps.fdroid | 7 |
| app.crescentcash.src | 3 |
| app.fedilab.castlab | 7 |
| app.fedilab.mobilizon | 3 |
| app.fedilab.nitterizeme | 9 |
| app.fedilab.nitterizemelite | 9 |
| app.hypostats | 3 |
| app.ladefuchs.android | 3 |
| app.michaelwuensch.bitbanana | 9 |
| app.notesr | 3 |
| app.organicmaps | 6 |
| app.pachli | 3 |
| app.prav.client | 9 |
| app.tice.TICE.production | 5 |
| app.tujice.jergasColombia | 9 |
| app.udderance | 3 |
| at.linuxtage.Eventfahrplan | 9 |
| at.manuelbichler.octalsuntime | 3 |
| at.mikenet.serbianlatintocyrillic | 5 |
| at.tomtasche.reader | 3 |
| au.com.wallaceit.reddinator | 9 |
| barilyuk.batterytemperature | 9 |
| be.digitalia.fosdem | 8 |
| be.humanoids.webthingify | 1 |
| be.mygod.vpnhotspot_foss | 8 |
| biz.binarysolutions.mindfulnessmeditation | 6 |
| biz.binarysolutions.stress | 3 |
| biz.binarysolutions.vatcalculator | 8 |
| bluepie.ad_silence | 8 |
| br.odb.knights | 3 |
| btools.routingapp | 3 |
| buet.rafi.dictionary | 3 |
| bus.chio.wishmaster | 8 |
| ca.andries.portknocker | 3 |
| ca.chancehorizon.paseo | 8 |
| ca.farrelltonsolar.classic | 8 |
| ca.momi.lift | 3 |
| ca.ramzan.delist | 3 |
| ca.rmen.android.frenchcalendar | 8 |
| ca.rmen.android.scrumchatter | 8 |
| ca.rmen.nounours | 8 |
| cat.jordihernandez.cinecat | 8 |
| cc.kafuu.bilidownload | 3 |
| cf.playhi.freezeyou | 8 |
| ch.abertschi.waterme.water_me | 3 |
| ch.bubendorf.locusaddon.gsakdatabase | 1 |
| ch.hgdev.toposuite | 7 |
| ch.joshuah.bibleverseapp | 8 |
| ch.mydoli.focal | 8 |
| cityfreqs.com.pilfershushjammer | 8 |
| cl.coders.faketraveler | 8 |

## Stage 1 — graph construction

| pin | value |
|-----|------:|
| k_burst | 5 |
| delta_sec | 5.0 |
| lambda_rec | 0.01 (source: abrg.config.LAMBDA_REC) |
| window_sec | 60.0 (multi-window cumulative) |
| normalize | shares_not_counts |
| static_mode | static_dynamic_fusion |
| apps static resolved | 59 |
| apps static fallback | 0 |

### Corpus graph statistics

- mapped_events: median=84 IQR=[26.75, 254] n=342
- n_active_nodes: median=3 IQR=[2, 4] n=342
- n_edges: median=2 IQR=[1, 6] n=342
- density: median=0.004329 IQR=[0.0021645, 0.012987] n=342

### Per-session graph stats

| app_id | export_dir_name | idx | mapped | active | edges | density | static |
|--------|-----------------|----:|-------:|-------:|------:|--------:|--------|
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s1__original | 1 | 388 | 6 | 16 | 0.034632 | True |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s2__original | 2 | 1329 | 6 | 25 | 0.0541126 | True |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s3__original | 3 | 360 | 5 | 14 | 0.030303 | True |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s6__extend | 6 | 656 | 5 | 9 | 0.0194805 | True |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s7__extend | 7 | 670 | 5 | 9 | 0.0194805 | True |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s8__extend | 8 | 656 | 5 | 9 | 0.0194805 | True |
| InfinityLoop1309.NewPipeEnhanced | b77ab89fd70e_llm_s9__extend | 9 | 607 | 5 | 9 | 0.0194805 | True |
| a2dp.Vol | f67ef52502fa_llm_s1__original | 1 | 2 | 1 | 0 | 0 | True |
| a2dp.Vol | f67ef52502fa_llm_s2__original | 2 | 2 | 1 | 0 | 0 | True |
| a2dp.Vol | f67ef52502fa_llm_s3__original | 3 | 2 | 1 | 0 | 0 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s1__original | 1 | 784 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s2__original | 2 | 760 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s3__original | 3 | 1034 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s4__extend | 4 | 771 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s5__extend | 5 | 1046 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s6__extend | 6 | 754 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s7__extend | 7 | 1028 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s8__extend | 8 | 841 | 4 | 9 | 0.0194805 | True |
| ac.robinson.mediaphone | 497e019dc8a1_llm_s9__extend | 9 | 1039 | 4 | 9 | 0.0194805 | True |
| ademar.bitac | 3f8f31a5b92b_llm_s1__original | 1 | 32 | 2 | 0 | 0 | True |
| ademar.bitac | 3f8f31a5b92b_llm_s2__original | 2 | 32 | 2 | 0 | 0 | True |
| agrigolo.opendrummer | 9347877bc340_llm_s1__original | 1 | 2 | 1 | 0 | 0 | True |
| agrigolo.opendrummer | 9347877bc340_llm_s2__original | 2 | 2 | 1 | 0 | 0 | True |
| agrigolo.opendrummer | 9347877bc340_llm_s3__original | 3 | 2 | 1 | 0 | 0 | True |
| ai.susi | 6f8510108099_llm_s1__original | 1 | 401 | 6 | 12 | 0.025974 | True |
| ai.susi | 6f8510108099_llm_s2__original | 2 | 408 | 6 | 14 | 0.030303 | True |
| ai.susi | 6f8510108099_llm_s3__original | 3 | 421 | 6 | 23 | 0.0497835 | True |
| ai.susi | 6f8510108099_llm_s1__canary | 4 | 348 | 6 | 12 | 0.025974 | True |
| ai.susi | 6f8510108099_llm_s5__extend | 5 | 420 | 6 | 14 | 0.030303 | True |
| ai.susi | 6f8510108099_llm_s6__extend | 6 | 368 | 6 | 20 | 0.04329 | True |
| ai.susi | 6f8510108099_llm_s7__extend | 7 | 69 | 5 | 10 | 0.021645 | True |
| ai.susi | 6f8510108099_llm_s8__extend | 8 | 74 | 5 | 16 | 0.034632 | True |
| ai.susi | 6f8510108099_llm_s9__extend | 9 | 69 | 5 | 10 | 0.021645 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s1__original | 1 | 24 | 4 | 4 | 0.00865801 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s2__original | 2 | 21 | 4 | 4 | 0.00865801 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s3__original | 3 | 23 | 4 | 4 | 0.00865801 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s6__extend | 6 | 19 | 4 | 4 | 0.00865801 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s7__extend | 7 | 23 | 4 | 4 | 0.00865801 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s8__extend | 8 | 20 | 4 | 4 | 0.00865801 | True |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s9__extend | 9 | 23 | 4 | 4 | 0.00865801 | True |
| app.alextran.immich | efcaf058dff9_llm_s1__original | 1 | 13 | 2 | 0 | 0 | True |
| app.alextran.immich | efcaf058dff9_llm_s2__original | 2 | 13 | 2 | 0 | 0 | True |
| app.alextran.immich | efcaf058dff9_llm_s3__original | 3 | 13 | 2 | 0 | 0 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s1__original | 1 | 160 | 5 | 8 | 0.017316 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s2__original | 2 | 148 | 5 | 7 | 0.0151515 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s3__original | 3 | 157 | 5 | 7 | 0.0151515 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s5__extend | 5 | 157 | 5 | 8 | 0.017316 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s6__extend | 6 | 157 | 5 | 7 | 0.0151515 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s7__extend | 7 | 241 | 3 | 1 | 0.0021645 | True |
| app.comaps.fdroid | 47d583fd8b06_llm_s8__extend | 8 | 221 | 3 | 1 | 0.0021645 | True |
| app.crescentcash.src | a02b64c18d0e_llm_s1__original | 1 | 6 | 1 | 0 | 0 | True |
| app.crescentcash.src | a02b64c18d0e_llm_s2__original | 2 | 6 | 1 | 0 | 0 | True |
| app.crescentcash.src | a02b64c18d0e_llm_s3__original | 3 | 6 | 1 | 0 | 0 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s1__original | 1 | 69 | 4 | 4 | 0.00865801 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s2__original | 2 | 92 | 4 | 4 | 0.00865801 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s3__original | 3 | 79 | 4 | 6 | 0.012987 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s4__extend | 4 | 48 | 3 | 2 | 0.004329 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s6__extend | 6 | 64 | 3 | 2 | 0.004329 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s7__extend | 7 | 65 | 3 | 2 | 0.004329 | True |
| app.fedilab.castlab | 5719f3b34f71_llm_s9__extend | 9 | 58 | 3 | 2 | 0.004329 | True |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s1__original | 1 | 127 | 5 | 15 | 0.0324675 | True |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s2__original | 2 | 127 | 5 | 14 | 0.030303 | True |
| app.fedilab.mobilizon | 9b7a3d5efee6_llm_s3__original | 3 | 127 | 5 | 14 | 0.030303 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s1__original | 1 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s2__original | 2 | 228 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s3__original | 3 | 168 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s4__extend | 4 | 168 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s5__extend | 5 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s6__extend | 6 | 170 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s7__extend | 7 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s8__extend | 8 | 226 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizeme | bcf251559ee4_llm_s9__extend | 9 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s1__original | 1 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s2__original | 2 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s3__original | 3 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s4__extend | 4 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s5__extend | 5 | 199 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s6__extend | 6 | 226 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s7__extend | 7 | 228 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s8__extend | 8 | 170 | 2 | 2 | 0.004329 | True |
| app.fedilab.nitterizemelite | 30ae40611f5f_llm_s9__extend | 9 | 199 | 2 | 2 | 0.004329 | True |
| app.hypostats | 56ba09e3fd7c_llm_s1__original | 1 | 2 | 1 | 0 | 0 | True |
| app.hypostats | 56ba09e3fd7c_llm_s2__original | 2 | 2 | 1 | 0 | 0 | True |
| app.hypostats | 56ba09e3fd7c_llm_s3__original | 3 | 2 | 1 | 0 | 0 | True |
| app.ladefuchs.android | 0f0dc4577a45_llm_s1__original | 1 | 106 | 3 | 3 | 0.00649351 | True |
| app.ladefuchs.android | 0f0dc4577a45_llm_s2__original | 2 | 101 | 3 | 3 | 0.00649351 | True |
| app.ladefuchs.android | 0f0dc4577a45_llm_s3__original | 3 | 113 | 3 | 3 | 0.00649351 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s1__original | 1 | 1941 | 3 | 5 | 0.0108225 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s2__original | 2 | 1941 | 3 | 5 | 0.0108225 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s3__original | 3 | 1941 | 3 | 5 | 0.0108225 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s4__extend | 4 | 1941 | 3 | 6 | 0.012987 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s5__extend | 5 | 1941 | 3 | 5 | 0.0108225 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s6__extend | 6 | 242 | 4 | 6 | 0.012987 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s7__extend | 7 | 421 | 3 | 5 | 0.0108225 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s8__extend | 8 | 243 | 4 | 5 | 0.0108225 | True |
| app.michaelwuensch.bitbanana | 36bdbc1733f0_llm_s9__extend | 9 | 256 | 4 | 5 | 0.0108225 | True |
| app.notesr | 3d3afadebd74_llm_s1__original | 1 | 2 | 1 | 0 | 0 | True |
| app.notesr | 3d3afadebd74_llm_s2__original | 2 | 1 | 1 | 0 | 0 | True |
| app.notesr | 3d3afadebd74_llm_s3__original | 3 | 2 | 1 | 0 | 0 | True |
| app.organicmaps | 4862fbeed029_llm_s1__original | 1 | 145 | 5 | 5 | 0.0108225 | True |
| app.organicmaps | 4862fbeed029_llm_s2__original | 2 | 142 | 5 | 5 | 0.0108225 | True |
| app.organicmaps | 4862fbeed029_llm_s3__original | 3 | 142 | 5 | 5 | 0.0108225 | True |
| app.organicmaps | 4862fbeed029_llm_s1__canary | 4 | 125 | 5 | 5 | 0.0108225 | True |
| app.organicmaps | 4862fbeed029_llm_s5__extend | 5 | 168 | 6 | 6 | 0.012987 | True |
| app.organicmaps | 4862fbeed029_llm_s6__extend | 6 | 168 | 5 | 5 | 0.0108225 | True |
| app.pachli | 6187300de1fe_llm_s1__original | 1 | 12 | 1 | 0 | 0 | True |
| app.pachli | 6187300de1fe_llm_s2__original | 2 | 12 | 1 | 0 | 0 | True |
| app.pachli | 6187300de1fe_llm_s3__original | 3 | 12 | 1 | 0 | 0 | True |
| app.prav.client | e4a6cdb972a2_llm_s1__original | 1 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s2__original | 2 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s3__original | 3 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s4__extend | 4 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s5__extend | 5 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s6__extend | 6 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s7__extend | 7 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s8__extend | 8 | 254 | 3 | 2 | 0.004329 | True |
| app.prav.client | e4a6cdb972a2_llm_s9__extend | 9 | 254 | 3 | 2 | 0.004329 | True |
| app.tice.TICE.production | 648d8ddb49f4_llm_s1__original | 1 | 833 | 4 | 3 | 0.00649351 | True |
| app.tice.TICE.production | 648d8ddb49f4_llm_s2__original | 2 | 780 | 7 | 6 | 0.012987 | True |
| app.tice.TICE.production | 648d8ddb49f4_llm_s3__original | 3 | 892 | 4 | 3 | 0.00649351 | True |
| app.tice.TICE.production | 648d8ddb49f4_llm_s4__extend | 4 | 722 | 7 | 11 | 0.0238095 | True |
| app.tice.TICE.production | 648d8ddb49f4_llm_s5__extend | 5 | 797 | 7 | 11 | 0.0238095 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s1__original | 1 | 11 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s2__original | 2 | 11 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s3__original | 3 | 12 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s4__extend | 4 | 9 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s5__extend | 5 | 11 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s6__extend | 6 | 11 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s7__extend | 7 | 10 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s8__extend | 8 | 12 | 3 | 1 | 0.0021645 | True |
| app.tujice.jergasColombia | ef6177e39b1d_llm_s9__extend | 9 | 12 | 3 | 1 | 0.0021645 | True |
| app.udderance | 2074fc55fb78_llm_s1__original | 1 | 170 | 3 | 1 | 0.0021645 | True |
| app.udderance | 2074fc55fb78_llm_s2__original | 2 | 169 | 3 | 1 | 0.0021645 | True |
| app.udderance | 2074fc55fb78_llm_s3__original | 3 | 170 | 3 | 1 | 0.0021645 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s1__original | 1 | 49 | 3 | 6 | 0.012987 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s2__original | 2 | 49 | 3 | 6 | 0.012987 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s3__original | 3 | 49 | 3 | 6 | 0.012987 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s4__extend | 4 | 49 | 2 | 0 | 0 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s5__extend | 5 | 48 | 2 | 0 | 0 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s6__extend | 6 | 48 | 3 | 6 | 0.012987 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s7__extend | 7 | 47 | 3 | 6 | 0.012987 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s8__extend | 8 | 48 | 3 | 6 | 0.012987 | True |
| at.linuxtage.Eventfahrplan | 84bca8b5903c_llm_s9__extend | 9 | 46 | 3 | 6 | 0.012987 | True |
| at.manuelbichler.octalsuntime | fe47baf78790_llm_s1__original | 1 | 48 | 2 | 0 | 0 | True |
| at.manuelbichler.octalsuntime | fe47baf78790_llm_s2__original | 2 | 48 | 2 | 0 | 0 | True |
| at.manuelbichler.octalsuntime | fe47baf78790_llm_s3__original | 3 | 48 | 2 | 0 | 0 | True |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s3__original | 1 | 34 | 2 | 2 | 0.004329 | True |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s2__extend | 2 | 35 | 2 | 2 | 0.004329 | True |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s3__extend | 3 | 36 | 2 | 2 | 0.004329 | True |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s5__extend | 5 | 37 | 2 | 2 | 0.004329 | True |
| at.mikenet.serbianlatintocyrillic | 4b633ea030db_llm_s7__extend | 7 | 35 | 2 | 2 | 0.004329 | True |
| at.tomtasche.reader | 407b766fceb3_llm_s1__original | 1 | 3 | 2 | 0 | 0 | True |
| at.tomtasche.reader | 407b766fceb3_llm_s2__original | 2 | 3 | 2 | 0 | 0 | True |
| at.tomtasche.reader | 407b766fceb3_llm_s3__original | 3 | 3 | 2 | 0 | 0 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s1__original | 1 | 45 | 3 | 3 | 0.00649351 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s2__original | 2 | 46 | 3 | 2 | 0.004329 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s3__original | 3 | 47 | 3 | 4 | 0.00865801 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s4__extend | 4 | 51 | 3 | 3 | 0.00649351 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s5__extend | 5 | 113 | 6 | 12 | 0.025974 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s6__extend | 6 | 47 | 3 | 3 | 0.00649351 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s7__extend | 7 | 45 | 3 | 3 | 0.00649351 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s8__extend | 8 | 47 | 3 | 3 | 0.00649351 | True |
| au.com.wallaceit.reddinator | c3751de467a1_llm_s9__extend | 9 | 45 | 3 | 4 | 0.00865801 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s1__original | 1 | 692 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s2__original | 2 | 696 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s3__original | 3 | 703 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s4__extend | 4 | 710 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s5__extend | 5 | 704 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s6__extend | 6 | 711 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s7__extend | 7 | 701 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s8__extend | 8 | 698 | 4 | 10 | 0.021645 | True |
| barilyuk.batterytemperature | 75dd71ae0f0a_llm_s9__extend | 9 | 725 | 4 | 10 | 0.021645 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s1__original | 1 | 46 | 2 | 2 | 0.004329 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s2__original | 2 | 56 | 2 | 2 | 0.004329 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s3__original | 3 | 44 | 2 | 1 | 0.0021645 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s4__extend | 4 | 16 | 2 | 2 | 0.004329 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s5__extend | 5 | 56 | 4 | 7 | 0.0151515 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s6__extend | 6 | 50 | 2 | 2 | 0.004329 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s7__extend | 7 | 52 | 2 | 2 | 0.004329 | True |
| be.digitalia.fosdem | 37b1a8bb28b9_llm_s8__extend | 8 | 52 | 2 | 2 | 0.004329 | True |
| be.humanoids.webthingify | 4bb0adc701ab_llm_s1__original | 1 | 7 | 1 | 0 | 0 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s1__original | 1 | 1674 | 4 | 10 | 0.021645 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s2__original | 2 | 1691 | 4 | 10 | 0.021645 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s3__original | 3 | 1657 | 4 | 11 | 0.0238095 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s4__extend | 4 | 1696 | 4 | 10 | 0.021645 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s5__extend | 5 | 1696 | 4 | 10 | 0.021645 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s6__extend | 6 | 1673 | 4 | 11 | 0.0238095 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s7__extend | 7 | 1717 | 4 | 11 | 0.0238095 | True |
| be.mygod.vpnhotspot_foss | a72518537ed0_llm_s8__extend | 8 | 1693 | 4 | 10 | 0.021645 | True |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s1__original | 1 | 10 | 3 | 3 | 0.00649351 | True |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s2__original | 2 | 10 | 3 | 3 | 0.00649351 | True |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s3__original | 3 | 10 | 3 | 3 | 0.00649351 | True |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s6__extend | 6 | 10 | 3 | 3 | 0.00649351 | True |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s7__extend | 7 | 10 | 3 | 3 | 0.00649351 | True |
| biz.binarysolutions.mindfulnessmeditation | fba1483a8a4d_llm_s8__extend | 8 | 10 | 3 | 3 | 0.00649351 | True |
| biz.binarysolutions.stress | a79d40377e87_llm_s1__original | 1 | 4 | 2 | 0 | 0 | True |
| biz.binarysolutions.stress | a79d40377e87_llm_s2__original | 2 | 4 | 2 | 0 | 0 | True |
| biz.binarysolutions.stress | a79d40377e87_llm_s3__original | 3 | 4 | 2 | 0 | 0 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s1__original | 1 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s2__original | 2 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s3__original | 3 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s4__extend | 4 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s5__extend | 5 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s6__extend | 6 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s7__extend | 7 | 10 | 2 | 1 | 0.0021645 | True |
| biz.binarysolutions.vatcalculator | bec3b8076c0f_llm_s8__extend | 8 | 10 | 2 | 1 | 0.0021645 | True |
| bluepie.ad_silence | c134927f92ec_llm_s1__original | 1 | 15 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s2__original | 2 | 17 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s3__original | 3 | 15 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s4__extend | 4 | 15 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s5__extend | 5 | 15 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s6__extend | 6 | 15 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s7__extend | 7 | 17 | 2 | 2 | 0.004329 | True |
| bluepie.ad_silence | c134927f92ec_llm_s8__extend | 8 | 15 | 2 | 2 | 0.004329 | True |
| br.odb.knights | 12a4c95ef388_llm_s1__original | 1 | 388 | 2 | 0 | 0 | True |
| br.odb.knights | 12a4c95ef388_llm_s2__original | 2 | 388 | 2 | 0 | 0 | True |
| br.odb.knights | 12a4c95ef388_llm_s3__original | 3 | 388 | 2 | 0 | 0 | True |
| btools.routingapp | ef0f40be1b94_llm_s1__original | 1 | 71 | 1 | 0 | 0 | True |
| btools.routingapp | ef0f40be1b94_llm_s2__original | 2 | 72 | 1 | 0 | 0 | True |
| btools.routingapp | ef0f40be1b94_llm_s3__original | 3 | 68 | 1 | 0 | 0 | True |
| buet.rafi.dictionary | 33f4266b15fd_llm_s1__original | 1 | 5 | 1 | 0 | 0 | True |
| buet.rafi.dictionary | 33f4266b15fd_llm_s2__original | 2 | 5 | 1 | 0 | 0 | True |
| buet.rafi.dictionary | 33f4266b15fd_llm_s3__original | 3 | 5 | 1 | 0 | 0 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s1__original | 1 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s2__original | 2 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s3__original | 3 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s4__extend | 4 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s5__extend | 5 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s6__extend | 6 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s7__extend | 7 | 52 | 2 | 1 | 0.0021645 | True |
| bus.chio.wishmaster | 39f811f07c23_llm_s8__extend | 8 | 52 | 2 | 1 | 0.0021645 | True |
| ca.andries.portknocker | f54d6d05f299_llm_s1__original | 1 | 4 | 1 | 0 | 0 | True |
| ca.andries.portknocker | f54d6d05f299_llm_s2__original | 2 | 4 | 1 | 0 | 0 | True |
| ca.andries.portknocker | f54d6d05f299_llm_s3__original | 3 | 4 | 1 | 0 | 0 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s1__original | 1 | 115 | 5 | 12 | 0.025974 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s2__original | 2 | 109 | 5 | 14 | 0.030303 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s3__original | 3 | 125 | 5 | 12 | 0.025974 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s4__extend | 4 | 106 | 5 | 12 | 0.025974 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s5__extend | 5 | 91 | 5 | 14 | 0.030303 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s6__extend | 6 | 88 | 5 | 12 | 0.025974 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s7__extend | 7 | 103 | 5 | 12 | 0.025974 | True |
| ca.chancehorizon.paseo | e271584cf787_llm_s8__extend | 8 | 88 | 5 | 12 | 0.025974 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s1__original | 1 | 134 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s2__original | 2 | 138 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s3__original | 3 | 130 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s4__extend | 4 | 154 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s5__extend | 5 | 186 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s6__extend | 6 | 170 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s7__extend | 7 | 174 | 3 | 5 | 0.0108225 | True |
| ca.farrelltonsolar.classic | 2d767cdb301f_llm_s8__extend | 8 | 170 | 3 | 5 | 0.0108225 | True |
| ca.momi.lift | 59ee61acbb1b_llm_s1__original | 1 | 6 | 1 | 0 | 0 | True |
| ca.momi.lift | 59ee61acbb1b_llm_s2__original | 2 | 6 | 1 | 0 | 0 | True |
| ca.momi.lift | 59ee61acbb1b_llm_s3__original | 3 | 6 | 1 | 0 | 0 | True |
| ca.ramzan.delist | 12d9ef307c03_llm_s1__original | 1 | 8 | 1 | 0 | 0 | True |
| ca.ramzan.delist | 12d9ef307c03_llm_s2__original | 2 | 8 | 1 | 0 | 0 | True |
| ca.ramzan.delist | 12d9ef307c03_llm_s3__original | 3 | 8 | 1 | 0 | 0 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s1__original | 1 | 95 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s2__original | 2 | 104 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s3__original | 3 | 103 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s4__extend | 4 | 103 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s5__extend | 5 | 103 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s6__extend | 6 | 104 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s7__extend | 7 | 103 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.frenchcalendar | 5e76f97d0425_llm_s8__extend | 8 | 95 | 2 | 1 | 0.0021645 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s1__original | 1 | 151 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s2__original | 2 | 187 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s3__original | 3 | 186 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s4__extend | 4 | 185 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s5__extend | 5 | 150 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s6__extend | 6 | 185 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s7__extend | 7 | 185 | 3 | 6 | 0.012987 | True |
| ca.rmen.android.scrumchatter | 7603ad0544fe_llm_s8__extend | 8 | 185 | 3 | 6 | 0.012987 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s1__original | 1 | 474 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s2__original | 2 | 661 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s3__original | 3 | 498 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s4__extend | 4 | 498 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s5__extend | 5 | 494 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s6__extend | 6 | 586 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s7__extend | 7 | 503 | 2 | 2 | 0.004329 | True |
| ca.rmen.nounours | 0e7da7b17b63_llm_s8__extend | 8 | 507 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s1__original | 1 | 42 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s2__original | 2 | 42 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s3__original | 3 | 42 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s4__extend | 4 | 56 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s5__extend | 5 | 58 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s6__extend | 6 | 43 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s7__extend | 7 | 43 | 2 | 2 | 0.004329 | True |
| cat.jordihernandez.cinecat | 24e9101cdb34_llm_s8__extend | 8 | 43 | 2 | 2 | 0.004329 | True |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s1__original | 1 | 8 | 3 | 1 | 0.0021645 | True |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s2__original | 2 | 8 | 3 | 1 | 0.0021645 | True |
| cc.kafuu.bilidownload | 64de55f0293d_llm_s3__original | 3 | 8 | 3 | 1 | 0.0021645 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s1__original | 1 | 267 | 4 | 6 | 0.012987 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s2__original | 2 | 267 | 4 | 6 | 0.012987 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s3__original | 3 | 267 | 4 | 5 | 0.0108225 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s4__extend | 4 | 268 | 4 | 6 | 0.012987 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s5__extend | 5 | 268 | 4 | 6 | 0.012987 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s6__extend | 6 | 268 | 4 | 6 | 0.012987 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s7__extend | 7 | 268 | 4 | 6 | 0.012987 | True |
| cf.playhi.freezeyou | 86b80fef253c_llm_s8__extend | 8 | 268 | 4 | 6 | 0.012987 | True |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s1__original | 1 | 12 | 2 | 2 | 0.004329 | True |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s3__original | 2 | 12 | 2 | 2 | 0.004329 | True |
| ch.abertschi.waterme.water_me | d42d78005adb_llm_s5__extend | 5 | 7 | 2 | 2 | 0.004329 | True |
| ch.bubendorf.locusaddon.gsakdatabase | 3eae0c6f3334_llm_s1__original | 1 | 183 | 1 | 0 | 0 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s1__original | 1 | 224 | 2 | 1 | 0.0021645 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s3__original | 2 | 224 | 2 | 1 | 0.0021645 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s3__extend | 3 | 215 | 2 | 1 | 0.0021645 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s4__extend | 4 | 224 | 2 | 1 | 0.0021645 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s5__extend | 5 | 224 | 2 | 1 | 0.0021645 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s6__extend | 6 | 224 | 2 | 1 | 0.0021645 | True |
| ch.hgdev.toposuite | 05e3f19e2717_llm_s7__extend | 7 | 308 | 2 | 1 | 0.0021645 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s1__original | 1 | 74 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s2__original | 2 | 74 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s3__original | 3 | 80 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s4__extend | 4 | 75 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s5__extend | 5 | 75 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s6__extend | 6 | 75 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s7__extend | 7 | 80 | 2 | 2 | 0.004329 | True |
| ch.joshuah.bibleverseapp | 18aff8885c8c_llm_s8__extend | 8 | 74 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s1__original | 1 | 59 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s2__original | 2 | 59 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s3__original | 3 | 59 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s4__extend | 4 | 59 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s5__extend | 5 | 58 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s6__extend | 6 | 50 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s7__extend | 7 | 58 | 2 | 2 | 0.004329 | True |
| ch.mydoli.focal | bbf18ac3b134_llm_s8__extend | 8 | 50 | 2 | 2 | 0.004329 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s1__original | 1 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s2__original | 2 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s3__original | 3 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s4__extend | 4 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s5__extend | 5 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s6__extend | 6 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s7__extend | 7 | 29 | 5 | 3 | 0.00649351 | True |
| cityfreqs.com.pilfershushjammer | c7c04de887f3_llm_s8__extend | 8 | 26 | 4 | 2 | 0.004329 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s1__original | 1 | 558 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s2__original | 2 | 558 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s3__original | 3 | 558 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s4__extend | 4 | 654 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s5__extend | 5 | 632 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s6__extend | 6 | 558 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s7__extend | 7 | 584 | 4 | 10 | 0.021645 | True |
| cl.coders.faketraveler | fb32bae7e64d_llm_s8__extend | 8 | 558 | 4 | 10 | 0.021645 | True |

### δ retention

- k_burst=5 delta_sec=5.0
- n_k_candidates=91816
- n_delta_retained=76970
- retention_overall=0.838307

| quartile | n_events_lo | n_events_hi | n_sessions | retention |
|---------:|------------:|------------:|-----------:|----------:|
| 1 | 1 | 26 | 86 | 0.272468 |
| 2 | 29 | 80 | 85 | 0.446296 |
| 3 | 88 | 254 | 86 | 0.671901 |
| 4 | 254 | 1941 | 85 | 0.905178 |

- fitted_model=a - b*exp(-c*n) fit_ok=True
- params={'a': 0.9412412198869295, 'b': 0.6669854874935399, 'c': 0.0022845582542341744}
- retention_at_5k=0.941234 at_10k=0.941241 at_50k=0.941241

## Stage 2 — reference convergence

- reference_combine: `equal_mean_normalised_session_tensors`
- justification: Each session graph is built independently with timed update_graph, then converted to a shares-not-counts dense tensor. R_k is the equal-weight arithmetic mean of session tensors 1..k. Sessions contribute equally (event-count does not overweight long traces); distances stay on the normalised scale used for GAE feeds; Stage-3 channel variants differ only in which adjacency channel(s) enter the tensor.
- channel (primary): both
- primary_metric: frobenius_combined
- n_apps: 35
- n_never_stabilise: 24
- never_stabilise_apps: ['ac.robinson.mediaphone', 'app.comaps.fdroid', 'app.fedilab.castlab', 'app.fedilab.nitterizeme', 'app.fedilab.nitterizemelite', 'app.michaelwuensch.bitbanana', 'app.prav.client', 'app.tice.TICE.production', 'app.tujice.jergasColombia', 'at.linuxtage.Eventfahrplan', 'at.mikenet.serbianlatintocyrillic', 'au.com.wallaceit.reddinator', 'barilyuk.batterytemperature', 'be.digitalia.fosdem', 'biz.binarysolutions.mindfulnessmeditation', 'biz.binarysolutions.vatcalculator', 'bus.chio.wishmaster', 'ca.farrelltonsolar.classic', 'cf.playhi.freezeyou', 'ch.hgdev.toposuite', 'ch.joshuah.bibleverseapp', 'ch.mydoli.focal', 'cityfreqs.com.pilfershushjammer', 'cl.coders.faketraveler']
- stabilisation_k: median=4 IQR=[3, 5.5] n=11
- pooled Spearman e vs k: {'n_pairs': 240, 'p': 0.018967715589492416, 'rho': 0.15136094900580135}
- Wilcoxon first>last held-out: {'alternative': 'first_gt_last', 'n': 35, 'p': 0.9946693338570185, 'statistic': 162.0}

### Pooled drift band

| k | median | q1 | q3 |
|--:|-------:|---:|---:|
| 1.0 | 0.401879 | 0.00809035 | 2.08321 |
| 2.0 | 0.318138 | 0.0183786 | 2.16473 |
| 3.0 | 0.275665 | 0.0434527 | 5.84197 |
| 4.0 | 0.4758 | 0.0497034 | 1.96119 |
| 5.0 | 0.308844 | 0.0401807 | 1.91496 |
| 6.0 | 0.209722 | 0.0292706 | 2.38837 |
| 7.0 | 0.235823 | 0.013808 | 2.85499 |
| 8.0 | 1.17468 | 0.135583 | 7.59928 |

### Pooled held-out band

| k | median | q1 | q3 |
|--:|-------:|---:|---:|
| 1.0 | 0.803758 | 0.0161807 | 4.16641 |
| 2.0 | 0.954414 | 0.0551357 | 6.4942 |
| 3.0 | 1.10266 | 0.173811 | 23.3679 |
| 4.0 | 2.379 | 0.248517 | 9.80597 |
| 5.0 | 1.85307 | 0.241084 | 11.4898 |
| 6.0 | 1.46806 | 0.204894 | 16.7186 |
| 7.0 | 1.88658 | 0.110464 | 22.8399 |
| 8.0 | 10.5722 | 1.22025 | 68.3935 |

### Per-app stabilisation k and Spearman

| app_id | stab_k | spearman_rho | spearman_p | n_sessions |
|--------|-------:|-------------:|-----------:|-----------:|
| InfinityLoop1309.NewPipeEnhanced | 4 | -0.942857 | 0.00480466 | 7 |
| ac.robinson.mediaphone | None | 0.047619 | 0.910849 | 9 |
| ai.susi | 5 | 0.5 | 0.207031 | 9 |
| anonvpn.anon_next.android | 3 | -0.6 | 0.208 | 7 |
| app.comaps.fdroid | None | 0.371429 | 0.468478 | 7 |
| app.fedilab.castlab | None | 0.257143 | 0.622787 | 7 |
| app.fedilab.nitterizeme | None | -0.333333 | 0.419753 | 9 |
| app.fedilab.nitterizemelite | None | 0.452381 | 0.260405 | 9 |
| app.michaelwuensch.bitbanana | None | 0.809524 | 0.0149027 | 9 |
| app.organicmaps | 3 | 0.5 | 0.391002 | 6 |
| app.prav.client | None | 0.166667 | 0.693239 | 9 |
| app.tice.TICE.production | None | 0.6 | 0.4 | 5 |
| app.tujice.jergasColombia | None | 0.452381 | 0.260405 | 9 |
| at.linuxtage.Eventfahrplan | None | 0.190476 | 0.651401 | 9 |
| at.mikenet.serbianlatintocyrillic | None | 0.8 | 0.2 | 5 |
| au.com.wallaceit.reddinator | None | 0.142857 | 0.735765 | 9 |
| barilyuk.batterytemperature | None | 0.404762 | 0.319889 | 9 |
| be.digitalia.fosdem | None | 0.107143 | 0.819151 | 8 |
| be.mygod.vpnhotspot_foss | 4 | -0.107143 | 0.819151 | 8 |
| biz.binarysolutions.mindfulnessmeditation | None | -0.2 | 0.74706 | 6 |
| biz.binarysolutions.vatcalculator | None | 0.321429 | 0.482072 | 8 |
| bluepie.ad_silence | 6 | -0.75 | 0.0521814 | 8 |
| bus.chio.wishmaster | None | 0.642857 | 0.119392 | 8 |
| ca.chancehorizon.paseo | 6 | -0.5 | 0.25317 | 8 |
| ca.farrelltonsolar.classic | None | -0.214286 | 0.644512 | 8 |
| ca.rmen.android.frenchcalendar | 3 | 0 | 1 | 8 |
| ca.rmen.android.scrumchatter | 6 | -0.642857 | 0.119392 | 8 |
| ca.rmen.nounours | 5 | -0.892857 | 0.00680719 | 8 |
| cat.jordihernandez.cinecat | 2 | 0.25 | 0.588724 | 8 |
| cf.playhi.freezeyou | None | 0.571429 | 0.180202 | 8 |
| ch.hgdev.toposuite | None | 0.428571 | 0.396501 | 7 |
| ch.joshuah.bibleverseapp | None | 0.285714 | 0.534509 | 8 |
| ch.mydoli.focal | None | 0.25 | 0.588724 | 8 |
| cityfreqs.com.pilfershushjammer | None | 0.892857 | 0.00680719 | 8 |
| cl.coders.faketraveler | None | 0.285714 | 0.534509 | 8 |

### Shuffled-session-order control (5 seeds)

- seed=0 n_never_stabilise=19 stab_k=median=4 IQR=[3, 5] n=16 wilcoxon={'alternative': 'first_gt_last', 'n': 35, 'p': 0.5418566310254391, 'statistic': 309.0}
  heldout_medians_by_k=[(1.0, '0.873489'), (2.0, '1.42761'), (3.0, '1.85309'), (4.0, '1.58188'), (5.0, '1.10986'), (6.0, '1.58622'), (7.0, '1.29032'), (8.0, '8.95238')]
- seed=1 n_never_stabilise=21 stab_k=median=5 IQR=[3.25, 5.75] n=14 wilcoxon={'alternative': 'first_gt_last', 'n': 35, 'p': 0.5610507224628236, 'statistic': 306.0}
  heldout_medians_by_k=[(1.0, '1.2694'), (2.0, '1.34669'), (3.0, '1.39726'), (4.0, '0.828783'), (5.0, '1.22734'), (6.0, '1.52098'), (7.0, '2.1536'), (8.0, '11.3084')]
- seed=2 n_never_stabilise=21 stab_k=median=5.5 IQR=[4.25, 6.75] n=14 wilcoxon={'alternative': 'first_gt_last', 'n': 35, 'p': 0.3579155042534694, 'statistic': 338.0}
  heldout_medians_by_k=[(1.0, '0.865011'), (2.0, '1.29564'), (3.0, '1.31576'), (4.0, '1.00407'), (5.0, '1.12674'), (6.0, '1.55672'), (7.0, '1.36817'), (8.0, '17.1329')]
- seed=3 n_never_stabilise=22 stab_k=median=4 IQR=[3, 7] n=13 wilcoxon={'alternative': 'first_gt_last', 'n': 35, 'p': 0.28821350799989887, 'statistic': 350.0}
  heldout_medians_by_k=[(1.0, '2.59867'), (2.0, '1.53208'), (3.0, '2.13815'), (4.0, '1.95169'), (5.0, '1.18841'), (6.0, '1.6022'), (7.0, '1.12145'), (8.0, '9.16106')]
- seed=4 n_never_stabilise=20 stab_k=median=4 IQR=[4, 7] n=15 wilcoxon={'alternative': 'first_gt_last', 'n': 35, 'p': 0.11271478701382875, 'statistic': 390.0}
  heldout_medians_by_k=[(1.0, '1.02339'), (2.0, '1.6865'), (3.0, '1.28057'), (4.0, '1.55949'), (5.0, '1.33004'), (6.0, '1.75439'), (7.0, '1.37936'), (8.0, '7.00581')]

### Cross-app control

- within_app: median=1.28314 IQR=[0.141152, 15.1735] n=240
- cross_app: median=38.3165 IQR=[15.1148, 86.2302] n=9350
- Mann-Whitney U: {'U': 354425.0, 'alternative': 'within_lt_cross', 'p': 1.0195951462519772e-73}

## Stage 3 — recency vs memory

- criterion (declared): primary=within_vs_cross_separation (Mann-Whitney U direction: within error < cross error, larger effect preferred); secondary=faster_stabilisation (smaller median stabilisation k).
- lambda_rec pin: 0.01

### Variant `both`
- stab_k: median=4 IQR=[3, 5.5] n=11
- n_never_stabilise: 24
- within: median=1.28314 IQR=[0.141152, 15.1735] n=240
- cross: median=38.3165 IQR=[15.1148, 86.2302] n=9350
- Mann-Whitney: {'U': 354425.0, 'alternative': 'within_lt_cross', 'p': 1.0195951462519772e-73}
- separation (cross_med − within_med): 37.0333

### Variant `w_cum`
- stab_k: median=4 IQR=[3, 5.5] n=11
- n_never_stabilise: 24
- within: median=1.23577 IQR=[0.141152, 15.0914] n=240
- cross: median=38.2711 IQR=[14.9895, 86.2144] n=9350
- Mann-Whitney: {'U': 355417.0, 'alternative': 'within_lt_cross', 'p': 1.560435052049075e-73}
- separation (cross_med − within_med): 37.0353

### Variant `w_rec`
- stab_k: median=4 IQR=[3, 5.5] n=11
- n_never_stabilise: 24
- within: median=1.24056 IQR=[0.141152, 15.1302] n=240
- cross: median=38.2693 IQR=[15.0043, 86.2144] n=9350
- Mann-Whitney: {'U': 355503.0, 'alternative': 'within_lt_cross', 'p': 1.619037952340308e-73}
- separation (cross_med − within_med): 37.0287

### Pairwise per-app deltas

- w_rec_minus_w_cum: median_delta=median=0 IQR=[0, 0.000503108] n=35
  wins_a=4 wins_b=16 ties=15 win_rate_a_lower=0.114286 wilcoxon={'p': 0.022768743718921815, 'statistic': 44.0}
  per_app_median_delta:
  - InfinityLoop1309.NewPipeEnhanced: 0.000102736
  - ac.robinson.mediaphone: 1.00004e-05
  - ai.susi: 0.000843247
  - anonvpn.anon_next.android: -0.000993994
  - app.comaps.fdroid: 0.00623077
  - app.fedilab.castlab: 0.0136931
  - app.fedilab.nitterizeme: 0
  - app.fedilab.nitterizemelite: 0
  - app.michaelwuensch.bitbanana: 0.00016297
  - app.organicmaps: -0.00782827
  - app.prav.client: 0
  - app.tice.TICE.production: 0.000922709
  - app.tujice.jergasColombia: 0
  - at.linuxtage.Eventfahrplan: -1.21065e-06
  - at.mikenet.serbianlatintocyrillic: 0
  - au.com.wallaceit.reddinator: 0.00558996
  - barilyuk.batterytemperature: 0.000102916
  - be.digitalia.fosdem: 0.00897461
  - be.mygod.vpnhotspot_foss: 3.90385e-05
  - biz.binarysolutions.mindfulnessmeditation: 1.45597e-08
  - biz.binarysolutions.vatcalculator: 0
  - bluepie.ad_silence: 0
  - bus.chio.wishmaster: 0
  - ca.chancehorizon.paseo: 0.00241219
  - ca.farrelltonsolar.classic: 3.5181e-05
  - ca.rmen.android.frenchcalendar: 0
  - ca.rmen.android.scrumchatter: 0.00151422
  - ca.rmen.nounours: 0
  - cat.jordihernandez.cinecat: 0
  - cf.playhi.freezeyou: -0.00261215
  - ch.hgdev.toposuite: 0
  - ch.joshuah.bibleverseapp: 0
  - ch.mydoli.focal: 0
  - cityfreqs.com.pilfershushjammer: 0
  - cl.coders.faketraveler: 0.0118652
- both_minus_w_cum: median_delta=median=0.000120237 IQR=[0, 0.00324388] n=35
  wins_a=0 wins_b=20 ties=15 win_rate_a_lower=0 wilcoxon={'p': 8.857457687863549e-05, 'statistic': 0.0}
  per_app_median_delta:
  - InfinityLoop1309.NewPipeEnhanced: 0.00256026
  - ac.robinson.mediaphone: 1.53717e-05
  - ai.susi: 0.0222883
  - anonvpn.anon_next.android: 0.000797102
  - app.comaps.fdroid: 0.295346
  - app.fedilab.castlab: 0.035282
  - app.fedilab.nitterizeme: 0
  - app.fedilab.nitterizemelite: 0
  - app.michaelwuensch.bitbanana: 0.000444432
  - app.organicmaps: 0.000773821
  - app.prav.client: 0
  - app.tice.TICE.production: 0.175283
  - app.tujice.jergasColombia: 0
  - at.linuxtage.Eventfahrplan: 0.00363381
  - at.mikenet.serbianlatintocyrillic: 0
  - au.com.wallaceit.reddinator: 0.04841
  - barilyuk.batterytemperature: 0.000120237
  - be.digitalia.fosdem: 0.105626
  - be.mygod.vpnhotspot_foss: 0.000182032
  - biz.binarysolutions.mindfulnessmeditation: 1.45597e-08
  - biz.binarysolutions.vatcalculator: 0
  - bluepie.ad_silence: 0
  - bus.chio.wishmaster: 0
  - ca.chancehorizon.paseo: 0.00285396
  - ca.farrelltonsolar.classic: 0.000137934
  - ca.rmen.android.frenchcalendar: 0
  - ca.rmen.android.scrumchatter: 0.0017012
  - ca.rmen.nounours: 0
  - cat.jordihernandez.cinecat: 0
  - cf.playhi.freezeyou: 0.0478179
  - ch.hgdev.toposuite: 0
  - ch.joshuah.bibleverseapp: 0
  - ch.mydoli.focal: 0
  - cityfreqs.com.pilfershushjammer: 0
  - cl.coders.faketraveler: 0.0134822
- both_minus_w_rec: median_delta=median=9.14057e-06 IQR=[0, 0.00314245] n=35
  wins_a=0 wins_b=19 ties=16 win_rate_a_lower=0 wilcoxon={'p': 0.0001318338889828333, 'statistic': 0.0}
  per_app_median_delta:
  - InfinityLoop1309.NewPipeEnhanced: 0.00260409
  - ac.robinson.mediaphone: 5.59485e-06
  - ai.susi: 0.0150433
  - anonvpn.anon_next.android: 0.0017911
  - app.comaps.fdroid: 0.290968
  - app.fedilab.castlab: 0.0215889
  - app.fedilab.nitterizeme: 0
  - app.fedilab.nitterizemelite: 0
  - app.michaelwuensch.bitbanana: 7.26406e-05
  - app.organicmaps: 0.0398756
  - app.prav.client: 0
  - app.tice.TICE.production: 0.174362
  - app.tujice.jergasColombia: 0
  - at.linuxtage.Eventfahrplan: 0.0036808
  - at.mikenet.serbianlatintocyrillic: 0
  - au.com.wallaceit.reddinator: 0.0794747
  - barilyuk.batterytemperature: 9.14057e-06
  - be.digitalia.fosdem: 0.0825448
  - be.mygod.vpnhotspot_foss: 0.000107435
  - biz.binarysolutions.mindfulnessmeditation: 0
  - biz.binarysolutions.vatcalculator: 0
  - bluepie.ad_silence: 0
  - bus.chio.wishmaster: 0
  - ca.chancehorizon.paseo: 0.000254401
  - ca.farrelltonsolar.classic: 6.16968e-05
  - ca.rmen.android.frenchcalendar: 0
  - ca.rmen.android.scrumchatter: 0.000131398
  - ca.rmen.nounours: 0
  - cat.jordihernandez.cinecat: 0
  - cf.playhi.freezeyou: 0.0504301
  - ch.hgdev.toposuite: 0
  - ch.joshuah.bibleverseapp: 0
  - ch.mydoli.focal: 0
  - cityfreqs.com.pilfershushjammer: 0
  - cl.coders.faketraveler: 0.00108987

### λ_rec sweep (channel=both)

| lambda_rec | stab_k_med | n_never | within_med | cross_med | sep |
|-----------:|-----------:|--------:|-----------:|----------:|----:|
| 0.001 | 4 | 24 | 4.08307 | 139.493 | 135.41 |
| 0.01 | 4 | 24 | 1.28314 | 38.3165 | 37.0333 |
| 0.05 | 4 | 27 | 0.542284 | 22.819 | 22.2767 |
| 0.1 | 5 | 26 | 0.500731 | 21.6616 | 21.1609 |

## Stage 4 — cold start

- e(R_1,S_2): median=0.803758 IQR=[0.0161807, 4.16641] n=35
- k to within 10% of final e: median=6 IQR=[4, 7.5] n=35
- n_never_reach_10pct: 0
- Spearman median_active_nodes vs stab_k: {'n': 11, 'p': 0.7348554010039637, 'rho': 0.11567104625085119}
- Spearman median_edges vs stab_k: {'n': 11, 'p': 0.23610552340739765, 'rho': 0.3897100174581493}

| app_id | e(R1,S2) | k_to_10pct |
|--------|---------:|-----------:|
| InfinityLoop1309.NewPipeEnhanced | 1144.66 | 4 |
| ac.robinson.mediaphone | 17.6963 | 8 |
| ai.susi | 19.9007 | 3 |
| anonvpn.anon_next.android | 1.11648 | 6 |
| app.comaps.fdroid | 1.81347 | 6 |
| app.fedilab.castlab | 8.06505 | 6 |
| app.fedilab.nitterizeme | 0.150142 | 8 |
| app.fedilab.nitterizemelite | 0.0400467 | 8 |
| app.michaelwuensch.bitbanana | 0.553499 | 8 |
| app.organicmaps | 1.24873 | 5 |
| app.prav.client | 0.0139009 | 8 |
| app.tice.TICE.production | 1.82014 | 4 |
| app.tujice.jergasColombia | 0.0152461 | 8 |
| at.linuxtage.Eventfahrplan | 3.53618 | 8 |
| at.mikenet.serbianlatintocyrillic | 0.409801 | 4 |
| au.com.wallaceit.reddinator | 0.803758 | 8 |
| barilyuk.batterytemperature | 19.72 | 8 |
| be.digitalia.fosdem | 0.0818267 | 2 |
| be.mygod.vpnhotspot_foss | 60.6515 | 2 |
| biz.binarysolutions.mindfulnessmeditation | 0.0103969 | 4 |
| biz.binarysolutions.vatcalculator | 0.000280529 | 5 |
| bluepie.ad_silence | 1.07163 | 7 |
| bus.chio.wishmaster | 0.0171153 | 7 |
| ca.chancehorizon.paseo | 51.369 | 3 |
| ca.farrelltonsolar.classic | 1.25907 | 6 |
| ca.rmen.android.frenchcalendar | 2.35193 | 7 |
| ca.rmen.android.scrumchatter | 35.0283 | 2 |
| ca.rmen.nounours | 0.792841 | 7 |
| cat.jordihernandez.cinecat | 0.00481684 | 7 |
| cf.playhi.freezeyou | 0.251528 | 5 |
| ch.hgdev.toposuite | 6.01463e-07 | 6 |
| ch.joshuah.bibleverseapp | 7.10496e-07 | 3 |
| ch.mydoli.focal | 6.71212e-06 | 7 |
| cityfreqs.com.pilfershushjammer | 0.000133816 | 7 |
| cl.coders.faketraveler | 4.79665 | 7 |

## Exclusions

- reference_tier_fail:InfinityLoop1309.NewPipeEnhanced/b77ab89fd70e_llm_s4__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:InfinityLoop1309.NewPipeEnhanced/b77ab89fd70e_llm_s5__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:anonvpn.anon_next.android/2f4839ccdb6e_llm_s4__extend:analyze_status:failed_frida_reattach,sim_not_success
- reference_tier_fail:anonvpn.anon_next.android/2f4839ccdb6e_llm_s5__extend:analyze_status:failed_frida_reattach,sim_not_success
- reference_tier_fail:app.comaps.fdroid/47d583fd8b06_llm_s1__canary:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:app.comaps.fdroid/47d583fd8b06_llm_s9__extend:flailing:same_element_cycle: screen hash b17834b15c17… dominates (81%) and top named target repeated 41/50 times
- reference_tier_fail:app.fedilab.castlab/5719f3b34f71_llm_s5__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:app.fedilab.castlab/5719f3b34f71_llm_s8__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:app.fedilab.mobilizon/9b7a3d5efee6_llm_s4__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:app.fedilab.mobilizon/9b7a3d5efee6_llm_s5__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:app.fedilab.mobilizon/9b7a3d5efee6_llm_s6__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.fedilab.mobilizon/9b7a3d5efee6_llm_s7__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.fedilab.mobilizon/9b7a3d5efee6_llm_s8__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.fedilab.mobilizon/9b7a3d5efee6_llm_s9__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.ladefuchs.android/0f0dc4577a45_llm_s4__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:app.ladefuchs.android/0f0dc4577a45_llm_s5__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:app.ladefuchs.android/0f0dc4577a45_llm_s6__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.ladefuchs.android/0f0dc4577a45_llm_s7__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.ladefuchs.android/0f0dc4577a45_llm_s8__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.ladefuchs.android/0f0dc4577a45_llm_s9__extend:analyze_status:partial:ux_quality_gate,sim_not_success
- reference_tier_fail:app.organicmaps/4862fbeed029_llm_s7__extend:analyze_status:partial:bad_handoff,sim_not_success,flailing:same_element_cycle: screen hash 29d9dc4f7967… dominates (89%) and top named target repeated 25/28 times
- reference_tier_fail:app.organicmaps/4862fbeed029_llm_s8__extend:analyze_status:partial:bad_handoff,sim_not_success,flailing:same_element_cycle: screen hash 29d9dc4f7967… dominates (89%) and top named target repeated 24/27 times
- reference_tier_fail:app.organicmaps/4862fbeed029_llm_s9__extend:analyze_status:partial:bad_handoff,sim_not_success,flailing:same_element_cycle: screen hash 29d9dc4f7967… dominates (89%) and top named target repeated 24/27 times
- reference_tier_fail:app.tice.TICE.production/648d8ddb49f4_llm_s6__extend:analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 55/55 times
- reference_tier_fail:app.tice.TICE.production/648d8ddb49f4_llm_s7__extend:analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 56/56 times
- reference_tier_fail:app.tice.TICE.production/648d8ddb49f4_llm_s8__extend:analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 56/56 times
- reference_tier_fail:app.tice.TICE.production/648d8ddb49f4_llm_s9__extend:analyze_status:partial:ux_quality_gate,sim_not_success,flailing:same_element_cycle: screen hash ac354b882cb0… dominates (100%) and top named target repeated 56/56 times
- reference_tier_fail:app.udderance/2074fc55fb78_llm_s4__extend:analyze_status:flag:webview_dominant
- reference_tier_fail:app.udderance/2074fc55fb78_llm_s5__extend:analyze_status:flag:webview_dominant
- reference_tier_fail:app.udderance/2074fc55fb78_llm_s6__extend:analyze_status:flag:webview_dominant
- reference_tier_fail:app.udderance/2074fc55fb78_llm_s7__extend:analyze_status:flag:webview_dominant
- reference_tier_fail:app.udderance/2074fc55fb78_llm_s8__extend:analyze_status:flag:webview_dominant
- reference_tier_fail:app.udderance/2074fc55fb78_llm_s9__extend:analyze_status:flag:webview_dominant
- reference_tier_fail:at.mikenet.serbianlatintocyrillic/4b633ea030db_llm_s4__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:at.mikenet.serbianlatintocyrillic/4b633ea030db_llm_s6__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:biz.binarysolutions.mindfulnessmeditation/fba1483a8a4d_llm_s4__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:biz.binarysolutions.mindfulnessmeditation/fba1483a8a4d_llm_s5__extend:analyze_status:partial:bad_handoff,sim_not_success
- reference_tier_fail:cc.kafuu.bilidownload/64de55f0293d_llm_s4__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:cc.kafuu.bilidownload/64de55f0293d_llm_s5__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:cc.kafuu.bilidownload/64de55f0293d_llm_s6__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:cc.kafuu.bilidownload/64de55f0293d_llm_s7__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:cc.kafuu.bilidownload/64de55f0293d_llm_s8__extend:analyze_status:partial:no_goal_progress,sim_not_success
- reference_tier_fail:ch.abertschi.waterme.water_me/d42d78005adb_llm_s3__extend:flailing:dominant_screen: hash e8e86dc0a776… on 12/12 execute+primary steps (100%); named_functional_taps=0
- reference_tier_fail:ch.abertschi.waterme.water_me/d42d78005adb_llm_s4__extend:flailing:dominant_screen: hash e8e86dc0a776… on 11/11 execute+primary steps (100%); named_functional_taps=0
- reference_tier_fail:ch.abertschi.waterme.water_me/d42d78005adb_llm_s6__extend:flailing:dominant_screen: hash e8e86dc0a776… on 12/12 execute+primary steps (100%); named_functional_taps=0
- reference_tier_fail:ch.abertschi.waterme.water_me/d42d78005adb_llm_s7__extend:flailing:dominant_screen: hash e8e86dc0a776… on 11/11 execute+primary steps (100%); named_functional_taps=0
- convergence_corpus_lt5:a2dp.Vol:n=3
- convergence_corpus_lt5:ademar.bitac:n=2
- convergence_corpus_lt5:agrigolo.opendrummer:n=3
- convergence_corpus_lt5:app.alextran.immich:n=3
- convergence_corpus_lt5:app.crescentcash.src:n=3
- convergence_corpus_lt5:app.fedilab.mobilizon:n=3
- convergence_corpus_lt5:app.hypostats:n=3
- convergence_corpus_lt5:app.ladefuchs.android:n=3
- convergence_corpus_lt5:app.notesr:n=3
- convergence_corpus_lt5:app.pachli:n=3
- convergence_corpus_lt5:app.udderance:n=3
- convergence_corpus_lt5:at.manuelbichler.octalsuntime:n=3
- convergence_corpus_lt5:at.tomtasche.reader:n=3
- convergence_corpus_lt5:be.humanoids.webthingify:n=1
- convergence_corpus_lt5:biz.binarysolutions.stress:n=3
- convergence_corpus_lt5:br.odb.knights:n=3
- convergence_corpus_lt5:btools.routingapp:n=3
- convergence_corpus_lt5:buet.rafi.dictionary:n=3
- convergence_corpus_lt5:ca.andries.portknocker:n=3
- convergence_corpus_lt5:ca.momi.lift:n=3
- convergence_corpus_lt5:ca.ramzan.delist:n=3
- convergence_corpus_lt5:cc.kafuu.bilidownload:n=3
- convergence_corpus_lt5:ch.abertschi.waterme.water_me:n=3
- convergence_corpus_lt5:ch.bubendorf.locusaddon.gsakdatabase:n=1

