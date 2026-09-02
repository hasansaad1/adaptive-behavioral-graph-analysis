"""AndroCT 2017 pre-graph diagnostics (read-only; does not modify parser/mapper)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import re
import tarfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from abrg.androct.categorize import (
    categorize_soot_callee,
    parse_soot_method_signature,
    unquote_jimple_ident,
)
from abrg.androct.parse import _CALL_RE  # noqa: PLC2701 — stage probe only
from abrg.androct.paths import ANDROCT_2017_ROOT, EXPECTED_ARCHIVES, androct_raw_dir
from abrg.api_category_map import categorize_callee
from abrg.registry import DROPPED_CATEGORIES, GRAPH_CATEGORY_UNIVERSE

DIAG_DIR = ANDROCT_2017_ROOT / "inventory" / "diagnostics"
SEED = 42

# Check 1 — raw callee-position probes (exact substrings as specified).
PROBE_SUBSTRINGS: tuple[str, ...] = (
    "SmsManager",
    "android.telephony",
    "sendTextMessage",
    "sendMultipartTextMessage",
    "SmsMessage",
    "DexClassLoader",
    "PathClassLoader",
    "BaseDexClassLoader",
    "InMemoryDexClassLoader",
    "System.load",
    "System.loadLibrary",
    "Runtime.exec",
)

# Known networking / TLS caller namespaces (Check 2).
TLS_NETWORK_PREFIXES: tuple[str, ...] = (
    "okhttp3.",
    "com.squareup.okhttp.",
    "com.android.okhttp.",
    "org.apache.http.",
    "org.apache.commons.http",
    "cz.msebera.android.httpclient.",
    "com.android.org.conscrypt.",
    "org.conscrypt.",
    "com.google.android.gms.org.conscrypt.",
    "java.net.",
    "javax.net.",
    "javax.net.ssl.",
    "android.net.",
    "com.android.volley.",
    "com.android.okhttp",
    "libcore.net.",
    "com.google.android.gms.internal.",  # often ads/network; counted separately in report notes via prefix table
)

_GRAPH_SET = frozenset(GRAPH_CATEGORY_UNIVERSE)

# Broader call-line detector for Check 3 "should have been allowed" (diagnostic only).
_PERMISSIVE_CALL = re.compile(
    r"^\s*(<[^>\n]+>)\s*->\s*(<[^>\n]+>)\s*(\+through\s+reflection)?\s*$"
)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    return float(sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f))


def _dist(vals: list[float | int]) -> dict[str, float]:
    if not vals:
        return {
            "n": 0,
            "min": math.nan,
            "p10": math.nan,
            "p25": math.nan,
            "p50": math.nan,
            "p75": math.nan,
            "p90": math.nan,
            "max": math.nan,
            "mean": math.nan,
            "mean_over_median": math.nan,
        }
    s = sorted(float(v) for v in vals)
    med = _pct(s, 50)
    mean = sum(s) / len(s)
    return {
        "n": len(s),
        "min": s[0],
        "p10": _pct(s, 10),
        "p25": _pct(s, 25),
        "p50": med,
        "p75": _pct(s, 75),
        "p90": _pct(s, 90),
        "max": s[-1],
        "mean": mean,
        "mean_over_median": (mean / med) if med else float("nan"),
    }


def _callee_side(line: str) -> str | None:
    """Text after first ' -> ' (callee position); None if absent."""
    idx = line.find(" -> ")
    if idx < 0:
        return None
    return line[idx + 4 :]


def _class_from_sig(sig: str) -> str | None:
    parsed = parse_soot_method_signature(sig)
    return parsed[0] if parsed else None


def _pipeline_stages(line: str) -> dict[str, Any]:
    """
    Stage-by-stage probe of one raw line (imports existing parser pieces; no edits).

    Stages:
      allowlist -> line_parse -> caller_callee_split -> signature_decomp -> categorize_callee
      -> categorize_soot_callee (adapter final)
    """
    out: dict[str, Any] = {
        "line": line[:500],
        "allowlist": False,
        "line_parse": False,
        "caller_callee_split": False,
        "signature_decomp": False,
        "class_name": None,
        "method_name": None,
        "categorize_callee_set": None,
        "categorize_callee_graph": None,
        "categorize_soot_callee": None,
        "fail_stage": None,
    }
    m = _CALL_RE.match(line)
    if not m:
        # Also try strip — parser uses match on full line.
        out["fail_stage"] = "allowlist_filter"
        # Diagnostic: would permissive pattern accept?
        out["permissive_would_accept"] = bool(_PERMISSIVE_CALL.match(line))
        return out
    out["allowlist"] = True
    out["line_parse"] = True
    caller, callee, _ref = m.group(1), m.group(2), m.group(3)
    if not caller or not callee:
        out["fail_stage"] = "caller_callee_split"
        return out
    out["caller_callee_split"] = True
    out["caller"] = caller
    out["callee"] = callee
    parsed = parse_soot_method_signature(callee)
    if parsed is None:
        out["fail_stage"] = "signature_decomposition"
        return out
    out["signature_decomp"] = True
    class_name, method_name = parsed
    out["class_name"] = class_name
    out["method_name"] = method_name
    raw_set = categorize_callee(class_name, method_name)
    graph_set = (raw_set - DROPPED_CATEGORIES) & _GRAPH_SET
    out["categorize_callee_set"] = sorted(raw_set)
    out["categorize_callee_graph"] = sorted(graph_set)
    final = categorize_soot_callee(callee)
    out["categorize_soot_callee"] = final
    if not graph_set and final is None:
        out["fail_stage"] = "categorize_callee"
    elif final is None and graph_set:
        out["fail_stage"] = "categorize_soot_callee_adapter"
    return out


def _decomp_failure_cause(callee: str) -> str | None:
    """If signature decomposition fails, classify cause; else None."""
    s = callee.strip()
    if s.startswith("<") and s.endswith(">"):
        s = s[1:-1]
    if ": " not in s:
        return "no_colon_separator"
    class_part, rest = s.split(": ", 1)
    if "'" in class_part or "'" in rest:
        # quoting present — try normal parse; if fail, quoting-related
        if parse_soot_method_signature(callee) is None:
            if re.search(r"['\u0080-\uffff]", callee):
                if re.search(r"[\u0080-\uffff]", callee):
                    return "unicode"
                return "quoting"
    if "<" in rest or ">" in rest.replace(")", ""):
        # generics in return/args often break naive patterns — soot usually doesn't nest here
        if parse_soot_method_signature(callee) is None:
            return "generics"
    if "[]" in callee and parse_soot_method_signature(callee) is None:
        return "array_types"
    if "$" in class_part and parse_soot_method_signature(callee) is None:
        return "inner_classes"
    paren = rest.find("(")
    if paren < 0:
        return "no_method_paren"
    head = rest[:paren].strip()
    bits = head.rsplit(None, 1)
    if len(bits) != 2:
        return "unexpected_arity_or_head"
    if parse_soot_method_signature(callee) is None:
        return "other"
    return None


def _is_tls_network_caller(caller_class: str) -> bool:
    return any(caller_class.startswith(p) for p in TLS_NETWORK_PREFIXES)


def _drop_bucket(line: str) -> str:
    s = line.strip()
    if s.startswith("--------- beginning of") or s.startswith("---------"):
        return "logcat_system_output"
    if re.match(r"^[A-Z]/WDEFV]/s*\(\d+\)", s):  # classic logcat tag line
        return "logcat_system_output"
    if "AndroidRuntime" in s or "FATAL EXCEPTION" in s or s.startswith("Process:"):
        return "logcat_system_output"
    if s.startswith("+through reflection"):
        return "droidfax_marker_not_in_allowlist"  # should be allowed — if dropped, bug
    if s.startswith("[ Intent"):
        return "droidfax_marker_not_in_allowlist"
    if s.startswith("caller=") or s.startswith("callsite=") or s.startswith("\t"):
        return "droidfax_marker_not_in_allowlist"
    if _CALL_RE.match(line):
        return "well_formed_call_should_have_been_allowed"
    if _PERMISSIVE_CALL.match(line):
        return "well_formed_call_should_have_been_allowed"
    if "<" in s and "->" in s:
        return "malformed_or_truncated_call_line"
    if s.startswith("<") and "->" in s:
        return "malformed_or_truncated_call_line"
    return "other"


class Reservoir:
    def __init__(self, k: int, rng: random.Random):
        self.k = k
        self.rng = rng
        self.n_seen = 0
        self.items: list[Any] = []

    def offer(self, item: Any) -> None:
        self.n_seen += 1
        if len(self.items) < self.k:
            self.items.append(item)
            return
        j = self.rng.randrange(self.n_seen)
        if j < self.k:
            self.items[j] = item


def iter_archive_lines(archive: Path) -> Iterable[tuple[str, str, str]]:
    """Yield (member_path, sha_or_stem, line) for each non-blank line."""
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf:
            if not member.isfile() or not member.name.endswith(".apk.logcat"):
                continue
            base = member.name.rsplit("/", 1)[-1]
            stem = base[: -len(".apk.logcat")] if base.endswith(".apk.logcat") else base
            handle = tf.extractfile(member)
            if handle is None:
                continue
            text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
            try:
                for line in text:
                    line = line.rstrip("\n\r")
                    yield member.name, stem, line
            finally:
                text.detach()


def run_check1(raw_dir: Path, out_dir: Path) -> dict[str, Any]:
    rng = random.Random(SEED)
    result: dict[str, Any] = {"check": 1, "probes": {}, "pipeline": {}, "generalization": {}}

    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        archive = raw_dir / fname
        print(f"[check1] raw probe {label} …", flush=True)
        # per substring: line_count, apps set, examples
        sub_stats = {
            s: {"raw_line_count": 0, "apps": set(), "examples": []}
            for s in PROBE_SUBSTRINGS
        }
        # Collect ALL matched lines for pipeline (may be large — stream stage counts)
        stage_counts = Counter()
        fail_examples: dict[str, list[str]] = defaultdict(list)
        matched_for_pipeline = 0
        post_mapper_sms = 0
        post_mapper_dcl = 0
        # For lines matching sms/dcl related probes specifically
        probe_pipeline_rows: list[dict[str, Any]] = []

        # generalization reservoirs
        call_sample = Reservoir(2000, rng)

        n_files = 0
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                n_files += 1
                if n_files % 200 == 0:
                    print(f"  … {label} check1 files={n_files}", flush=True)
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
                try:
                    for line in text:
                        line = line.rstrip("\n\r")
                        if not line.strip():
                            continue
                        callee_txt = _callee_side(line)
                        if callee_txt is not None:
                            for sub in PROBE_SUBSTRINGS:
                                if sub in callee_txt:
                                    st = sub_stats[sub]
                                    st["raw_line_count"] += 1
                                    st["apps"].add(member.name)
                                    if len(st["examples"]) < 5:
                                        st["examples"].append(line[:400])
                                    # pipeline every matched probe line
                                    stages = _pipeline_stages(line)
                                    matched_for_pipeline += 1
                                    # surviving counts
                                    if stages["allowlist"]:
                                        stage_counts["allowlist"] += 1
                                    else:
                                        stage_counts["fail_allowlist"] += 1
                                        if len(fail_examples["allowlist_filter"]) < 20:
                                            fail_examples["allowlist_filter"].append(line[:400])
                                        continue
                                    if stages["caller_callee_split"]:
                                        stage_counts["caller_callee_split"] += 1
                                    else:
                                        stage_counts["fail_caller_callee_split"] += 1
                                        continue
                                    if stages["signature_decomp"]:
                                        stage_counts["signature_decomp"] += 1
                                    else:
                                        stage_counts["fail_signature_decomp"] += 1
                                        if len(fail_examples["signature_decomposition"]) < 20:
                                            fail_examples["signature_decomposition"].append(
                                                json.dumps(
                                                    {
                                                        "line": line[:300],
                                                        "callee": stages.get("callee"),
                                                    }
                                                )
                                            )
                                        continue
                                    stage_counts["reached_categorize_callee"] += 1
                                    if stages["categorize_callee_graph"]:
                                        stage_counts["categorize_callee_nonempty_graph"] += 1
                                    else:
                                        stage_counts["fail_categorize_callee_empty"] += 1
                                        if len(fail_examples["categorize_callee"]) < 30:
                                            fail_examples["categorize_callee"].append(
                                                json.dumps(
                                                    {
                                                        "class": stages["class_name"],
                                                        "method": stages["method_name"],
                                                        "raw_set": stages["categorize_callee_set"],
                                                        "line": line[:300],
                                                    }
                                                )
                                            )
                                    final = stages["categorize_soot_callee"]
                                    if final == "sms":
                                        post_mapper_sms += 1
                                        stage_counts["final_sms"] += 1
                                    if final == "dynamic_code_loading":
                                        post_mapper_dcl += 1
                                        stage_counts["final_dynamic_code_loading"] += 1
                                    if final is not None:
                                        stage_counts["final_mapped"] += 1
                                    if len(probe_pipeline_rows) < 5000:
                                        probe_pipeline_rows.append(
                                            {
                                                "label": label,
                                                "path": member.name,
                                                "substring_hits": [
                                                    s
                                                    for s in PROBE_SUBSTRINGS
                                                    if s in (callee_txt or "")
                                                ],
                                                "fail_stage": stages.get("fail_stage"),
                                                "final": final,
                                                "class_name": stages.get("class_name"),
                                                "method_name": stages.get("method_name"),
                                                "raw_set": stages.get("categorize_callee_set"),
                                                "line": line[:400],
                                            }
                                        )

                        # generalization: allowlisted calls
                        m = _CALL_RE.match(line)
                        if m:
                            call_sample.offer(m.group(2))
                finally:
                    text.detach()

        # Serialize probe stats
        result["probes"][label] = {
            sub: {
                "raw_line_count": sub_stats[sub]["raw_line_count"],
                "n_apps": len(sub_stats[sub]["apps"]),
                "examples": sub_stats[sub]["examples"],
            }
            for sub in PROBE_SUBSTRINGS
        }
        result["pipeline"][label] = {
            "matched_probe_lines_processed": matched_for_pipeline,
            "stage_counts": dict(stage_counts),
            "post_mapper_sms": post_mapper_sms,
            "post_mapper_dynamic_code_loading": post_mapper_dcl,
            "fail_examples": {k: v for k, v in fail_examples.items()},
            "sample_pipeline_rows_n": len(probe_pipeline_rows),
        }

        # Gate analysis across all probe-matched lines that mention sms/dcl indicators
        raw_sms_related = sum(
            result["probes"][label][s]["raw_line_count"]
            for s in (
                "SmsManager",
                "sendTextMessage",
                "sendMultipartTextMessage",
                "SmsMessage",
            )
        )
        raw_dcl_related = sum(
            result["probes"][label][s]["raw_line_count"]
            for s in (
                "DexClassLoader",
                "PathClassLoader",
                "BaseDexClassLoader",
                "InMemoryDexClassLoader",
            )
        )
        result["pipeline"][label]["raw_sms_related_line_count"] = raw_sms_related
        result["pipeline"][label]["raw_dcl_related_line_count"] = raw_dcl_related

        # Generalization on 2000 allowlisted callees
        print(f"[check1] generalization sample {label} n={len(call_sample.items)}", flush=True)
        decomp_fail = Counter()
        empty_cat = 0
        ok = 0
        empty_prefixes: Counter[str] = Counter()
        for callee in call_sample.items:
            cause = _decomp_failure_cause(callee)
            parsed = parse_soot_method_signature(callee)
            if parsed is None:
                decomp_fail[cause or "other"] += 1
                continue
            ok += 1
            class_name, method_name = parsed
            cats = (categorize_callee(class_name, method_name) - DROPPED_CATEGORIES) & _GRAPH_SET
            # also check adapter
            final = categorize_soot_callee(callee)
            if not cats and final is None:
                empty_cat += 1
                parts = class_name.split(".")
                # prefix: first 2 segments, else full
                pref = ".".join(parts[:2]) if len(parts) >= 2 else class_name
                empty_prefixes[pref] += 1
            elif cats:
                pass
            else:
                empty_cat += 1
                parts = class_name.split(".")
                pref = ".".join(parts[:2]) if len(parts) >= 2 else class_name
                empty_prefixes[pref] += 1

        n_samp = len(call_sample.items)
        result["generalization"][label] = {
            "n_sampled_allowlisted_callees": n_samp,
            "n_seen_allowlisted_calls": call_sample.n_seen,
            "decomp_success": ok,
            "decomp_fail": dict(decomp_fail),
            "decomp_fail_rate": (sum(decomp_fail.values()) / n_samp) if n_samp else float("nan"),
            "empty_category_set_among_decomp_ok": empty_cat,
            "empty_category_rate_among_decomp_ok": (empty_cat / ok) if ok else float("nan"),
            "top50_empty_category_class_prefixes": empty_prefixes.most_common(50),
        }

        # Write per-label probe CSV
        with (out_dir / f"check1_probes_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["substring", "raw_line_count", "n_apps", "example_1", "example_2", "example_3", "example_4", "example_5"])
            for sub in PROBE_SUBSTRINGS:
                st = result["probes"][label][sub]
                ex = st["examples"] + [""] * 5
                w.writerow([sub, st["raw_line_count"], st["n_apps"], *ex[:5]])

        with (out_dir / f"check1_pipeline_samples_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "label",
                    "path",
                    "substring_hits",
                    "fail_stage",
                    "final",
                    "class_name",
                    "method_name",
                    "raw_set",
                    "line",
                ],
            )
            w.writeheader()
            for row in probe_pipeline_rows:
                w.writerow(
                    {
                        **row,
                        "substring_hits": "|".join(row["substring_hits"]),
                        "raw_set": "|".join(row["raw_set"] or []),
                    }
                )

        with (out_dir / f"check1_empty_prefixes_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "class_prefix", "count"])
            for i, (pref, c) in enumerate(empty_prefixes.most_common(50), 1):
                w.writerow([i, pref, c])

    # Gate summary
    gates = {}
    for label in ("benign", "malware"):
        p = result["pipeline"][label]
        gates[label] = {
            "sms": {
                "raw_related": p["raw_sms_related_line_count"],
                "post_mapper": p["post_mapper_sms"],
                "gate_trip": p["raw_sms_related_line_count"] > 0 and p["post_mapper_sms"] == 0,
            },
            "dynamic_code_loading": {
                "raw_related": p["raw_dcl_related_line_count"],
                "post_mapper": p["post_mapper_dynamic_code_loading"],
                "gate_trip": p["raw_dcl_related_line_count"] > 0
                and p["post_mapper_dynamic_code_loading"] == 0,
            },
            "android.telephony_raw": result["probes"][label]["android.telephony"]["raw_line_count"],
            "System.loadLibrary_raw": result["probes"][label]["System.loadLibrary"]["raw_line_count"],
            "Runtime.exec_raw": result["probes"][label]["Runtime.exec"]["raw_line_count"],
            "fail_stage_counts": {
                k: v
                for k, v in p["stage_counts"].items()
                if k.startswith("fail_") or k in (
                    "allowlist",
                    "signature_decomp",
                    "categorize_callee_nonempty_graph",
                    "final_sms",
                    "final_dynamic_code_loading",
                )
            },
            "fail_examples": p["fail_examples"],
        }
    result["gate"] = gates
    (out_dir / "check1_gate.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result


# ---------------------------------------------------------------------------
# Checks 2–4 (run only after Check 1 gate is written)
# ---------------------------------------------------------------------------


def run_checks_2_3_4(raw_dir: Path, out_dir: Path) -> dict[str, Any]:
    rng = random.Random(SEED)
    out: dict[str, Any] = {"check2": {}, "check3": {}, "check4": {}}

    for fname, meta in EXPECTED_ARCHIVES.items():
        label = meta["label"]
        archive = raw_dir / fname
        print(f"[check2-4] pass {label} …", flush=True)

        crypto_callee: Counter[str] = Counter()
        crypto_caller: Counter[str] = Counter()
        network_caller: Counter[str] = Counter()
        file_io_caller: Counter[str] = Counter()
        crypto_app = 0
        crypto_tls = 0
        crypto_other = 0
        crypto_total = 0

        # per-app accumulators
        app_crypto: dict[str, int] = defaultdict(int)
        app_mapped: dict[str, int] = defaultdict(int)
        app_caller_pref: dict[str, Counter[str]] = defaultdict(Counter)
        app_n_events: dict[str, int] = defaultdict(int)
        app_n_mapped: dict[str, int] = defaultdict(int)
        app_n_active: dict[str, set[str]] = defaultdict(set)
        app_n_dropped: dict[str, int] = defaultdict(int)
        app_n_lines_nonblank: dict[str, int] = defaultdict(int)

        drop_res = Reservoir(500, rng)
        drop_prefixes: Counter[str] = Counter()

        # For check2 caller classification we need dominant package first —
        # two-pass per file: collect then classify crypto. Do per-file.
        n_files = 0
        with tarfile.open(archive, "r:gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".apk.logcat"):
                    continue
                n_files += 1
                if n_files % 200 == 0:
                    print(f"  … {label} c2-4 files={n_files}", flush=True)
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                text = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")

                # Single stream pass: defer crypto app/tls split until dominant pkg known.
                caller_pkg_counts: Counter[str] = Counter()
                crypto_callers_this_app: list[str] = []
                n_dropped = 0
                n_nonblank = 0
                n_events = 0
                n_mapped = 0
                active: set[str] = set()
                app_key = member.name

                try:
                    for line in text:
                        line = line.rstrip("\n\r")
                        if not line.strip():
                            continue
                        n_nonblank += 1
                        m = _CALL_RE.match(line)
                        if m:
                            n_events += 1
                            caller_sig, callee_sig = m.group(1), m.group(2)
                            ccls = _class_from_sig(caller_sig) or ""
                            if ccls:
                                pkg = ccls.rsplit(".", 1)[0] if "." in ccls else ccls
                                caller_pkg_counts[pkg] += 1
                            cat = categorize_soot_callee(callee_sig)
                            if cat is None:
                                continue
                            n_mapped += 1
                            active.add(cat)
                            callee_cls = _class_from_sig(callee_sig) or ""
                            if cat == "crypto":
                                crypto_total += 1
                                crypto_callee[callee_cls] += 1
                                crypto_caller[ccls] += 1
                                app_crypto[app_key] += 1
                                crypto_callers_this_app.append(ccls)
                            elif cat == "network":
                                network_caller[ccls] += 1
                            elif cat == "file_io":
                                file_io_caller[ccls] += 1
                            continue
                        if re.match(
                            r"^\s*\[\s*Intent\s+(sent|received)\s*\]\s*$", line, re.I
                        ):
                            n_events += 1
                            continue
                        if re.match(r"^\s*\+through\s+reflection\s*$", line, re.I):
                            continue
                        if line.startswith("caller=") or line.startswith("callsite="):
                            continue
                        if line.startswith("\t"):
                            continue
                        n_dropped += 1
                        pref = line[:40].replace("\t", "\\t")
                        drop_prefixes[pref] += 1
                        drop_res.offer(line[:500])
                finally:
                    text.detach()

                dominant_pkg = (
                    caller_pkg_counts.most_common(1)[0][0] if caller_pkg_counts else ""
                )
                for ccls in crypto_callers_this_app:
                    is_app = bool(dominant_pkg) and (
                        ccls == dominant_pkg or ccls.startswith(dominant_pkg + ".")
                    )
                    is_tls = _is_tls_network_caller(ccls)
                    if is_app and not is_tls:
                        crypto_app += 1
                    elif is_tls:
                        crypto_tls += 1
                    else:
                        crypto_other += 1

                app_n_events[app_key] = n_events
                app_n_dropped[app_key] = n_dropped
                app_n_lines_nonblank[app_key] = n_nonblank
                app_mapped[app_key] = n_mapped
                app_n_mapped[app_key] = n_mapped
                app_n_active[app_key] = active
                if dominant_pkg:
                    app_caller_pref[app_key][dominant_pkg] = caller_pkg_counts[dominant_pkg]

        # Check 2 aggregates
        crypto_shares = []
        n_crypto_gt_50 = 0
        for app, nm in app_mapped.items():
            if nm <= 0:
                continue
            share = app_crypto[app] / nm
            crypto_shares.append(share)
            if share > 0.5:
                n_crypto_gt_50 += 1

        def top30(counter: Counter[str]) -> list[list[Any]]:
            return [[k, v] for k, v in counter.most_common(30)]

        # Proposed split counts already in crypto_app / crypto_tls / crypto_other
        out["check2"][label] = {
            "crypto_total_events": crypto_total,
            "top30_crypto_callee_classes": top30(crypto_callee),
            "top30_crypto_caller_classes": top30(crypto_caller),
            "top30_network_caller_classes": top30(network_caller),
            "top30_file_io_caller_classes": top30(file_io_caller),
            "crypto_caller_share": {
                "app_own_package": crypto_app,
                "tls_or_network_library": crypto_tls,
                "other": crypto_other,
                "app_own_package_frac": (crypto_app / crypto_total) if crypto_total else float("nan"),
                "tls_or_network_library_frac": (crypto_tls / crypto_total) if crypto_total else float("nan"),
                "other_frac": (crypto_other / crypto_total) if crypto_total else float("nan"),
            },
            "proposed_crypto_split": {
                "app_initiated_events": crypto_app,
                "transport_layer_events": crypto_tls,
                "unassigned_other_events": crypto_other,
                "rule": (
                    "app_initiated := caller class is under the app's dominant caller "
                    "package (mode of caller packages in that trace) and not under "
                    "TLS_NETWORK_PREFIXES; transport_layer := caller under TLS_NETWORK_PREFIXES; "
                    "else other"
                ),
                "tls_network_prefixes": list(TLS_NETWORK_PREFIXES),
            },
            "per_app_crypto_share_of_mapped": {
                **_dist(crypto_shares),
                "n_apps_crypto_share_gt_50pct": n_crypto_gt_50,
            },
        }

        # Check 3
        bucket_counts: Counter[str] = Counter()
        bucket_examples: dict[str, list[str]] = defaultdict(list)
        for line in drop_res.items:
            b = _drop_bucket(line)
            bucket_counts[b] += 1
            if len(bucket_examples[b]) < 10:
                bucket_examples[b].append(line)

        drop_rates = []
        app_drop_rows = []
        for app, nd in app_n_dropped.items():
            nb = app_n_lines_nonblank[app]
            rate = (nd / nb) if nb else 0.0
            drop_rates.append(rate)
            app_drop_rows.append((rate, nd, nb, app_n_events[app], app))
        app_drop_rows.sort(reverse=True)

        out["check3"][label] = {
            "dropped_sample_n": len(drop_res.items),
            "dropped_sample_seen": drop_res.n_seen,
            "bucket_counts": dict(bucket_counts),
            "bucket_examples": {k: v for k, v in bucket_examples.items()},
            "top40_dropped_line_prefixes": drop_prefixes.most_common(40),
            "per_app_drop_rate_dist": _dist(drop_rates),
            "top20_highest_drop_rate_apps": [
                {
                    "path": a,
                    "drop_rate": r,
                    "n_dropped": nd,
                    "n_nonblank": nb,
                    "n_events": ne,
                }
                for r, nd, nb, ne, a in app_drop_rows[:20]
            ],
            "gate_well_formed_should_allowed_nonempty": bucket_counts.get(
                "well_formed_call_should_have_been_allowed", 0
            )
            > 0,
        }

        # Persist per-app metrics for check 4
        out.setdefault("_per_app", {})[label] = {
            "n_events": dict(app_n_events),
            "n_mapped": dict(app_n_mapped),
            "n_active": {k: len(v) for k, v in app_n_active.items()},
            "drop_rate": {
                k: (app_n_dropped[k] / app_n_lines_nonblank[k]) if app_n_lines_nonblank[k] else 0.0
                for k in app_n_events
            },
            # exclude header-only (0 events) for AUC on length metrics? Spec says per app —
            # use effective apps (n_events > 0) for event metrics; drop rate for all with lines
            "header_only": {k: app_n_events[k] == 0 for k in app_n_events},
        }

        # CSVs
        with (out_dir / f"check2_crypto_callees_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "callee_class", "count"])
            for i, (k, v) in enumerate(crypto_callee.most_common(30), 1):
                w.writerow([i, k, v])
        with (out_dir / f"check2_crypto_callers_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "caller_class", "count"])
            for i, (k, v) in enumerate(crypto_caller.most_common(30), 1):
                w.writerow([i, k, v])
        with (out_dir / f"check2_network_callers_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "caller_class", "count"])
            for i, (k, v) in enumerate(network_caller.most_common(30), 1):
                w.writerow([i, k, v])
        with (out_dir / f"check2_file_io_callers_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "caller_class", "count"])
            for i, (k, v) in enumerate(file_io_caller.most_common(30), 1):
                w.writerow([i, k, v])

        with (out_dir / f"check3_dropped_sample_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["bucket", "line"])
            for line in drop_res.items:
                w.writerow([_drop_bucket(line), line])
        with (out_dir / f"check3_drop_prefixes_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "prefix40", "count"])
            for i, (p, c) in enumerate(drop_prefixes.most_common(40), 1):
                w.writerow([i, p, c])
        with (out_dir / f"check3_top_drop_apps_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "path", "drop_rate", "n_dropped", "n_nonblank", "n_events"])
            for i, (r, nd, nb, ne, a) in enumerate(app_drop_rows[:20], 1):
                w.writerow([i, a, r, nd, nb, ne])

    # Check 4 AUCs
    def auc_and_dists(metric: str) -> dict[str, Any]:
        b_all = out["_per_app"]["benign"]
        m_all = out["_per_app"]["malware"]
        if metric == "drop_rate":
            bx = list(b_all["drop_rate"].values())
            mx = list(m_all["drop_rate"].values())
        elif metric == "n_active":
            bx = [v for k, v in b_all["n_active"].items() if not b_all["header_only"][k]]
            mx = [v for k, v in m_all["n_active"].items() if not m_all["header_only"][k]]
        else:
            bx = [v for k, v in b_all[metric].items() if not b_all["header_only"][k]]
            mx = [v for k, v in m_all[metric].items() if not m_all["header_only"][k]]
        # Mann-Whitney U via scipy; AUC = U / (n1*n2)
        from scipy.stats import mannwhitneyu

        res = mannwhitneyu(bx, mx, alternative="two-sided")
        # scipy returns U for first sample (benign); AUC_benign_gt = U/(n_b*n_m) is P(Xb > Xm) + 0.5 P(eq)
        nb, nm = len(bx), len(mx)
        auc_b_gt_m = float(res.statistic) / (nb * nm)
        db, dm = _dist(bx), _dist(mx)
        return {
            "metric": metric,
            "n_benign": nb,
            "n_malware": nm,
            "U": float(res.statistic),
            "p_value": float(res.pvalue),
            "AUC": auc_b_gt_m,
            "AUC_definition": "U_benign_vs_malware / (n_benign * n_malware) = P(X_benign > X_malware) + 0.5 P(eq)",
            "benign_dist": db,
            "malware_dist": dm,
            "higher_at_median": "benign" if db["p50"] > dm["p50"] else ("malware" if dm["p50"] > db["p50"] else "tie"),
            "higher_at_mean": "benign" if db["mean"] > dm["mean"] else ("malware" if dm["mean"] > db["mean"] else "tie"),
        }

    out["check4"] = {
        "total_event_count": auc_and_dists("n_events"),
        "mapped_event_count": auc_and_dists("n_mapped"),
        "distinct_active_categories": auc_and_dists("n_active"),
        "allowlist_drop_rate": auc_and_dists("drop_rate"),
        "floor_note": "These AUCs are the floor any ABRG result must clear.",
    }
    # strip heavy per-app before JSON dump of summary
    per_app = out.pop("_per_app")
    # write compact per-app metrics CSV
    for label, data in per_app.items():
        with (out_dir / f"check4_per_app_{label}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["path", "header_only", "n_events", "n_mapped", "n_active", "drop_rate"])
            for path in sorted(data["n_events"]):
                w.writerow(
                    [
                        path,
                        data["header_only"][path],
                        data["n_events"][path],
                        data["n_mapped"][path],
                        data["n_active"][path],
                        data["drop_rate"][path],
                    ]
                )

    with (out_dir / f"check4_auc.json").open("w", encoding="utf-8") as f:
        json.dump(out["check4"], f, indent=2)
    with (out_dir / f"check2_summary.json").open("w", encoding="utf-8") as f:
        json.dump(out["check2"], f, indent=2)
    with (out_dir / f"check3_summary.json").open("w", encoding="utf-8") as f:
        json.dump(out["check3"], f, indent=2)
    return out


def render_diagnostics_md(check1: dict[str, Any], rest: dict[str, Any] | None, out_dir: Path) -> str:
    lines: list[str] = []
    lines.append("# AndroCT 2017 — pre-graph diagnostics\n")
    lines.append(f"- Generated (UTC): {datetime.now(timezone.utc).isoformat()}")
    lines.append("- Scope: `datasets/androct_2017/` only (read-only).")
    lines.append("")

    # ---- Check 1 ----
    lines.append("## Check 1 — recall: sms / dynamic_code_loading\n")
    lines.append("### Raw callee-position substring hits\n")
    lines.append("| Class | Substring | Raw line count | Distinct apps |")
    lines.append("|---|---|---:|---:|")
    for label in ("benign", "malware"):
        for sub in PROBE_SUBSTRINGS:
            st = check1["probes"][label][sub]
            lines.append(f"| {label} | `{sub}` | {st['raw_line_count']} | {st['n_apps']} |")
    lines.append("")
    for label in ("benign", "malware"):
        lines.append(f"#### Examples — {label}\n")
        for sub in PROBE_SUBSTRINGS:
            st = check1["probes"][label][sub]
            if not st["examples"]:
                continue
            lines.append(f"**`{sub}`**")
            for ex in st["examples"]:
                lines.append(f"- `{ex}`")
            lines.append("")

    lines.append("### Pipeline survival (probe-matched lines)\n")
    for label in ("benign", "malware"):
        p = check1["pipeline"][label]
        lines.append(f"#### {label}\n")
        lines.append(f"- Probe-matched lines processed: {p['matched_probe_lines_processed']}")
        lines.append(f"- Stage counts: `{json.dumps(p['stage_counts'])}`")
        lines.append(f"- Post-mapper `sms`: {p['post_mapper_sms']}")
        lines.append(f"- Post-mapper `dynamic_code_loading`: {p['post_mapper_dynamic_code_loading']}")
        lines.append("")

    lines.append("### GATE\n")
    for label in ("benign", "malware"):
        g = check1["gate"][label]
        lines.append(f"#### {label}\n")
        for cat in ("sms", "dynamic_code_loading"):
            gg = g[cat]
            lines.append(
                f"- **{cat}**: raw_related={gg['raw_related']}, post_mapper={gg['post_mapper']}, "
                f"gate_trip={gg['gate_trip']}"
            )
        # Identify failing stage from fail examples / counts
        sc = check1["pipeline"][label]["stage_counts"]
        fe = check1["pipeline"][label]["fail_examples"]
        lines.append(f"- Stage fail tallies: allowlist={sc.get('fail_allowlist', 0)}, "
                     f"signature_decomp={sc.get('fail_signature_decomp', 0)}, "
                     f"categorize_callee_empty={sc.get('fail_categorize_callee_empty', 0)}")
        if fe.get("categorize_callee"):
            lines.append("- Example inputs failing at `categorize_callee` (empty graph set):")
            for ex in fe["categorize_callee"][:10]:
                lines.append(f"  - `{ex}`")
        if fe.get("allowlist_filter"):
            lines.append("- Example inputs failing at `allowlist_filter`:")
            for ex in fe["allowlist_filter"][:5]:
                lines.append(f"  - `{ex}`")
        if fe.get("signature_decomposition"):
            lines.append("- Example inputs failing at `signature_decomposition`:")
            for ex in fe["signature_decomposition"][:5]:
                lines.append(f"  - `{ex}`")
        lines.append("")

    lines.append("### Generalization — 2000 allowlisted callees / class\n")
    for label in ("benign", "malware"):
        g = check1["generalization"][label]
        lines.append(f"#### {label}\n")
        lines.append(f"- Sampled: {g['n_sampled_allowlisted_callees']} (from {g['n_seen_allowlisted_calls']} seen)")
        lines.append(f"- Decomp success: {g['decomp_success']}; fail rate: {g['decomp_fail_rate']:.6f}")
        lines.append(f"- Decomp fail causes: `{json.dumps(g['decomp_fail'])}`")
        lines.append(
            f"- Empty category set among decomp-ok: {g['empty_category_set_among_decomp_ok']} "
            f"(rate {g['empty_category_rate_among_decomp_ok']:.6f})"
        )
        lines.append("- Top 50 prefixes with empty category set:")
        for pref, c in g["top50_empty_category_class_prefixes"]:
            lines.append(f"  - `{pref}`: {c}")
        lines.append("")

    if rest is None:
        lines.append("## Checks 2–4\n")
        lines.append("Not run — Check 1 gate requires failing stage to be reported first (this file).\n")
        text = "\n".join(lines) + "\n"
        (out_dir / "DIAGNOSTICS.md").write_text(text, encoding="utf-8")
        return text

    # ---- Check 2 ----
    lines.append("## Check 2 — crypto semantics\n")
    for label in ("benign", "malware"):
        c2 = rest["check2"][label]
        lines.append(f"### {label}\n")
        lines.append(f"- Crypto events: {c2['crypto_total_events']}")
        lines.append(f"- Caller share: `{json.dumps(c2['crypto_caller_share'])}`")
        lines.append(f"- Proposed split: `{json.dumps(c2['proposed_crypto_split'])}`")
        lines.append(f"- Per-app crypto share of mapped: `{json.dumps(c2['per_app_crypto_share_of_mapped'])}`")
        lines.append("#### Top 30 crypto callee classes")
        for row in c2["top30_crypto_callee_classes"]:
            lines.append(f"- `{row[0]}`: {row[1]}")
        lines.append("#### Top 30 crypto caller classes")
        for row in c2["top30_crypto_caller_classes"]:
            lines.append(f"- `{row[0]}`: {row[1]}")
        lines.append("#### Top 30 network caller classes")
        for row in c2["top30_network_caller_classes"]:
            lines.append(f"- `{row[0]}`: {row[1]}")
        lines.append("#### Top 30 file_io caller classes")
        for row in c2["top30_file_io_caller_classes"]:
            lines.append(f"- `{row[0]}`: {row[1]}")
        lines.append("")

    # ---- Check 3 ----
    lines.append("## Check 3 — allowlist asymmetry\n")
    for label in ("benign", "malware"):
        c3 = rest["check3"][label]
        lines.append(f"### {label}\n")
        lines.append(f"- Dropped sample: {c3['dropped_sample_n']} (from {c3['dropped_sample_seen']} dropped seen)")
        lines.append(f"- Bucket counts: `{json.dumps(c3['bucket_counts'])}`")
        lines.append(
            f"- GATE well_formed_call_should_have_been_allowed nonempty: "
            f"**{c3['gate_well_formed_should_allowed_nonempty']}**"
        )
        lines.append(f"- Per-app drop rate dist: `{json.dumps(c3['per_app_drop_rate_dist'])}`")
        for bucket, exs in c3["bucket_examples"].items():
            lines.append(f"#### Bucket `{bucket}` examples")
            for ex in exs:
                lines.append(f"- `{ex}`")
        lines.append("#### Top 40 dropped line prefixes")
        for pref, c in c3["top40_dropped_line_prefixes"]:
            lines.append(f"- `{pref}`: {c}")
        lines.append("#### Top 20 highest drop-rate apps")
        for row in c3["top20_highest_drop_rate_apps"]:
            lines.append(
                f"- `{row['path']}`: drop_rate={row['drop_rate']:.4f}, "
                f"dropped={row['n_dropped']}, nonblank={row['n_nonblank']}, events={row['n_events']}"
            )
        lines.append("")

    # ---- Check 4 ----
    lines.append("## Check 4 — trivial baselines (AUC)\n")
    lines.append(f"- {rest['check4']['floor_note']}\n")
    for key in (
        "total_event_count",
        "mapped_event_count",
        "distinct_active_categories",
        "allowlist_drop_rate",
    ):
        t = rest["check4"][key]
        lines.append(f"### {key}\n")
        lines.append(
            f"- AUC={t['AUC']:.6f}, U={t['U']:.3g}, p={t['p_value']:.3g}, "
            f"n_benign={t['n_benign']}, n_malware={t['n_malware']}"
        )
        lines.append(f"- Higher at median: **{t['higher_at_median']}**; higher at mean: **{t['higher_at_mean']}**")
        lines.append(f"- Benign dist: `{json.dumps(t['benign_dist'])}`")
        lines.append(f"- Malware dist: `{json.dumps(t['malware_dist'])}`")
        lines.append("")

    text = "\n".join(lines) + "\n"
    (out_dir / "DIAGNOSTICS.md").write_text(text, encoding="utf-8")
    return text


def main() -> None:
    raw_dir = androct_raw_dir()
    out_dir = DIAG_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print("[diagnostics] Check 1 …", flush=True)
    check1 = run_check1(raw_dir, out_dir)
    render_diagnostics_md(check1, None, out_dir)
    print("[diagnostics] Check 1 written; gate reported in DIAGNOSTICS.md", flush=True)

    # Proceed only after gate is reported (file written above).
    print("[diagnostics] Checks 2–4 …", flush=True)
    rest = run_checks_2_3_4(raw_dir, out_dir)
    render_diagnostics_md(check1, rest, out_dir)
    print("[diagnostics] done →", out_dir / "DIAGNOSTICS.md", flush=True)


if __name__ == "__main__":
    main()
