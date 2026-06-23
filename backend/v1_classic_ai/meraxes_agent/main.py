"""
Meraxes Agent Optimizer API — Track 2 (optional standalone port 8030).

Agent routes are also mounted on main.py (8005) so the website works with one server.
"""

from __future__ import annotations

import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
if str(V1_ROOT) not in sys.path:
    sys.path.insert(0, str(V1_ROOT))

from fastapi import FastAPI

from config import PRODUCT_NAME
from meraxes_agent.routes import router as agent_router
from meraxes_agent.chat_routes import router as agent_chat_router

app = FastAPI(
    title=f"{PRODUCT_NAME} Agent Quality Lab",
    description="Track 2 — Optimize Meraxes v1 trainable chatbot models",
    version="1.0.0",
)

app.include_router(agent_router)
app.include_router(agent_chat_router)


@app.get("/health")
def health():
    models_dir = V1_ROOT / "models" / "meraxes"
    trained = [p.name for p in models_dir.iterdir() if p.is_dir() and p.name != "logs"] if models_dir.is_dir() else []
    return {
        "status": "ok",
        "product": PRODUCT_NAME,
        "track": "Track 2 — Optimize (Existing Agents)",
        "agent": "meraxes_v1_quality_lab",
        "v1_port": 8005,
        "trained_models": trained,
        "datasets": ["saas", "ecommerce", "healthcare", "finance", "general"],
    }
