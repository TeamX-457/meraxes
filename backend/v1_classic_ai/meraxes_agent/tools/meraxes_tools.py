"""
Meraxes v1 agent tools — train, run, evaluate, and retrain real BotEngine models.

Uses existing datasets in v1_classic_ai/datasets/ (no new dataset downloads).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

V1_ROOT = Path(__file__).resolve().parents[2]
if str(V1_ROOT) not in sys.path:
    sys.path.insert(0, str(V1_ROOT))

from dataset_loader import load_template, merge_custom_qa
from engine import BotEngine, invalidate_engine
from meraxes_agent.models.schemas import ToolResult

DATASETS_DIR = V1_ROOT / "datasets"
MODELS_DIR = V1_ROOT / "models" / "meraxes"


def _meraxes_bot_id(dataset: str) -> str:
    return f"meraxes_{dataset}"


def _load_test_cases(dataset: str, limit: int = 8) -> list[dict]:
    path = DATASETS_DIR / f"{dataset}.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    cases: list[dict] = []
    for intent in data.get("intents", [])[:limit]:
        patterns = intent.get("patterns", [])
        responses = intent.get("responses", [])
        if patterns:
            cases.append({
                "input": patterns[0],
                "expected_intent": intent.get("tag"),
                "expected_answer_hint": responses[0] if responses else "",
            })
    for q in data.get("suggested_customer_questions", [])[: max(0, limit - len(cases))]:
        cases.append({"input": q, "expected_intent": "customer_inquiry", "expected_answer_hint": ""})
    return cases[:limit]


def _get_engine(dataset: str, custom_qa: list | None = None) -> BotEngine:
    bot_id = _meraxes_bot_id(dataset)
    template = load_template(dataset)
    custom_qa = custom_qa or []
    engine = BotEngine(bot_id, dataset, "hybrid", custom_qa)
    engine.intents = merge_custom_qa(template["intents"], custom_qa)
    return engine


class MeraxesTrainTool:
    name = "meraxes_trainer"
    description = "Train Meraxes v1 intent model for a business vertical"

    def execute(self, **kwargs: Any) -> ToolResult:
        dataset = kwargs.get("dataset", "saas")
        quick = bool(kwargs.get("quick_train", False))
        model_path = MODELS_DIR / dataset / "chat_model.pth"

        if model_path.is_file() and not kwargs.get("force_retrain", False):
            return ToolResult(
                success=True,
                output={
                    "dataset": dataset,
                    "bot_id": _meraxes_bot_id(dataset),
                    "model_path": str(model_path),
                    "already_trained": True,
                },
            )

        try:
            from train_meraxes import train_vertical
            stats = train_vertical(
                dataset,
                quick=quick and not kwargs.get("minimal"),
                minimal=bool(kwargs.get("minimal")),
            )
            invalidate_engine(_meraxes_bot_id(dataset))
            return ToolResult(success=True, output={"dataset": dataset, "trained": True, "stats": stats})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class MeraxesAgentRunnerTool:
    name = "meraxes_runner"
    description = "Run Meraxes v1 BotEngine against benchmark test cases"

    def execute(self, **kwargs: Any) -> ToolResult:
        loader = kwargs.get("dataset_loader") or {}
        dataset = loader.get("dataset") or kwargs.get("dataset", "saas")
        cases = loader.get("test_cases", []) if isinstance(loader, dict) else []
        custom_qa = kwargs.get("custom_qa") or kwargs.get("refinement_qa") or []

        if not cases:
            cases = _load_test_cases(dataset, int(kwargs.get("test_case_limit", 8)))

        try:
            engine = _get_engine(dataset, custom_qa=custom_qa)
            # Ensure model weights exist
            if not (MODELS_DIR / dataset / "chat_model.pth").is_file():
                from train_meraxes import train_vertical
                train_vertical(dataset, minimal=True)
                invalidate_engine(_meraxes_bot_id(dataset))
                engine = _get_engine(dataset, custom_qa=custom_qa)

            outputs: list[dict] = []
            for case in cases:
                user_input = case.get("input", "")
                result = engine.reply("benchmark_user", user_input, lambda _: None, lambda *_: None)
                outputs.append({
                    "input": user_input,
                    "output": result.get("response", ""),
                    "source": result.get("source", ""),
                    "expected_intent": case.get("expected_intent"),
                })

            return ToolResult(
                success=bool(outputs),
                output={
                    "run_outputs": outputs,
                    "dataset": dataset,
                    "bot_id": _meraxes_bot_id(dataset),
                    "custom_qa_count": len(custom_qa),
                    "agent_type": "meraxes_v1",
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class MeraxesOutputEvaluatorTool:
    name = "meraxes_evaluator"
    description = "Score Meraxes v1 responses (intent match, source quality, length)"

    def execute(self, **kwargs: Any) -> ToolResult:
        runner = kwargs.get("meraxes_runner") or kwargs.get("agent_runner") or {}
        outputs = runner.get("run_outputs", []) if isinstance(runner, dict) else []

        scores: list[dict] = []
        for item in outputs:
            output = item.get("output", "")
            source = item.get("source", "fallback")
            expected = item.get("expected_intent", "")
            score = 0.4
            if len(output) >= 20:
                score += 0.15
            if source in ("faq", "intent", "faq+intent", "rule"):
                score += 0.25
            if source == "fallback":
                score -= 0.2
            if expected and expected.replace("_", " ") in output.lower():
                score += 0.15
            if "not sure" in output.lower() or "rephrasing" in output.lower():
                score -= 0.15
            score = max(0.0, min(score, 1.0))
            scores.append({**item, "score": round(score, 4), "passed": score >= 0.55, "source": item.get("source", "")})

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


class MeraxesFailureDetectorTool:
    name = "meraxes_failure_detector"
    description = "Detect Meraxes v1 failure patterns from benchmark scores"

    def execute(self, **kwargs: Any) -> ToolResult:
        evaluation = kwargs.get("meraxes_evaluator") or kwargs.get("output_evaluator") or {}
        failures = evaluation.get("failures", []) if isinstance(evaluation, dict) else []
        avg = evaluation.get("average_score", 0) if isinstance(evaluation, dict) else 0

        patterns: list[str] = []
        if any(f.get("source") == "fallback" for f in failures):
            patterns.append("high_fallback_rate")
        if avg < 0.6:
            patterns.append("overall_quality_below_threshold")
        if len(failures) > 2:
            patterns.append("multiple_intent_misses")

        return ToolResult(
            success=True,
            output={
                "failure_patterns": patterns or ["no_failures_detected"],
                "needs_refinement": avg < 0.7 or len(failures) > 1,
                "average_score": avg,
                "failures": failures[:5],
            },
        )


class MeraxesRetrainTool:
    name = "meraxes_retrainer"
    description = "Add failed Q&A pairs as custom_qa and retrain Meraxes model"

    def execute(self, **kwargs: Any) -> ToolResult:
        detector = kwargs.get("meraxes_failure_detector") or kwargs.get("failure_detector") or {}
        dataset = kwargs.get("dataset") or (kwargs.get("dataset_loader") or {}).get("dataset", "saas")
        failures = detector.get("failures", []) if isinstance(detector, dict) else []
        needs = detector.get("needs_refinement", False) if isinstance(detector, dict) else False

        if not needs or not failures:
            return ToolResult(
                success=True,
                output={"refined": False, "custom_qa_added": [], "message": "No retraining needed"},
            )

        custom_qa = []
        for f in failures[:3]:
            question = f.get("input", "")
            if not question:
                continue
            # Generate helpful answer from template intent if possible
            hint = f.get("expected_answer_hint") or f"Thanks for asking about '{question}'. Let me help you with that."
            custom_qa.append({"question": question, "answer": hint})

        try:
            engine = _get_engine(dataset, custom_qa=custom_qa)
            stats = engine.train()
            invalidate_engine(_meraxes_bot_id(dataset))
            return ToolResult(
                success=True,
                output={
                    "refined": True,
                    "custom_qa_added": custom_qa,
                    "retrain_stats": stats,
                    "refinement_qa": custom_qa,
                    "dataset": dataset,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class MeraxesDatasetLoaderTool:
    name = "meraxes_dataset_loader"
    description = "Load Meraxes v1 benchmark cases from existing datasets"

    def execute(self, **kwargs: Any) -> ToolResult:
        dataset = kwargs.get("dataset", "saas")
        limit = int(kwargs.get("test_case_limit", 8))
        cases = _load_test_cases(dataset, limit)
        extra = kwargs.get("extra_test_cases") or []
        if isinstance(extra, list):
            for case in extra:
                if isinstance(case, dict) and case.get("input"):
                    cases.append(case)
        cases = cases[: limit + len(extra)]
        return ToolResult(
            success=bool(cases),
            output={
                "dataset": dataset,
                "dataset_path": str(DATASETS_DIR / f"{dataset}.json"),
                "test_cases": cases,
                "case_count": len(cases),
            },
            error=None if cases else f"Dataset not found: {dataset}",
        )


class MeraxesScoreTrackerTool:
    name = "meraxes_score_tracker"
    description = "Compare Meraxes scores before and after retraining"

    def execute(self, **kwargs: Any) -> ToolResult:
        before = kwargs.get("meraxes_evaluator") or kwargs.get("output_evaluator") or {}
        rerun = kwargs.get("meraxes_rerun") or kwargs.get("agent_rerun") or {}

        before_avg = before.get("average_score", 0) if isinstance(before, dict) else 0

        if rerun and isinstance(rerun, dict) and rerun.get("run_outputs"):
            after_eval = MeraxesOutputEvaluatorTool().execute(meraxes_runner=rerun)
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
                "target_met": after_avg >= float(kwargs.get("target_score", 0.7)),
            },
        )
