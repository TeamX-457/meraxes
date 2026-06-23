"""
Multi-LLM API Router — production FastAPI gateway.

Run:
  cd AImodel/llm_router
  uvicorn main:app --host 0.0.0.0 --port 8020
"""
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from config import settings
from core.cache import response_cache
from core.router import router as llm_router
from core.usage import usage_tracker
from schemas import ChatMessage, ChatRequest, ChatResponse, HealthResponse

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("llm_router")

FRONTEND = Path(__file__).resolve().parent / "frontend" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Multi-LLM Router started on port %s", settings.port)
    logger.info("Providers: %s", llm_router.list_providers())
    yield
    logger.info("Router shutdown")


app = FastAPI(
    title="Multi-LLM API Router",
    version="1.0.0",
    description="Cost-optimized routing across Gemini, Groq, Together, OpenRouter, xAI, OpenAI",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
def ui():
    if not FRONTEND.exists():
        return HTMLResponse("<h1>frontend/index.html missing</h1>")
    return FRONTEND.read_text(encoding="utf-8")


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        providers=llm_router.list_providers(),
        cache_entries=response_cache.size(),
    )


@app.get("/api/usage")
def usage():
    return usage_tracker.snapshot()


@app.get("/api/config")
def api_config():
    return {
        "port": settings.port,
        "providers": llm_router.list_providers(),
        "priority": settings.priority_list(),
        "parallel_enabled": settings.parallel_enabled,
        "cache_enabled": settings.cache_enabled,
        "task_routing": llm_router.TASK_PROVIDER_ORDER,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def api_chat(req: ChatRequest):
    t0 = time.monotonic()
    try:
        resp = await llm_router.chat(req)
        logger.info(
            "chat provider=%s model=%s task=%s cached=%s latency=%dms",
            resp.provider,
            resp.model,
            resp.task,
            resp.cached,
            resp.latency_ms or int((time.monotonic() - t0) * 1000),
        )
        return resp
    except Exception as e:
        logger.exception("Chat failed")
        raise HTTPException(500, detail=str(e)) from e


@app.post("/v1/chat/completions")
async def openai_compatible(request: Request):
    """OpenAI-compatible endpoint for CLI tools (Cursor, Cline, etc.)."""
    body = await request.json()
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(400, "messages required")

    req = ChatRequest(
        messages=[
            ChatMessage(role=m["role"], content=m.get("content") or "")
            for m in messages
        ],
        model=body.get("model"),
        max_tokens=body.get("max_tokens"),
        temperature=body.get("temperature", 0.7),
        stream=body.get("stream", False),
        task=body.get("task", "auto"),
        provider=body.get("provider"),
        parallel=body.get("parallel"),
        use_cache=body.get("use_cache", True),
    )

    if req.stream:
        async def streamer():
            result = await llm_router.chat(req)
            chunk = {
                "id": "router-1",
                "object": "chat.completion.chunk",
                "choices": [{"delta": {"content": result.content}, "index": 0}],
            }
            import json
            yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(streamer(), media_type="text/event-stream")

    result = await llm_router.chat(req)
    return {
        "id": "router-1",
        "object": "chat.completion",
        "model": result.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": result.content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": result.input_tokens,
            "completion_tokens": result.output_tokens,
        },
        "router_meta": {
            "provider": result.provider,
            "task": result.task,
            "cached": result.cached,
            "fallbacks": result.fallbacks_used,
        },
    }


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s", request.url)
    return JSONResponse(status_code=500, content={"detail": str(exc)})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
