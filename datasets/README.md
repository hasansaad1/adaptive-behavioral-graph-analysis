# Datasets

Versioned behavioral datasets for adaptive graph analysis.

| Version | Path | Description |
|---------|------|-------------|
| **v2** (current) | [`v2/`](v2/) | Reference-tier benign corpus — 168 sessions / 59 apps, Frida hook_apis.js **v3** |
| v1 | [`v1/`](v1/) | Faithfulness-curated benign corpus — 129 apps, LLM agent + Frida traces (hook v2) |
| androct_2017 (separate) | [`androct_2017/`](androct_2017/) | AndroCT / DroidFax 2017 emulator traces (Zenodo 4470320) — **not** via `CURRENT` |

The active Frida dataset version is recorded in [`CURRENT`](CURRENT). Point scripts and notebooks at `datasets/<version>/` rather than hard-coding export names from ContextDroid.

**AndroCT is a separate evaluation corpus.** Do not merge it with v1/v2, do not share caches or `abrg/output` dirs, and label any comparison to Frida results as cross-corpus.

Python helpers in `abrg/dataset_paths.py` resolve `CURRENT` automatically:

```python
from abrg.dataset_paths import current_sessions_dir, current_dataset_version
sessions = current_sessions_dir()  # e.g. datasets/v2/sessions
```

## Layout (per version)

```
datasets/
  CURRENT                 # single line: active version id (e.g. v2)
  README.md               # this file
  v1/
  v2/
    VERSION.json          # machine-readable version metadata
    README.md             # human-readable dataset docs
    working_dataset.csv   # session index
    working_dataset_manifest.json
    sessions/             # one folder per app session
    archive/              # original zip export(s)
```

Future versions (`v3/`, …) follow the same structure. Do not overwrite an existing version directory; add a new one and update `CURRENT` when promoting a release.
