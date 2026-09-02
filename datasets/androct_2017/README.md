# AndroCT 2017 evaluation corpus (Zenodo 4470320)

**Isolated from `datasets/v1` / `datasets/v2`.** Do not merge sessions, share
normalization stats, model weights, or ABRG output dirs with the Frida corpora.
`datasets/CURRENT` is intentionally unchanged (still pins the Frida reference set).

## License / use constraints

AndroCT is CC-BY-4.0; authors additionally require a faculty sponsor, no
redistribution, no commercial use, and citation of the MSR 2021 data paper:

```bibtex
@inproceedings{AndroidCT,
  title = {AndroCT: Ten Years of App Call Traces in Android},
  author = {Wen Li, Xiaoqin Fu, and Haipeng Cai},
  booktitle = {The 18th International Conference on Mining Software Repositories
               (MSR 2021), Data Showcase Track},
  year = {2021},
}
```

## Slice

Emulator traces for calendar year **2017** only:

| Archive | MD5 | Inner dir | Files |
|---------|-----|-----------|------:|
| `raw/trace-benign-2017.tar.gz` | `7e6f8ddd13dd1756e34177d82e65a70a` | `benign2017` | 2256 |
| `raw/trace-malware-2017.tar.gz` | `52943731da71ce46461462fc20e52c8b` | `malware-2017` | 1742 |

`real-trace-*` (physical device) is deferred.

## Layout

```
datasets/androct_2017/
  README.md
  raw/*.tar.gz          # verified archives (gitignored)
  inventory/            # parse inventory only (no graphs yet)
abrg/output/androct_2017/   # reserved for later rebuilds (never share with v2)
```

## Inventory (first step)

```bash
python -m abrg.run_androct_inventory
```

Streams from the tar.gz files (no full extract required). See `inventory/INVENTORY.md`.
