"""Embedded Multi-LLM router — runs inside V2 (no port 8020 needed)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

from v2_llm_agent.llm_engine import LLMResponse

_ROUTER_DIR = Path(__file__).resolve().parent.parent / "llm_router"
if _ROUTER_DIR.is_dir() and str(_ROUTER_DIR) not in sys.path:
    sys.path.insert(0, str(_ROUTER_DIR))

from core.router import router as _embedded_router  # type: ignore  # noqa: E402
from schemas import ChatMessage, ChatRequest as RouterChatRequest  # type: ignore  # noqa: E402

TIER_TO_TASK = {
    "fast": "fast",
    "strong": "reasoning",
    "local": "cheap",
    "auto": "auto",
}


def list_providers() -> dict[str, bool]:
    return _embedded_router.list_providers()


def usage_snapshot() -> dict:
    from core.usage import usage_tracker  # type: ignore  # noqa: E402
    return usage_tracker.snapshot()


_VALID_TASKS = frozenset({"auto", "fast", "long", "reasoning", "cheap"})


async def route_messages(
    messages: list[dict],
    tier: str,
    temperature: float,
    max_tokens: int,
    task: str | None = None,
) -> LLMResponse:
    router_task = task if task in _VALID_TASKS else TIER_TO_TASK.get(tier, "auto")
    clean = [
        ChatMessage(role=m["role"], content=m.get("content") or "")
        for m in messages
        if m.get("content")
    ]
    t0 = time.monotonic()
    resp = await _embedded_router.chat(
        RouterChatRequest(
            messages=clean,
            task=router_task,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    )
    return LLMResponse(
        content=resp.content,
        provider=resp.provider,
        model=resp.model,
        latency_ms=resp.latency_ms or int((time.monotonic() - t0) * 1000),
        tier=tier,
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
    )
