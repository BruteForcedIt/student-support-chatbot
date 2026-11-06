"""The vector database (Chroma). Stores each chunk of text with its numbers (embedding) and labels (metadata)."""
import logging
import math

import chromadb

from . import config, embeddings

log = logging.getLogger("kb")
NAME = "knowledge_base"
_client = None
_collection = None
_generation = 0     # goes up whenever chunks change in this process, so keyword_search rebuilds its index


def generation() -> int:
    return _generation


def _changed() -> None:
    global _generation
    _generation += 1


def _open_client():
    global _client
    if _client is None:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _client


def _make_collection():
    # We always create the embeddings ourselves, so Chroma's own embedder is switched off.
    return _open_client().get_or_create_collection(
        NAME, metadata={"hnsw:space": "cosine"}, embedding_function=None
    )


def collection():
    global _collection
    if _collection is None:
        _collection = _make_collection()
    return _collection


def reset() -> None:
    """Delete everything in the knowledge base (used before a full re-index)."""
    global _collection
    client = _open_client()
    try:
        client.delete_collection(NAME)
    except Exception:
        pass
    _collection = _make_collection()
    _changed()


def add_chunks(doc_id: str, chunks: list[dict], vectors: list[list[float]], meta: dict) -> None:
    """chunks: [{"text": ..., "page": int}]. meta: title, category, source_url, version."""
    col = collection()
    for start in range(0, len(chunks), 500):
        part = chunks[start:start + 500]
        col.upsert(
            ids=[f"{doc_id}:{start + i}" for i in range(len(part))],
            documents=[c["text"] for c in part],
            embeddings=vectors[start:start + 500],
            metadatas=[
                {**meta, "doc_id": doc_id, "page": int(c["page"]), "chunk_index": start + i,
                 "embedding_model": embeddings.model_id()}
                for i, c in enumerate(part)
            ],
        )
    _changed()


def delete_doc(doc_id: str) -> None:
    collection().delete(where={"doc_id": doc_id})
    _changed()


def count() -> int:
    return collection().count()


def search(vector: list[float], k: int, category: str | None = None) -> list[dict]:
    """Return the k closest chunks, best first. score = cosine similarity (1.0 = identical meaning)."""
    col = collection()
    total = col.count()
    if total == 0:
        return []
    result = col.query(
        query_embeddings=[vector],
        n_results=min(k, total),
        where={"category": category} if category else None,
        include=["documents", "metadatas", "distances"],
    )
    return [{**_hit(cid, text, meta), "score": 1.0 - float(dist)}
            for cid, text, meta, dist in zip(result["ids"][0], result["documents"][0],
                                             result["metadatas"][0], result["distances"][0])]


def _hit(chunk_id: str, text: str, meta: dict) -> dict:
    return {
        "id": chunk_id,
        "text": text,
        "doc_id": meta.get("doc_id", ""),
        "title": meta.get("title", ""),
        "category": meta.get("category", ""),
        "source_url": meta.get("source_url", ""),
        "page": meta.get("page", 0),
    }


def all_chunks() -> list[dict]:
    """Every stored chunk (text + labels, no embeddings). Used to build the keyword index."""
    result = collection().get(include=["documents", "metadatas"])
    return [_hit(cid, text, meta) for cid, text, meta in zip(result["ids"], result["documents"], result["metadatas"])]


def scores_for(vector: list[float], chunk_ids: list[str]) -> dict[str, float]:
    """Cosine similarity between the question and the given chunks, worked out the same way as search()."""
    if not chunk_ids:
        return {}
    result = collection().get(ids=chunk_ids, include=["embeddings"])
    q_norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    scores = {}
    for cid, emb in zip(result["ids"], result["embeddings"]):
        emb = [float(x) for x in emb]
        norm = math.sqrt(sum(x * x for x in emb)) or 1.0
        scores[cid] = sum(a * b for a, b in zip(vector, emb)) / (q_norm * norm)
    return scores


def stored_embedding_model() -> str | None:
    """Which embedding model built the stored chunks (None if the database is empty)."""
    col = collection()
    if col.count() == 0:
        return None
    sample = col.get(limit=1, include=["metadatas"])
    return sample["metadatas"][0].get("embedding_model") if sample["metadatas"] else None
