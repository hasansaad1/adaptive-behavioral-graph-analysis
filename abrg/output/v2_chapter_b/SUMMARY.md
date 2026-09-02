# Chapter B — SUMMARY

Descriptive only. Benign v2. No detector, no AUC, no supervised probe.

## verify_export.py

| exit_code | 0 |

```
VERIFY OK — 783 files, 388 sessions
```

## Unit alignment (Run 2)

- method: `concat_then_build`
- builder: `abrg.androct.graph_build.update_graph_sequence` k_burst=5
- per-session n=342; per-app pooled n=59
- AndroCT unit: one whole-trace graph per app (effective traces)

Per-app pooled v2 graphs are built by concatenating each app's usable sessions' mapped category streams in session_index_within_app order (start-time order), then calling abrg.androct.graph_build.update_graph_sequence once on the concatenated stream. This matches AndroCT's unit: one ordered whole-trace category stream → one graph. Graphs are not built per session and then merged; no edge-weight combination rule is applied.

## Representation comparison

| metric | v2 per-session | v2 per-app pooled | AndroCT benign | AndroCT malware |
|---|---|---|---|---|
| mapped events | med=84 IQR=[26.75, 254] p10=8 p90=697.8 n=342 | med=372 IQR=[37.5, 1335] p10=11.4 p90=4309 n=59 | med=185 IQR=[33, 853] p10=6 p90=3084 n=2231 | med=818 IQR=[311, 1774] p10=185 p90=4220 n=1736 |
| total events | med=524 IQR=[174, 1950] p10=66 p90=7979 n=342 | med=1703 IQR=[493, 9008] p10=174.8 p90=3.444e+04 n=59 | med=6878 IQR=[1064, 4.123e+04] p10=529 p90=1.569e+05 n=2231 | med=3.144e+04 IQR=[1.65e+04, 7.413e+04] p10=2622 p90=1.104e+05 n=1736 |
| mapped-event rate | med=0.243561 IQR=[0.0483671, 0.632041] p10=0.0116024 p90=0.829023 n=342 | med=0.204282 IQR=[0.0340895, 0.559186] p10=0.0112917 p90=0.749003 n=59 | med=0.0258816 IQR=[0.0100783, 0.0486898] p10=0.0035756 p90=0.106643 n=2231 | med=0.0368541 IQR=[0.00928299, 0.10188] p10=0.00278378 p90=0.168185 n=1736 |
| active nodes | med=3 IQR=[2, 4] p10=1.1 p90=5 n=342 | med=2 IQR=[2, 4] p10=1 p90=5 n=59 | med=6 IQR=[3, 8] p10=1 p90=9 n=2231 | med=6 IQR=[3, 7] p10=2 p90=9 n=1736 |
| edges | med=5 IQR=[2, 10] p10=0.1 p90=12 n=342 | med=2 IQR=[2, 10] p10=0 p90=17.2 n=59 | med=16 IQR=[5, 32] p10=0 p90=49 n=2231 | med=22 IQR=[6, 29] p10=2 p90=46 n=1736 |
| density | med=0.0108225 IQR=[0.004329, 0.021645] p10=0.00021645 p90=0.025974 n=342 | med=0.004329 IQR=[0.004329, 0.021645] p10=0 p90=0.0372294 n=59 | med=0.034632 IQR=[0.0108225, 0.0692641] p10=0 p90=0.106061 n=2231 | med=0.047619 IQR=[0.012987, 0.0627706] p10=0.004329 p90=0.0995671 n=1736 |
| wall / protocol length | med=460.882 IQR=[454.288, 469.551] p10=449.712 p90=479.809 n=342 | med=3236 IQR=[1384, 3746] p10=1353 p90=4162 n=59 | protocol 600.0s (no per-trace wall clock) | protocol 600.0s |
| frac graphs ≤2 edges | 0.4619883040935672 (n=158) | 0.5423728813559322 (n=32) | 0.20394441954280593 (n=455) | 0.17453917050691245 (n=303) |

### Active-node full distribution (value counts)

| unit | value counts |
|------|--------------|
| v2 per-session | `{'1': 35, '2': 123, '3': 76, '4': 59, '5': 36, '6': 10, '7': 3}` |
| v2 per-app pooled | `{'1': 13, '2': 19, '3': 9, '4': 9, '5': 4, '6': 4, '7': 1}` |
| AndroCT benign | `{'0': 109, '1': 132, '2': 212, '3': 197, '4': 222, '5': 232, '6': 282, '7': 266, '8': 252, '9': 157, '10': 84, '11': 58, '12': 26, '13': 2}` |
| AndroCT malware | `{'0': 33, '1': 43, '2': 227, '3': 268, '4': 101, '5': 139, '6': 253, '7': 325, '8': 130, '9': 105, '10': 42, '11': 26, '12': 38, '13': 5, '14': 1}` |

