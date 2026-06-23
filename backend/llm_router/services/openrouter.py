from config import settings
from services.base import BaseProvider, ProviderResult
from services.openai_compat import chat_complete


class OpenRouterProvider(BaseProvider):
    id = "openrouter"

    def __init__(self):
        super().__init__(
            settings.enable_openrouter,
            settings.openrouter_api_key,
            settings.openrouter_base_url,
            settings.models_list(settings.openrouter_models),
        )
        self._headers = {
            "HTTP-Referer": settings.openrouter_app_url,
            "X-Title": settings.openrouter_app_name,
        }

    async def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        return await chat_complete(
            self.id,
            self.api_key,
            self.base_url,
            messages,
            model,
            max_tokens,
            temperature,
            extra_headers=self._headers,
        )
