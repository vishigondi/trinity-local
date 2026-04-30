"""Embedding pipeline for routing examples.

Converts RoutingExample transcript windows into dense feature vectors.
Uses a tiered approach:
  1. TF-IDF (always available, no deps)
  2. sentence-transformers (if installed)
  3. MLX embeddings (if installed, Apple Silicon only)

The product core never imports this module.
Vectors are written to ~/.trinity/research/embeddings.jsonl
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..state_paths import research_dir
from ..training_schema import RoutingExample


@dataclass
class EmbeddingRecord:
    """One example's embedding vector with metadata."""
    example_id: str
    provider: str
    label: str
    task_kind: str
    method: str  # "tfidf", "sentence-transformers", "mlx"
    vector: list[float]
    text_hash: str  # For dedup

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Text preparation
# ---------------------------------------------------------------------------

def _example_text(example: RoutingExample) -> str:
    """Build the text representation for embedding."""
    parts: list[str] = []
    t = example.transcript
    if t.first_user_text:
        parts.append(t.first_user_text[:1500])
    if t.task_kind_hint:
        parts.append(f"[task:{t.task_kind_hint}]")
    if t.cwd:
        # Just the last 2 path components
        cwd_parts = Path(t.cwd).parts[-2:]
        parts.append(f"[project:{'/'.join(cwd_parts)}]")
    # Tool usage summary
    tool_names = [tool.name for tool in t.tools[:5]]
    if tool_names:
        parts.append(f"[tools:{','.join(tool_names)}]")
    return " ".join(parts)


def _text_hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# TF-IDF embeddings (zero dependencies)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Simple word tokenizer."""
    return re.findall(r'[a-z0-9_]+', text.lower())


def build_tfidf_vectors(
    examples: list[RoutingExample],
) -> list[EmbeddingRecord]:
    """Build TF-IDF vectors for a set of examples.

    Returns dense vectors of dimension = min(vocab_size, 512).
    Uses sublinear TF and smooth IDF.
    """
    texts = [_example_text(ex) for ex in examples]
    tokenized = [_tokenize(t) for t in texts]

    # Build vocabulary (top 512 by document frequency)
    doc_freq: Counter[str] = Counter()
    for tokens in tokenized:
        for token in set(tokens):
            doc_freq[token] += 1

    # Filter: must appear in at least 2 docs, max 80% of docs
    n_docs = len(tokenized)
    min_df = 2
    max_df = max(int(n_docs * 0.8), min_df + 1)
    vocab_candidates = [
        (token, df)
        for token, df in doc_freq.items()
        if min_df <= df <= max_df
    ]
    vocab_candidates.sort(key=lambda x: -x[1])
    vocab = {token: idx for idx, (token, _) in enumerate(vocab_candidates[:512])}
    dim = len(vocab)

    if dim == 0:
        # Not enough data — return zero vectors
        return [
            EmbeddingRecord(
                example_id=ex.example_id,
                provider=ex.chosen_provider,
                label=ex.label,
                task_kind=ex.transcript.task_kind_hint or "general",
                method="tfidf",
                vector=[0.0],
                text_hash=_text_hash(texts[i]),
            )
            for i, ex in enumerate(examples)
        ]

    # IDF: log(N / df) + 1 (smooth)
    idf = {token: math.log(n_docs / df) + 1.0 for token, df in doc_freq.items() if token in vocab}

    records: list[EmbeddingRecord] = []
    for i, (tokens, text, example) in enumerate(zip(tokenized, texts, examples)):
        tf = Counter(tokens)
        vector = [0.0] * dim
        for token, count in tf.items():
            if token in vocab:
                # Sublinear TF: 1 + log(count)
                tf_val = 1.0 + math.log(count) if count > 0 else 0.0
                vector[vocab[token]] = tf_val * idf.get(token, 1.0)

        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        records.append(EmbeddingRecord(
            example_id=example.example_id,
            provider=example.chosen_provider,
            label=example.label,
            task_kind=example.transcript.task_kind_hint or "general",
            method="tfidf",
            vector=vector,
            text_hash=_text_hash(text),
        ))

    return records


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def embeddings_path() -> Path:
    return research_dir() / "embeddings.jsonl"


def save_embeddings(records: list[EmbeddingRecord]) -> Path:
    """Append embedding records to the embeddings log."""
    path = embeddings_path()
    with path.open("a", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record.to_dict()) + "\n")
    return path


def load_embeddings() -> list[EmbeddingRecord]:
    """Load all embedding records."""
    path = embeddings_path()
    if not path.exists():
        return []
    records: list[EmbeddingRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            records.append(EmbeddingRecord(**raw))
        except (json.JSONDecodeError, TypeError):
            continue
    return records


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