### Mann–Whitney U — v2 per-app pooled vs AndroCT benign

Declared material rule: p < 0.05 and |Cliff δ| ≥ 0.147.

| metric | test |
|--------|------|
| mapped_events | U=7.303e+04 p=0.150053 δ=0.109634 | does not differ at p < 0.05 (v2_per_app_pooled vs androct_benign: p=0.15, Cliff δ=0.11) |
| total_events | U=4.722e+04 p=0.000208689 δ=-0.282461 | differs materially (v2_per_app_pooled vs androct_benign: p=0.000209, Cliff δ=-0.282, small) |
| mapped_event_rate | U=1.032e+05 p=9.19164e-14 δ=0.567588 | differs materially (v2_per_app_pooled vs androct_benign: p=9.19e-14, Cliff δ=0.568, large) |
| active_nodes | U=3.113e+04 p=3.61213e-12 δ=-0.526981 | differs materially (v2_per_app_pooled vs androct_benign: p=3.61e-12, Cliff δ=-0.527, large) |
| edges | U=3.336e+04 p=9.07503e-11 δ=-0.493189 | differs materially (v2_per_app_pooled vs androct_benign: p=9.08e-11, Cliff δ=-0.493, large) |
| density | U=3.336e+04 p=9.07503e-11 δ=-0.493189 | differs materially (v2_per_app_pooled vs androct_benign: p=9.08e-11, Cliff δ=-0.493, large) |
| trace_or_session_length | AndroCT traces have no wall-clock. Protocol duration is 600.0s for every effective app. MWU on wall seconds is not computed. Event-count length is metric total_events. |

Metrics meeting the material rule: ['total_events', 'mapped_event_rate', 'active_nodes', 'edges', 'density']

## Category fire rate (per-app, 22 categories)

Fraction of apps with ≥1 mapped event. Ranked by |v2 − AndroCT benign|.

| category | v2 n | v2 frac | AndroCT benign n | AndroCT benign frac | diff |
|----------|-----:|--------:|-----------------:|--------------------:|-----:|
| package_manager | 1 | 0.0169492 | 1677 | 0.751681 | -0.734732 |
| native_code | 9 | 0.152542 | 1742 | 0.780816 | -0.628273 |
| ipc_intents | 18 | 0.305085 | 1517 | 0.679964 | -0.374879 |
| process | 2 | 0.0338983 | 789 | 0.353653 | -0.319755 |
| crypto | 13 | 0.220339 | 1146 | 0.513671 | -0.293332 |
| storage | 44 | 0.745763 | 1197 | 0.536531 | 0.209232 |
| device_info | 0 | 0 | 389 | 0.174361 | -0.174361 |
| network | 12 | 0.20339 | 781 | 0.350067 | -0.146677 |
| webview | 6 | 0.101695 | 453 | 0.203048 | -0.101353 |
| file_io | 42 | 0.711864 | 1457 | 0.65307 | 0.058794 |
| database | 9 | 0.152542 | 440 | 0.197221 | -0.0446786 |
| media | 0 | 0 | 74 | 0.033169 | -0.033169 |
| audio | 2 | 0.0338983 | 7 | 0.00313761 | 0.0307607 |
| content_access | 3 | 0.0508475 | 160 | 0.0717167 | -0.0208693 |
| location | 1 | 0.0169492 | 72 | 0.0322725 | -0.0153234 |
| notifications | 2 | 0.0338983 | 42 | 0.0188256 | 0.0150727 |
| accounts | 0 | 0 | 28 | 0.0125504 | -0.0125504 |
| camera | 1 | 0.0169492 | 17 | 0.0076199 | 0.00932925 |
| dynamic_code_loading | 0 | 0 | 4 | 0.00179292 | -0.00179292 |
| clipboard | 0 | 0 | 1 | 0.000448229 | -0.000448229 |
| telephony | 0 | 0 | 1 | 0.000448229 | -0.000448229 |
| sms | 0 | 0 | 0 | 0 | 0 |

### Dead categories

