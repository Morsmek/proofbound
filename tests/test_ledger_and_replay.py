import pytest
from proofbound.core.agent import ProofboundAgent

def test_ledger_deterministic_replay():
    agent = ProofboundAgent()
    run = agent.create_run("Research deterministic audit logging")
    completed = agent.execute_run(run.id)

    replay = agent.ledger.replay_run(completed.id)
    assert replay.is_identical
    assert replay.match_rate == 1.0
    assert len(replay.divergences) == 0

def test_audit_markdown_export():
    agent = ProofboundAgent()
    run = agent.create_run("Research markdown exports")
    completed = agent.execute_run(run.id)

    md = agent.ledger.export_markdown(completed.id)
    assert "# Proofbound Verifiable Action Ledger Report" in md
    assert completed.id in md
    assert completed.inputs_hash in md
