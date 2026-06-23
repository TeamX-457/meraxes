"""
main.py — FastAPI entry point for the Hybrid AI Agent.

Endpoints:
  POST /chat          — main chat endpoint
  GET  /health        — system + LLM health check
  GET  /memory/stats  — FAISS stats
  DELETE /user/{id}   — wipe user data
"""

import logging
import re
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from v2_llm_agent import config
from v2_llm_agent.config import MODEL_TIERS, PUBLIC_URL
from v2_llm_agent.database import init_db, get_user_name, upsert_user, save_turn, get_history
from v2_llm_agent.llm_engine import generate, health_check
from v2_llm_agent.memory import add_memory, search_memory, memory_stats, warmup
from v2_llm_agent.prompts import build_messages

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ─── App lifecycle ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Agent starting up...")
    init_db()
    threading.Thread(target=warmup, name="memory-warmup", daemon=True).start()
    logger.info("UI ready at %s — memory model loading in background", PUBLIC_URL)
    yield
    logger.info("🛑 Agent shutting down.")


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
FAVICON = BASE_DIR / "static" / "favicon.svg"
GENERATED_DIR = BASE_DIR / "static" / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Nova AI V2",
    version="4.0.0",
    description="Designer chat UI with embedded Multi-LLM router, memory, and fallbacks",
    lifespan=lifespan,
)


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    path = FAVICON if FAVICON.exists() else BASE_DIR.parent / "v1_classic_ai" / "static" / "favicon.svg"
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def ui():
    html_path = FRONTEND_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(404, "UI not found")
    return html_path.read_text(encoding="utf-8")


@app.get("/api/config")
def api_config():
    from v2_llm_agent.config import use_openai

    from v2_llm_agent.config import LLM_PROVIDER_ORDER, has_cloud_api_key

    return {
        "default_tier": config.DEFAULT_TIER,
        "use_openai": use_openai(),
        "llm_mode": "hybrid" if use_openai() else "local_only",
        "provider_order": LLM_PROVIDER_ORDER,
        "cloud_configured": has_cloud_api_key(),
        "tiers": {
            k: {"openai": v["openai_models"], "ollama": v["ollama_models"]}
            for k, v in MODEL_TIERS.items()
        },
        "embedding_model": config.EMBEDDING_MODEL,
        "port": config.PORT,
    }


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / response schemas ───────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096)
    user_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tier: str = Field(default="strong", description="strong | fast | local")
    task: str | None = Field(None, description="auto | fast | long | reasoning | cheap")
    stream: bool = False


class ChatResponse(BaseModel):
    reply: str
    user_id: str
    provider: str
    model: str
    tier: str
    latency_ms: int
    memory_hits: int
    image_url: str | None = None
    user_message_id: int | None = None


# ─── Name extraction (simple heuristic) ───────────────────────────────────────

_NAME_PATTERNS = [
    re.compile(r"(?:my name is|i(?:'m| am)|call me)\s+([A-Z][a-z]+)", re.I),
    re.compile(r"^([A-Z][a-z]+)\s+here\b", re.I),
]


def _extract_name(text: str) -> str | None:
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).capitalize()
    return None


