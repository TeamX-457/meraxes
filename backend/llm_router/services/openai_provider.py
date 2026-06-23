from config import settings
from services.base import BaseProvider, ProviderResult
from services.openai_compat import chat_complete


class OpenAIProvider(BaseProvider):
    id = "openai"

    def __init__(self):
        super().__init__(
            settings.enable_openai,
            settings.openai_api_key,
            settings.openai_base_url,
            settings.models_list(settings.openai_models),
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