- v2 per-app pooled: ['accounts', 'clipboard', 'device_info', 'dynamic_code_loading', 'media', 'sms', 'telephony']
- AndroCT benign: ['sms']
- AndroCT malware: ['camera', 'clipboard', 'sms', 'telephony']

| category | v2 n apps | v2 dead | AndroCT benign n | benign dead | AndroCT malware n | malware dead |
|----------|----------:|:-------:|-----------------:|:-----------:|------------------:|:------------:|
| sms | 0 | True | 0 | True | 0 | True |
| dynamic_code_loading | 0 | True | 4 | False | 10 | False |
| telephony | 0 | True | 1 | False | 0 | True |
| camera | 1 | False | 17 | False | 0 | True |
| clipboard | 0 | True | 1 | False | 0 | True |

## Static slice

v2: n_apps=59 resolved=59 fallback=0 all-zero=0 L2 med=7.6642 IQR=[5.35163, 15.3348] p10=4.54003 p90=26.5317 n=59

AndroCT benign (Run-2 cache tensors): n=703 all-zero=0 L2 med=9.73139 IQR=[5.96992, 18.0336] p10=5.06952 p90=39.5737 n=703

| coordinate | v2 all-nodes | v2 per-app mean | AndroCT benign all-nodes | AndroCT benign per-app mean |
|------------|--------------|-----------------|--------------------------|------------------------------|
| s_v | med=0.2 IQR=[0.2, 0.7] p10=0 p90=0.7 n=1298 | med=0.409091 IQR=[0.4, 0.418182] p10=0.38 p90=0.427273 n=59 | med=0.2 IQR=[0.2, 0.7] p10=0.2 p90=0.7 n=15466 | med=0.427273 IQR=[0.418182, 0.427273] p10=0.4 p90=0.427273 n=703 |
| declared_v | med=1 IQR=[0, 1] p10=0 p90=1 n=1298 | med=0.636364 IQR=[0.522727, 0.681818] p10=0.4 p90=0.727273 n=59 | med=1 IQR=[0, 1] p10=0 p90=1 n=15466 | med=0.772727 IQR=[0.727273, 0.818182] p10=0.545455 p90=0.863636 n=703 |
| gate_v[0]_normal | med=0 IQR=[0, 0] p10=0 p90=1 n=1298 | med=0.0909091 IQR=[0.0454545, 0.159091] p10=0 p90=0.227273 n=59 | med=0 IQR=[0, 0] p10=0 p90=1 n=15466 | med=0.136364 IQR=[0.0909091, 0.181818] p10=0.0454545 p90=0.272727 n=703 |
| gate_v[1]_dangerous | med=0 IQR=[0, 0] p10=0 p90=0 n=1298 | med=0 IQR=[0, 0] p10=0 p90=0 n=59 | med=0 IQR=[0, 0] p10=0 p90=0 n=15466 | med=0 IQR=[0, 0] p10=0 p90=0 n=703 |
| gate_v[2]_signature | med=0 IQR=[0, 0] p10=0 p90=0 n=1298 | med=0 IQR=[0, 0] p10=0 p90=0 n=59 | med=0 IQR=[0, 0] p10=0 p90=0 n=15466 | med=0 IQR=[0, 0] p10=0 p90=0 n=703 |
| reach_v | med=0 IQR=[0, 0] p10=0 p90=2 n=1298 | med=0.409091 IQR=[0.227273, 0.977273] p10=0.0909091 p90=2.24545 n=59 | med=0 IQR=[0, 0] p10=0 p90=2 n=15466 | med=0.590909 IQR=[0.227273, 1.31818] p10=0.0454545 p90=2.89091 n=703 |
| epoch_v | med=0 IQR=[0, 0] p10=0 p90=0 n=1298 | med=0 IQR=[0, 0] p10=0 p90=0 n=59 | med=0 IQR=[0, 0] p10=0 p90=0 n=15466 | med=0 IQR=[0, 0] p10=0 p90=0 n=703 |

## Event yield

| | v2 per-session | AndroCT benign | AndroCT malware |
|---|---|---|---|
| events / s | med=1.15148 IQR=[0.365188, 4.22817] p10=0.140576 p90=16.8117 n=342 | med=11.4633 IQR=[1.77333, 68.715] p10=0.881667 p90=261.563 n=2231 | med=52.3958 IQR=[27.5079, 123.551] p10=4.36917 p90=184.004 n=1736 |
| mapped / s | med=0.183758 IQR=[0.0578171, 0.544691] p10=0.0176076 p90=1.50579 n=342 | med=0.308333 IQR=[0.055, 1.42167] p10=0.01 p90=5.14 n=2231 | med=1.36333 IQR=[0.518333, 2.95708] p10=0.308333 p90=7.03333 n=1736 |
| wall | med=460.882 IQR=[454.288, 469.551] p10=449.712 p90=479.809 n=342 | protocol 600.0s | protocol 600.0s |

