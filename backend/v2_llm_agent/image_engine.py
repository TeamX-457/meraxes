"""
Image generation for V2 — cloud API first (no local CPU/GPU), optional SD WebUI fallback.

Provider order (IMAGE_PROVIDER in .env):
  pollinations — FREE, no API key (best if you have no budget)
  openai       — DALL-E (costs ~$0.04/image)
  sd-webui     — local or Colab GPU tunnel
"""
from __future__ import annotations

import base64
import logging
import re
import time
import uuid
from pathlib import Path

from urllib.parse import quote

import httpx
from openai import AsyncOpenAI

from v2_llm_agent.config import (
    ENABLE_IMAGE_GEN,
    IMAGE_PROVIDER_ORDER,
    OPENAI_API_KEY,
    OPENAI_IMAGE_MODEL,
    OPENAI_IMAGE_QUALITY,
    OPENAI_IMAGE_SIZE,
    POLLINATIONS_MODEL,
    POLLINATIONS_SIZE,
    SD_IMAGE_SIZE,
    SD_IMAGE_STEPS,
    SD_WEBUI_URL,
)

logger = logging.getLogger(__name__)

_IMAGES_DIR = Path(__file__).resolve().parent / "static" / "generated"
_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

_IMAGE_TRIGGERS = re.compile(
    r"\b("
    r"create|generate|make|draw|design|render|produce|show me|give me"
    r")\b.{0,40}\b("
    r"image|picture|photo|illustration|artwork|logo|icon|wallpaper|poster|drawing"
    r")\b",
    re.I,
)
_IMAGE_OF = re.compile(
    r"\b(image|picture|photo|illustration|drawing|art)\s+of\b",
    re.I,
)
_DRAW = re.compile(r"\bdraw\s+(me\s+)?(a|an)\s+", re.I)

_STRIP_PREFIX = re.compile(
    r"^(please\s+)?("
    r"create|generate|make|draw|design|render|produce|show me|give me"
    r")\s+(an?\s+)?("
    r"image|picture|photo|illustration|artwork|logo|icon|wallpaper|poster|drawing"
    r")\s+(of\s+)?",
    re.I,
)


