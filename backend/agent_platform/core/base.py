"""Agent loop for optimizer platform."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from agent_platform.models.schemas import (
    AgentDecisionLog,
    AgentGoal,
    AgentPlan,
    AgentRunResult,
    AgentTask,
    EvaluationResult,
    StepResult,
    TaskStatus,
    ToolResult,
)

logger = logging.getLogger("agent_platform")


class AgentTool(Protocol):
    name: str
    description: str

    def execute(self, **kwargs: Any) -> ToolResult: ...


class AgentMemory:
    def __init__(self):
        self._store: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value

    def update(self, data: dict[str, Any]) -> None:
        self._store.update(data)

    @property
    def context(self) -> dict[str, Any]:
        return dict(self._store)


class AgentDecisionLogger:
    def __init__(self, log_dir: str | None = None):
        self._decisions: list[AgentDecisionLog] = []
        self._log_dir = Path(log_dir) if log_dir else None
        if self._log_dir:
            self._log_dir.mkdir(parents=True, exist_ok=True)

    @property
    def decisions(self) -> list[AgentDecisionLog]:
        return list(self._decisions)

    def log(self, phase: str, message: str, **data: Any) -> None:
        self._decisions.append(AgentDecisionLog(phase=phase, message=message, data=data))
        logger.info("[OPTIMIZER:%s] %s", phase, message)

    def persist_run(self, run: AgentRunResult) -> None:
        if not self._log_dir:
            return
        path = self._log_dir / f"{run.run_id}.json"
        path.write_text(json.dumps(run.model_dump(mode="json"), indent=2, default=str), encoding="utf-8")


class BasePlanner(ABC):
    @abstractmethod
    def plan(self, goal: AgentGoal, memory: AgentMemory) -> AgentPlan: ...


class BaseToolSelector(ABC):
    @abstractmethod
    def select(self, task: AgentTask, tools: dict, memory: AgentMemory) -> str: ...


class Executor:
    def __init__(self, logger: AgentDecisionLogger):
        self._logger = logger

    def run(self, task: AgentTask, tool: AgentTool, memory: AgentMemory) -> StepResult:
        params = {**task.parameters, **memory.context}
        for attempt in range(1, task.max_retries + 2):
            start = time.perf_counter()
            try:
                result = tool.execute(**params)
                result.duration_ms = (time.perf_counter() - start) * 1000
            except Exception as exc:
                result = ToolResult(success=False, error=str(exc))

            if result.success:
                task.status = TaskStatus.COMPLETED
                memory.set(task.name, result.output)
                return StepResult(
                    task_id=task.id,
                    task_name=task.name,
                    tool_name=tool.name,
                    result=result,
                    reasoning=f"OK attempt {attempt}",
                    attempt=attempt,
                )
            self._logger.log("retry", f"{task.name} failed", error=result.error)

        task.status = TaskStatus.FAILED
        return StepResult(
            task_id=task.id,
            task_name=task.name,
            tool_name=tool.name,
            result=ToolResult(success=False, error="Max retries"),
            reasoning="Failed",
            attempt=task.max_retries + 1,
        )


class Evaluator(ABC):
    @abstractmethod
    def evaluate_step(
        self, task: AgentTask, step: StepResult, goal: AgentGoal, memory: AgentMemory
    ) -> EvaluationResult: ...

    @abstractmethod
    def evaluate_final(
        self, goal: AgentGoal, steps: list[StepResult], memory: AgentMemory
    ) -> EvaluationResult: ...


class AgentLoop:
    def __init__(
        self,
        agent_name: str,
        planner: BasePlanner,
        tool_selector: BaseToolSelector,
        evaluator: Evaluator,
        tools: dict[str, AgentTool],
        log_dir: str | None = None,
    ):
        self.agent_name = agent_name
        self.planner = planner
        self.tool_selector = tool_selector
        self.evaluator = evaluator
        self.tools = tools
        self._logger = AgentDecisionLogger(log_dir=log_dir)
        self.executor = Executor(self._logger)

    def run(self, goal: AgentGoal) -> AgentRunResult:
        memory = AgentMemory()
        memory.update(goal.context)
        plan = self.planner.plan(goal, memory)
        self._logger.log("plan", plan.reasoning)

        run = AgentRunResult(
            agent_name=self.agent_name,
            goal=goal.description,
            status="running",
            plan=plan,
            decisions=self._logger.decisions,
        )

        steps: list[StepResult] = []
        evaluations: list[EvaluationResult] = []
        completed: set[str] = set()

        for task in plan.tasks:
            if task.depends_on and not all(d in completed for d in task.depends_on):
                continue
            tool_name = task.tool_name or self.tool_selector.select(task, self.tools, memory)
            tool = self.tools.get(tool_name)
            step = (
                self.executor.run(task, tool, memory)
                if tool
                else StepResult(
                    task_id=task.id,
                    task_name=task.name,
                    tool_name=tool_name,
                    result=ToolResult(success=False, error="Missing tool"),
                    reasoning="Missing tool",
                )
            )
            steps.append(step)
            ev = self.evaluator.evaluate_step(task, step, goal, memory)
            evaluations.append(ev)
            if step.result.success:
                completed.add(task.id)

        final_ev = self.evaluator.evaluate_final(goal, steps, memory)
        evaluations.append(final_ev)

        failed = sum(1 for s in steps if not s.result.success)
        run.steps = steps
        run.evaluations = evaluations
        run.decisions = self._logger.decisions
        run.final_output = memory.context
        run.completed_at = datetime.now(timezone.utc)
        run.status = "completed" if failed == 0 and final_ev.passed else ("partial" if failed < len(steps) else "failed")
        self._logger.persist_run(run)
        return run
