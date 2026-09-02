import pytest
from proofbound.models.action_run import ActionRun, PlanStep, RiskLevel, ApprovalState

def test_action_run_lifecycle():
    run = ActionRun(
        id="run-test-01",
        intent="Research evidence architectures",
        risk_level=RiskLevel.LOW,
        approval_state=ApprovalState.PENDING
    )
    assert run.inputs_hash != ""
    assert len(run.events) == 0

    event = run.add_event(event_type="test_event", message="Testing event pipeline", payload={"key": "val"})
    assert len(run.events) == 1
    assert event.payload_hash != ""
    assert not run.is_completed()

    run.mark_completed()
    assert run.is_completed()
    assert run.completed_at is not None
