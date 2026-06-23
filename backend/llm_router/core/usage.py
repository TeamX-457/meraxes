"""Per-provider usage and rate-limit tracking."""
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from config import settings


@dataclass
class ProviderUsage:
    requests: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    errors: int = 0
    rate_limited: int = 0
    window_requests: list[float] = field(default_factory=list)


class UsageTracker:
    def __init__(self):
        self._data: dict[str, ProviderUsage] = defaultdict(ProviderUsage)
        self._lock = Lock()
        self._limits = {
            "openai": settings.rate_limit_openai,
            "gemini": settings.rate_limit_gemini,
            "groq": settings.rate_limit_groq,
            "together": settings.rate_limit_together,
            "openrouter": settings.rate_limit_openrouter,
            "xai": settings.rate_limit_xai,
        }

    def _prune_window(self, usage: ProviderUsage) -> None:
        cutoff = time.time() - 60
        usage.window_requests = [t for t in usage.window_requests if t >= cutoff]

    def is_rate_limited(self, provider_id: str) -> bool:
        with self._lock:
            usage = self._data[provider_id]
            self._prune_window(usage)
            limit = self._limits.get(provider_id, 60)
            return len(usage.window_requests) >= limit

    def record_request(self, provider_id: str) -> None:
        with self._lock:
            usage = self._data[provider_id]
            usage.requests += 1
            usage.window_requests.append(time.time())

    def record_success(self, provider_id: str, tokens_in: int, tokens_out: int) -> None:
        with self._lock:
            u = self._data[provider_id]
            u.tokens_in += tokens_in
            u.tokens_out += tokens_out

    def record_error(self, provider_id: str, rate_limited: bool = False) -> None:
        with self._lock:
            u = self._data[provider_id]
            u.errors += 1
            if rate_limited:
                u.rate_limited += 1

    def snapshot(self) -> dict[str, dict]:
        with self._lock:
            return {
                pid: {
                    "requests": u.requests,
                    "tokens_in": u.tokens_in,
                    "tokens_out": u.tokens_out,
                    "errors": u.errors,
                    "rate_limited": u.rate_limited,
                    "rpm": len([t for t in u.window_requests if t >= time.time() - 60]),
                }
                for pid, u in self._data.items()
            }


usage_tracker = UsageTracker()
