"""Fallback chain execution across providers."""
import logging

from core.usage import usage_tracker
from services.base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


async def execute_with_fallback(
    providers: list[BaseProvider],
    messages: list[dict],
    model_hint: str | None,
    max_tokens: int,
    temperature: float,
) -> tuple[ProviderResult, list[str]]:
    fallbacks: list[str] = []
    last_error = "no providers available"

    for provider in providers:
        if not provider.enabled:
            continue
        if usage_tracker.is_rate_limited(provider.id):
            fallbacks.append(f"{provider.id}:rate_limited")
            logger.warning("Skipping %s — rate limit", provider.id)
            continue

        model = provider.pick_model(model_hint)
        usage_tracker.record_request(provider.id)
        result = await provider.complete(messages, model, max_tokens, temperature)

        if result.success and result.content:
            usage_tracker.record_success(provider.id, result.input_tokens, result.output_tokens)
            logger.info("OK provider=%s model=%s latency=%dms", provider.id, model, result.latency_ms)
            return result, fallbacks

        err = result.error or "empty response"
        rate_limited = "rate_limit" in err.lower()
        usage_tracker.record_error(provider.id, rate_limited=rate_limited)
        fallbacks.append(f"{provider.id}:{err[:80]}")
        last_error = err
        logger.warning("Fallback from %s: %s", provider.id, err)

    return (
        ProviderResult(
            content="",
            provider="none",
            model="",
            latency_ms=0,
            success=False,
            error=last_error,
        ),
        fallbacks,
    )
