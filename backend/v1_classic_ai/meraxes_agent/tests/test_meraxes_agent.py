"""Tests for Meraxes v1 quality lab."""

import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V1_ROOT))

from meraxes_agent.models.schemas import AgentGoal
from meraxes_agent.optimizer_agent import MeraxesQualityLab


def test_meraxes_optimizer_runs():
    goal = AgentGoal(
        description="Improve Meraxes SaaS bot accuracy",
        context={"dataset": "saas", "test_case_limit": 4, "target_score": 0.5, "quick_train": True},
    )
    run = MeraxesQualityLab(log_dir=None).run(goal)
    assert run.run_id.startswith("meraxes_")
    assert run.agent_name == "meraxes_v1_quality_lab"
    assert len(run.steps) >= 10
    assert run.final_output.get("user_summary")
    assert run.final_output.get("product") == "Meraxes v1"
    assert run.status == "completed", f"Expected completed, got {run.status}. Steps: {[(s.task_name, s.result.success) for s in run.steps]}"
