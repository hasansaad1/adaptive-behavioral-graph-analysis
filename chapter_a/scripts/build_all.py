"""Build Chapter A artifacts from saved experiment outputs (no re-run)."""
from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from inventory import build_manifest
from build_master import build_master
from make_tables import make_tables
from make_figures import make_figures
from make_notebooks import make_notebooks
from write_docs import write_docs


def main():
    man = build_manifest()
    master = build_master()
    make_tables()
    make_figures()
    make_notebooks()
    write_docs(man, master)
    print("chapter_a build complete")


if __name__ == "__main__":
    main()
