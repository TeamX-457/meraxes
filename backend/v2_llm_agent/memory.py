"""
memory.py — FAISS-backed semantic memory layer.

Handles:
- Embedding via SentenceTransformer
- Vector storage / retrieval via FAISS
- Metadata persistence via JSON sidecar
- Deduplication before storing
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

from v2_llm_agent.config import (
    EMBEDDING_MODEL,
    FAISS_INDEX_PATH,
    FAISS_META_PATH,
    MEMORY_TOP_K,
    MEMORY_SCORE_THRESHOLD,
    MEMORY_MIN_RESPONSE_LEN,
)

logger = logging.getLogger(__name__)


# ─── Singleton embedding model ────────────────────────────────────────────────

_embedder: Optional[SentenceTransformer] = None


def _get_embedder() -> SentenceTransformer:
    global _embedder
    if _embedder is None:
        logger.info("Loading embedding model: %s", EMBEDDING_MODEL)
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
    return _embedder


def embed(text: str) -> np.ndarray:
    vec = _get_embedder().encode([text], convert_to_numpy=True, normalize_embeddings=True)
    return vec.astype("float32")


# ─── FAISS index helpers ──────────────────────────────────────────────────────

_index: Optional[faiss.IndexFlatIP] = None   # Inner-product on L2-normalised = cosine
_meta: list[dict] = []


def _ensure_dirs() -> None:
    Path(FAISS_INDEX_PATH).parent.mkdir(parents=True, exist_ok=True)


def _load() -> None:
    global _index, _meta
    _ensure_dirs()

    dim = _get_embedder().get_sentence_embedding_dimension()
    if Path(FAISS_INDEX_PATH).exists() and Path(FAISS_META_PATH).exists():
        try:
            loaded = faiss.read_index(FAISS_INDEX_PATH)
            if loaded.d != dim:
                logger.warning(
                    "FAISS dim %d != embedder %d — rebuilding index (embedding upgrade)",
                    loaded.d, dim,
                )
                raise ValueError("dimension mismatch")
            _index = loaded
            with open(FAISS_META_PATH, "r") as f:
                _meta = json.load(f)
            logger.info("Loaded FAISS index (dim=%d, vectors=%d)", dim, _index.ntotal)
        except Exception as e:
            logger.warning("Resetting FAISS index: %s", e)
            _index = faiss.IndexFlatIP(dim)
            _meta = []
    else:
        _index = faiss.IndexFlatIP(dim)
        _meta = []
        logger.info("Created fresh FAISS index (dim=%d)", dim)


def _save() -> None:
    _ensure_dirs()
    faiss.write_index(_index, FAISS_INDEX_PATH)
    with open(FAISS_META_PATH, "w") as f:
        json.dump(_meta, f, indent=2)


def _get_index():
    if _index is None:
        _load()
    return _index


def get_index():
    return _get_index()


# ─── Public API ───────────────────────────────────────────────────────────────

def add_memory(
    question: str,
    answer: str,
    user_id: str = "global",
    source: str = "llm",
    force: bool = False,
) -> bool:
    """
    Store a Q&A pair in FAISS.

    Returns True if stored, False if skipped (too short / duplicate).
    """
    if not force and len(answer.strip()) < MEMORY_MIN_RESPONSE_LEN:
        logger.debug("Skipping short response (len=%d)", len(answer))
        return False

    # Deduplication: check cosine similarity against existing entries
    results = search_memory(question, top_k=1)
    if results and results[0]["score"] >= 0.92:
        logger.debug("Skipping near-duplicate memory (score=%.3f)", results[0]["score"])
        return False

    idx = _get_index()
    vec = embed(question)
    idx.add(vec)

    _meta.append(
        {
            "id": len(_meta),
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "source": source,          # "openai" | "ollama" | "user"
            "ts": int(time.time()),
        }
    )
    _save()
    logger.info("Memory stored (total=%d, source=%s)", len(_meta), source)
    return True


def search_memory(
    query: str,
    top_k: int = MEMORY_TOP_K,
    user_id: Optional[str] = None,
    min_score: float = MEMORY_SCORE_THRESHOLD,
) -> list[dict]:
    """
    Return top-k relevant memories above `min_score`.

    Each result: {question, answer, score, source, user_id}
    """
    idx = _get_index()
    if idx.ntotal == 0:
        return []

    vec = embed(query)
    k = min(top_k * 3, idx.ntotal)   # fetch extra, filter after
    scores, indices = idx.search(vec, k)

    results = []
    for score, i in zip(scores[0], indices[0]):
        if i == -1 or score < min_score:
            continue
        entry = _meta[i]
        if user_id and entry["user_id"] not in (user_id, "global"):
            continue
        results.append(
            {
                "question": entry["question"],
                "answer": entry["answer"],
                "score": float(score),
                "source": entry["source"],
                "user_id": entry["user_id"],
            }
        )
        if len(results) >= top_k:
            break

    return results


def memory_stats() -> dict:
    if _index is None:
        return {
            "status": "loading",
            "total_vectors": 0,
            "total_meta": 0,
            "index_path": FAISS_INDEX_PATH,
        }
    return {
        "status": "ready",
        "total_vectors": _index.ntotal,
        "total_meta": len(_meta),
        "index_path": FAISS_INDEX_PATH,
    }


def warmup() -> None:
    """Load embedding model + FAISS index (may download on first run)."""
    _load()


def delete_user_memories(user_id: str) -> int:
    """
    Remove all FAISS vectors for a given user.
    Rebuilds index — call sparingly.
    Returns count of deleted entries.
    """
    global _index, _meta

    keep = [m for m in _meta if m["user_id"] != user_id]
    removed = len(_meta) - len(keep)
    if removed == 0:
        return 0

    dim = _get_embedder().get_sentence_embedding_dimension()
    new_index = faiss.IndexFlatIP(dim)

    if keep:
        vecs = np.vstack([embed(m["question"]) for m in keep])
        new_index.add(vecs)

    # Re-assign sequential IDs
    for i, m in enumerate(keep):
        m["id"] = i

    _index = new_index
    _meta = keep
    _save()
    logger.info("Deleted %d memories for user_id=%s", removed, user_id)
    return removed


def delete_memory_pair(user_id: str, question: str, answer: str) -> int:
    """Remove one Q&A memory matching exact question+answer for user."""
    global _index, _meta

    q = question.strip()
    a = answer.strip()
    keep = [
        m for m in _meta
        if not (m.get("user_id") == user_id and m.get("question", "").strip() == q and m.get("answer", "").strip() == a)
    ]
    removed = len(_meta) - len(keep)
    if removed == 0:
        return 0

    dim = _get_embedder().get_sentence_embedding_dimension()
    new_index = faiss.IndexFlatIP(dim)
    if keep:
        vecs = np.vstack([embed(m["question"]) for m in keep])
        new_index.add(vecs)
    for i, m in enumerate(keep):
        m["id"] = i
    _index = new_index
    _meta = keep
    _save()
    return removed

