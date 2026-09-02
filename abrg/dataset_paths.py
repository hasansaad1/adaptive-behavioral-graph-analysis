"""Resolve active dataset version from datasets/CURRENT."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATASETS_ROOT = REPO_ROOT / "datasets"
CURRENT_FILE = DATASETS_ROOT / "CURRENT"


def current_dataset_version() -> str:
    """Read datasets/CURRENT (e.g. 'v2'). Falls back to 'v1' if missing."""
    if CURRENT_FILE.is_file():
        version = CURRENT_FILE.read_text(encoding="utf-8").strip()
        if version:
            return version
    return "v1"


def current_dataset_root() -> Path:
    root = DATASETS_ROOT / current_dataset_version()
    if not root.is_dir():
        raise FileNotFoundError(f"Dataset root missing: {root} (CURRENT={current_dataset_version()})")
    return root


def current_sessions_dir() -> Path:
    sessions = current_dataset_root() / "sessions"
    if not sessions.is_dir():
        raise FileNotFoundError(f"Sessions dir missing: {sessions}")
    return sessions


def find_frida_trace(session_dir: Path) -> Path:
    matches = list(session_dir.glob("*_frida.jsonl"))
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one *_frida.jsonl in {session_dir}, got {matches}")
    return matches[0]


def default_demo_session_dir(
    preferred_packages: tuple[str, ...] = (
        "ch.protonvpn.android",
        "app.michaelwuensch.bitbanana",
        "app.tice.TICE.production",
    ),
) -> Path:
    """
    Pick a demo session under the active dataset.
    Prefer known packages (llm_s1 first), else first session with a Frida trace.
    """
    sessions = current_sessions_dir()
    dirs = sorted(p for p in sessions.iterdir() if p.is_dir())

    for package in preferred_packages:
        candidates = [d for d in dirs if d.name.endswith(f"__{package}")]
        if not candidates:
            continue
        s1 = [d for d in candidates if "_llm_s1__" in d.name]
        pick = sorted(s1 or candidates)[0]
        if list(pick.glob("*_frida.jsonl")):
            return pick

    for d in dirs:
        if list(d.glob("*_frida.jsonl")):
            return d

    raise FileNotFoundError(f"No Frida sessions under {sessions}")


def default_demo_frida_trace() -> Path:
    return find_frida_trace(default_demo_session_dir())

def resolve_repo_path(path: str | Path) -> Path:
    """Resolve a path from a reproduce config against the repository root.

    Absolute paths under REPO_ROOT are accepted for back-compat; prefer
    repository-relative paths in configs (e.g. ``datasets/v2/sessions``).
    """
    path = Path(path)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()