Spearman (v2 sessions):
- mapped vs wall: {'rho': 0.07392265305561369, 'p_value': 0.17258920604552158, 'n': 342}
- total vs wall: {'rho': -0.03633022360469888, 'p_value': 0.5030969172517791, 'n': 342}
- mapped/s vs wall: {'rho': 0.05437783649915521, 'p_value': 0.3160139245295976, 'n': 342}

Hooks (all type==event APIs, including dropped categories): hooked_set_n=58 fired_corpus_wide_n=40 never_fired_n=22
- fired: ['AssetManager.open', 'AudioRecord.<init>', 'CameraManager.openCamera', 'Cipher.doFinal', 'ContentResolver.delete', 'ContentResolver.insert', 'ContentResolver.query', 'ContentResolver.update', 'Context.bindService', 'Context.sendBroadcast', 'Context.startActivity', 'Context.startService', 'File.delete', 'FileInputStream.<init>', 'LocationManager.requestLocationUpdates', 'MediaRecorder.setAudioSource', 'MessageDigest.digest', 'MessageDigest.getInstance', 'Method.invoke', 'NotificationManager.notify', 'NotificationManager.notifyAsUser', 'PackageManager.getInstalledPackages', 'ProcessBuilder.start', 'Runtime.exec', 'SQLiteDatabase.execSQL', 'SQLiteDatabase.insert', 'SQLiteDatabase.rawQuery', 'SecretKeySpec.<init>', 'SharedPreferences.apply', 'SharedPreferences.getInt', 'SharedPreferences.getString', 'SharedPreferences.putString', 'Socket.connect', 'System.loadLibrary', 'URL.openConnection', 'WebView.loadUrl', 'hook_loaded', 'okhttp3.RealCall.enqueue', 'okhttp3.RealCall.execute', 'retrofit2.OkHttpCall.execute']
- never: ['AccountManager.getAccounts', 'AccountManager.getAccountsByType', 'Camera.open', 'Cipher.getInstance', 'ClipboardManager.setPrimaryClip', 'DexClassLoader.<init>', 'FileOutputStream.<init>', 'HttpURLConnection.connect', 'MediaPlayer.prepare', 'MediaPlayer.setDataSource', 'MediaPlayer.start', 'PackageManager.getInstalledApplications', 'PathClassLoader.<init>', 'Runtime.load', 'Runtime.loadLibrary', 'SmsManager.sendMultipartTextMessage', 'SmsManager.sendTextMessage', 'TelephonyManager.getCallState', 'TelephonyManager.getDeviceId', 'TelephonyManager.getSimSerialNumber', 'TelephonyManager.getSubscriberId', 'volley.RequestQueue.add']
- n hooks fired per session: med=7 IQR=[5, 9] p10=4 p90=11 n=342

Screens / activities: v2_extended export does not include exploration logs (llm_actions.jsonl / navigation artifacts). Distinct activities or screens per session are not computable from the export.

## Corpus inventory (Run 1)

| | indexed | usable (reference-tier pass) | pass | fail |
|--|--:|--:|--:|--:|
| all | 388 | 342 | 342 | 46 |

| batch | indexed | pass | fail |
|-------|--------:|-----:|-----:|
| canary | 3 | 2 | 1 |
| extend | 217 | 172 | 45 |
| original | 168 | 168 | 0 |

Apps with ≥1 usable session: 59
GAE-eligible before extension: 40
GAE-eligible after extension: 40
Entered eligibility: []
Left eligibility: []

Session-count distribution (n_sessions → n_apps):
- before (original pass): `{'1': 3, '2': 3, '3': 53}`
- after (all pass): `{'1': 2, '2': 1, '3': 21, '5': 2, '6': 2, '7': 5, '8': 16, '9': 10}`

