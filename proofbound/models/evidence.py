import hashlib
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

class Citation(BaseModel):
    id: str
    run_id: str
    source_type: Literal["web", "file", "draft", "memory", "system"] = "web"
    source_uri: str
    title: str
    snippet: str
    content_hash: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def model_post_init(self, __context):
        if not self.content_hash:
            raw = f"{self.source_uri}:{self.snippet}"
            self.content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

class Artifact(BaseModel):
    id: str
    run_id: str
    artifact_type: Literal["file", "diff", "screenshot", "draft", "report", "log"] = "file"
    name: str
    path_or_uri: str
    mime_type: str = "text/plain"
    size_bytes: int = 0
    content_preview: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DiffRecord(BaseModel):
    file_path: str
    original_hash: str
    new_hash: str
    unified_diff: str
    reversible: bool = True
    applied_at: datetime = Field(default_factory=datetime.utcnow)

class ReplaySession(BaseModel):
    run_id: str
    total_events: int
    replayed_events: int
    match_rate: float
    divergences: list[str] = Field(default_factory=list)
    is_identical: bool = True
    executed_at: datetime = Field(default_factory=datetime.utcnow)
