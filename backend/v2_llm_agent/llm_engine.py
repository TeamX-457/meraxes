"""
llm_engine.py — Multi-model router with tiered fallbacks.

Priority (tier=strong):
  1. OpenAI: gpt-4o → gpt-4o-mini (configurable chain)
  2. Ollama: llama3.1 / qwen2.5 / mistral (first available)
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from openai import AsyncOpenAI, APIConnectionError, APIStatusError, AuthenticationError, RateLimitError

from v2_llm_agent.config import (
    DEFAULT_TIER,
    GOOGLE_API_KEY,
    GOOGLE_BASE_URL,
    GOOGLE_MODELS,
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODELS,
    LLM_PROVIDER_ORDER,
    MODEL_TIERS,
    OLLAMA_NUM_CTX,
    OLLAMA_REPEAT_PENALTY,
    OPENAI_API_KEY,
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_MODELS,
    OPENAI_RETRIES,
    OPENAI_TEMPERATURE,
    OPENAI_TIMEOUT,
    OPENAI_TOP_P,
    OPENROUTER_API_KEY,
    OPENROUTER_APP_NAME,
    OPENROUTER_APP_URL,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODELS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_MODELS,
    OLLAMA_TIMEOUT,
    has_cloud_api_key,
    use_openai,
    USE_EMBEDDED_ROUTER,
    USE_LLM_ROUTER,
    LLM_ROUTER_URL,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None
    success: bool = True
    tier: str = "strong"


_compat_clients: dict[str, AsyncOpenAI] = {}
_ollama_available: Optional[set[str]] = None


def _tier_config(tier: str) -> dict:
    return MODEL_TIERS.get(tier, MODEL_TIERS[DEFAULT_TIER])


def _cloud_provider_specs(tier: str) -> list[tuple[str, str, str | None, list[str], dict | None]]:
    """(provider_id, api_key, base_url, models, extra_headers) in configured order."""
    cfg = _tier_config(tier)
    tier_openai = cfg.get("openai_models") or OPENAI_MODELS
    specs: dict[str, tuple[str, str | None, list[str], dict | None]] = {
        "openai": (OPENAI_API_KEY, None, tier_openai, None),
        "groq": (GROQ_API_KEY, GROQ_BASE_URL, GROQ_MODELS, None),
        "openrouter": (
            OPENROUTER_API_KEY,
            OPENROUTER_BASE_URL,
            OPENROUTER_MODELS,
            {
                "HTTP-Referer": OPENROUTER_APP_URL,
                "X-Title": OPENROUTER_APP_NAME,
            },
        ),
        "google": (GOOGLE_API_KEY, GOOGLE_BASE_URL, GOOGLE_MODELS, None),
    }
    out: list[tuple[str, str, str | None, list[str], dict | None]] = []
    for pid in LLM_PROVIDER_ORDER:
        if pid == "ollama":
            continue
        key, base, models, headers = specs.get(pid, ("", None, [], None))
        if key and models:
            out.append((pid, key, base, models, headers))
    return out


def _get_compat_client(
    provider_id: str,
    api_key: str,
    base_url: str | None,
    extra_headers: dict | None,
) -> AsyncOpenAI:
    cache_key = f"{provider_id}:{base_url or 'default'}"
    if cache_key not in _compat_clients:
        kwargs: dict = {"api_key": api_key, "timeout": OPENAI_TIMEOUT}
        if base_url:
            kwargs["base_url"] = base_url
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        _compat_clients[cache_key] = AsyncOpenAI(**kwargs)
    return _compat_clients[cache_key]


async def _list_ollama_models() -> set[str]:
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            names = {m.get("name", "").split(":")[0] for m in r.json().get("models", [])}
            full = set()
            for m in r.json().get("models", []):
                n = m.get("name", "")
                if n:
                    full.add(n)
                    full.add(n.split(":")[0])
            _ollama_available = full
            return full
    except Exception as e:
        logger.warning("Could not list Ollama models: %s", e)
        _ollama_available = set()
        return _ollama_available


def _resolve_ollama_chain(preferred: list[str]) -> list[str]:
    """Return models to try, preferring installed ones."""
    return preferred or OLLAMA_MODELS


def _ollama_model_installed(model: str, installed: set[str]) -> bool:
    """Match qwen2.5:7b against qwen2.5-coder:7b, llama3 against llama3:latest, etc."""
    if not installed:
        return True
    return _resolve_installed_tag(model, installed) is not None


def _resolve_installed_tag(requested: str, installed: set[str]) -> str | None:
    if not installed:
        return requested
    req = requested.lower()
    base = req.split(":")[0]
    for name in installed:
        if name.lower() == req:
            return name
    same_family = [n for n in installed if n.lower().split(":")[0] == base]
    if same_family:
        return sorted(same_family, key=len)[-1]
    fuzzy = [n for n in installed if base in n.lower().split(":")[0]]
    return fuzzy[0] if fuzzy else None


def _build_ollama_try_order(preferred: list[str], installed: set[str]) -> list[str]:
    order: list[str] = []
    seen: set[str] = set()
    for model in preferred:
        tag = _resolve_installed_tag(model, installed) if installed else model
        if tag and tag not in seen:
            order.append(tag)
            seen.add(tag)
    if not order and installed:
        order = sorted(installed)
    elif not order:
        order = list(preferred)
    return order


async def _call_compat(
    provider_id: str,
    client: AsyncOpenAI,
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
) -> LLMResponse:
    t0 = time.monotonic()
    last_err = ""
    for attempt in range(OPENAI_RETRIES + 1):
        try:
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=OPENAI_TOP_P,
                presence_penalty=0.1,
                frequency_penalty=0.1,
            )
            latency = int((time.monotonic() - t0) * 1000)
            content = (resp.choices[0].message.content or "").strip()
            usage = resp.usage
            logger.info("%s OK model=%s latency=%dms", provider_id, model, latency)
            return LLMResponse(
                content=content,
                provider=provider_id,
                model=model,
                latency_ms=latency,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            )
        except RateLimitError as e:
            last_err = str(e)
            logger.warning("%s rate limit %s (attempt %d)", provider_id, model, attempt + 1)
            await _sleep_backoff(attempt)
        except AuthenticationError as e:
            return LLMResponse(
                content="",
                provider=provider_id,
                model=model,
                latency_ms=0,
                success=False,
                error=str(e),
            )
        except (APIConnectionError, APIStatusError) as e:
            last_err = str(e)
            logger.warning("%s error model=%s: %s", provider_id, model, e)
            break
        except Exception as e:
            last_err = str(e)
            logger.exception("%s unexpected error model=%s", provider_id, model)
            break
    return LLMResponse(
        content="",
        provider=provider_id,
        model=model,
        latency_ms=0,
        success=False,
        error=last_err,
    )


async def _sleep_backoff(attempt: int) -> None:
    import asyncio
    await asyncio.sleep(min(2 ** attempt, 8))


async def _call_ollama(
    messages: list[dict],
    model: str,
    temperature: float,
    max_tokens: int,
    num_ctx: int | None = None,
) -> LLMResponse:
    url = f"{OLLAMA_BASE_URL}/api/chat"
    ctx = num_ctx or OLLAMA_NUM_CTX
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
            "num_ctx": ctx,
            "top_p": OPENAI_TOP_P,
            "top_k": 40,
            "repeat_penalty": OLLAMA_REPEAT_PENALTY,
        },
    }
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        latency = int((time.monotonic() - t0) * 1000)
        content = (data.get("message", {}).get("content", "") or "").strip()
        usage = data.get("usage", {})
        logger.info("Ollama OK model=%s latency=%dms", model, latency)
        return LLMResponse(
            content=content,
            provider="ollama",
            model=model,
            latency_ms=latency,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
    except Exception as e:
        logger.warning("Ollama failed model=%s: %s", model, e)
        return LLMResponse(
            content="", provider="ollama", model=model, latency_ms=0,
            success=False, error=str(e),
        )


async def generate(
    messages: list[dict],
    tier: str | None = None,
    task: str | None = None,
) -> LLMResponse:
    tier = tier or DEFAULT_TIER
    if tier not in MODEL_TIERS:
        tier = DEFAULT_TIER
    cfg = _tier_config(tier)
    temperature = cfg["temperature"]
    max_tokens = cfg["max_tokens"]
    ollama_models = _resolve_ollama_chain(cfg["ollama_models"])

    errors: list[str] = []
    num_ctx = cfg.get("num_ctx", OLLAMA_NUM_CTX)

    if USE_EMBEDDED_ROUTER and tier != "local":
        try:
            from v2_llm_agent.router_bridge import route_messages
            return await route_messages(messages, tier, temperature, max_tokens, task=task)
        except Exception as e:
            errors.append(f"embedded_router:{e}")
            logger.warning("Embedded router failed, trying Ollama/cloud fallbacks: %s", e)

    # Local tier: Ollama first (your machine — no API cost)
    if tier == "local":
        installed = await _list_ollama_models()
        try_order = _build_ollama_try_order(ollama_models, installed)
        for model in try_order:
            result = await _call_ollama(
                messages, model, temperature, max_tokens, num_ctx=num_ctx
            )
            result.tier = tier
            if result.success and result.content:
                return result
            errors.append(f"ollama/{model}: {result.error}")

    if USE_LLM_ROUTER:
        task_map = {"fast": "fast", "strong": "reasoning", "local": "cheap"}
        router_task = task_map.get(tier, "auto")
        base = LLM_ROUTER_URL.rstrip("/").removesuffix("/v1")
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=OPENAI_TIMEOUT) as client:
                r = await client.post(
                    f"{base}/api/chat",
                    json={
                        "messages": messages,
                        "task": router_task,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                )
                r.raise_for_status()
                data = r.json()
            latency = int((time.monotonic() - t0) * 1000)
            content = (data.get("content") or "").strip()
            if content:
                return LLMResponse(
                    content=content,
                    provider=data.get("provider", "llm_router"),
                    model=data.get("model", "router"),
                    latency_ms=latency,
                    tier=tier,
                )
            errors.append("router:empty")
        except Exception as e:
            errors.append(f"router:{e}")
            logger.warning("LLM router failed, falling back to direct providers: %s", e)

    if use_openai() and has_cloud_api_key():
        for pid, api_key, base_url, models, headers in _cloud_provider_specs(tier):
            client = _get_compat_client(pid, api_key, base_url, headers)
            for model in models:
                result = await _call_compat(
                    pid, client, messages, model, temperature, max_tokens
                )
                result.tier = tier
                if result.success and result.content:
                    return result
                errors.append(f"{pid}/{model}: {result.error}")

    installed = await _list_ollama_models()
    try_order = _build_ollama_try_order(ollama_models, installed)

    for model in try_order:
        result = await _call_ollama(
            messages, model, temperature, max_tokens, num_ctx=num_ctx
        )
        result.tier = tier
        if result.success and result.content:
            return result
        errors.append(f"ollama/{model}: {result.error}")

    raise RuntimeError(
        "All LLM providers failed. "
        + ("; ".join(errors[-4:]) if errors else "Install Ollama and run pull-smart-local.bat")
    )


async def health_check() -> dict:
    status: dict = {
        "default_tier": DEFAULT_TIER,
        "tiers": list(MODEL_TIERS.keys()),
        "use_openai": use_openai(),
        "llm_mode": "hybrid" if use_openai() else "local_only",
    }

    status["cloud_providers"] = {}
    if has_cloud_api_key():
        for pid, api_key, base_url, _models, headers in _cloud_provider_specs(DEFAULT_TIER):
            try:
                client = _get_compat_client(pid, api_key, base_url, headers)
                await client.models.list()
                status["cloud_providers"][pid] = "ok"
            except Exception as e:
                status["cloud_providers"][pid] = f"error: {e}"
    else:
        status["cloud_providers"] = {"note": "no_api_keys"}
    status["openai"] = status["cloud_providers"].get("openai", "not_configured")
    if OPENAI_API_KEY:
        status["openai_primary"] = OPENAI_MODEL

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            if r.status_code == 200:
                models = [m.get("name") for m in r.json().get("models", [])]
                status["ollama"] = "ok"
                status["ollama_models_installed"] = models[:10]
            else:
                status["ollama"] = f"http_{r.status_code}"
    except Exception as e:
        status["ollama"] = f"error: {e}"

    return status
