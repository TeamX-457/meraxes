"""Shared Meraxes agent API routes — mount on main app (8005) or standalone (8030)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

V1_ROOT = Path(__file__).resolve().parents[1]
if str(V1_ROOT) not in sys.path:
    sys.path.insert(0, str(V1_ROOT))

from config import PRODUCT_NAME
from meraxes_agent.models.schemas import AgentGoal
from meraxes_agent.optimizer_agent import MeraxesQualityLab

router = APIRouter(tags=["agents"])


class OptimizeGoalRequest(BaseModel):
    goal: str = Field(..., min_length=5, examples=["Research refunds and add intents so my bot handles billing questions"])
    dataset: str = Field(default="saas", examples=["saas", "ecommerce", "healthcare", "finance", "general"])
    test_case_limit: int = Field(default=6, ge=3, le=15)
    target_score: float = Field(default=0.7, ge=0, le=1)
    quick_train: bool = Field(default=True)
    enable_research: bool = Field(default=True, description="Research topics before adding intents")


def _serialize_run(run) -> dict:
    fo = run.final_output or {}
    us = fo.get("user_summary") or {}
    return {
        "run_id": run.run_id,
        "agent_name": run.agent_name,
        "product": PRODUCT_NAME,
        "track": fo.get("track", "Track 2 — Optimize (Existing Agents)"),
        "goal": run.goal,
        "status": run.status,
        "dataset": fo.get("dataset"),
        "baseline_score": fo.get("baseline_score"),
        "post_refine_score": fo.get("post_refine_score"),
        "improvement": fo.get("improvement"),
        "custom_qa_added": fo.get("custom_qa_added"),
        "intents_added": fo.get("intents_added", []),
        "research_brief": fo.get("research_brief", ""),
        "user_summary": us,
        "model_dir": fo.get("model_dir"),
        "tool_usage": [{"task": s.task_name, "tool": s.tool_name, "success": s.result.success} for s in run.steps],
        "decisions": [d.model_dump(mode="json") for d in run.decisions],
    }


@router.get("/agents/health")
def agent_health():
    models_dir = V1_ROOT / "models" / "meraxes"
    trained = [p.name for p in models_dir.iterdir() if p.is_dir() and p.name != "logs"] if models_dir.is_dir() else []
    return {
        "status": "ok",
        "agent": "meraxes_v1_quality_lab",
        "track": "Track 2 — Optimize (Existing Agents)",
        "trained_models": trained,
    }


@router.post("/agents/optimize")
def optimize_meraxes(body: OptimizeGoalRequest):
    """Run the full quality-lab agent with your goal."""
    goal = AgentGoal(
        description=body.goal,
        context={
            **body.model_dump(exclude={"goal"}),
            "minimal_train": True,
        },
    )
    run = MeraxesQualityLab().run(goal)
    return _serialize_run(run)


@router.post("/agents/train")
def train_meraxes_models(dataset: str = "saas", quick: bool = True):
    from train_meraxes import train_vertical

    try:
        stats = train_vertical(dataset, quick=quick, minimal=True)
        return {"ok": True, "stats": stats}
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/agents/runs/{run_id}")
def get_run(run_id: str):
    log_path = V1_ROOT / "models" / "meraxes" / "logs" / f"{run_id}.json"
    if not log_path.is_file():
        raise HTTPException(404, "Run not found")
    return json.loads(log_path.read_text(encoding="utf-8"))
