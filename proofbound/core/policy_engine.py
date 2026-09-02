import os
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Any
from pydantic import BaseModel, Field
from proofbound.models.action_run import RiskLevel
from proofbound.config import settings

class CapabilityToken(BaseModel):
    token_id: str
    run_id: str
    worker_id: str
    granted_scopes: list[str]
    allowed_paths: list[str] = Field(default_factory=list)
    domain_allowlist: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=30))
    signature: str = ""

    def model_post_init(self, __context):
        if not self.signature:
            raw = f"{self.token_id}:{self.run_id}:{','.join(self.granted_scopes)}"
            self.signature = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def has_scope(self, scope: str) -> bool:
        if datetime.utcnow() > self.expires_at:
            return False
        return scope in self.granted_scopes or "admin:all" in self.granted_scopes

class RiskAssessment(BaseModel):
    risk_level: RiskLevel
    requires_approval: bool
    explanation: str
    identified_scopes: list[str]
    risk_factors: list[str]
    is_blocked: bool = False
    block_reason: Optional[str] = None

class PolicyEngine:
    @classmethod
    def evaluate_intent(cls, intent: str) -> RiskAssessment:
        lower = intent.lower()
        risk_factors = []
        identified_scopes = []
        
        for blocked in settings.blocked_commands:
            if blocked.lower() in lower:
                return RiskAssessment(
                    risk_level=RiskLevel.CRITICAL,
                    requires_approval=True,
                    explanation=f"CRITICAL: Intent matches blocked destructive command rule: '{blocked}'",
                    identified_scopes=["system:admin"],
                    risk_factors=["Blocked destructive pattern detected"],
                    is_blocked=True,
                    block_reason=f"Security violation: Forbidden command sequence '{blocked}'"
                )

        if any(w in lower for w in ["delete", "remove", "drop table", "truncate", "wipe", "destroy"]):
            risk_factors.append("Destructive modification detected")
            identified_scopes.append("workspace:delete")
            level = RiskLevel.CRITICAL
            req_approval = True
        elif any(w in lower for w in ["edit", "write", "modify", "patch", "create file", "update code"]):
            risk_factors.append("Local filesystem mutation")
            identified_scopes.append("workspace:write")
            identified_scopes.append("workspace:read")
            level = RiskLevel.HIGH
            req_approval = True
        elif any(w in lower for w in ["draft", "compose email", "stage commit", "queue message", "prepare post"]):
            risk_factors.append("Reversible draft staging")
            identified_scopes.append("draft:create")
            level = RiskLevel.MEDIUM
            req_approval = not settings.auto_approve_low_risk
        elif any(w in lower for w in ["browse", "search web", "read url", "research", "scrape", "lookup"]):
            risk_factors.append("External web query & data ingestion")
            identified_scopes.append("browser:read")
            level = RiskLevel.LOW
            req_approval = False
        else:
            identified_scopes.append("workspace:read")
            level = RiskLevel.LOW
            req_approval = False

        explanation = f"Evaluated as {level.value}. Identified scopes: {', '.join(identified_scopes) if identified_scopes else 'None'}. Factors: {', '.join(risk_factors) if risk_factors else 'Standard read-only operation'}."
        
        return RiskAssessment(
            risk_level=level,
            requires_approval=req_approval,
            explanation=explanation,
            identified_scopes=identified_scopes,
            risk_factors=risk_factors
        )

    @classmethod
    def evaluate_tool_call(cls, tool_name: str, parameters: dict[str, Any], token: CapabilityToken) -> tuple[bool, str]:
        if datetime.utcnow() > token.expires_at:
            return False, "Capability token expired"

        if tool_name.startswith("browser_"):
            if not token.has_scope("browser:read") and not token.has_scope("browser:write"):
                return False, f"Missing browser scope for tool {tool_name}"
            
            url = parameters.get("url", "")
            if url:
                domain = url.split("//")[-1].split("/")[0].lower()
                if token.domain_allowlist:
                    matched = any(domain == d or domain.endswith("." + d) for d in token.domain_allowlist)
                    if not matched:
                        return False, f"Domain '{domain}' is not in the authorized allowlist"

        elif tool_name.startswith("workspace_"):
            is_write = any(k in tool_name for k in ["write", "edit", "patch", "delete"])
            required_scope = "workspace:write" if is_write else "workspace:read"
            if not token.has_scope(required_scope):
                return False, f"Missing {required_scope} scope for workspace tool {tool_name}"

            path = parameters.get("file_path", "")
            if path and token.allowed_paths:
                clean_path = os.path.normcase(os.path.abspath(path))
                allowed = any(clean_path.startswith(os.path.normcase(os.path.abspath(p))) for p in token.allowed_paths)
                if not allowed:
                    return False, f"Path '{path}' is outside designated workspace sandbox"

        elif tool_name.startswith("draft_"):
            if not token.has_scope("draft:create"):
                return False, f"Missing draft:create scope for draft tool {tool_name}"

        return True, "Authorized"

    @classmethod
    def issue_token(cls, run_id: str, worker_id: str, scopes: list[str], allowed_paths: Optional[list[str]] = None) -> CapabilityToken:
        return CapabilityToken(
            token_id=f"cap-{secrets.token_hex(8)}",
            run_id=run_id,
            worker_id=worker_id,
            granted_scopes=scopes,
            allowed_paths=allowed_paths or [str(settings.workspace_root)],
            domain_allowlist=settings.domain_allowlist,
        )
