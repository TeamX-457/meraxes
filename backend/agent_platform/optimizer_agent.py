"""
Nova Agent Quality Lab — Track 2 optimization engine.

Quality engineering pipeline for stress-testing and refining existing agents.
NOT a build agent — NOT shared with Gaxtron or Ad Studio.

Optimizer team owned.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent_platform.models.schemas import (
    AgentDecisionLog,
    AgentGoal,
    AgentPlan,
    AgentRunResult,
    AgentTask,
    EvaluationResult,
    StepResult,
    ToolResult,
)
from agent_platform.tools.optimizer_tools import (
    AgentRunnerTool,
    DatasetLoaderTool,
    FailureDetectorTool,
    OutputEvaluatorTool,
    PromptRefinerTool,
    ReRunAgentTool,
    ScoreTrackerTool,
)

logger = logging.getLogger("nova.quality_lab")


@dataclass
class OptimizationCycle:
    """Track 2 quality cycle — distinct from build-track agent loops."""

    cycle_id: str
    baseline_score: float = 0.0
    stress_failures: list[dict] = field(default_factory=list)
    refined_instructions: str = ""
    post_refine_score: float = 0.0
    improvement: float = 0.0
    audit_trail: list[AgentDecisionLog] = field(default_factory=list)

    def record(self, phase: str, message: str, **data: Any) -> None:
        self.audit_trail.append(AgentDecisionLog(phase=phase, message=message, data=data))
        logger.info("[NOVA_QA:%s] %s", phase, message)


class AgentQualityLab:
    """
    Track 2: Optimize (Existing Agents).

    Rigorous quality engineering:
    baseline → stress test → score → detect failures → refine → regression → measure improvement
    """

    AGENT_NAME = "nova_agent_quality_lab"
    TRACK = "Track 2 — Optimize (Existing Agents)"

    def __init__(self, log_dir: str | None = None):
        self._log_dir = log_dir
        self._dataset_loader = DatasetLoaderTool()
        self._runner = AgentRunnerTool()
        self._evaluator = OutputEvaluatorTool()
        self._failure_detector = FailureDetectorTool()
        self._refiner = PromptRefinerTool()
        self._rerunner = ReRunAgentTool()
        self._scorer = ScoreTrackerTool()

    def run(self, goal: AgentGoal) -> AgentRunResult:
        run_id = f"nova_{uuid.uuid4().hex[:12]}"
        started = datetime.now(timezone.utc)
        cycle = OptimizationCycle(cycle_id=run_id)
        ctx = dict(goal.context)
        steps: list[StepResult] = []

        def _step(name: str, tool_name: str, result: ToolResult, reasoning: str) -> None:
            steps.append(
                StepResult(
                    task_id=name,
                    task_name=name,
                    tool_name=tool_name,
                    result=result,
                    reasoning=reasoning,
                )
            )

        # Phase 1: Load benchmark suite from existing datasets
        cycle.record("benchmark_load", "Loading test cases from existing datasets")
        load_result = self._dataset_loader.execute(**ctx)
        _step("benchmark_load", "dataset_loader", load_result, "Load existing v1 datasets")
        if not load_result.success:
            return self._build_run(run_id, goal, steps, cycle, started, "failed")

        ctx["dataset_loader"] = load_result.output

        # Phase 2: Baseline run — stress test existing agent behavior
        cycle.record("stress_test", "Running baseline agent against test cases")
        baseline_result = self._runner.execute(**ctx)
        _step("baseline_run", "agent_runner", baseline_result, "Baseline stress test")
        ctx["agent_runner"] = baseline_result.output

        # Phase 3: Score baseline outputs
        cycle.record("score_baseline", "Scoring baseline agent outputs")
        eval_result = self._evaluator.execute(agent_runner=baseline_result.output)
        _step("score_baseline", "output_evaluator", eval_result, "Baseline quality score")
        ctx["output_evaluator"] = eval_result.output
        cycle.baseline_score = eval_result.output.get("average_score", 0)

        # Phase 4: Detect failure patterns (edge cases)
        cycle.record("failure_analysis", "Detecting edge-case failure patterns")
        fail_result = self._failure_detector.execute(output_evaluator=eval_result.output)
        _step("failure_analysis", "failure_detector", fail_result, "Edge-case failure detection")
        ctx["failure_detector"] = fail_result.output
        cycle.stress_failures = eval_result.output.get("failures", [])

        # Phase 5: Programmatically refine system instructions
        cycle.record("instruction_refine", "Refining system instructions based on failures")
        refine_result = self._refiner.execute(
            failure_detector=fail_result.output,
            agent_runner=baseline_result.output,
        )
        _step("instruction_refine", "prompt_refiner", refine_result, "Programmatic instruction refinement")
        ctx["prompt_refiner"] = refine_result.output
        cycle.refined_instructions = refine_result.output.get("refined_instructions", "")

        # Phase 6: Regression re-run with refined instructions
        cycle.record("regression_test", "Re-running agent with refined instructions")
        rerun_result = self._rerunner.execute(
            prompt_refiner=refine_result.output,
            dataset_loader=load_result.output,
            agent_type=ctx.get("agent_type", "marketing"),
            iteration=ctx.get("iteration", 0),
        )
        _step("regression_test", "agent_rerun", rerun_result, "Regression test after refinement")
        ctx["agent_rerun"] = rerun_result.output

        # Phase 7: Measure score improvement
        cycle.record("score_delta", "Measuring before/after score improvement")
        score_result = self._scorer.execute(
            output_evaluator=eval_result.output,
            agent_rerun=rerun_result.output,
            target_score=ctx.get("target_score", 0.75),
        )
        _step("score_delta", "score_tracker", score_result, "Score improvement measurement")
        cycle.post_refine_score = score_result.output.get("score_after", 0)
        cycle.improvement = score_result.output.get("improvement", 0)

        improved = score_result.output.get("improved", False)
        status = "completed" if improved or cycle.post_refine_score >= ctx.get("target_score", 0.75) else "partial"

        return self._build_run(run_id, goal, steps, cycle, started, status, score_result.output)

    def _build_run(
        self,
        run_id: str,
        goal: AgentGoal,
        steps: list[StepResult],
        cycle: OptimizationCycle,
        started: datetime,
        status: str,
        score_output: dict | None = None,
    ) -> AgentRunResult:
        score_output = score_output or {}
        final_score = score_output.get("score_after", cycle.baseline_score)

        run = AgentRunResult(
            run_id=run_id,
            agent_name=self.AGENT_NAME,
            goal=goal.description,
            status=status,
            plan=AgentPlan(
                goal=goal.description,
                tasks=[
                    AgentTask(name="benchmark_load", description="Load datasets", tool_name="dataset_loader"),
                    AgentTask(name="baseline_run", description="Stress test", tool_name="agent_runner"),
                    AgentTask(name="score_baseline", description="Score outputs", tool_name="output_evaluator"),
                    AgentTask(name="failure_analysis", description="Detect failures", tool_name="failure_detector"),
                    AgentTask(name="instruction_refine", description="Refine instructions", tool_name="prompt_refiner"),
                    AgentTask(name="regression_test", description="Regression re-run", tool_name="agent_rerun"),
                    AgentTask(name="score_delta", description="Measure improvement", tool_name="score_tracker"),
                ],
                reasoning=f"Nova quality lab optimization cycle ({self.TRACK})",
            ),
            steps=steps,
            evaluations=[
                EvaluationResult(
                    passed=status == "completed",
                    score=final_score,
                    feedback=f"Baseline: {cycle.baseline_score:.2f} → After: {cycle.post_refine_score:.2f} (Δ{cycle.improvement:+.2f})",
                )
            ],
            decisions=cycle.audit_trail,
            final_output={
                "track": self.TRACK,
                "baseline_score": cycle.baseline_score,
                "post_refine_score": cycle.post_refine_score,
                "improvement": cycle.improvement,
                "refined_instructions": cycle.refined_instructions,
                "stress_failures": cycle.stress_failures,
                "score_tracker": score_output,
            },
            started_at=started,
            completed_at=datetime.now(timezone.utc),
        )

        if self._log_dir:
            from pathlib import Path
            Path(self._log_dir).mkdir(parents=True, exist_ok=True)
            Path(self._log_dir, f"{run_id}.json").write_text(
                json.dumps(run.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
            )

        return run


# Backward-compatible alias
AgentOptimizer = AgentQualityLab
