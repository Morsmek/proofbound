import pytest
from proofbound.core.policy_engine import PolicyEngine, RiskLevel

def test_risk_evaluation_read_only():
    assessment = PolicyEngine.evaluate_intent("Research articles about agents")
    assert assessment.risk_level == RiskLevel.LOW
    assert not assessment.is_blocked
    assert "browser:read" in assessment.identified_scopes

def test_risk_evaluation_file_write():
    assessment = PolicyEngine.evaluate_intent("Edit and patch the configuration file")
    assert assessment.risk_level == RiskLevel.HIGH
    assert assessment.requires_approval
    assert "workspace:write" in assessment.identified_scopes

def test_destructive_command_blocking():
    assessment = PolicyEngine.evaluate_intent("rm -rf /")
    assert assessment.risk_level == RiskLevel.CRITICAL
    assert assessment.is_blocked
    assert "Security violation" in assessment.block_reason