def is_image_request(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if _IMAGE_TRIGGERS.search(t):
        return True
    if _IMAGE_OF.search(t):
        return True
    if _DRAW.search(t):
        return True
    return False


def extract_image_prompt(text: str) -> str:
    p = text.strip()
    p = _STRIP_PREFIX.sub("", p)
    p = re.sub(r"^(please\s+)", "", p, flags=re.I)
    p = re.sub(r"\s+", " ", p).strip()
    return p if len(p) >= 3 else text.strip()


_CONTEXT_PRONOUNS = re.compile(r"\b(it|that|this|same)\b", re.I)
_IMAGE_FOLLOWUP = re.compile(
    r"\b("
    r"too\s+blur|blur(?:ry|red)?|sharper|sharpen|clearer|more\s+detail|"
    r"regenerat|redo|try\s+again|again|fix\s+(?:the\s+)?image|improve|less\s+blur|"
    r"make\s+it\s+(?:less\s+)?blur|not\s+blur"
    r")\b",
    re.I,
)


def is_image_followup(text: str) -> bool:
    """Short feedback about a prior image (e.g. 'too blurry') — not a new image command."""
    t = text.strip()
    if not t or is_image_request(t):
        return False
    return bool(_IMAGE_FOLLOWUP.search(t))


def wants_image(text: str) -> bool:
    return is_image_request(text) or is_image_followup(text)


def _subject_from_generated(content: str) -> str | None:
    m = re.search(r"Generated image:\s*\*\*(.+?)\*\*", content or "")
    return m.group(1).strip() if m else None


def _base_image_subject(history: list[dict]) -> str | None:
    """First concrete image subject in the thread (before 'it' / 'that' refs)."""
    for msg in history:
        if msg.get("role") != "user":
            continue
        c = msg.get("content", "")
        if not is_image_request(c):
            continue
        p = extract_image_prompt(c)
        if p and not _CONTEXT_PRONOUNS.search(p):
            return p
    return None


def _latest_image_scene(history: list[dict]) -> str | None:
    """Most recent image subject — user prompt or last generated caption."""
    for msg in reversed(history):
        if msg.get("role") == "assistant":
            subj = _subject_from_generated(msg.get("content", ""))
            if subj:
                return subj
        if msg.get("role") == "user" and is_image_request(msg.get("content", "")):
            return extract_image_prompt(msg["content"])
    return None


def _resolve_pronouns(text: str, base: str) -> str:
    return _CONTEXT_PRONOUNS.sub(base, text)


def resolve_image_prompt(user_input: str, history: list[dict]) -> str:
    """
    Build a self-contained Pollinations prompt using prior turns.
    Image gen skips the LLM, so 'it' / 'too blurry' must be expanded here.
    """
    base = _base_image_subject(history)
    scene = _latest_image_scene(history)
    clean = extract_image_prompt(user_input)
    feedback = user_input.strip()

    if is_image_followup(user_input):
        subject = scene or base
        if not subject:
            return feedback
        if base and _CONTEXT_PRONOUNS.search(subject):
            subject = _resolve_pronouns(subject, base)
        low = feedback.lower()
        if re.search(r"blur", low):
            return f"{subject}, sharp focus, crisp details, high quality, not blurry"
        if re.search(r"sharper|sharpen|clearer|detail", low):
            return f"{subject}, ultra sharp, highly detailed, 4k"
        return f"{subject}, {feedback}"

    if base and _CONTEXT_PRONOUNS.search(clean):
        return _resolve_pronouns(clean, base)

    if base and scene and base != scene and _CONTEXT_PRONOUNS.search(clean):
        resolved = _resolve_pronouns(clean, base)
        return resolved

    return clean if len(clean) >= 3 else user_input.strip()


def _save_png(data: bytes) -> str:
    fname = f"{uuid.uuid4().hex[:12]}.png"
    (_IMAGES_DIR / fname).write_bytes(data)
    return f"/static/generated/{fname}"


async def sd_webui_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{SD_WEBUI_URL.rstrip('/')}/sdapi/v1/sd-models")
            return r.status_code == 200
    except Exception:
        return False


async def image_providers_status() -> dict:
    out = {"order": IMAGE_PROVIDER_ORDER, "providers": {}}
    if "pollinations" in IMAGE_PROVIDER_ORDER:
        out["providers"]["pollinations"] = {
            "free": True,
            "model": POLLINATIONS_MODEL,
            "note": "No API key required",
        }
    if "openai" in IMAGE_PROVIDER_ORDER:
        out["providers"]["openai"] = {
            "configured": bool(OPENAI_API_KEY),
            "model": OPENAI_IMAGE_MODEL,
        }
    if "sd-webui" in IMAGE_PROVIDER_ORDER:
        out["providers"]["sd-webui"] = {
            "url": SD_WEBUI_URL,
            "online": await sd_webui_available(),
        }
    return out


def _clean_prompt(prompt: str, *, resolved: bool = False) -> str:
    return prompt if resolved else extract_image_prompt(prompt)


async def _generate_openai(prompt: str, *, resolved: bool = False) -> dict:
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY not set", "provider": "openai"}
    clean = _clean_prompt(prompt, resolved=resolved)
    t0 = time.perf_counter()
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    try:
        resp = await client.images.generate(
            model=OPENAI_IMAGE_MODEL,
            prompt=clean,
            size=OPENAI_IMAGE_SIZE,
            quality=OPENAI_IMAGE_QUALITY,
            n=1,
        )
    except Exception as e:
        return {"ok": False, "error": str(e), "provider": "openai"}

    item = resp.data[0]
    ms = int((time.perf_counter() - t0) * 1000)

    if item.b64_json:
        raw = base64.b64decode(item.b64_json)
        return {
            "ok": True,
            "image_url": _save_png(raw),
            "prompt": clean,
            "latency_ms": ms,
            "provider": "openai",
            "model": OPENAI_IMAGE_MODEL,
        }

    if item.url:
        async with httpx.AsyncClient(timeout=60.0) as http:
            r = await http.get(item.url)
            r.raise_for_status()
            return {
                "ok": True,
                "image_url": _save_png(r.content),
                "prompt": clean,
                "latency_ms": ms,
                "provider": "openai",
                "model": OPENAI_IMAGE_MODEL,
            }

    return {"ok": False, "error": "OpenAI returned no image data", "provider": "openai"}


async def _generate_pollinations(prompt: str, *, resolved: bool = False) -> dict:
    """Free image API — no key, no cost. https://pollinations.ai"""
    clean = _clean_prompt(prompt, resolved=resolved)
    t0 = time.perf_counter()
    w = h = POLLINATIONS_SIZE
    url = (
        f"https://image.pollinations.ai/prompt/{quote(clean)}"
        f"?width={w}&height={h}&model={quote(POLLINATIONS_MODEL)}&nologo=true"
    )
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            if not r.content or len(r.content) < 1000:
                return {"ok": False, "error": "Empty response from Pollinations", "provider": "pollinations"}
    except Exception as e:
        return {"ok": False, "error": str(e), "provider": "pollinations"}

    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "image_url": _save_png(r.content),
        "prompt": clean,
        "latency_ms": ms,
        "provider": "pollinations",
        "model": POLLINATIONS_MODEL,
    }


