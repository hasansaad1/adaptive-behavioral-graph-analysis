"""Stage 1 — TF-IDF vocabulary from train-benign ONLY."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from abrg.apigraph.extract import category_for_callee

# Integrity: vocab must never see malware / held-out benign.
VOCAB_SOURCE_ASSERTION = (
    "Node vocabulary is derived exclusively from the 562 train-benign apps. "
    "Malware and held-out benign are never used to rank or select nodes."
)


def build_vocabularies(
    train_benign_seqs: dict[str, list[str]],
    train_benign_shas: list[str],
    *,
    ks: tuple[int, ...],
    out_dir: Path,
) -> dict[str, Any]:
    """
    Ranking formula (stated in README):

      tf(a,c)  = count(c in a) / len(sequence_a)
      idf(c)   = log(N / df(c))   where N = |train_benign|, df = #apps containing c
      tfidf(a,c) = tf(a,c) * idf(c)
      score(c) = mean_{a : c in a} tfidf(a,c)  *  df(c)

    Only train-benign apps contribute to counts, df, and ranking.
    """
    assert set(train_benign_seqs.keys()) == set(train_benign_shas), (
        "STOP: vocab sequences keys must equal train-benign SHA list exactly"
    )
    N = len(train_benign_shas)
    assert N == 562, f"STOP: expected 562 train-benign, got {N}"

    # Per-app tf numerators and document frequency — TRAIN BENIGN ONLY
    df: Counter[str] = Counter()
    app_tf: dict[str, dict[str, float]] = {}
    global_freq: Counter[str] = Counter()

    for sha in train_benign_shas:
        seq = train_benign_seqs[sha]
        if not seq:
            app_tf[sha] = {}
            continue
        counts = Counter(seq)
        L = float(len(seq))
        app_tf[sha] = {c: cnt / L for c, cnt in counts.items()}
        for c in counts:
            df[c] += 1
            global_freq[c] += counts[c]

    # score
    scores: dict[str, float] = {}
    for c, dfc in df.items():
        idf = math.log(N / dfc)
        tfidfs = [app_tf[sha][c] * idf for sha in train_benign_shas if c in app_tf[sha]]
        mean_tfidf = sum(tfidfs) / len(tfidfs)
        scores[c] = mean_tfidf * dfc

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))

    # Frequency distribution / coverage thresholds
    n_apps = N
    thresh_counts = {
        ">=1%": sum(1 for c, d in df.items() if d / n_apps >= 0.01),
        ">=5%": sum(1 for c, d in df.items() if d / n_apps >= 0.05),
        ">=25%": sum(1 for c, d in df.items() if d / n_apps >= 0.25),
        ">=50%": sum(1 for c, d in df.items() if d / n_apps >= 0.50),
    }
    freq_dist = {
        "n_distinct_callees": len(df),
        "n_train_benign_apps": N,
        "total_call_events": int(sum(global_freq.values())),
        "document_frequency_thresholds": thresh_counts,
        "top20_by_df": [
            {"callee": c, "df": int(d), "df_frac": d / n_apps}
            for c, d in df.most_common(20)
        ],
        # log-log plot data: rank vs frequency
        "loglog_rank_freq": [
            {"rank": i + 1, "freq": int(f)}
            for i, (_, f) in enumerate(global_freq.most_common())
        ],
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "frequency_distribution.json").write_text(
        json.dumps(freq_dist, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "VOCAB_INTEGRITY.txt").write_text(
        VOCAB_SOURCE_ASSERTION + f"\nasserted_n_train_benign={N}\n"
        f"asserted_no_malware_in_ranking=True\n",
        encoding="utf-8",
    )

    vocabs: dict[int, list[dict[str, Any]]] = {}
    for K in ks:
        rows = []
        for rank, (callee, score) in enumerate(ranked[:K], start=1):
            rows.append(
                {
                    "rank": rank,
                    "callee": callee,
                    "document_frequency": int(df[callee]),
                    "tfidf_score": float(score),
                    "category": category_for_callee(callee),
                }
            )
        vocabs[K] = rows
        csv_path = out_dir / f"vocab_K{K}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["rank", "callee", "document_frequency", "tfidf_score", "category"],
            )
            w.writeheader()
            w.writerows(rows)
        print(f"[apigraph] wrote {csv_path.name} n={len(rows)}", flush=True)

    return {
        "integrity": VOCAB_SOURCE_ASSERTION,
        "n_train_benign": N,
        "frequency_distribution": {
            k: v
            for k, v in freq_dist.items()
            if k != "loglog_rank_freq"  # huge; kept on disk only
        },
        "loglog_path": str(out_dir / "frequency_distribution.json"),
        "vocabs": {str(k): [r["callee"] for r in rows] for k, rows in vocabs.items()},
        "vocab_rows": {str(k): rows for k, rows in vocabs.items()},
    }


def coverage_table(
    vocabs: dict[str, list[str]],
    sequences: dict[str, list[str]],
    partitions: dict[str, list[str]],
) -> dict[str, Any]:
    """Fraction of call events falling inside vocabulary, per K and partition."""
    out: dict[str, Any] = {}
    for k_str, vocab in vocabs.items():
        vset = frozenset(vocab)
        out[k_str] = {}
        for part, shas in partitions.items():
            total = 0
            inv = 0
            for sha in shas:
                seq = sequences[sha]
                total += len(seq)
                inv += sum(1 for c in seq if c in vset)
            frac = inv / total if total else float("nan")
            out[k_str][part] = {
                "in_vocab_events": inv,
                "total_events": total,
                "coverage_frac": frac,
                "oov_frac": 1.0 - frac if total else float("nan"),
            }
    return out
