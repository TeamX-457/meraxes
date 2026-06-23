"""Router configuration from environment."""
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8020
    debug: bool = False

    # Provider toggles
    enable_openai: bool = True
    enable_gemini: bool = True
    enable_groq: bool = True
    enable_together: bool = True
    enable_openrouter: bool = True
    enable_xai: bool = True

    # API keys
    openai_api_key: str = ""
    google_api_key: str = ""
    groq_api_key: str = ""
    together_api_key: str = ""
    openrouter_api_key: str = ""
    xai_api_key: str = ""

    # Base URLs
    openai_base_url: str = "https://api.openai.com/v1"
    google_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    together_base_url: str = "https://api.together.xyz/v1"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    xai_base_url: str = "https://api.x.ai/v1"

    # Models per provider
    openai_models: str = "gpt-4o-mini,gpt-4o"
    gemini_models: str = "gemini-2.0-flash,gemini-1.5-flash"
    groq_models: str = "llama-3.3-70b-versatile,llama-3.1-8b-instant"
    together_models: str = "meta-llama/Llama-3.3-70B-Instruct-Turbo,meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"
    openrouter_models: str = "openai/gpt-4o-mini,anthropic/claude-3.5-haiku,google/gemini-2.0-flash-001"
    xai_models: str = "grok-2-1212,grok-beta"

    # Routing defaults
    provider_priority: str = "groq,gemini,openrouter,together,xai,openai"
    long_prompt_chars: int = 4000
    default_max_tokens: int = 1024
    fast_max_tokens: int = 512
    reasoning_max_tokens: int = 2048

    # Cache
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    cache_max_entries: int = 500

    # Parallel mode
    parallel_enabled: bool = True
    parallel_providers: str = "groq,gemini"

    # Rate limits (per provider, per minute)
    rate_limit_openai: int = 60
    rate_limit_gemini: int = 60
    rate_limit_groq: int = 30
    rate_limit_together: int = 60
    rate_limit_openrouter: int = 60
    rate_limit_xai: int = 30

    openrouter_app_url: str = "http://127.0.0.1:8020"
    openrouter_app_name: str = "Multi-LLM Router"

    request_timeout: int = 120

    def models_list(self, raw: str) -> list[str]:
        return [m.strip() for m in raw.split(",") if m.strip()]

    def priority_list(self) -> list[str]:
        return [p.strip().lower() for p in self.provider_priority.split(",") if p.strip()]


settings = Settings()