# ─── /chat ────────────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    user_id = req.user_id
    user_input = req.message.strip()

    # Image requests — fast path before memory/LLM (avoids slow embed + 500s on stale code paths)
    from v2_llm_agent.config import ENABLE_IMAGE_GEN
    from v2_llm_agent.image_engine import generate_image, wants_image, resolve_image_prompt

    if ENABLE_IMAGE_GEN and wants_image(user_input):
        history = get_history(user_id, limit=config.CONVERSATION_WINDOW * 2)
        img_prompt = resolve_image_prompt(user_input, history)
        try:
            img = await generate_image(img_prompt, resolved=True)
            if img.get("ok"):
                reply = f"Generated image: **{img['prompt']}**"
                user_msg_id = save_turn(user_id, "user", user_input)
                save_turn(user_id, "assistant", reply)
                return ChatResponse(
                    reply=reply,
                    user_id=user_id,
                    provider=img.get("provider", "image"),
                    model=img.get("model", "flux"),
                    tier="image",
                    latency_ms=img.get("latency_ms", 0),
                    memory_hits=0,
                    image_url=img.get("image_url"),
                    user_message_id=user_msg_id,
                )
            reply = img.get("error", "Image generation failed.")
        except Exception as exc:
            logger.exception("Image generation error")
            reply = f"Image generation failed: {exc}"
        user_msg_id = save_turn(user_id, "user", user_input)
        save_turn(user_id, "assistant", reply)
        return ChatResponse(
            reply=reply,
            user_id=user_id,
            provider="image",
            model="error",
            tier="image",
            latency_ms=0,
            memory_hits=0,
            user_message_id=user_msg_id,
        )

    # 1. Detect and persist user name if mentioned
    detected_name = _extract_name(user_input)
    if detected_name:
        upsert_user(user_id, name=detected_name)
        logger.info("Name stored for user %s: %s", user_id, detected_name)

    # 2. Retrieve user name from DB
    user_name = get_user_name(user_id)

    # 3. Semantic memory retrieval
    memories = search_memory(user_input, user_id=user_id)
    logger.debug("Memory hits: %d for query: %.60s...", len(memories), user_input)

    # 4. Load conversation history
    history = get_history(user_id)

    # 5. Build prompt for text LLM
    tier = req.tier if req.tier in MODEL_TIERS else config.DEFAULT_TIER

    messages = build_messages(
        user_input=user_input,
        history=history,
        memories=memories,
        user_name=user_name,
        tier=tier,
    )

    try:
        llm_resp = await generate(messages, tier=tier, task=req.task)
    except RuntimeError as e:
        logger.error("All LLM providers failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    reply = llm_resp.content.strip()

    # 7. Persist conversation turn
    user_msg_id = save_turn(user_id, "user", user_input)
    save_turn(user_id, "assistant", reply)

    # 8. Memory learning — store high-quality LLM responses
    add_memory(
        question=user_input,
        answer=reply,
        user_id=user_id,
        source=llm_resp.provider,
    )

    # 9. Silent training: external API answers → V1 intents + local export
    try:
        from v2_llm_agent.silent_trainer import record_chat_for_training
        record_chat_for_training(user_input, reply, llm_resp.provider, llm_resp.model)
    except Exception:
        logger.debug("Silent trainer skipped", exc_info=True)

    return ChatResponse(
        reply=reply,
        user_id=user_id,
        provider=llm_resp.provider,
        model=llm_resp.model,
        tier=llm_resp.tier,
        latency_ms=llm_resp.latency_ms,
        memory_hits=len(memories),
        user_message_id=user_msg_id,
    )


@app.get("/api/chat/history")
def api_history(user_id: str, limit: int = 50):
    return {"messages": get_history(user_id, limit=limit)}


@app.get("/api/chat/conversations")
def api_conversations(limit: int = 40):
    from v2_llm_agent.database import list_sessions
    return {"conversations": list_sessions(limit=limit)}


def _purge_generated_images(*texts: str) -> int:
    import re
    n = 0
    base = BASE_DIR / "static" / "generated"
    for text in texts:
        for m in re.finditer(r"/static/generated/([a-zA-Z0-9]+\.png)", text or ""):
            path = base / m.group(1)
            if path.is_file():
                path.unlink(missing_ok=True)
                n += 1
    return n


@app.delete("/api/chat/conversations/{user_id}")
def api_delete_conversation(user_id: str):
    """Permanently delete chat, all messages, FAISS memories, and local image files."""
    from v2_llm_agent.database import delete_conversation, get_history
    from v2_llm_agent.memory import delete_user_memories

    msgs = get_history(user_id, limit=500)
    texts = [m.get("content", "") for m in msgs]
    images_removed = _purge_generated_images(*texts)
    messages_removed = delete_conversation(user_id)
    memories_removed = delete_user_memories(user_id)
    return {
        "deleted": True,
        "user_id": user_id,
        "messages_removed": messages_removed,
        "memories_removed": memories_removed,
        "images_removed": images_removed,
    }


@app.delete("/api/chat/messages/{msg_id}")
def api_delete_message(msg_id: int, user_id: str):
    """Permanently delete one message and its paired user/assistant turn."""
    from v2_llm_agent.database import delete_message_turn
    from v2_llm_agent.memory import delete_memory_pair

    deleted = delete_message_turn(msg_id, user_id)
    if not deleted:
        raise HTTPException(404, "Message not found")
    texts = [d.get("content", "") for d in deleted]
    _purge_generated_images(*texts)
    mem_removed = 0
    users = [d for d in deleted if d["role"] == "user"]
    bots = [d for d in deleted if d["role"] == "assistant"]
    if users and bots:
        mem_removed = delete_memory_pair(user_id, users[0]["content"], bots[0]["content"])
    return {
        "deleted": True,
        "removed": len(deleted),
        "memories_removed": mem_removed,
    }


@app.delete("/api/chat/history")
def api_clear_chat_history(user_id: str):
    """Permanently clear all messages in current chat (keeps session id)."""
    from v2_llm_agent.database import clear_history, get_history
    from v2_llm_agent.memory import delete_user_memories

    msgs = get_history(user_id, limit=500)
    texts = [m.get("content", "") for m in msgs]
    _purge_generated_images(*texts)
    n = clear_history(user_id)
    mem = delete_user_memories(user_id)
    return {"cleared": n, "memories_removed": mem}


# ─── /health ──────────────────────────────────────────────────────────────────

@app.get("/api/training/status")
def training_status():
    from v2_llm_agent.silent_trainer import get_training_status
    return get_training_status()


@app.post("/api/training/run-v1")
def training_run_v1_now():
    """Manually flush queue and retrain V1 bot from V2 chats."""
    from v2_llm_agent.silent_trainer import run_v1_train_now
    import threading
    threading.Thread(target=run_v1_train_now, daemon=True).start()
    return {"ok": True, "message": "V1 training started in background"}


class OllamaBuildRequest(BaseModel):
    create_model: bool = Field(default=False, description="Run ollama create (needs Ollama installed)")


@app.post("/api/training/build-ollama")
def training_build_ollama(req: OllamaBuildRequest):
    """Write Modelfile from chat export; optionally run ollama create."""
    from v2_llm_agent.silent_trainer import run_ollama_build_now
    import threading

    if req.create_model:
        threading.Thread(
            target=run_ollama_build_now,
            kwargs={"force_create": True},
            daemon=True,
        ).start()
        return {"ok": True, "message": "Ollama model build started in background"}
    return run_ollama_build_now(force_create=False)


@app.get("/api/router/usage")
def router_usage():
    try:
        from v2_llm_agent.router_bridge import usage_snapshot
        return usage_snapshot()
    except Exception:
        return {}


@app.get("/health")
async def health():
    llm_status = await health_check()
    mem = memory_stats()
    out = {
        "status": "ok",
        "llm": llm_status,
        "memory": mem,
    }
    if config.USE_EMBEDDED_ROUTER:
        try:
            from v2_llm_agent.router_bridge import list_providers
            out["router"] = list_providers()
        except Exception as e:
            out["router"] = {"error": str(e)}
    if config.ENABLE_IMAGE_GEN:
        try:
            from v2_llm_agent.image_engine import image_providers_status
            out["image_gen"] = {"enabled": True, **await image_providers_status()}
        except Exception as e:
            out["image_gen"] = {"enabled": True, "error": str(e)}
    return out


# ─── /memory/stats ────────────────────────────────────────────────────────────

@app.get("/memory/stats")
async def mem_stats():
    return memory_stats()


# ─── DELETE /user/{user_id} ───────────────────────────────────────────────────

@app.delete("/user/{user_id}")
async def delete_user_data(user_id: str):
    from v2_llm_agent.database import delete_user
    from v2_llm_agent.memory import delete_user_memories

    delete_user(user_id)
    removed = delete_user_memories(user_id)
    return {"deleted": True, "memories_removed": removed}


# ─── Global error handler ─────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url)
    detail = str(exc) if config.DEBUG else "Internal server error"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
    )


# ─── Dev runner ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="debug" if config.DEBUG else "info",
    )