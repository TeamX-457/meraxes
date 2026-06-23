"""Shared OpenAI-compatible client calls."""
import logging
import time

from openai import APIConnectionError, APIStatusError, AsyncOpenAI, RateLimitError

from config import settings
from services.base import ProviderResult

logger = logging.getLogger(__name__)

_clients: dict[str, AsyncOpenAI] = {}


def get_client(provider_id: str, api_key: str, base_url: str, extra_headers: dict | None = None) -> AsyncOpenAI:
    key = f"{provider_id}:{base_url}"
    if key not in _clients:
        kwargs: dict = {"api_key": api_key, "timeout": settings.request_timeout}
        if base_url:
            kwargs["base_url"] = base_url
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        _clients[key] = AsyncOpenAI(**kwargs)
    return _clients[key]


async def chat_complete(
    provider_id: str,
    api_key: str,
    base_url: str,
    messages: list[dict],
    model: str,
    max_tokens: int,
    temperature: float,
    extra_headers: dict | None = None,
) -> ProviderResult:
    client = get_client(provider_id, api_key, base_url, extra_headers)
    t0 = time.monotonic()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=0.92,
        )
        latency = int((time.monotonic() - t0) * 1000)
        content = (resp.choices[0].message.content or "").strip()
        usage = resp.usage
        return ProviderResult(
            content=content,
            provider=provider_id,
            model=model,
            latency_ms=latency,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
    except RateLimitError as e:
        return ProviderResult(
            content="",
            provider=provider_id,
            model=model,
            latency_ms=int((time.monotonic() - t0) * 1000),
            success=False,
            error=f"rate_limit: {e}",
        )
    except (APIConnectionError, APIStatusError) as e:
        return ProviderResult(
            content="",
            provider=provider_id,
            model=model,
            latency_ms=int((time.monotonic() - t0) * 1000),
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.exception("%s request failed", provider_id)
        return ProviderResult(
            content="",
            provider=provider_id,
            model=model,
            latency_ms=int((time.monotonic() - t0) * 1000),
            success=False,
            error=str(e),
        )
