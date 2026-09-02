# AndroCT 2017 — parse inventory (pre-graph)

- Source: Zenodo 4470320 (AndroCT; Li, Fu, Cai; MSR 2021)
- Isolation: Separate from datasets/v1|v2; CURRENT pin untouched; dedicated output under abrg/output/androct_2017/
- Scored (UTC): 2026-08-07T10:47:33.537403+00:00

## Per class

| Class | Files | Header-only | Effective n | Events | Mapped | Mapped rate | Active cats / 22 | Dropped lines |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| benign | 2256 | 25 | 2231 | 155553398 | 4514569 | 0.0290 | 21 | 5853 |
| malware | 1742 | 6 | 1736 | 98280021 | 3277113 | 0.0333 | 18 | 4882 |

## Distinct active categories (per-app distribution)

- **benign**: n=2231, min=0.0, p25=3.0, p50=6.0, p75=8.0, max=13.0, mean=5.38
- **malware**: n=1736, min=0.0, p25=3.0, p50=6.0, p75=7.0, max=14.0, mean=5.43

## Trace-length distribution (total events, effective apps)

- **benign**: min=2.0, p25=1064, p50=6878, p75=41229, p90=156938, max=1753234.0, mean=69723.6
- **malware**: min=24.0, p25=16505, p50=31438, p75=74130, p90=110402, max=3300608.0, mean=56612.9

## Trace-length significance (Mann–Whitney U, two-sided)

- **Total events**: U=1.22e+06, p=1.82e-89, median_benign=6878, median_malware=31458
- **Mapped events**: U=1.15e+06, p=3.28e-107, median_benign=185, median_malware=818

## Corpus-wide category coverage

- **benign**: 21/22 — accounts, audio, camera, clipboard, content_access, crypto, database, device_info, dynamic_code_loading, file_io, ipc_intents, location, media, native_code, network, notifications, package_manager, process, storage, telephony, webview
- **malware**: 18/22 — accounts, audio, content_access, crypto, database, device_info, dynamic_code_loading, file_io, ipc_intents, location, media, native_code, network, notifications, package_manager, process, storage, webview

> Any comparison to Frida datasets/v2 (or other AbrG runs) is across corpora and must be labeled as such.

