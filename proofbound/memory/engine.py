import uuid
from datetime import datetime
from typing import List, Optional
from proofbound.models.memory import (
    ProvenanceFact,
    MemoryUpdateProposal,
    MemoryCategory,
    MemoryStatus,
    MemoryRevision,
)
from proofbound.memory.storage import MemoryStorage

class MemoryEngine:
    def __init__(self, storage: Optional[MemoryStorage] = None):
        self.storage = storage or MemoryStorage()

    def propose_fact(self, run_id: str, content: str, source: str, category: MemoryCategory = MemoryCategory.FACT, confidence: float = 0.9, justification: str = "") -> MemoryUpdateProposal:
        return MemoryUpdateProposal(
            proposal_id=f"prop-{uuid.uuid4().hex[:8]}",
            run_id=run_id,
            proposed_category=category,
            proposed_content=content,
            provenance_source=source,
            confidence=confidence,
            justification=justification or f"Extracted during execution of {run_id}",
            status="PENDING"
        )

    def accept_proposal(self, proposal: MemoryUpdateProposal) -> ProvenanceFact:
        proposal.status = "ACCEPTED"
        fact = ProvenanceFact(
            id=f"mem-{uuid.uuid4().hex[:8]}",
            category=proposal.proposed_category,
            content=proposal.proposed_content,
            provenance_run_id=proposal.run_id,
            provenance_source=proposal.provenance_source,
            confidence=proposal.confidence,
            status=MemoryStatus.ACCEPTED,
        )
        self.storage.save_fact(fact)
        return fact

    def edit_fact(self, fact_id: str, new_content: str, author: str = "user", reason: str = "Manual correction") -> ProvenanceFact:
        fact = self.storage.get_fact(fact_id)
        if not fact:
            raise ValueError(f"Memory fact '{fact_id}' not found")

        rev = MemoryRevision(
            revision_id=f"rev-{uuid.uuid4().hex[:8]}",
            author=author,
            previous_content=fact.content,
            reason=reason,
            timestamp=datetime.utcnow()
        )
        fact.revisions.append(rev)
        fact.content = new_content
        fact.status = MemoryStatus.EDITED
        fact.updated_at = datetime.utcnow()
        self.storage.save_fact(fact)
        return fact

    def rollback_fact(self, fact_id: str, target_revision_id: Optional[str] = None) -> ProvenanceFact:
        fact = self.storage.get_fact(fact_id)
        if not fact:
            raise ValueError(f"Memory fact '{fact_id}' not found")
        if not fact.revisions:
            raise ValueError(f"No previous revisions found for fact '{fact_id}'")

        if target_revision_id:
            matching_rev = next((r for r in fact.revisions if r.revision_id == target_revision_id), None)
            if not matching_rev:
                raise ValueError(f"Revision '{target_revision_id}' not found in fact history")
            restored_content = matching_rev.previous_content
        else:
            last_rev = fact.revisions.pop()
            restored_content = last_rev.previous_content

        fact.content = restored_content
        fact.updated_at = datetime.utcnow()
        self.storage.save_fact(fact)
        return fact

    def search_memories(self, query: str) -> List[ProvenanceFact]:
        all_facts = self.storage.list_facts()
        q = query.lower()
        return [
            f for f in all_facts
            if q in f.content.lower() or q in f.provenance_source.lower() or any(q in t.lower() for t in f.tags)
        ]
