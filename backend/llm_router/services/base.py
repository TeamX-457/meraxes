from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    content: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    success: bool = True
    error: str | None = None
    raw: Any = field(default=None, repr=False)


class BaseProvider(ABC):
    id: str = "base"

    def __init__(self, enabled: bool, api_key: str, base_url: str, models: list[str]):
        self.enabled = enabled and bool(api_key.strip())
        self.api_key = api_key.strip()
        self.base_url = base_url
        self.models = models

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResult:
        ...

    def default_model(self) -> str:
        return self.models[0] if self.models else ""

    def pick_model(self, preferred: str | None) -> str:
        if preferred and preferred in self.models:
            return preferred
        if preferred:
            for m in self.models:
                if preferred in m or m in preferred:
                    return m
        return self.default_model()
