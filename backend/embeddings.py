"""Turn text into lists of numbers (embeddings) that capture meaning."""
import hashlib
import re

import numpy as np

from . import config

_model = None


def _load():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(config.EMBEDDING_MODEL)
        _model.max_seq_length = 512   # our chunks are short; this is faster than the model's 8192 default
    return _model


def _hash_embed(texts: list[str], dim: int = 512) -> list[list[float]]:
    """TESTING ONLY: word-hashing vectors. Gives rough keyword matching, no real meaning."""
    out = np.zeros((len(texts), dim), dtype="float32")
    for i, text in enumerate(texts):
        for word in re.findall(r"\w+", text.lower()):
            out[i, int(hashlib.md5(word.encode()).hexdigest(), 16) % dim] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (out / norms).tolist()


def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    if config.EMBEDDING_BACKEND == "hash":
        return _hash_embed(texts)
    vectors = _load().encode(texts, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
    return vectors.tolist()


def model_id() -> str:
    return "hash-test" if config.EMBEDDING_BACKEND == "hash" else config.EMBEDDING_MODEL
