"""Schemas for Meraxes agent optimizer."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentGoal(BaseModel):
    description: str
    context: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid4().hex[:8]}")
    name: str
    description: str
    tool_name: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class AgentPlan(BaseModel):
    goal: str
    tasks: list[AgentTask]
    reasoning: str


class ToolResult(BaseModel):
    success: bool
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: float = 0


class StepResult(BaseModel):
    task_id: str
    task_name: str
    tool_name: str
    result: ToolResult
    reasoning: str
    attempt: int = 1


class EvaluationResult(BaseModel):
    task_id: str | None = None
    passed: bool
    score: float = Field(ge=0, le=1)
    feedback: str
    should_retry: bool = False


class AgentDecisionLog(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    phase: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run_{uuid4().hex[:12]}")
    agent_name: str
    goal: str
    status: str
    plan: AgentPlan
    steps: list[StepResult] = Field(default_factory=list)
    evaluations: list[EvaluationResult] = Field(default_factory=list)
    decisions: list[AgentDecisionLog] = Field(default_factory=list)
    final_output: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
