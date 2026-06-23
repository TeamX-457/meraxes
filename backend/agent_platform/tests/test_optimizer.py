"""Agent platform tests."""

from agent_platform.models.schemas import AgentGoal
from agent_platform.optimizer_agent import AgentQualityLab


def test_optimizer_pipeline_runs():
    goal = AgentGoal(
        description="Improve marketing agent response quality",
        context={"dataset": "saas", "test_case_limit": 5, "target_score": 0.7},
    )
    run = AgentQualityLab(log_dir=None).run(goal)
    assert run.run_id
    assert len(run.steps) >= 5
    assert run.plan.reasoning
    assert run.status in ("completed", "partial", "failed")
