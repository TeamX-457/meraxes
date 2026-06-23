"""
Self-contained multi-LLM bridge for Meraxes.

Loads keys from learn/llm_router/.env (or process env) and calls providers
directly over HTTP. Avoids the llm_router package's `config`/`schemas` module
names, which collide with v1_classic_ai's own modules.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

V1_ROOT = Path(__file__).resolve().parents[1]
_ENV_FILE = V1_ROOT.parent / "llm_router" / ".env"


def _load_env_file() -> dict[str, str]:
    data: dict[str, str] = {}
    if _ENV_FILE.is_file():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            data[key.strip()] = val.strip()
    return data


_ENV = _load_env_file()


def _key(name: str) -> str:
    return os.getenv(name) or _ENV.get(name, "")


# Make Gemini key available to the rest of the agent (planner, direct synth)
_GOOGLE = _key("GOOGLE_API_KEY") or _key("GEMINI_API_KEY")
if _GOOGLE and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = _GOOGLE

_GROQ = _key("GROQ_API_KEY")
_OPENAI = _key("OPENAI_API_KEY")
_OPENROUTER = _key("OPENROUTER_API_KEY")

# Priority: Groq (fast/free) → Gemini → OpenRouter → OpenAI
_PROVIDERS = [
    ("groq", _GROQ, "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    ("gemini", _GOOGLE, "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.0-flash"),
    ("openrouter", _OPENROUTER, "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4o-mini"),
    ("openai", _OPENAI, "https://api.openai.com/v1/chat/completions", "gpt-4o-mini"),
]


def router_available() -> bool:
    return any(key for _, key, _, _ in _PROVIDERS)


def list_providers() -> dict[str, bool]:
    return {name: bool(key) for name, key, _, _ in _PROVIDERS}


def gemini_key() -> str:
    return _GOOGLE


async def chat_with_router(
    messages: list[dict],
    task: str = "auto",
    max_tokens: int = 1024,
    temperature: float = 0.5,
) -> dict | None:
    """Call the first available provider with an OpenAI-compatible chat payload."""
    clean = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("content")
    ]
    if not clean:
        return None

    async with httpx.AsyncClient(timeout=40) as client:
        for name, key, url, model in _PROVIDERS:
            if not key:
                continue
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if name == "openrouter":
                headers["HTTP-Referer"] = "http://127.0.0.1:8005"
                headers["X-Title"] = "Meraxes"
            payload = {
                "model": model,
                "messages": clean,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            try:
                r = await client.post(url, headers=headers, json=payload)
                if r.status_code != 200:
                    continue
                body = r.json()
                content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if content and content.strip():
                    usage = body.get("usage") or {}
                    return {
                        "content": content.strip(),
                        "provider": name,
                        "model": model,
                        "input_tokens": usage.get("prompt_tokens", 0),
                        "output_tokens": usage.get("completion_tokens", 0),
                    }
            except Exception:
                continue
    return None
