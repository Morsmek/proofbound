import pytest
from proofbound.memory.engine import MemoryEngine
from proofbound.models.memory import MemoryCategory

def test_memory_provenance_and_rollback():
    engine = MemoryEngine()
    
    proposal = engine.propose_fact(
        run_id="run-mem-01",
        content="Agents must link assertions to citations",
        source="https://example.com/spec",
        category=MemoryCategory.FACT,
        confidence=0.95
    )
    fact = engine.accept_proposal(proposal)
    assert fact.provenance_run_id == "run-mem-01"
    assert fact.confidence == 0.95

    edited = engine.edit_fact(fact.id, "Updated: Evidence-first agents require citations", author="reviewer")
    assert len(edited.revisions) == 1
    assert edited.revisions[0].previous_content == "Agents must link assertions to citations"

    rolled_back = engine.rollback_fact(fact.id)
    assert rolled_back.content == "Agents must link assertions to citations"
