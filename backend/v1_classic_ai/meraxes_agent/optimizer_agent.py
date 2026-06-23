"""
Meraxes Quality Lab — Track 2 production agent.

Pipeline: parse goal → research → build intents → deploy → train → benchmark →
          evaluate → detect failures → retrain → regression → score → user summary
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from meraxes_agent.models.schemas import (
    AgentDecisionLog,
    AgentGoal,
    AgentPlan,
    AgentRunResult,
    AgentTask,
    EvaluationResult,
    StepResult,
    ToolResult,
)
from meraxes_agent.tools.meraxes_tools import (
    MeraxesAgentRunnerTool,
    MeraxesDatasetLoaderTool,
    MeraxesFailureDetectorTool,
    MeraxesOutputEvaluatorTool,
    MeraxesRetrainTool,
    MeraxesScoreTrackerTool,
    MeraxesTrainTool,
)
from meraxes_agent.tools.research_tools import (
    MeraxesGoalParserTool,
    MeraxesIntentBuilderTool,
    MeraxesIntentDeployTool,
    MeraxesResearchTool,
    MeraxesUserSummaryTool,
)

V1_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = V1_ROOT / "models" / "meraxes"

logger = logging.getLogger("meraxes.quality_lab")


@dataclass
class MeraxesOptimizationCycle:
    cycle_id: str
    dataset: str = "saas"
    baseline_score: float = 0.0
    post_refine_score: float = 0.0
    improvement: float = 0.0
    audit_trail: list[AgentDecisionLog] = field(default_factory=list)
    progress_cb: Any = None

    def record(self, phase: str, message: str, **data: Any) -> None:
        self.audit_trail.append(AgentDecisionLog(phase=phase, message=message, data=data))
        logger.info("[MERAXES:%s] %s", phase, message)
        if self.progress_cb:
            try:
                self.progress_cb(phase, message, len(self.audit_trail))
            except Exception:
                pass


class MeraxesQualityLab:
    """Track 2 agent — research, intent expansion, and quality optimization."""

    AGENT_NAME = "meraxes_v1_quality_lab"
    TRACK = "Track 2 — Optimize (Existing Agents)"

    def __init__(self, log_dir: str | None = None):
        self._log_dir = log_dir or str(V1_ROOT / "models" / "meraxes" / "logs")
        self._parser = MeraxesGoalParserTool()
        self._research = MeraxesResearchTool()
        self._intent_builder = MeraxesIntentBuilderTool()
        self._intent_deploy = MeraxesIntentDeployTool()
        self._train = MeraxesTrainTool()
        self._loader = MeraxesDatasetLoaderTool()
        self._runner = MeraxesAgentRunnerTool()
        self._evaluator = MeraxesOutputEvaluatorTool()
        self._detector = MeraxesFailureDetectorTool()
        self._retrainer = MeraxesRetrainTool()
        self._scorer = MeraxesScoreTrackerTool()
        self._summary = MeraxesUserSummaryTool()

    def run(self, goal: AgentGoal) -> AgentRunResult:
        run_id = f"meraxes_{uuid.uuid4().hex[:12]}"
        started = datetime.now(timezone.utc)
        cycle = MeraxesOptimizationCycle(cycle_id=run_id, dataset=goal.context.get("dataset", "saas"))
        cycle.progress_cb = goal.context.get("progress_cb")
        ctx = dict(goal.context)
        ctx["goal"] = goal.description
        ctx["goal_description"] = goal.description
        ctx["enable_research"] = ctx.get("enable_research", True)
        steps: list[StepResult] = []

        def _step(name: str, tool: str, result: ToolResult, reasoning: str) -> None:
            steps.append(StepResult(task_id=name, task_name=name, tool_name=tool, result=result, reasoning=reasoning))

        # ── Phase A: Understand user goal ─────────────────────────────────────
        cycle.record("parse", "Understanding your request")
        parse_result = self._parser.execute(**ctx)
        _step("goal_parse", "meraxes_goal_parser", parse_result, "Parse goal into topics and actions")
        ctx["meraxes_goal_parser"] = parse_result.output
        cycle.dataset = parse_result.output.get("dataset", cycle.dataset)
        ctx["dataset"] = cycle.dataset

        # ── Phase B: Research ─────────────────────────────────────────────────
        cycle.record("research", "Researching topics for accurate bot answers")
        research_result = self._research.execute(**ctx)
        _step("research", "meraxes_researcher", research_result, "Web & knowledge research")
        ctx["meraxes_researcher"] = research_result.output

        # ── Phase C: Build & deploy new intents ───────────────────────────────
        cycle.record("intents", "Building new conversation topics from your goal")
        build_result = self._intent_builder.execute(**ctx)
        _step("intent_build", "meraxes_intent_builder", build_result, "Generate intent definitions")
        ctx["meraxes_intent_builder"] = build_result.output

        cycle.record("deploy", "Training bot with new topics")
        deploy_result = self._intent_deploy.execute(**ctx)
        _step("intent_deploy", "meraxes_intent_deployer", deploy_result, "Merge intents and retrain model")
        ctx["meraxes_intent_deployer"] = deploy_result.output

        extra_cases = []
        for intent in build_result.output.get("intents") or []:
            for pattern in intent.get("patterns", [])[:2]:
                extra_cases.append({"input": pattern, "expected_intent": intent.get("tag")})
        ctx["extra_test_cases"] = extra_cases

        # ── Phase D: Quality cycle ────────────────────────────────────────────
        cycle.record("train", f"Ensuring Meraxes model for {cycle.dataset}")
        train_result = self._train.execute(
            dataset=cycle.dataset,
            minimal=ctx.get("minimal_train", True),
            quick_train=ctx.get("quick_train", False),
            force_retrain=deploy_result.output.get("deployed", False),
        )
        if not train_result.success and not (MODELS_DIR / cycle.dataset / "chat_model.pth").is_file():
            train_result = self._train.execute(dataset=cycle.dataset, minimal=True)
        _step("meraxes_train", "meraxes_trainer", train_result, "Train v1 model")

        cycle.record("benchmark", "Loading test conversations")
        load_result = self._loader.execute(**ctx)
        _step("benchmark_load", "meraxes_dataset_loader", load_result, "Load benchmark cases")
        ctx["dataset_loader"] = load_result.output

        cycle.record("baseline", "Testing bot before final tuning")
        baseline = self._runner.execute(**ctx)
        _step("baseline_run", "meraxes_runner", baseline, "Baseline inference")
        ctx["meraxes_runner"] = baseline.output

        cycle.record("evaluate", "Reviewing answer quality")
        eval_result = self._evaluator.execute(meraxes_runner=baseline.output)
        _step("score_baseline", "meraxes_evaluator", eval_result, "Baseline quality score")
        cycle.baseline_score = eval_result.output.get("average_score", 0)
        ctx["meraxes_evaluator"] = eval_result.output

        cycle.record("failures", "Finding weak answers")
        fail_result = self._detector.execute(meraxes_evaluator=eval_result.output)
        _step("failure_analysis", "meraxes_failure_detector", fail_result, "Failure detection")
        ctx["meraxes_failure_detector"] = fail_result.output

        cycle.record("retrain", "Fine-tuning from weak spots")
        retrain_result = self._retrainer.execute(**ctx)
        _step("meraxes_retrain", "meraxes_retrainer", retrain_result, "Retrain with corrections")
        refinement_qa = retrain_result.output.get("refinement_qa", [])
        ctx["refinement_qa"] = refinement_qa
        ctx["custom_qa"] = refinement_qa

        cycle.record("regression", "Re-testing after tuning")
        rerun = self._runner.execute(**ctx)
        _step("regression_run", "meraxes_runner", rerun, "Post-tune inference")
        ctx["meraxes_rerun"] = rerun.output

        cycle.record("score_delta", "Measuring improvement")
        score_result = self._scorer.execute(
            meraxes_evaluator=eval_result.output,
            meraxes_rerun=rerun.output,
            target_score=ctx.get("target_score", 0.7),
        )
        _step("score_delta", "meraxes_score_tracker", score_result, "Score delta")
        cycle.post_refine_score = score_result.output.get("score_after", 0)
        cycle.improvement = score_result.output.get("improvement", 0)
        ctx["meraxes_score_tracker"] = score_result.output

        summary_result = self._summary.execute(**ctx)
        _step("user_summary", "meraxes_user_summary", summary_result, "Plain-language summary")

        all_steps_ok = all(s.result.success for s in steps)
        status = "completed" if all_steps_ok else "failed"
        user_summary = summary_result.output

        run = AgentRunResult(
            run_id=run_id,
            agent_name=self.AGENT_NAME,
            goal=goal.description,
            status=status,
            plan=AgentPlan(
                goal=goal.description,
                tasks=[
                    AgentTask(name="goal_parse", description="Parse user goal", tool_name="meraxes_goal_parser"),
                    AgentTask(name="research", description="Research topics", tool_name="meraxes_researcher"),
                    AgentTask(name="intent_build", description="Build intents", tool_name="meraxes_intent_builder"),
                    AgentTask(name="intent_deploy", description="Deploy & train", tool_name="meraxes_intent_deployer"),
                    AgentTask(name="meraxes_train", description="Ensure model", tool_name="meraxes_trainer"),
                    AgentTask(name="benchmark_load", description="Load tests", tool_name="meraxes_dataset_loader"),
                    AgentTask(name="baseline_run", description="Baseline test", tool_name="meraxes_runner"),
                    AgentTask(name="score_baseline", description="Score", tool_name="meraxes_evaluator"),
                    AgentTask(name="failure_analysis", description="Find failures", tool_name="meraxes_failure_detector"),
                    AgentTask(name="meraxes_retrain", description="Fine-tune", tool_name="meraxes_retrainer"),
                    AgentTask(name="regression_run", description="Re-test", tool_name="meraxes_runner"),
                    AgentTask(name="score_delta", description="Measure delta", tool_name="meraxes_score_tracker"),
                ],
                reasoning=f"Meraxes production agent: research → intents → optimize ({self.TRACK})",
            ),
            steps=steps,
            evaluations=[
                EvaluationResult(
                    passed=status == "completed",
                    score=cycle.post_refine_score,
                    feedback=f"Baseline {cycle.baseline_score:.2f} → {cycle.post_refine_score:.2f} (Δ{cycle.improvement:+.2f})",
                )
            ],
            decisions=cycle.audit_trail,
            final_output={
                "track": self.TRACK,
                "product": "Meraxes v1",
                "dataset": cycle.dataset,
                "baseline_score": cycle.baseline_score,
                "post_refine_score": cycle.post_refine_score,
                "improvement": cycle.improvement,
                "custom_qa_added": refinement_qa,
                "intents_added": deploy_result.output.get("added_tags", []),
                "research_brief": research_result.output.get("brief", ""),
                "research_sources": research_result.output.get("sources", []),
                "user_summary": user_summary,
                "model_dir": str(V1_ROOT / "models" / "meraxes" / cycle.dataset),
            },
            started_at=started,
            completed_at=datetime.now(timezone.utc),
        )

        if self._log_dir:
            log_path = Path(self._log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            (log_path / f"{run_id}.json").write_text(
                json.dumps(run.model_dump(mode="json"), indent=2, default=str), encoding="utf-8"
            )

        return run
