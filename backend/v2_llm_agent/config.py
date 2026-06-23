"""V2 agent configuration — local-first or OpenAI hybrid."""

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_FILE)

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)



# ─── Provider mode ───────────────────────────────────────────────────────────

# USE_OPENAI=false  → never call OpenAI (100% local via Ollama)

# USE_OPENAI=auto   → use OpenAI only when OPENAI_API_KEY is set (default)

# USE_OPENAI=true   → require OpenAI (fail if key missing)

_use_openai_raw = os.getenv("USE_OPENAI", "auto").lower().strip()





def _has_key(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def has_cloud_api_key() -> bool:
    return any(
        _has_key(k)
        for k in (
            "OPENAI_API_KEY",
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
            "GOOGLE_API_KEY",
        )
    )


def use_openai() -> bool:
    """True when cloud LLM providers (not only Ollama) should be tried."""
    if _use_openai_raw in ("false", "0", "no", "local"):
        return False
    if _use_openai_raw in ("true", "1", "yes"):
        return has_cloud_api_key()
    return has_cloud_api_key()





# Best local models (install with pull-smart-local.bat). Order = try first.

_LOCAL_STRONG = [

    "qwen2.5:14b",

    "qwen2.5:7b",

    "qwen2.5-coder:7b",

    "llama3.1:8b",

    "llama3.1",

    "llama3:latest",

    "mistral-nemo",

    "gemma2:9b",

    "mistral",

    "llama3",

]

_LOCAL_FAST = [

    "llama3.2:3b",

    "qwen2.5:3b",

    "llama3:latest",

    "qwen2.5-coder:7b",

    "llama3",

]



# ─── Model tiers (request ?tier=strong|fast|local) ───────────────────────────

MODEL_TIERS = {

    "strong": {

        "openai_models": ["gpt-4o", "gpt-4o-2024-08-06", "gpt-4o-mini"],

        "ollama_models": _LOCAL_STRONG,

        "temperature": 0.55,

        "max_tokens": 4096,

        "num_ctx": 8192,

    },

    "fast": {

        "openai_models": ["gpt-4o-mini", "gpt-4o"],

        "ollama_models": _LOCAL_FAST,

        "temperature": 0.65,

        "max_tokens": 1536,

        "num_ctx": 4096,

    },

    "local": {

        "openai_models": [],

        "ollama_models": _LOCAL_STRONG,

        "temperature": 0.55,

        "max_tokens": 4096,

        "num_ctx": 8192,

    },

}



_default_tier = os.getenv("DEFAULT_MODEL_TIER", "").strip()

if _default_tier:

    DEFAULT_TIER = _default_tier

elif not has_cloud_api_key():

    DEFAULT_TIER = "local"

else:

    DEFAULT_TIER = "strong"



# ─── OpenAI ─────────────────────────────────────────────────────────────────

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

OPENAI_MODELS: list[str] = [

    m.strip()

    for m in os.getenv(

        "OPENAI_MODELS",

        "gpt-4o,gpt-4o-mini",

    ).split(",")

    if m.strip()

]

OPENAI_TIMEOUT: int = int(os.getenv("OPENAI_TIMEOUT", "90"))

OPENAI_MAX_TOKENS: int = int(os.getenv("OPENAI_MAX_TOKENS", "2048"))

OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.65"))

OPENAI_TOP_P: float = float(os.getenv("OPENAI_TOP_P", "0.92"))

OPENAI_RETRIES: int = int(os.getenv("OPENAI_RETRIES", "2"))


# ─── Groq (OpenAI-compatible) ────────────────────────────────────────────────

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

GROQ_BASE_URL: str = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")

GROQ_MODELS: list[str] = [
    m.strip()
    for m in os.getenv(
        "GROQ_MODELS",
        "llama-3.3-70b-versatile,llama-3.1-8b-instant",
    ).split(",")
    if m.strip()
]


# ─── OpenRouter (OpenAI-compatible) ──────────────────────────────────────────

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")

OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)

OPENROUTER_MODELS: list[str] = [
    m.strip()
    for m in os.getenv(
        "OPENROUTER_MODELS",
        "openai/gpt-4o-mini,anthropic/claude-3.5-haiku,google/gemini-2.0-flash-001",
    ).split(",")
    if m.strip()
]

OPENROUTER_APP_URL: str = os.getenv("OPENROUTER_APP_URL", "http://127.0.0.1:8006")

OPENROUTER_APP_NAME: str = os.getenv("OPENROUTER_APP_NAME", "V2 Strong AI Agent")


# ─── Google Gemini (OpenAI-compatible endpoint) ──────────────────────────────

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")

GOOGLE_BASE_URL: str = os.getenv(
    "GOOGLE_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai/",
)

GOOGLE_MODELS: list[str] = [
    m.strip()
    for m in os.getenv(
        "GOOGLE_MODELS",
        "gemini-2.0-flash,gemini-1.5-flash",
    ).split(",")
    if m.strip()
]


# Provider try order (comma-separated): openai,groq,openrouter,google,ollama

LLM_PROVIDER_ORDER: list[str] = [
    p.strip().lower()
    for p in os.getenv(
        "LLM_PROVIDER_ORDER",
        "openai,groq,openrouter,google,ollama",
    ).split(",")
    if p.strip()
]


