"""Paths for the AndroCT 2017 evaluation corpus (never via datasets/CURRENT)."""

from __future__ import annotations

from pathlib import Path

from abrg.dataset_paths import DATASETS_ROOT, REPO_ROOT

CORPUS_ID = "androct_2017"
ANDROCT_2017_ROOT = DATASETS_ROOT / CORPUS_ID
ANDROCT_OUTPUT_ROOT = REPO_ROOT / "abrg" / "output" / CORPUS_ID

# Zenodo record 4470320 — emulator traces only for this corpus slice.
EXPECTED_ARCHIVES: dict[str, dict[str, str]] = {
    "trace-benign-2017.tar.gz": {
        "md5": "7e6f8ddd13dd1756e34177d82e65a70a",
        "url": "https://zenodo.org/records/4470320/files/trace-benign-2017.tar.gz?download=1",
        "label": "benign",
        "inner_dir": "benign2017",
        "n_files": "2256",
    },
    "trace-malware-2017.tar.gz": {
        "md5": "52943731da71ce46461462fc20e52c8b",
        "url": "https://zenodo.org/records/4470320/files/trace-malware-2017.tar.gz?download=1",
        "label": "malware",
        "inner_dir": "malware-2017",
        "n_files": "1742",
    },
}


def androct_raw_dir() -> Path:
    return ANDROCT_2017_ROOT / "raw"


def androct_inventory_dir() -> Path:
    return ANDROCT_2017_ROOT / "inventory"


def androct_apk_dir() -> Path:
    """
    Dedicated APK store for AndroCT static features.

    Prefer the AndroCT APK vault (/Volumes/ABRG_ANDROCT_APKS), else ABRG_MW.
    Never inside the git worktree, synced dirs, or system temp.
    """
    candidates = [
        Path("/Volumes/ABRG_ANDROCT_APKS/androct_2017_apks"),
        Path("/Volumes/ABRG_MW/androct_2017_apks"),
    ]
    for path in candidates:
        if path.parent.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            return path
    raise FileNotFoundError(
        "No APK vault mounted. Attach "
        "~/Vaults/androct_apks.sparsebundle → /Volumes/ABRG_ANDROCT_APKS "
        "or /Volumes/ABRG_MW."
    )


def androct_run2_output_dir() -> Path:
    return ANDROCT_OUTPUT_ROOT / "run2"


def androct_run3_output_dir() -> Path:
    return ANDROCT_OUTPUT_ROOT / "run3"


def androct_run3_5_output_dir() -> Path:
    """Diagnostic supervised capacity probe (not a proposed method)."""
    return ANDROCT_OUTPUT_ROOT / "run3_5"


def androct_run4_output_dir() -> Path:
    return ANDROCT_OUTPUT_ROOT / "run4"


def androct_run5_output_dir() -> Path:
    return ANDROCT_OUTPUT_ROOT / "run5"


def androct_run6_output_dir() -> Path:
    return ANDROCT_OUTPUT_ROOT / "run6"


def androct_run8_output_dir() -> Path:
    return ANDROCT_OUTPUT_ROOT / "run8"