| app_id | n before (original pass) | n after (all pass) |
|--------|-------------------------:|-------------------:|
| InfinityLoop1309.NewPipeEnhanced | 3 | 7 |
| a2dp.Vol | 3 | 3 |
| ac.robinson.mediaphone | 3 | 9 |
| ademar.bitac | 2 | 2 |
| agrigolo.opendrummer | 3 | 3 |
| ai.susi | 3 | 9 |
| anonvpn.anon_next.android | 3 | 7 |
| app.alextran.immich | 3 | 3 |
| app.comaps.fdroid | 3 | 7 |
| app.crescentcash.src | 3 | 3 |
| app.fedilab.castlab | 3 | 7 |
| app.fedilab.mobilizon | 3 | 3 |
| app.fedilab.nitterizeme | 3 | 9 |
| app.fedilab.nitterizemelite | 3 | 9 |
| app.hypostats | 3 | 3 |
| app.ladefuchs.android | 3 | 3 |
| app.michaelwuensch.bitbanana | 3 | 9 |
| app.notesr | 3 | 3 |
| app.organicmaps | 3 | 6 |
| app.pachli | 3 | 3 |
| app.prav.client | 3 | 9 |
| app.tice.TICE.production | 3 | 5 |
| app.tujice.jergasColombia | 3 | 9 |
| app.udderance | 3 | 3 |
| at.linuxtage.Eventfahrplan | 3 | 9 |
| at.manuelbichler.octalsuntime | 3 | 3 |
| at.mikenet.serbianlatintocyrillic | 1 | 5 |
| at.tomtasche.reader | 3 | 3 |
| au.com.wallaceit.reddinator | 3 | 9 |
| barilyuk.batterytemperature | 3 | 9 |
| be.digitalia.fosdem | 3 | 8 |
| be.humanoids.webthingify | 1 | 1 |
| be.mygod.vpnhotspot_foss | 3 | 8 |
| biz.binarysolutions.mindfulnessmeditation | 3 | 6 |
| biz.binarysolutions.stress | 3 | 3 |
| biz.binarysolutions.vatcalculator | 3 | 8 |
| bluepie.ad_silence | 3 | 8 |
| br.odb.knights | 3 | 3 |
| btools.routingapp | 3 | 3 |
| buet.rafi.dictionary | 3 | 3 |
| bus.chio.wishmaster | 3 | 8 |
| ca.andries.portknocker | 3 | 3 |
| ca.chancehorizon.paseo | 3 | 8 |
| ca.farrelltonsolar.classic | 3 | 8 |
| ca.momi.lift | 3 | 3 |
| ca.ramzan.delist | 3 | 3 |
| ca.rmen.android.frenchcalendar | 3 | 8 |
| ca.rmen.android.scrumchatter | 3 | 8 |
| ca.rmen.nounours | 3 | 8 |
| cat.jordihernandez.cinecat | 3 | 8 |
| cc.kafuu.bilidownload | 3 | 3 |
| cf.playhi.freezeyou | 3 | 8 |
| ch.abertschi.waterme.water_me | 2 | 3 |
| ch.bubendorf.locusaddon.gsakdatabase | 1 | 1 |
| ch.hgdev.toposuite | 2 | 7 |
| ch.joshuah.bibleverseapp | 3 | 8 |
| ch.mydoli.focal | 3 | 8 |
| cityfreqs.com.pilfershushjammer | 3 | 8 |
| cl.coders.faketraveler | 3 | 8 |

| batch | n | start UTC | end UTC |
|-------|--:|-----------|---------|
| canary | 3 | 2026-08-13T22:28:42.534000Z | 2026-08-13T22:49:45.128000Z |
| extend | 217 | 2026-08-13T23:17:33.502000Z | 2026-08-15T06:07:05.633000Z |
| original | 168 | 2026-07-12T17:26:14.626000Z | 2026-07-19T07:21:53.932000Z |

### Old vs new (original pass vs canary+extend pass)

n original=168 n new=174 n pooled=342

