from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel, Field
from proofbound.core.policy_engine import CapabilityToken
from proofbound.models.evidence import Citation, Artifact

class WorkerResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)

class BaseWorker(ABC):
    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def execute_tool(self, tool_name: str, parameters: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        pass
