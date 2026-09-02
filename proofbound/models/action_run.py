import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field
from proofbound.models.evidence import Citation, Artifact
from proofbound.models.memory import MemoryUpdateProposal

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ApprovalState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    AUTO_APPROVED = "AUTO_APPROVED"
    CANCELLED = "CANCELLED"

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class PlanStep(BaseModel):
    id: str
    step_index: int
    title: str
    description: str
    tool_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    estimated_risk: RiskLevel = RiskLevel.LOW
    status: StepStatus = StepStatus.PENDING
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None

class ActionEvent(BaseModel):
    id: str
    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    step_index: Optional[int] = None
    event_type: str
    severity: str = "INFO"  # INFO, WARNING, ERROR, CRITICAL
    message: str
    payload_hash: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context):
        if not self.payload_hash and self.payload:
            dumped = json.dumps(self.payload, sort_keys=True, default=str)
            self.payload_hash = hashlib.sha256(dumped.encode("utf-8")).hexdigest()[:16]

class RollbackInfo(BaseModel):
    target_step_id: Optional[str] = None
    restored_artifacts: list[str] = Field(default_factory=list)
    reverted_memories: list[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: str = "SUCCESS"
    details: str = ""

class ActionRun(BaseModel):
    """
    Canonical ActionRun contract as defined in the Brief:
    ActionRun {
      id, user_id, intent, plan_steps[], requested_scopes[],
      risk_level, approval_state, worker, inputs_hash,
      events[], artifacts[], citations[], memory_updates[],
      started_at, completed_at, rollback_or_recovery
    }
    """
    id: str
    user_id: str = "user-default"
    intent: str
    plan_steps: list[PlanStep] = Field(default_factory=list)
    requested_scopes: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    approval_state: ApprovalState = ApprovalState.PENDING
    worker: str = "proofbound_core"
    inputs_hash: str = ""
    events: list[ActionEvent] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    memory_updates: list[MemoryUpdateProposal] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    rollback_or_recovery: Optional[RollbackInfo] = None

    def model_post_init(self, __context):
        if not self.inputs_hash:
            raw = f"{self.user_id}:{self.intent}:{self.started_at.isoformat()}"
            self.inputs_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def add_event(self, event_type: str, message: str, step_index: Optional[int] = None, severity: str = "INFO", payload: Optional[dict[str, Any]] = None) -> ActionEvent:
        event = ActionEvent(
            id=f"evt-{len(self.events) + 1:04d}",
            run_id=self.id,
            step_index=step_index,
            event_type=event_type,
            severity=severity,
            message=message,
            payload=payload or {}
        )
        self.events.append(event)
        return event

    def is_completed(self) -> bool:
        return self.completed_at is not None

    def mark_completed(self):
        self.completed_at = datetime.utcnow()