| metric | original | new | pooled | MWU |
|--------|----------|-----|--------|-----|
| mapped_events_per_session | med=57.5 IQR=[10, 199] p10=4 p90=588.9 n=168 | med=119 IQR=[48, 268] p10=15 p90=708.2 n=174 | med=84 IQR=[26.75, 254] p10=8 p90=697.8 n=342 | U=1.088e+04 p=4.29496e-05 δ=-0.25585 | differs materially (original vs new_canary_extend: p=4.29e-05, Cliff δ=-0.256, small) |
| total_events_per_session | med=385 IQR=[144.75, 1429] p10=36 p90=6734 n=168 | med=701.5 IQR=[194.25, 2166] p10=101.4 p90=8300 n=174 | med=524 IQR=[174, 1950] p10=66 p90=7979 n=342 | U=1.228e+04 p=0.0105334 δ=-0.159996 | differs materially (original vs new_canary_extend: p=0.0105, Cliff δ=-0.16, small) |
| active_nodes_per_graph | med=2 IQR=[2, 4] p10=1 p90=5 n=168 | med=3 IQR=[2, 4] p10=2 p90=5 n=174 | med=3 IQR=[2, 4] p10=1.1 p90=5 n=342 | U=1.132e+04 p=0.000195441 δ=-0.225301 | differs materially (original vs new_canary_extend: p=0.000195, Cliff δ=-0.225, small) |
| edges_per_graph | med=2 IQR=[0, 5] p10=0 p90=10 n=168 | med=2.5 IQR=[2, 6] p10=1 p90=10 n=174 | med=2 IQR=[1, 6] p10=0 p90=10 n=342 | U=1.042e+04 p=3.38176e-06 δ=-0.28698 | differs materially (original vs new_canary_extend: p=3.38e-06, Cliff δ=-0.287, small) |
| graph_density | med=0.004329 IQR=[0, 0.0108225] p10=0 p90=0.021645 n=168 | med=0.00541126 IQR=[0.004329, 0.012987] p10=0.0021645 p90=0.021645 n=174 | med=0.004329 IQR=[0.0021645, 0.012987] p10=0 p90=0.021645 n=342 | U=1.042e+04 p=3.38176e-06 δ=-0.28698 | differs materially (original vs new_canary_extend: p=3.38e-06, Cliff δ=-0.287, small) |
| wall_duration_s | med=460.721 IQR=[454.057, 468.252] p10=449.589 p90=477.235 n=168 | med=462.067 IQR=[454.482, 470.537] p10=450.141 p90=481.398 n=174 | med=460.882 IQR=[454.288, 469.551] p10=449.712 p90=479.809 n=342 | U=1.387e+04 p=0.41287 δ=-0.0512452 | does not differ at p < 0.05 (original vs new_canary_extend: p=0.413, Cliff δ=-0.0512) |

Metrics meeting the material rule (p < 0.05 and |δ| ≥ 0.147): ['mapped_events_per_session', 'total_events_per_session', 'active_nodes_per_graph', 'edges_per_graph', 'graph_density']
Any material: True

### Reference-tier failures (n=46)

- n_apps in canary/extend: 40
- n_apps with ≥1 failure: 13
- n_apps where all new slots failed: 4
- per-app failure counts: `{'app.fedilab.mobilizon': 6, 'app.ladefuchs.android': 6, 'app.udderance': 6, 'cc.kafuu.bilidownload': 5, 'app.tice.TICE.production': 4, 'ch.abertschi.waterme.water_me': 4, 'app.organicmaps': 3, 'InfinityLoop1309.NewPipeEnhanced': 2, 'anonvpn.anon_next.android': 2, 'app.comaps.fdroid': 2, 'app.fedilab.castlab': 2, 'at.mikenet.serbianlatintocyrillic': 2, 'biz.binarysolutions.mindfulnessmeditation': 2}`
- reason families: `{'partial:bad_handoff': 14, 'partial:ux_quality_gate': 12, 'partial:no_goal_progress': 7, 'webview_dominant': 6, 'flailing:dominant_screen': 4, 'failed_frida_reattach': 2, 'flailing:same_element_cycle': 1}`
- fail-rate distribution: med=0 IQR=[0, 0.333333] p10=0 p90=0.82 n=40
- concentration numbers: `{'max_failures_on_one_app': 6, 'median_failures_among_apps_with_fail': 3}`

### Exit codes

source_meta readable=388 missing=0 nonzero analysis_exit_code=2
- exit_code counts: `{'0': 386, '12': 2}`
- analysis_status counts: `{'success': 344, 'partial:bad_handoff': 14, 'failed_frida_reattach': 2, 'partial:no_goal_progress': 7, 'partial:ux_quality_gate': 12, 'flag:webview_dominant': 9}`

| app_id | session_id | batch | exit | status |
|--------|------------|-------|-----:|--------|
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s4 | extend | 12 | failed_frida_reattach |
| anonvpn.anon_next.android | 2f4839ccdb6e_llm_s5 | extend | 12 | failed_frida_reattach |

## Figures

- `figures/category_fire_rate.svg`
- `figures/active_nodes_dist.svg`
- `figures/edges_dist.svg`