# ─── Ollama (local — no API key) ─────────────────────────────────────────────

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

OLLAMA_MODELS: list[str] = [

    m.strip()

    for m in os.getenv("OLLAMA_MODELS", ",".join(_LOCAL_STRONG)).split(",")

    if m.strip()

]

OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "300"))

OLLAMA_NUM_CTX: int = int(os.getenv("OLLAMA_NUM_CTX", "8192"))

OLLAMA_REPEAT_PENALTY: float = float(os.getenv("OLLAMA_REPEAT_PENALTY", "1.12"))



# ─── Memory / FAISS ───────────────────────────────────────────────────────────

FAISS_INDEX_PATH: str = os.getenv("FAISS_INDEX_PATH", str(_DATA_DIR / "faiss.index"))

FAISS_META_PATH: str = os.getenv("FAISS_META_PATH", str(_DATA_DIR / "faiss_meta.json"))

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-mpnet-base-v2")

MEMORY_TOP_K: int = int(os.getenv("MEMORY_TOP_K", "6"))

MEMORY_SCORE_THRESHOLD: float = float(os.getenv("MEMORY_SCORE_THRESHOLD", "0.52"))



# ─── SQLite ─────────────────────────────────────────────────────────────────

SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", str(_DATA_DIR / "agent.db"))

MEMORY_MIN_RESPONSE_LEN: int = int(os.getenv("MEMORY_MIN_RESPONSE_LEN", "60"))

CONVERSATION_WINDOW: int = int(os.getenv("CONVERSATION_WINDOW", "20"))



# ─── API server ─────────────────────────────────────────────────────────────

HOST: str = os.getenv("HOST", "0.0.0.0")

PORT: int = int(os.getenv("PORT", "8006"))

DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

PUBLIC_URL: str = os.getenv("V2_PUBLIC_URL", f"http://127.0.0.1:{PORT}")

# Embedded router (llm_router package inside AImodel — recommended)
USE_EMBEDDED_ROUTER: bool = os.getenv("USE_EMBEDDED_ROUTER", "true").lower() in (
    "true", "1", "yes", "on",
)
# External router on :8020 (optional)
USE_LLM_ROUTER: bool = os.getenv("USE_LLM_ROUTER", "false").lower() in (
    "true", "1", "yes", "on",
)
LLM_ROUTER_URL: str = os.getenv("LLM_ROUTER_URL", "http://127.0.0.1:8020/v1")

# ─── Silent V1 training from V2 external API chats ───────────────────────────

SILENT_V1_TRAINING: bool = os.getenv("SILENT_V1_TRAINING", "true").lower() in (
    "true", "1", "yes", "on",
)
EXPORT_LOCAL_FINETUNE: bool = os.getenv("EXPORT_LOCAL_FINETUNE", "true").lower() in (
    "true", "1", "yes", "on",
)
V1_TRAIN_BOT_ID: str = os.getenv("V1_TRAIN_BOT_ID", "").strip()
V1_TRAIN_EVERY_N: int = int(os.getenv("V1_TRAIN_EVERY_N", "5"))
V1_TRAIN_MIN_QUESTION_LEN: int = int(os.getenv("V1_TRAIN_MIN_QUESTION_LEN", "8"))
V1_TRAIN_MIN_ANSWER_LEN: int = int(os.getenv("V1_TRAIN_MIN_ANSWER_LEN", "40"))

# Ollama local model from V2 chat export
OLLAMA_BASE_MODEL: str = os.getenv("OLLAMA_BASE_MODEL", os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
OLLAMA_CUSTOM_MODEL: str = os.getenv("OLLAMA_CUSTOM_MODEL", "nova-v2-learned")
AUTO_BUILD_OLLAMA: bool = os.getenv("AUTO_BUILD_OLLAMA", "false").lower() in (
    "true", "1", "yes", "on",
)
OLLAMA_REBUILD_EVERY_N: int = int(os.getenv("OLLAMA_REBUILD_EVERY_N", "10"))

# Image generation — cloud DALL-E first (light on PC), optional local SD WebUI
ENABLE_IMAGE_GEN: bool = os.getenv("ENABLE_IMAGE_GEN", "true").lower() in (
    "true", "1", "yes", "on",
)
IMAGE_PROVIDER_ORDER: list[str] = [
    p.strip().lower()
    for p in os.getenv("IMAGE_PROVIDER", "pollinations,openai,sd-webui").split(",")
    if p.strip()
]
POLLINATIONS_MODEL: str = os.getenv("POLLINATIONS_MODEL", "flux")
POLLINATIONS_SIZE: int = int(os.getenv("POLLINATIONS_SIZE", "1024"))
OPENAI_IMAGE_MODEL: str = os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3")
OPENAI_IMAGE_SIZE: str = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024")
OPENAI_IMAGE_QUALITY: str = os.getenv("OPENAI_IMAGE_QUALITY", "standard")
SD_WEBUI_URL: str = os.getenv("SD_WEBUI_URL", "http://127.0.0.1:7860")
SD_IMAGE_STEPS: int = int(os.getenv("SD_IMAGE_STEPS", "12"))
SD_IMAGE_SIZE: int = int(os.getenv("SD_IMAGE_SIZE", "384"))


