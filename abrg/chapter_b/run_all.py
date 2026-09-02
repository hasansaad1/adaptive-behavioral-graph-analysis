"""Orchestrate Chapter B runs. Stop if verify_export.py is non-zero."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from abrg.chapter_b.config import OUTPUT_ROOT, RUN2_DIR
from abrg.chapter_b.figures import make_figures
from abrg.chapter_b.ingest import load_sessions, pass_sessions, run_verify_export
from abrg.chapter_b.provenance import assemble_provenance, write_provenance_md
from abrg.chapter_b.report import write_reproduce, write_summary
from abrg.chapter_b.run1 import run1 as run1_corpus
from abrg.chapter_b.run2 import run2 as run2_compare
from abrg.chapter_b.safety import write_safety_md


def main(argv: list[str] | None = None) -> int:
    del argv
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    print("[chapter_b] verify_export.py …", flush=True)
    code, text = run_verify_export()
    print(text, end="" if text.endswith("\n") else "\n")
    (OUTPUT_ROOT / "verify_export.log").write_text(text, encoding="utf-8")
    if code != 0:
        (OUTPUT_ROOT / "STOP.md").write_text(
            f"verify_export.py exit {code}. Chapter B stopped.\n\n{text}\n",
            encoding="utf-8",
        )
        print(f"[chapter_b] STOP verify_export exit={code}", file=sys.stderr)
        return code

    rows = load_sessions()
    r1 = run1_corpus(rows)
    r2 = run2_compare(pass_sessions(rows))
    androct_cache = json.loads((RUN2_DIR / "androct_graph_cache.json").read_text(encoding="utf-8"))
    v2_units = json.loads((RUN2_DIR / "v2_units.json").read_text(encoding="utf-8"))
    figs = make_figures(r2, v2_units, androct_cache)
    prov = assemble_provenance(r1)
    write_provenance_md(prov)
    write_safety_md()
    write_summary(verify_exit=code, verify_text=text, run1=r1, run2=r2, figure_paths=figs)
    write_reproduce(code, r1, r2)
    print(f"[chapter_b] wrote {OUTPUT_ROOT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
