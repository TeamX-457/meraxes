"""
V1 Chatbot Platform — embeddable website assistants with business templates.
Run: uvicorn main:app --host 0.0.0.0 --port 8005
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from meraxes_agent.routes import router as agent_router
from meraxes_agent.chat_routes import router as agent_chat_router

from database import (
    clear_messages,
    create_bot,
    get_bot,
    get_messages,
    get_user_name,
    init_db,
    list_bots,
    save_message,
    save_user_name,
    update_bot,
)
from dataset_loader import list_business_templates, load_template
from engine import MODEL_TYPES, get_engine, invalidate_engine
from config import PORT, PRODUCT_NAME, PUBLIC_URL

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title=f"{PRODUCT_NAME} — V1 Chatbot Platform", version="2.0.0")

FAVICON_PATH = STATIC_DIR / "favicon.svg"


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.svg", include_in_schema=False)
def favicon():
    if not FAVICON_PATH.exists():
        raise HTTPException(404)
    return FileResponse(
        FAVICON_PATH,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Track 2 agent — same server as website (no separate port needed)
app.include_router(agent_router)
app.include_router(agent_chat_router)


def _retrain_all_bots() -> None:
    """Reload latest business templates and retrain so new intent patterns apply."""
    import logging
    from dataset_loader import load_template, merge_custom_qa

    log = logging.getLogger(__name__)
    for bot in list_bots():
        try:
            template = load_template(bot["business_id"])
            invalidate_engine(bot["bot_id"])
            engine = get_engine(bot)
            engine.intents = merge_custom_qa(
                template["intents"], bot.get("custom_qa", [])
            )
            stats = engine.train()
            log.info("Retrained bot %s: %s", bot["bot_id"], stats)
        except Exception as exc:
            log.warning("Retrain skipped for %s: %s", bot.get("bot_id"), exc)


@app.on_event("startup")
def on_startup():
    import threading

    init_db()

    def _startup_tasks():
        _retrain_all_bots()
        # Ensure default Meraxes agent model exists for demos
        try:
            from pathlib import Path
            saas_model = BASE_DIR / "models" / "meraxes" / "saas" / "chat_model.pth"
            if not saas_model.is_file():
                from train_meraxes import train_vertical
                train_vertical("saas", minimal=True)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Meraxes default model skip: %s", exc)

    threading.Thread(target=_startup_tasks, name="v1-retrain", daemon=True).start()


@app.get("/api/health")
def health():
    models_dir = BASE_DIR / "models" / "meraxes"
    trained = [p.name for p in models_dir.iterdir() if p.is_dir()] if models_dir.is_dir() else []
    return {
        "status": "ok",
        "product": PRODUCT_NAME,
        "port": PORT,
        "url": PUBLIC_URL,
        "trained_meraxes_models": trained,
    }


# ─── Schemas ─────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    user_id: str = "guest"
    bot_id: str | None = None


class CreateBotRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    business_id: str = "general"
    model_type: str = "hybrid"


class UpdateBotRequest(BaseModel):
    name: str | None = None
    business_id: str | None = None
    model_type: str | None = None
    custom_qa: list[dict] | None = None


class CustomQAItem(BaseModel):
    question: str
    answer: str


# ─── Pages ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard():
    path = STATIC_DIR / "dashboard.html"
    if not path.exists():
        raise HTTPException(404, "dashboard.html missing")
    html = path.read_text(encoding="utf-8")
    if "<link rel=\"icon\"" not in html:
        html = html.replace(
            "<title>",
            '<link rel="icon" href="/favicon.svg?v=2" type="image/svg+xml" />\n'
            '<link rel="shortcut icon" href="/favicon.ico?v=2" />\n  <title>',
            1,
        )
    return html


@app.get("/preview/{bot_id}", response_class=HTMLResponse)
def preview_bot(bot_id: str):
    path = STATIC_DIR / "widget-preview.html"
    return path.read_text(encoding="utf-8").replace("{{BOT_ID}}", bot_id)


# ─── Platform API ────────────────────────────────────────────────────────────

@app.get("/api/model-types")
def api_model_types():
    return list(MODEL_TYPES.values())


@app.get("/api/businesses")
def api_businesses():
    return list_business_templates()


@app.get("/api/businesses/{business_id}")
def api_business_detail(business_id: str):
    try:
        return load_template(business_id)
    except FileNotFoundError:
        raise HTTPException(404, "Business template not found")


@app.get("/api/bots")
def api_list_bots():
    return list_bots()


@app.post("/api/bots")
def api_create_bot(req: CreateBotRequest):
    if req.model_type not in MODEL_TYPES:
        raise HTTPException(400, f"model_type must be one of: {list(MODEL_TYPES)}")
    try:
        load_template(req.business_id)
    except FileNotFoundError:
        raise HTTPException(400, "Invalid business_id")
    bot = create_bot(req.name, req.business_id, req.model_type)
    engine = get_engine(bot)
    engine.intents = __import__("dataset_loader").merge_custom_qa(
        load_template(req.business_id)["intents"], []
    )
    engine.train()
    return bot


@app.get("/api/bots/{bot_id}")
def api_get_bot(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    template = load_template(bot["business_id"])
    return {**bot, "template": template}


@app.patch("/api/bots/{bot_id}")
def api_update_bot(bot_id: str, req: UpdateBotRequest):
    bot = update_bot(bot_id, **req.model_dump(exclude_unset=True))
    if not bot:
        raise HTTPException(404, "Bot not found")
    invalidate_engine(bot_id)
    return bot


@app.post("/api/bots/{bot_id}/train")
def api_train_bot(bot_id: str):
    from dataset_loader import load_template, merge_custom_qa

    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    invalidate_engine(bot_id)
    engine = get_engine(bot)
    engine.intents = merge_custom_qa(
        load_template(bot["business_id"])["intents"],
        bot.get("custom_qa", []),
    )
    stats = engine.train()
    return {"ok": True, "stats": stats}


@app.post("/api/bots/{bot_id}/custom-qa")
def api_add_custom_qa(bot_id: str, item: CustomQAItem):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    qa = bot["custom_qa"]
    qa.append({"question": item.question, "answer": item.answer})
    bot = update_bot(bot_id, custom_qa=qa)
    invalidate_engine(bot_id)
    eng = get_engine(bot)
    eng.intents = __import__("dataset_loader").merge_custom_qa(
        load_template(bot["business_id"])["intents"],
        bot.get("custom_qa", []),
    )
    eng.train()
    return bot


# ─── Chat (default bot if none specified) ───────────────────────────────────

DEFAULT_BOT_ID = None


def _resolve_bot(bot_id: str | None) -> dict:
    if bot_id:
        bot = get_bot(bot_id)
        if not bot:
            raise HTTPException(404, "Bot not found")
        return bot
    bots = list_bots()
    if bots:
        return bots[0]
    bot = create_bot("Default Assistant", "general", "hybrid")
    get_engine(bot).train()
    return bot


@app.get("/api/chat/history")
def api_chat_history(bot_id: str, user_id: str, limit: int = 100):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    return {"messages": get_messages(bot_id, user_id, limit=limit)}


@app.delete("/api/chat/history")
def api_clear_history(bot_id: str, user_id: str):
    if not get_bot(bot_id):
        raise HTTPException(404, "Bot not found")
    removed = clear_messages(bot_id, user_id)
    return {"cleared": removed}


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        bot = _resolve_bot(req.bot_id)
        save_message(bot["bot_id"], req.user_id, "user", req.message.strip())
        engine = get_engine(bot)
        result = engine.reply(
            req.user_id,
            req.message,
            get_user_name,
            save_user_name,
        )
        save_message(bot["bot_id"], req.user_id, "assistant", result["response"])
        return {
            "response": result["response"],
            "source": result["source"],
            "bot_id": bot["bot_id"],
            "model_type": bot["model_type"],
        }
    except Exception as exc:
        import logging
        logging.exception("Chat error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ─── Website embed ─────────────────────────────────────────────────────────────

@app.get("/embed/{bot_id}.js")
def embed_script(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    js = (STATIC_DIR / "embed-widget.js").read_text(encoding="utf-8")
    js = js.replace("{{API_BASE}}", PUBLIC_URL)
    js = js.replace("{{BOT_ID}}", bot_id)
    js = js.replace("{{BOT_NAME}}", bot["name"].replace('"', '\\"'))
    return HTMLResponse(js, media_type="application/javascript")


@app.get("/api/bots/{bot_id}/embed-code")
def embed_code(bot_id: str):
    bot = get_bot(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    base = PUBLIC_URL
    snippet = (
        f'<script src="{base}/embed/{bot_id}.js" defer></script>\n'
        f'<!-- Or iframe: <iframe src="{base}/preview/{bot_id}" '
        f'width="400" height="560" style="border:none;border-radius:12px;"></iframe> -->'
    )
    return {"bot_id": bot_id, "snippet": snippet, "iframe_url": f"{base}/preview/{bot_id}"}
