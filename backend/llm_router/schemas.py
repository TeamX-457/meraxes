from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    max_tokens: int | None = None
    temperature: float = 0.7
    stream: bool = False
    task: Literal["auto", "fast", "long", "reasoning", "cheap"] = "auto"
    provider: str | None = Field(None, description="Force a specific provider")
    parallel: bool | None = None
    use_cache: bool = True


class ChatResponse(BaseModel):
    content: str
    provider: str
    model: str
    task: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cached: bool = False
    fallbacks_used: list[str] = []
    parallel_winner: bool = False


class UsageStats(BaseModel):
    provider: str
    requests: int
    tokens_in: int
    tokens_out: int
    errors: int
    rate_limited: int


class HealthResponse(BaseModel):
    status: str
    providers: dict[str, Any]
    cache_entries: int
