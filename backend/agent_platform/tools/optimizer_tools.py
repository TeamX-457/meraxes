"""Agent optimizer tools — evaluation, refinement, scoring using existing datasets."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent_platform.models.schemas import ToolResult

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
V1_DATASETS = PLATFORM_ROOT.parent / "v1_classic_ai" / "datasets"


def _load_test_cases(dataset: str, limit: int = 10) -> list[dict]:
    path = V1_DATASETS / f"{dataset}.json"
    if not path.is_file():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    cases: list[dict] = []
    for intent in data.get("intents", [])[:limit]:
        patterns = intent.get("patterns", [])
        if patterns:
            cases.append(
                {
                    "input": patterns[0],
                    "expected_intent": intent.get("tag"),
                    "expected_response_type": "informative",
                }
            )
    for q in data.get("suggested_customer_questions", [])[: max(0, limit - len(cases))]:
        cases.append(
            {
                "input": q,
                "expected_intent": "customer_inquiry",
                "expected_response_type": "helpful",
            }
        )
    return cases[:limit]


class DatasetLoaderTool:
    name = "dataset_loader"
    description = "Load evaluation test cases from existing v1_classic_ai datasets"

    def execute(self, **kwargs: Any) -> ToolResult:
        dataset = kwargs.get("dataset", "saas")
        limit = int(kwargs.get("test_case_limit", 8))
        cases = _load_test_cases(dataset, limit)

        return ToolResult(
            success=bool(cases),
            output={
                "dataset": dataset,
                "dataset_path": str(V1_DATASETS / f"{dataset}.json"),
                "test_cases": cases,
                "case_count": len(cases),
            },
            error=None if cases else f"Dataset not found: {dataset}",
        )


class AgentRunnerTool:
    name = "agent_runner"
    description = "Run agent against test cases with current system instructions"

    DEFAULT_INSTRUCTIONS = (
        "You are a helpful marketing and customer support agent. "
        "Answer clearly, stay on topic, and include a call-to-action when appropriate."
    )

    def execute(self, **kwargs: Any) -> ToolResult:
        loader = kwargs.get("dataset_loader") or {}
        cases = loader.get("test_cases", []) if isinstance(loader, dict) else []
        instructions = kwargs.get("system_instructions") or self.DEFAULT_INSTRUCTIONS
        agent_type = kwargs.get("agent_type", "marketing")

        outputs: list[dict] = []
        for case in cases:
            user_input = case.get("input", "")
            output_text = self._simulate_agent_response(user_input, instructions, agent_type)
            outputs.append(
                {
                    "input": user_input,
                    "output": output_text,
                    "expected_intent": case.get("expected_intent"),
                }
            )

        return ToolResult(
            success=bool(outputs),
            output={
                "run_outputs": outputs,
                "system_instructions": instructions,
                "agent_type": agent_type,
            },
        )

    def _simulate_agent_response(self, user_input: str, instructions: str, agent_type: str) -> str:
        """Rule-based agent simulation for evaluation (no external API required)."""
        lower = user_input.lower()
        if "price" in lower or "cost" in lower:
            return "Our plans start with a free tier. Visit pricing for details. [CTA: View Plans]"
        if "cancel" in lower or "refund" in lower:
            return "You can cancel anytime from Settings. Refunds follow our policy. [CTA: Contact Support]"
        if "api" in lower or "integrate" in lower:
            return "Full REST API docs are available. OAuth2 and webhooks supported. [CTA: Read Docs]"
        if agent_type == "marketing":
            return f"Thanks for your interest! {instructions[:60]}... We help you achieve your goals. [CTA: Get Started]"
        return f"Understood: '{user_input[:80]}'. How can I assist further?"


class OutputEvaluatorTool:
    name = "output_evaluator"
    description = "Score agent outputs against expected behavior"

    def execute(self, **kwargs: Any) -> ToolResult:
        runner = kwargs.get("agent_runner") or {}
        outputs = runner.get("run_outputs", []) if isinstance(runner, dict) else []

        scores: list[dict] = []
        for item in outputs:
            output = item.get("output", "")
            score = self._score_output(output, item.get("expected_intent", ""))
            scores.append({**item, "score": score, "passed": score >= 0.6})

        avg = sum(s["score"] for s in scores) / max(len(scores), 1)
        failures = [s for s in scores if not s["passed"]]

        return ToolResult(
            success=True,
            output={
                "scores": scores,
                "average_score": round(avg, 4),
                "failure_count": len(failures),
                "failures": failures[:5],
            },
        )

    def _score_output(self, output: str, expected_intent: str) -> float:
        score = 0.5
        if len(output) >= 30:
            score += 0.15
        if "[CTA:" in output or "cta" in output.lower():
            score += 0.15
        if expected_intent and expected_intent.replace("_", " ") in output.lower():
            score += 0.2
        if not re.search(r"(error|unknown|cannot)", output.lower()):
            score += 0.1
        return min(score, 1.0)


class FailureDetectorTool:
    name = "failure_detector"
    description = "Detect patterns in failed evaluations"

    def execute(self, **kwargs: Any) -> ToolResult:
        evaluation = kwargs.get("output_evaluator") or {}
        failures = evaluation.get("failures", []) if isinstance(evaluation, dict) else []
        avg = evaluation.get("average_score", 0) if isinstance(evaluation, dict) else 0

        patterns: list[str] = []
        if any("price" in f.get("input", "").lower() for f in failures):
            patterns.append("pricing_responses_weak")
        if any("api" in f.get("input", "").lower() for f in failures):
            patterns.append("technical_responses_weak")
        if avg < 0.6:
            patterns.append("overall_quality_below_threshold")
        if not failures:
            patterns.append("no_failures_detected")

        return ToolResult(
            success=True,
            output={
                "failure_patterns": patterns,
                "needs_refinement": avg < 0.75 or len(failures) > 2,
                "average_score": avg,
            },
        )


class PromptRefinerTool:
    name = "prompt_refiner"
    description = "Refine system instructions based on detected failures"

    REFINEMENTS = {
        "pricing_responses_weak": "Always include specific pricing tiers and a link to the pricing page when asked about cost.",
        "technical_responses_weak": "For API/integration questions, mention REST API, authentication, and link to documentation.",
        "overall_quality_below_threshold": "Keep responses concise (2-3 sentences), always end with a clear call-to-action.",
    }

    def execute(self, **kwargs: Any) -> ToolResult:
        detector = kwargs.get("failure_detector") or {}
        runner = kwargs.get("agent_runner") or {}
        current = runner.get("system_instructions", AgentRunnerTool.DEFAULT_INSTRUCTIONS) if isinstance(runner, dict) else AgentRunnerTool.DEFAULT_INSTRUCTIONS

        patterns = detector.get("failure_patterns", []) if isinstance(detector, dict) else []
        needs = detector.get("needs_refinement", False) if isinstance(detector, dict) else False

        if not needs:
            return ToolResult(
                success=True,
                output={"refined_instructions": current, "changes_applied": [], "refined": False},
            )

        additions = [self.REFINEMENTS[p] for p in patterns if p in self.REFINEMENTS]
        refined = current + " " + " ".join(additions)

        return ToolResult(
            success=True,
            output={
                "refined_instructions": refined.strip(),
                "changes_applied": additions,
                "refined": True,
            },
        )


class ReRunAgentTool:
    name = "agent_rerun"
    description = "Re-run agent with refined instructions"

    def execute(self, **kwargs: Any) -> ToolResult:
        refiner = kwargs.get("prompt_refiner") or {}
        loader = kwargs.get("dataset_loader") or {}

        refined = refiner.get("refined_instructions") if isinstance(refiner, dict) else None
        if not refined:
            refined = kwargs.get("system_instructions", AgentRunnerTool.DEFAULT_INSTRUCTIONS)

        runner = AgentRunnerTool()
        result = runner.execute(
            dataset_loader=loader,
            system_instructions=refined,
            agent_type=kwargs.get("agent_type", "marketing"),
        )
        if result.success:
            result.output["iteration"] = int(kwargs.get("iteration", 1)) + 1
        return result


class ScoreTrackerTool:
    name = "score_tracker"
    description = "Compare before/after scores and measure improvement"

    def execute(self, **kwargs: Any) -> ToolResult:
        before = kwargs.get("output_evaluator") or {}
        rerun = kwargs.get("agent_rerun") or {}

        before_avg = before.get("average_score", 0) if isinstance(before, dict) else 0

        # Re-evaluate rerun outputs
        if rerun and isinstance(rerun, dict) and rerun.get("run_outputs"):
            evaluator = OutputEvaluatorTool()
            after_eval = evaluator.execute(agent_runner=rerun)
            after_avg = after_eval.output.get("average_score", 0)
        else:
            after_avg = before_avg

        improvement = round(after_avg - before_avg, 4)
        return ToolResult(
            success=True,
            output={
                "score_before": before_avg,
                "score_after": after_avg,
                "improvement": improvement,
                "improved": improvement > 0,
                "target_met": after_avg >= float(kwargs.get("target_score", 0.75)),
            },
        )
