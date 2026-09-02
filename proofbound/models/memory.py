from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class MemoryCategory(str, Enum):
    PREFERENCE = "preference"
    FACT = "fact"
    DECISION = "decision"
    SUMMARY = "summary"
    POLICY = "policy"

class MemoryStatus(str, Enum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EDITED = "edited"
    ARCHIVED = "archived"

class MemoryRevision(BaseModel):
    revision_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    author: str = "agent"
    previous_content: str
    reason: str

class ProvenanceFact(BaseModel):
    id: str
    category: MemoryCategory
    content: str
    provenance_run_id: str
    provenance_source: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: MemoryStatus = MemoryStatus.ACCEPTED
    revisions: list[MemoryRevision] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

class MemoryUpdateProposal(BaseModel):
    proposal_id: str
    run_id: str
    fact_id: Optional[str] = None
    operation: str = "CREATE"  # CREATE, UPDATE, DELETE
    proposed_category: MemoryCategory = MemoryCategory.FACT
    proposed_content: str
    provenance_source: str
    confidence: float = 0.9
    justification: str
    status: str = "PENDING"  # PENDING, ACCEPTED, REJECTED
    created_at: datetime = Field(default_factory=datetime.utcnow)
