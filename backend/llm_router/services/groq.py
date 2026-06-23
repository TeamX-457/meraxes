from config import settings
from services.base import BaseProvider, ProviderResult
from services.openai_compat import chat_complete


class GroqProvider(BaseProvider):
    id = "groq"

    def __init__(self):
        super().__init__(
            settings.enable_groq,
            settings.groq_api_key,
            settings.groq_base_url,
            settings.models_list(settings.groq_models),
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
