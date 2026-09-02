"""Parse DroidFax / AndroCT ``*.apk.logcat`` call traces (no fabricated timestamps)."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Iterable, Iterator, TextIO

from abrg.androct.categorize import categorize_icc_callsite, categorize_soot_callee
from abrg.registry import GRAPH_CATEGORY_UNIVERSE

# Soot method ref: <class: ret name(args)> with optional Jimple quoting inside.
_SOOT_SIG = r"<(?:[^<>']|<(?:cl)?init>|'[^']*')+>"
# Call edge; optional same-line reflection suffix.
_CALL_RE = re.compile(
    rf"^\s*({_SOOT_SIG})\s*->\s*({_SOOT_SIG})\s*(\+through\s+reflection)?\s*$"
)
_REFLECTION_LINE = re.compile(r"^\s*\+through\s+reflection\s*$", re.IGNORECASE)
_INTENT_SENT = re.compile(r"^\s*\[\s*Intent\s+sent\s*\]\s*$", re.IGNORECASE)
_INTENT_RECV = re.compile(r"^\s*\[\s*Intent\s+received\s*\]\s*$", re.IGNORECASE)
_ICC_CALLER = re.compile(r"^\s*caller=(.*)$")
_ICC_CALLSITE = re.compile(r"^\s*callsite=(.*)$")
_ICC_FIELD = re.compile(
    r"^\t+(Action|Categories|PackageName|DataString|DataURI|Scheme|Type|Flags|Extras|"
    r"Component|ClipData)=",
    re.IGNORECASE,
)
_ICC_CATEGORY_ITEM = re.compile(r"^\t{2,}\S")
_LOG_BEGIN = re.compile(r"^-+ beginning of")


@dataclass
class CallEvent:
    """One ordered behavioral event (call or ICC). No wall-clock time."""

    kind: str  # "call" | "icc_sent" | "icc_recv"
    caller: str | None
    callee: str | None
    category: str | None
    through_reflection: bool = False
    callsite: str | None = None


@dataclass
class AndroCTParseReport:
    path: str = ""
    label: str = ""
    sha256: str = ""
    n_lines: int = 0
    n_blank: int = 0
    n_dropped: int = 0
    n_allowed_misc: int = 0
    n_call_events: int = 0
    n_icc_events: int = 0
    n_reflection_calls: int = 0
    n_mapped_events: int = 0
    header_only: bool = False
    category_counts: dict[str, int] = field(default_factory=dict)
    dropped_examples: list[str] = field(default_factory=list)

    @property
    def n_events(self) -> int:
        return self.n_call_events + self.n_icc_events

    @property
    def mapped_rate(self) -> float:
        return (self.n_mapped_events / self.n_events) if self.n_events else 0.0

    @property
    def active_categories(self) -> set[str]:
        return {c for c, n in self.category_counts.items() if n > 0}


def _sha_from_member_name(name: str) -> str:
    base = name.rsplit("/", 1)[-1]
    if base.endswith(".apk.logcat"):
        stem = base[: -len(".apk.logcat")]
    else:
        stem = base
    if re.fullmatch(r"[0-9A-Fa-f]{64}", stem):
        return stem.upper()
    return stem


def _record_drop(report: AndroCTParseReport, line: str) -> None:
    report.n_dropped += 1
    if len(report.dropped_examples) < 5:
        report.dropped_examples.append(line[:200])


def _bump_cat(report: AndroCTParseReport, cat: str | None) -> None:
    if cat is None:
        return
    report.n_mapped_events += 1
    report.category_counts[cat] = report.category_counts.get(cat, 0) + 1


def _emit_call(
    report: AndroCTParseReport,
    events: list[CallEvent] | None,
    caller: str,
    callee: str,
    through_ref: bool,
) -> None:
    cat = categorize_soot_callee(callee)
    report.n_call_events += 1
    if through_ref:
        report.n_reflection_calls += 1
    _bump_cat(report, cat)
    if events is not None:
        events.append(
            CallEvent(
                kind="call",
                caller=caller,
                callee=callee,
                category=cat,
                through_reflection=through_ref,
            )
        )


def parse_androct_lines(
    lines: Iterable[str],
    *,
    path: str = "",
    label: str = "",
    yield_events: bool = False,
) -> tuple[AndroCTParseReport, list[CallEvent] | None]:
    """
    Allowlist-filter DroidFax markers; count drops explicitly.

    Allowed:
      - ``<caller> -> <callee>`` (+ optional ``+through reflection`` suffix)
      - standalone ``+through reflection`` (marks the *following* call)
      - ``[ Intent sent ]`` / ``[ Intent received ]`` + ICC field lines

    Call lines may interleave with ICC field lines; ICC state is kept open until
    a non-ICC, non-call line appears or EOF.
    """
    report = AndroCTParseReport(path=path, label=label, sha256=_sha_from_member_name(path))
    events: list[CallEvent] | None = [] if yield_events else None
    pending_reflection = False
    in_icc = False
    icc_kind: str | None = None
    icc_caller: str | None = None
    icc_callsite: str | None = None
    icc_seen_meta = False

    def flush_icc() -> None:
        nonlocal in_icc, icc_kind, icc_caller, icc_callsite, icc_seen_meta
        if not in_icc or icc_kind is None:
            in_icc = False
            return
        cat = categorize_icc_callsite(icc_callsite)
        report.n_icc_events += 1
        _bump_cat(report, cat)
        if events is not None:
            events.append(
                CallEvent(
                    kind=icc_kind,
                    caller=icc_caller,
                    callee=None,
                    category=cat,
                    callsite=icc_callsite,
                )
            )
        in_icc = False
        icc_kind = None
        icc_caller = None
        icc_callsite = None
        icc_seen_meta = False

    for raw in lines:
        report.n_lines += 1
        line = raw.rstrip("\n\r")
        if not line.strip():
            report.n_blank += 1
            continue

        if _REFLECTION_LINE.match(line):
            report.n_allowed_misc += 1
            pending_reflection = True
            continue

        if _INTENT_SENT.match(line) or _INTENT_RECV.match(line):
            flush_icc()
            in_icc = True
            icc_kind = "icc_sent" if _INTENT_SENT.match(line) else "icc_recv"
            icc_caller = None
            icc_callsite = None
            icc_seen_meta = False
            continue

        m_call = _CALL_RE.match(line)
        if m_call:
            # Calls may sit between Intent marker and its field lines — keep ICC open.
            through_ref = bool(m_call.group(3)) or pending_reflection
            pending_reflection = False
            _emit_call(report, events, m_call.group(1), m_call.group(2), through_ref)
            continue

        if in_icc:
            mc = _ICC_CALLER.match(line)
            if mc:
                report.n_allowed_misc += 1
                icc_caller = mc.group(1).strip()
                icc_seen_meta = True
                continue
            ms = _ICC_CALLSITE.match(line)
            if ms:
                report.n_allowed_misc += 1
                icc_callsite = ms.group(1).strip()
                icc_seen_meta = True
                continue
            if _ICC_FIELD.match(line) or _ICC_CATEGORY_ITEM.match(line):
                report.n_allowed_misc += 1
                icc_seen_meta = True
                continue
            # End of ICC block (or never received fields).
            flush_icc()
            # Re-classify this line outside ICC context (one-level retry).
            if _REFLECTION_LINE.match(line):
                report.n_allowed_misc += 1
                pending_reflection = True
                continue
            m_call = _CALL_RE.match(line)
            if m_call:
                through_ref = bool(m_call.group(3)) or pending_reflection
                pending_reflection = False
                _emit_call(report, events, m_call.group(1), m_call.group(2), through_ref)
                continue
            if _INTENT_SENT.match(line) or _INTENT_RECV.match(line):
                in_icc = True
                icc_kind = "icc_sent" if _INTENT_SENT.match(line) else "icc_recv"
                continue

        if _LOG_BEGIN.match(line.strip()):
            _record_drop(report, line)
            continue

        _record_drop(report, line)

    flush_icc()
    report.header_only = report.n_events == 0
    for c in GRAPH_CATEGORY_UNIVERSE:
        report.category_counts.setdefault(c, 0)
    return report, events


def parse_androct_logcat(
    source: str | TextIO | Iterator[str],
    *,
    path: str = "",
    label: str = "",
    yield_events: bool = False,
) -> tuple[AndroCTParseReport, list[CallEvent] | None]:
    if isinstance(source, str):
        lines: Iterable[str] = source.splitlines()
    else:
        lines = source  # type: ignore[assignment]
    return parse_androct_lines(lines, path=path, label=label, yield_events=yield_events)


def parse_androct_text_stream(
    stream: TextIO,
    *,
    path: str = "",
    label: str = "",
    yield_events: bool = False,
) -> tuple[AndroCTParseReport, list[CallEvent] | None]:
    return parse_androct_logcat(stream, path=path, label=label, yield_events=yield_events)


def parse_androct_bytes(
    data: bytes,
    *,
    path: str = "",
    label: str = "",
    yield_events: bool = False,
) -> tuple[AndroCTParseReport, list[CallEvent] | None]:
    text = io.TextIOWrapper(io.BytesIO(data), encoding="utf-8", errors="replace")
    try:
        return parse_androct_logcat(text, path=path, label=label, yield_events=yield_events)
    finally:
        text.detach()
