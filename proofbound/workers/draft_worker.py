import uuid
from typing import Any
from proofbound.workers.base import BaseWorker, WorkerResult
from proofbound.core.policy_engine import CapabilityToken, PolicyEngine
from proofbound.models.evidence import Artifact

class DraftWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="reversible_draft_worker")

    def execute_tool(self, tool_name: str, parameters: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        auth_ok, reason = PolicyEngine.evaluate_tool_call(tool_name, parameters, token)
        if not auth_ok:
            return WorkerResult(success=False, error=f"Policy Block: {reason}")

        if tool_name == "draft_create_email":
            return self._create_email_draft(parameters, token)
        elif tool_name == "draft_stage_commit":
            return self._stage_commit(parameters, token)
        else:
            return WorkerResult(success=False, error=f"Unknown draft tool '{tool_name}'")

    def _create_email_draft(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        recipient = params.get("recipient", "team@example.com")
        subject = params.get("subject", "Automated Ops Brief")
        body = params.get("body", "")

        art = Artifact(
            id=f"art-{uuid.uuid4().hex[:8]}",
            run_id=token.run_id,
            artifact_type="draft",
            name=f"email_draft_{subject[:20]}.eml",
            path_or_uri=f"draft://emails/{token.run_id}",
            mime_type="message/rfc822",
            size_bytes=len(f"To: {recipient}\nSubject: {subject}\n\n{body}".encode("utf-8")),
            content_preview=f"To: {recipient}\nSubject: {subject}\n\n{body}"
        )

        return WorkerResult(
            success=True,
            data={"draft_id": art.id, "status": "staged_reversible", "recipient": recipient, "subject": subject},
            artifacts=[art],
            logs=[f"Created reversible email draft for {recipient}. Not sent."]
        )

    def _stage_commit(self, params: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        message = params.get("message", "feat: staged operational change")
        art = Artifact(
            id=f"art-{uuid.uuid4().hex[:8]}",
            run_id=token.run_id,
            artifact_type="draft",
            name="staged_git_commit.msg",
            path_or_uri=f"draft://git/{token.run_id}",
            mime_type="text/plain",
            size_bytes=len(message),
            content_preview=message
        )
        return WorkerResult(
            success=True,
            data={"status": "staged", "commit_message": message},
            artifacts=[art],
            logs=[f"Staged git commit draft: '{message}'"]
        )
