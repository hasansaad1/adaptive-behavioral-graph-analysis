"""Stream AndroCT logcats → normalized callee sequences (cached)."""

from __future__ import annotations

import io
import json
import tarfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from abrg.androct.categorize import parse_soot_method_signature
from abrg.androct.parse import _CALL_RE
from abrg.androct.paths import EXPECTED_ARCHIVES, androct_raw_dir
from abrg.apigraph import APIGRAPH_OUTPUT_ROOT


def normalize_callee(soot_sig: str) -> str | None:
    """fully.qualified.Class.methodName — drop params and return type."""
    parsed = parse_soot_method_signature(soot_sig)
    if parsed is None:
        return None
    cls, meth = parsed
    return f"{cls}.{meth}"


@lru_cache(maxsize=200_000)
def category_for_callee(callee: str) -> str:
    cls, _, meth = callee.rpartition(".")
    if not cls or not meth:
        return "unmapped"
    # Rebuild a minimal soot-like path via categorize_soot_callee needs soot sig;
    # use categorize_callee package rules through a synthetic soot form.
    from abrg.api_category_map import categorize_callee
    from abrg.registry import DROPPED_CATEGORIES, GRAPH_CATEGORY_UNIVERSE

    cats = categorize_callee(cls, meth) - DROPPED_CATEGORIES
    cats &= frozenset(GRAPH_CATEGORY_UNIVERSE)
    if not cats:
        # try HOOK map
        from abrg.api_category_map import HOOK_API_TO_CATEGORY

        simple = f"{cls.split('.')[-1]}.{meth}"
        hit = HOOK_API_TO_CATEGORY.get(simple)
        if hit and hit in GRAPH_CATEGORY_UNIVERSE:
            return hit
        return "unmapped"
    # same priority as categorize_soot_callee
    from abrg.androct.categorize import _PRIORITY

    for pref in _PRIORITY:
        if pref in cats:
            return pref
    return sorted(cats)[0]


def _iter_call_lines(text_io: io.TextIOWrapper) -> Iterator[str]:
    for line in text_io:
        m = _CALL_RE.match(line.rstrip("\n\r"))
        if not m:
            continue
        callee = normalize_callee(m.group(2))
        if callee is not None:
            yield callee


def extract_sequences(
    apps: list[Any],
    *,
    cache_dir: Path | None = None,
    force: bool = False,
) -> dict[str, list[str]]:
    """
    Extract normalized callee sequences for apps. Cache under apigraph/cache/sequences/.
    One pass per tar archive.
    """
    cache_dir = cache_dir or (APIGRAPH_OUTPUT_ROOT / "cache" / "sequences")
    cache_dir.mkdir(parents=True, exist_ok=True)
    want = {a.path: a for a in apps}
    out: dict[str, list[str]] = {}
    pending = []
    for a in apps:
        cp = cache_dir / f"{a.sha256}.json"
        if cp.is_file() and not force:
            out[a.sha256] = json.loads(cp.read_text(encoding="utf-8"))
        else:
            pending.append(a)

    if not pending:
        print(f"[apigraph] sequences cache hit n={len(out)}", flush=True)
        return out

    print(f"[apigraph] extracting sequences for {len(pending)} apps …", flush=True)
    by_label: dict[str, list] = {"benign": [], "malware": []}
    for a in pending:
        by_label[a.label].append(a)

    raw = androct_raw_dir()
    for label, group in by_label.items():
        if not group:
            continue
        fname = next(
            name
            for name, meta in EXPECTED_ARCHIVES.items()
            if meta["label"] == label
        )
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
                    seq = list(_iter_call_lines(text))
                finally:
                    text.detach()
                out[app.sha256] = seq
                (cache_dir / f"{app.sha256}.json").write_text(
                    json.dumps(seq), encoding="utf-8"
                )
                found += 1
                if found % 100 == 0:
                    print(f"  … {label} extracted={found}/{len(group)}", flush=True)
        missing = [a.sha256 for a in group if a.sha256 not in out]
        if missing:
            raise SystemExit(f"STOP: missing traces for {len(missing)} {label} apps e.g. {missing[:3]}")
        print(f"[apigraph] {label} sequences done n={found}", flush=True)

    # reload any that were cached before pending
    for a in apps:
        if a.sha256 not in out:
            out[a.sha256] = json.loads((cache_dir / f"{a.sha256}.json").read_text(encoding="utf-8"))
    return out
