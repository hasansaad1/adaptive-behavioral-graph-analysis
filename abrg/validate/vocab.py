"""Train-benign-only vocabulary builders (A/B/C) for arbitrary K and SHA lists."""

from __future__ import annotations

import math
from collections import Counter
from typing import Any, Literal

VocabMethod = Literal["A_tfidf", "B_docfreq", "C_rawfreq"]


def rank_vocab(
    train_seqs: dict[str, list[str]],
    train_shas: list[str],
    *,
    method: VocabMethod,
    k: int,
) -> list[str]:
    """
    Rank callees on the provided train SHA list ONLY.
    Asserts keys == train_shas. Does not accept malware / held-out SHAs.
    """
    assert set(train_seqs.keys()) == set(train_shas), (
        "STOP: vocab sequences must equal train SHA list exactly (integrity)"
    )
    # No empty train
    assert len(train_shas) >= 1
    N = len(train_shas)
    df: Counter[str] = Counter()
    raw: Counter[str] = Counter()
    app_tf: dict[str, dict[str, float]] = {}
    for sha in train_shas:
        seq = train_seqs[sha]
        if not seq:
            app_tf[sha] = {}
            continue
        counts = Counter(seq)
        L = float(len(seq))
        app_tf[sha] = {c: cnt / L for c, cnt in counts.items()}
        for c, cnt in counts.items():
            df[c] += 1
            raw[c] += cnt

    if method == "A_tfidf":
        scores: dict[str, float] = {}
        for c, dfc in df.items():
            idf = math.log(N / dfc) if dfc > 0 else 0.0
            tfidfs = [app_tf[sha][c] * idf for sha in train_shas if c in app_tf[sha]]
            scores[c] = (sum(tfidfs) / len(tfidfs)) * dfc if tfidfs else 0.0
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    elif method == "B_docfreq":
        ranked = sorted(df.items(), key=lambda kv: (-kv[1], kv[0]))
    elif method == "C_rawfreq":
        ranked = sorted(raw.items(), key=lambda kv: (-kv[1], kv[0]))
    else:
        raise ValueError(method)

    return [c for c, _ in ranked[:k]]


def assert_train_benign_only(
    train_shas: list[str],
    *,
    malware_shas: set[str],
    heldout_benign_shas: set[str],
) -> None:
    bad_m = set(train_shas) & malware_shas
    bad_h = set(train_shas) & heldout_benign_shas
    if bad_m or bad_h:
        raise SystemExit(
            f"STOP: vocab train list leaked "
            f"malware={len(bad_m)} heldout_benign={len(bad_h)}"
        )
