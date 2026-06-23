"""Smart routing, parallel execution, and orchestration."""
import asyncio
import logging
import re

from config import settings
from core.cache import response_cache
from core.fallback import execute_with_fallback
from core.optimizer import detect_task, max_tokens_for_task, optimize_messages
from core.usage import usage_tracker
from schemas import ChatRequest, ChatResponse
from services import (
    GeminiProvider,
    GroqProvider,
    OpenAIProvider,
    OpenRouterProvider,
    TogetherProvider,
    XAIProvider,
)
from services.base import BaseProvider, ProviderResult

logger = logging.getLogger(__name__)


class LLMRouter:
    TASK_PROVIDER_ORDER = {
        "fast": ["groq", "gemini", "openrouter", "together", "xai", "openai"],
        "long": ["gemini", "openrouter", "together", "groq", "xai", "openai"],
        "reasoning": ["openrouter", "openai", "xai", "gemini", "together", "groq"],
        "cheap": ["together", "openrouter", "groq", "gemini", "xai", "openai"],
        "auto": None,
    }

    def __init__(self):
        self._registry: dict[str, BaseProvider] = {
            "gemini": GeminiProvider(),
            "groq": GroqProvider(),
            "together": TogetherProvider(),
            "openrouter": OpenRouterProvider(),
            "openai": OpenAIProvider(),
            "xai": XAIProvider(),
        }

    def list_providers(self) -> dict[str, bool]:
        return {pid: p.enabled for pid, p in self._registry.items()}

    def _order_for_task(self, task: str) -> list[str]:
        custom = self.TASK_PROVIDER_ORDER.get(task)
        if custom:
            return custom
        return settings.priority_list()

    def _providers_ordered(
        self,
        task: str,
        force_provider: str | None = None,
    ) -> list[BaseProvider]:
        if force_provider:
            p = self._registry.get(force_provider.lower())
            return [p] if p and p.enabled else []

        order = self._order_for_task(task)
        out: list[BaseProvider] = []
        seen: set[str] = set()
        for pid in order:
            if pid in seen:
                continue
            prov = self._registry.get(pid)
            if prov and prov.enabled:
                out.append(prov)
                seen.add(pid)
        for pid, prov in self._registry.items():
            if pid not in seen and prov.enabled:
                out.append(prov)
        return out

    @staticmethod
    def _score_response(content: str) -> float:
        if not content:
            return 0.0
        score = min(len(content) / 500, 2.0)
        if re.search(r"\d+\.\s", content):
            score += 0.5
        if content.count("\n") >= 2:
            score += 0.3
        if len(content) < 40:
            score -= 1.0
        return score

    async def _parallel_race(
        self,
        provider_ids: list[str],
        messages: list[dict],
        model_hint: str | None,
        max_tokens: int,
        temperature: float,
    ) -> tuple[ProviderResult, list[str]]:
        providers = [
            self._registry[pid]
            for pid in provider_ids
            if pid in self._registry and self._registry[pid].enabled
        ]
        if len(providers) < 2:
            return await execute_with_fallback(providers, messages, model_hint, max_tokens, temperature)

        async def _one(prov: BaseProvider) -> ProviderResult:
            if usage_tracker.is_rate_limited(prov.id):
                return ProviderResult("", prov.id, "", 0, success=False, error="rate_limited")
            model = prov.pick_model(model_hint)
            usage_tracker.record_request(prov.id)
            r = await prov.complete(messages, model, max_tokens, temperature)
            if r.success:
                usage_tracker.record_success(prov.id, r.input_tokens, r.output_tokens)
            else:
                usage_tracker.record_error(prov.id, "rate_limit" in (r.error or "").lower())
            return r

        tasks = [asyncio.create_task(_one(p)) for p in providers]
        fallbacks: list[str] = []
        pending = set(tasks)
        best: ProviderResult | None = None
        parallel_win = False

        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                try:
                    r = t.result()
                except Exception as e:
                    fallbacks.append(f"parallel_error:{e}")
                    continue
                if not r.success or not r.content:
                    fallbacks.append(f"{r.provider}:{r.error}")
                    continue
                if best is None or self._score_response(r.content) > self._score_response(best.content):
                    best = r
                    parallel_win = True
            if best and self._score_response(best.content) >= 1.5:
                for t in pending:
                    t.cancel()
                break

        if best:
            return best, fallbacks if not parallel_win else fallbacks + ["parallel:winner"]

        return await execute_with_fallback(providers, messages, model_hint, max_tokens, temperature)

    async def chat(self, req: ChatRequest) -> ChatResponse:
        raw = [{"role": m.role, "content": m.content} for m in req.messages]
        messages = optimize_messages(raw)
        task = detect_task(messages, req.task)
        max_tokens = max_tokens_for_task(task, req.max_tokens)
        model_hint = req.model

        cache_key_model = model_hint or task
        if req.use_cache:
            cached = response_cache.get(messages, cache_key_model, task, max_tokens)
            if cached:
                return ChatResponse(
                    content=cached,
                    provider="cache",
                    model=cache_key_model,
                    task=task,
                    latency_ms=0,
                    cached=True,
                )

        use_parallel = req.parallel if req.parallel is not None else (
            settings.parallel_enabled and task in ("fast", "reasoning")
        )

        if use_parallel and not req.provider:
            pids = [p.strip() for p in settings.parallel_providers.split(",") if p.strip()]
            result, fallbacks = await self._parallel_race(
                pids, messages, model_hint, max_tokens, req.temperature
            )
        else:
            providers = self._providers_ordered(task, req.provider)
            result, fallbacks = await execute_with_fallback(
                providers, messages, model_hint, max_tokens, req.temperature
            )

        if not result.success or not result.content:
            raise RuntimeError(
                "All providers failed. " + "; ".join(fallbacks[-5:] if fallbacks else [result.error or ""])
            )

        if req.use_cache:
            response_cache.set(messages, result.model, task, max_tokens, result.content)

        return ChatResponse(
            content=result.content,
            provider=result.provider,
            model=result.model,
            task=task,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            fallbacks_used=fallbacks,
            parallel_winner=any("parallel:winner" in f for f in fallbacks),
        )


router = LLMRouter()
