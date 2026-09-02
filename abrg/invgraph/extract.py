"""Extract (caller, callee) invocation pairs from AndroCT traces (cached)."""

from __future__ import annotations

import csv
import io
import json
import tarfile
from pathlib import Path
from typing import Any, Iterator

from abrg.androct.parse import _CALL_RE, _INTENT_RECV, _INTENT_SENT
from abrg.androct.paths import EXPECTED_ARCHIVES, androct_raw_dir
from abrg.apigraph.extract import normalize_callee
from abrg.invgraph import INVGRAPH_OUTPUT_ROOT

# Where the caller was previously discarded (documented for Stage 1):
CALLER_DISCARD_SITES = [
    {
        "path": "abrg/apigraph/extract.py",
        "symbol": "_iter_call_lines",
        "detail": "matches _CALL_RE but yields only normalize_callee(m.group(2)); m.group(1) unused",
    },
    {
        "path": "abrg/androct/run2_corpus.py",
        "symbol": "_load_categories",
        "detail": "categorizes m.group(2) only; caller never enters the 22-node stream",
    },
    {
        "path": "abrg/androct/run_gae_run2.py",
        "symbol": "load_categories_for_eligible",
        "detail": "same: categorize_soot_callee(m.group(2)) only",
    },
]

# ICC decision (stated explicitly):
ICC_DECISION = (
    "ICC blocks ([ Intent sent ] / [ Intent received ]) do not yield "
    "(caller, callee) method pairs: the full parser sets callee=None and "
    "attaches category via callsite. Invgraph EXCLUDES ICC markers from "
    "invocation edges; only `<caller> -> <callee>` soot call lines are used."
)


def load_b_docfreq_vocab(csv_path: Path) -> list[str]:
    rows: list[str] = []
    with csv_path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r["callee"])
    if len(rows) != 1000:
        raise SystemExit(f"STOP: expected K=1000 B_docfreq vocab, got {len(rows)} from {csv_path}")
    return rows


def _iter_pairs(text_io: io.TextIOWrapper) -> Iterator[tuple[str, str]]:
    """Yield normalized (caller, callee) from allowlisted call lines only."""
    for line in text_io:
        raw = line.rstrip("\n\r")
        if _INTENT_SENT.match(raw) or _INTENT_RECV.match(raw):
            continue  # ICC: no (caller,callee) pair — see ICC_DECISION
        m = _CALL_RE.match(raw)
        if not m:
            continue
        caller = normalize_callee(m.group(1))
        callee = normalize_callee(m.group(2))
        if caller is not None and callee is not None:
            yield caller, callee


def extract_invocation_pairs(
    apps: list[Any],
    *,
    cache_dir: Path | None = None,
    force: bool = False,
) -> dict[str, list[tuple[str, str]]]:
    cache_dir = cache_dir or (INVGRAPH_OUTPUT_ROOT / "cache" / "pairs")
    cache_dir.mkdir(parents=True, exist_ok=True)
    out: dict[str, list[tuple[str, str]]] = {}
    pending = []
    for a in apps:
        cp = cache_dir / f"{a.sha256}.json"
        if cp.is_file() and not force:
            data = json.loads(cp.read_text(encoding="utf-8"))
            out[a.sha256] = [tuple(p) for p in data]
        else:
            pending.append(a)

    if not pending:
        print(f"[invgraph] pairs cache hit n={len(out)}", flush=True)
        return out

    print(f"[invgraph] extracting caller→callee pairs for {len(pending)} apps …", flush=True)
    by_label: dict[str, list] = {"benign": [], "malware": []}
    for a in pending:
        by_label[a.label].append(a)

    raw = androct_raw_dir()
    for label, group in by_label.items():
        if not group:
            continue
        fname = next(n for n, m in EXPECTED_ARCHIVES.items() if m["label"] == label)
        want_path = {a.path: a for a in group}
        found = 0
        with tarfile.open(raw / fname, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or member.name not in want_path:
                    continue
                app = want_path[member.name]
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                try:
                    pairs = list(_iter_pairs(text))
                finally:
                    text.detach()
                out[app.sha256] = pairs
                (cache_dir / f"{app.sha256}.json").write_text(
                    json.dumps(pairs), encoding="utf-8"
                )
                found += 1
                if found % 100 == 0:
                    print(f"  … {label} pairs={found}/{len(group)}", flush=True)
        missing = [a.sha256 for a in group if a.sha256 not in out]
        if missing:
            raise SystemExit(f"STOP: missing pairs for {len(missing)} {label} apps")
        print(f"[invgraph] {label} pairs done n={found}", flush=True)

    for a in apps:
        if a.sha256 not in out:
            out[a.sha256] = [
                tuple(p)
                for p in json.loads((cache_dir / f"{a.sha256}.json").read_text(encoding="utf-8"))
            ]
    return out


def pairs_to_callee_sequence(pairs: list[tuple[str, str]]) -> list[str]:
    """Callee-only stream — same axis as apigraph sequences for node features / V1."""
    return [c for _, c in pairs]
