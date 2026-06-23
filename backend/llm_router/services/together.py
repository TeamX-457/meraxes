from config import settings
from services.base import BaseProvider, ProviderResult
from services.openai_compat import chat_complete


class TogetherProvider(BaseProvider):
    id = "together"

    def __init__(self):
        super().__init__(
            settings.enable_together,
            settings.together_api_key,
            settings.together_base_url,
            settings.models_list(settings.together_models),
        )

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
        )
