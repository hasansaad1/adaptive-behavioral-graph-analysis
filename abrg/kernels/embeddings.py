"""
Whole-graph embeddings (unsupervised).

karateclub / gensim fail to build on CPython 3.14 in this environment.
Implementations below are faithful ports of the karateclub algorithms
(FGSD, NetLSD) plus Graph2Vec/GL2Vec-style WL bag-of-features + TF-IDF +
TruncatedSVD (Doc2Vec unavailable). Fit parameters on TRAIN-BENIGN ONLY.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

import networkx as nx
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

FitScope = Literal["train_benign_only"]


@dataclass
class EmbeddingResult:
    name: str
    X_train: np.ndarray
    X_eval: np.ndarray
    dim: int
    wall_sec: float
    failures: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ""
    fit_scope: FitScope = "train_benign_only"


def _assert_fit_ids(fit_ids: list[str], train_ids: list[str], forbidden: list[str]) -> None:
    fit_set = set(fit_ids)
    train_set = set(train_ids)
    forb = set(forbidden)
    if not fit_set <= train_set:
        raise SystemExit("STOP: embedding fit IDs not ⊆ train-benign")
    if fit_set & forb:
        raise SystemExit("STOP: malware/held-out benign touched embedding fit")


def _ensure_nonzero_graph(G: nx.Graph) -> nx.Graph:
    """FGSD/NetLSD need ≥1 node; empty edge graphs OK (isolates)."""
    if G.number_of_nodes() == 0:
        H = nx.Graph()
        H.add_node(0)
        return H
    return G


def fgsd_vector(G: nx.Graph, *, hist_bins: int = 200, hist_range: int = 20) -> np.ndarray:
    """karateclub FGSD._calculate_fgsd port."""
    G = _ensure_nonzero_graph(G)
    # normalized_laplacian requires undirected
    if isinstance(G, nx.DiGraph):
        G = G.to_undirected()
    n = G.number_of_nodes()
    if n == 1 or G.number_of_edges() == 0:
        # spectral features degenerate → zero hist except bin 0 mass
        hist = np.zeros(hist_bins, dtype=np.float64)
        hist[0] = float(n * n)
        return hist
    L = nx.normalized_laplacian_matrix(G).todense()
    fL = np.linalg.pinv(np.asarray(L, dtype=np.float64))
    ones = np.ones(L.shape[0])
    S = np.outer(np.diag(fL), ones) + np.outer(ones, np.diag(fL)) - 2.0 * fL
    hist, _ = np.histogram(
        np.asarray(S).ravel(), bins=hist_bins, range=(0, hist_range)
    )
    return hist.astype(np.float64)


def netlsd_vector(
    G: nx.Graph,
    *,
    scale_min: float = -2.0,
    scale_max: float = 2.0,
    scale_steps: int = 250,
) -> np.ndarray:
    """
    NetLSD heat-kernel trace descriptor (Tsitsulin et al.).
    Exact eigendecomposition of normalized Laplacian (karateclub uses approx;
    exact is fine at n≤1000).
    """
    G = _ensure_nonzero_graph(G)
    if isinstance(G, nx.DiGraph):
        G = G.to_undirected()
    n = G.number_of_nodes()
    scales = np.logspace(scale_min, scale_max, scale_steps)
    if n == 1 or G.number_of_edges() == 0:
        # heat trace → n for all t on edgeless
        return np.full(scale_steps, float(n), dtype=np.float64)
    L = np.asarray(nx.normalized_laplacian_matrix(G).todense(), dtype=np.float64)
    # symmetric → eigh
    evals = np.clip(np.linalg.eigvalsh(L), 0.0, None)
    # h(t) = sum_i exp(-t * λ_i)
    return np.sum(np.exp(-np.outer(scales, evals)), axis=1).astype(np.float64)


def _wl_words(G: nx.Graph, labels: dict[int, int], iterations: int) -> list[str]:
    """Weisfeiler-Lehman subtree feature strings (Graph2Vec document tokens)."""
    if isinstance(G, nx.DiGraph):
        G = G.to_undirected()
    cur = {n: str(labels.get(n, 0)) for n in G.nodes()}
    words: list[str] = list(cur.values())
    for _ in range(iterations):
        nxt = {}
        for n in G.nodes():
            neigh = sorted(cur[m] for m in G.neighbors(n))
            nxt[n] = cur[n] + "_" + "_".join(neigh)
        cur = nxt
        words.extend(cur.values())
    return words


def _line_graph_words(G: nx.Graph, iterations: int = 2, *, max_edges: int = 2000) -> list[str]:
    """GL2Vec-style: WL on line graph with edge-weight quantized labels.

    If the graph has more than ``max_edges`` edges, use a weight-bucket bag
    (no line-graph expansion) — full line-graph WL is intractable (e.g. 10k+
    edges → ~1M line-graph edges).
    """
    if isinstance(G, nx.DiGraph):
        G = G.to_undirected()
    if G.number_of_edges() == 0:
        return ["empty"]
    weights = [float(d.get("weight", 1.0)) for _, _, d in G.edges(data=True)]
    if G.number_of_edges() > max_edges:
        # tractability fallback: 20-bin weight histogram tokens
        hist, _ = np.histogram(weights, bins=20)
        return [f"wbin{i}:{int(c)}" for i, c in enumerate(hist)] + [
            f"nedges:{G.number_of_edges()}"
        ]
    LG = nx.line_graph(G)
    w_sorted = sorted(weights)

    def bucket(w: float) -> int:
        idx = int(np.searchsorted(w_sorted, w, side="right") - 1)
        return max(0, min(9, idx * 10 // max(len(w_sorted), 1)))

    edge_label = {}
    for u, v, d in G.edges(data=True):
        e = (u, v) if (u, v) in LG else (v, u)
        edge_label[e] = bucket(float(d.get("weight", 1.0)))
        if (v, u) in LG and (v, u) != e:
            edge_label[(v, u)] = edge_label[e]
    labels = {n: int(edge_label.get(n, edge_label.get((n[1], n[0]), 0))) for n in LG.nodes()}
    return _wl_words(LG, labels, iterations)


class _TfidfSvdEmbedder:
    """Fit Tfidf+SVD on train documents only; transform eval."""

    def __init__(self, *, dimensions: int = 128, seed: int = 42):
        self.dimensions = dimensions
        self.seed = seed
        self.vectorizer: TfidfVectorizer | None = None
        self.svd: TruncatedSVD | None = None

    def fit(self, docs: list[str]) -> np.ndarray:
        self.vectorizer = TfidfVectorizer(
            lowercase=False,
            token_pattern=r"(?u)\S+",
            min_df=1,
        )
        X = self.vectorizer.fit_transform(docs)
        n_comp = min(self.dimensions, max(1, X.shape[1] - 1), X.shape[0] - 1)
        self.svd = TruncatedSVD(n_components=n_comp, random_state=self.seed)
        return self.svd.fit_transform(X)

    def transform(self, docs: list[str]) -> np.ndarray:
        assert self.vectorizer is not None and self.svd is not None
        return self.svd.transform(self.vectorizer.transform(docs))


def embed_fgsd(
    train_graphs: list[nx.Graph],
    eval_graphs: list[nx.Graph],
    *,
    train_ids: list[str],
    eval_ids: list[str],
    forbidden_ids: list[str],
) -> EmbeddingResult:
    _assert_fit_ids(train_ids, train_ids, forbidden_ids)
    t0 = time.perf_counter()
    failures: list[dict[str, Any]] = []
    Xtr = []
    for i, G in enumerate(train_graphs):
        try:
            Xtr.append(fgsd_vector(G))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": train_ids[i], "split": "train", "reason": str(e)})
            Xtr.append(np.zeros(200))
    Xev = []
    for i, G in enumerate(eval_graphs):
        try:
            Xev.append(fgsd_vector(G))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": eval_ids[i], "split": "eval", "reason": str(e)})
            Xev.append(np.zeros(200))
    X_train = np.vstack(Xtr)
    X_eval = np.vstack(Xev)
    return EmbeddingResult(
        name="FGSD",
        X_train=X_train,
        X_eval=X_eval,
        dim=int(X_train.shape[1]),
        wall_sec=time.perf_counter() - t0,
        failures=failures,
        notes="native port of karateclub FGSD (hist_bins=200, hist_range=20); no fit params",
    )


def embed_netlsd(
    train_graphs: list[nx.Graph],
    eval_graphs: list[nx.Graph],
    *,
    train_ids: list[str],
    eval_ids: list[str],
    forbidden_ids: list[str],
) -> EmbeddingResult:
    _assert_fit_ids(train_ids, train_ids, forbidden_ids)
    t0 = time.perf_counter()
    failures: list[dict[str, Any]] = []
    Xtr, Xev = [], []
    for i, G in enumerate(train_graphs):
        try:
            Xtr.append(netlsd_vector(G))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": train_ids[i], "split": "train", "reason": str(e)})
            Xtr.append(np.zeros(250))
    for i, G in enumerate(eval_graphs):
        try:
            Xev.append(netlsd_vector(G))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": eval_ids[i], "split": "eval", "reason": str(e)})
            Xev.append(np.zeros(250))
    X_train = np.vstack(Xtr)
    X_eval = np.vstack(Xev)
    return EmbeddingResult(
        name="NetLSD",
        X_train=X_train,
        X_eval=X_eval,
        dim=int(X_train.shape[1]),
        wall_sec=time.perf_counter() - t0,
        failures=failures,
        notes="native NetLSD heat-trace (scale_steps=250); exact eigendecomposition; no fit params",
    )


def embed_graph2vec(
    train_graphs: list[nx.Graph],
    eval_graphs: list[nx.Graph],
    train_labels: list[dict[int, int]],
    eval_labels: list[dict[int, int]],
    *,
    train_ids: list[str],
    eval_ids: list[str],
    forbidden_ids: list[str],
    wl_iterations: int = 2,
    dimensions: int = 128,
    seed: int = 42,
) -> EmbeddingResult:
    _assert_fit_ids(train_ids, train_ids, forbidden_ids)
    t0 = time.perf_counter()
    failures: list[dict[str, Any]] = []
    tr_docs, ev_docs = [], []
    for i, G in enumerate(train_graphs):
        try:
            words = _wl_words(G, train_labels[i], wl_iterations)
            tr_docs.append(" ".join(words))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": train_ids[i], "split": "train", "reason": str(e)})
            tr_docs.append("fail")
    for i, G in enumerate(eval_graphs):
        try:
            words = _wl_words(G, eval_labels[i], wl_iterations)
            ev_docs.append(" ".join(words))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": eval_ids[i], "split": "eval", "reason": str(e)})
            ev_docs.append("fail")
    emb = _TfidfSvdEmbedder(dimensions=dimensions, seed=seed)
    X_train = emb.fit(tr_docs)
    X_eval = emb.transform(ev_docs)
    return EmbeddingResult(
        name="Graph2Vec",
        X_train=X_train,
        X_eval=X_eval,
        dim=int(X_train.shape[1]),
        wall_sec=time.perf_counter() - t0,
        failures=failures,
        notes=(
            "Graph2Vec-style: WL subtree tokens + TfidfVectorizer + TruncatedSVD; "
            "fit on train-benign only. karateclub/gensim unavailable on CPython 3.14."
        ),
    )


def embed_gl2vec(
    train_graphs: list[nx.Graph],
    eval_graphs: list[nx.Graph],
    *,
    train_ids: list[str],
    eval_ids: list[str],
    forbidden_ids: list[str],
    dimensions: int = 128,
    seed: int = 42,
) -> EmbeddingResult:
    _assert_fit_ids(train_ids, train_ids, forbidden_ids)
    t0 = time.perf_counter()
    failures: list[dict[str, Any]] = []
    tr_docs, ev_docs = [], []
    for i, G in enumerate(train_graphs):
        try:
            tr_docs.append(" ".join(_line_graph_words(G)))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": train_ids[i], "split": "train", "reason": str(e)})
            tr_docs.append("fail")
    for i, G in enumerate(eval_graphs):
        try:
            ev_docs.append(" ".join(_line_graph_words(G)))
        except Exception as e:  # noqa: BLE001
            failures.append({"sha": eval_ids[i], "split": "eval", "reason": str(e)})
            ev_docs.append("fail")
    emb = _TfidfSvdEmbedder(dimensions=dimensions, seed=seed)
    X_train = emb.fit(tr_docs)
    X_eval = emb.transform(ev_docs)
    return EmbeddingResult(
        name="GL2Vec",
        X_train=X_train,
        X_eval=X_eval,
        dim=int(X_train.shape[1]),
        wall_sec=time.perf_counter() - t0,
        failures=failures,
        notes=(
            "GL2Vec-style: WL on line graph with weight-bucket edge labels + TF-IDF + SVD; "
            "fit train-benign only. Uses edge weights. "
            "Graphs with >2000 edges use weight-histogram tokens (line-graph WL intractable)."
        ),
    )


EMBEDDING_BUILDERS: dict[str, Callable[..., EmbeddingResult]] = {
    "FGSD": embed_fgsd,
    "NetLSD": embed_netlsd,
    "Graph2Vec": embed_graph2vec,
    "GL2Vec": embed_gl2vec,
}
