"""In-memory response cache with TTL."""
import hashlib
import json
import time
from collections import OrderedDict
from threading import Lock

from config import settings


class ResponseCache:
    def __init__(self):
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._lock = Lock()

    def _key(self, messages: list[dict], model: str, task: str, max_tokens: int) -> str:
        payload = json.dumps(
            {"m": messages, "model": model, "task": task, "max": max_tokens},
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, messages: list[dict], model: str, task: str, max_tokens: int) -> str | None:
        if not settings.cache_enabled:
            return None
        key = self._key(messages, model, task, max_tokens)
        with self._lock:
            if key not in self._store:
                return None
            content, expires = self._store[key]
            if time.time() > expires:
                del self._store[key]
                return None
            self._store.move_to_end(key)
            return content

    def set(self, messages: list[dict], model: str, task: str, max_tokens: int, content: str) -> None:
        if not settings.cache_enabled or not content:
            return
        key = self._key(messages, model, task, max_tokens)
        with self._lock:
            while len(self._store) >= settings.cache_max_entries:
                self._store.popitem(last=False)
            self._store[key] = (content, time.time() + settings.cache_ttl_seconds)

    def size(self) -> int:
        with self._lock:
            return len(self._store)


response_cache = ResponseCache()