async def _generate_sd_webui(prompt: str, *, resolved: bool = False) -> dict:
    clean = _clean_prompt(prompt, resolved=resolved)
    t0 = time.perf_counter()
    payload = {
        "prompt": clean,
        "negative_prompt": "blurry, low quality, distorted, watermark, text, ugly",
        "steps": SD_IMAGE_STEPS,
        "width": SD_IMAGE_SIZE,
        "height": SD_IMAGE_SIZE,
        "cfg_scale": 7,
        "sampler_name": "Euler a",
    }
    url = f"{SD_WEBUI_URL.rstrip('/')}/sdapi/v1/txt2img"
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
    except httpx.ConnectError:
        return {
            "ok": False,
            "error": f"SD WebUI offline at {SD_WEBUI_URL}",
            "provider": "sd-webui",
        }
    except Exception as e:
        return {"ok": False, "error": str(e), "provider": "sd-webui"}

    images = data.get("images") or []
    if not images:
        return {"ok": False, "error": "SD WebUI returned no image", "provider": "sd-webui"}

    raw = base64.b64decode(images[0].split(",", 1)[-1])
    ms = int((time.perf_counter() - t0) * 1000)
    return {
        "ok": True,
        "image_url": _save_png(raw),
        "prompt": clean,
        "latency_ms": ms,
        "provider": "sd-webui",
        "model": "stable-diffusion-local",
    }


async def generate_image(prompt: str, *, resolved: bool = False) -> dict:
    """Try IMAGE_PROVIDER_ORDER until one succeeds."""
    if not ENABLE_IMAGE_GEN:
        return {"ok": False, "error": "Image generation disabled in .env"}

    errors: list[str] = []
    for provider in IMAGE_PROVIDER_ORDER:
        if provider == "pollinations":
            result = await _generate_pollinations(prompt, resolved=resolved)
        elif provider == "openai":
            result = await _generate_openai(prompt, resolved=resolved)
        elif provider in ("sd-webui", "sd", "local"):
            result = await _generate_sd_webui(prompt, resolved=resolved)
        else:
            continue
        if result.get("ok"):
            return result
        err = result.get("error", "unknown")
        errors.append(f"{provider}: {err}")
        logger.warning("Image provider %s failed: %s", provider, err)

    return {
        "ok": False,
        "error": (
            "All image providers failed. "
            + (" | ".join(errors) if errors else "Check .env IMAGE_PROVIDER and API keys.")
            + " Free option: IMAGE_PROVIDER=pollinations (no key, no cost)."
        ),
    }
