"""Per-bot FAISS memory — safe fallbacks so chat never crashes."""
import logging
import os
import pickle
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)

_embedder = None
BASE_DIR = Path(__file__).resolve().parent


def _get_embedder():
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _paths(bot_id: str = "global"):
    d = BASE_DIR / "memory" / bot_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "index.faiss", d / "data.pkl"


def _load(bot_id: str = "global"):
    index_path, data_path = _paths(bot_id)
    dim = 384
    index = faiss.IndexFlatL2(dim)
    memory_data: list[str] = []
    if index_path.exists() and data_path.exists():
        try:
            index = faiss.read_index(str(index_path))
            with open(data_path, "rb") as f:
                memory_data = pickle.load(f)
            if index.ntotal != len(memory_data):
                logger.warning("Memory index mismatch for %s — resetting", bot_id)
                index = faiss.IndexFlatL2(dim)
                memory_data = []
        except Exception as e:
            logger.warning("Could not load memory for %s: %s", bot_id, e)
    return index, memory_data


def _save(bot_id: str, index, memory_data: list[str]) -> None:
    index_path, data_path = _paths(bot_id)
    faiss.write_index(index, str(index_path))
    with open(data_path, "wb") as f:
        pickle.dump(memory_data, f)


def add_memory(text: str, bot_id: str = "global") -> None:
    try:
        index, memory_data = _load(bot_id)
        vec = _get_embedder().encode([text], convert_to_numpy=True).astype("float32")
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        index.add(vec)
        memory_data.append(text)
        _save(bot_id, index, memory_data)
    except Exception as e:
        logger.warning("add_memory failed: %s", e)


def search_memory(query: str, k: int = 3, bot_id: str = "global") -> list[str]:
    try:
        index, memory_data = _load(bot_id)
        if len(memory_data) == 0 or index.ntotal == 0:
            return []
        k = min(k, len(memory_data), index.ntotal)
        vec = _get_embedder().encode([query], convert_to_numpy=True).astype("float32")
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        _, indices = index.search(vec, k)
        results = []
        for i in indices[0]:
            if 0 <= i < len(memory_data):
                results.append(memory_data[i])
        return results
    except Exception as e:
        logger.warning("search_memory failed: %s", e)
        return []
