"""Prompt trimming and token budget optimization."""
import re
from typing import Literal

from config import settings

TaskType = Literal["auto", "fast", "long", "reasoning", "cheap"]


def total_chars(messages: list[dict]) -> int:
    return sum(len(m.get("content", "") or "") for m in messages)


def detect_task(messages: list[dict], task: TaskType) -> TaskType:
    if task != "auto":
        return task
    chars = total_chars(messages)
    text = " ".join(m.get("content", "") for m in messages).lower()

    reasoning_signals = (
        "analyze", "compare", "architecture", "design", "prove", "step by step",
        "reasoning", "trade-off", "evaluate", "strategy", "complex",
    )
    if any(s in text for s in reasoning_signals):
        return "reasoning"
    if chars >= settings.long_prompt_chars:
        return "long"
    if chars < 800:
        return "fast"
    return "cheap"


def trim_messages(messages: list[dict], max_chars: int = 12000) -> list[dict]:
    """Keep system + recent turns; compress middle history."""
    if total_chars(messages) <= max_chars:
        return messages

    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    if len(rest) <= 4:
        trimmed = []
        budget = max_chars
        for m in reversed(rest):
            c = m.get("content", "") or ""
            if len(c) > budget // 2:
                c = c[: budget // 2] + "\n...[truncated]"
            trimmed.insert(0, {**m, "content": c})
            budget -= len(c)
        return system + trimmed

    head = rest[:1]
    tail = rest[-3:]
    middle_summary = {
        "role": "system",
        "content": f"[Earlier conversation summarized: {len(rest) - 4} messages omitted to save tokens.]",
    }
    return system + head + [middle_summary] + tail


def compress_prompt_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def optimize_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        content = compress_prompt_text(m.get("content", "") or "")
        out.append({**m, "content": content})
    return trim_messages(out)


def max_tokens_for_task(task: TaskType, requested: int | None) -> int:
    if requested is not None:
        return min(requested, settings.reasoning_max_tokens)
    caps = {
        "fast": settings.fast_max_tokens,
        "cheap": settings.fast_max_tokens,
        "long": settings.default_max_tokens,
        "reasoning": settings.reasoning_max_tokens,
        "auto": settings.default_max_tokens,
    }
    return caps.get(task, settings.default_max_tokens)
