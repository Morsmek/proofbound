from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from proofbound.core.agent import ProofboundAgent
from proofbound.core.approval_gate import ApprovalGate
from proofbound.models.action_run import ActionRun

router = APIRouter()
agent = ProofboundAgent()

from functools import wraps


def run_locked(function):
    @wraps(function)
    def wrapped(run_id, *args, **kwargs):
        try:
            agent.ledger.claim_run(run_id)
        except PermissionError as exc:
            raise HTTPException(409, str(exc))
        try:
            return function(run_id, *args, **kwargs)
        finally:
            agent.ledger.release_run(run_id)
    return wrapped


class CreateRunRequest(BaseModel):
    intent: str = Field(min_length=1, max_length=10000)
    user_id: Optional[str] = "web-user"

class ApprovalDecisionRequest(BaseModel):
    decision: str
    approver: Optional[str] = "web-user"
    reason: Optional[str] = ""

@router.post("/", response_model=ActionRun)
def create_run(req: CreateRunRequest):
    try:
        run = agent.create_run(intent=req.intent, user_id=req.user_id)
        return run
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{run_id}", response_model=ActionRun)
def get_run(run_id: str):
    run = agent.ledger.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run

@router.post("/{run_id}/decision", response_model=ActionRun)
@run_locked
def handle_decision(run_id: str, req: ApprovalDecisionRequest):
    run = agent.ledger.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
    if run.completed_at or run.approval_state.value in ("REJECTED", "CANCELLED"):
        raise HTTPException(status_code=409, detail="Run is already final")
    if req.decision.lower() == "approve":
        ApprovalGate.grant_approval(run, approver=req.approver, notes=req.reason)
        agent.ledger.save_run(run)
    elif req.decision.lower() == "reject":
        ApprovalGate.reject_approval(run, approver=req.approver, reason=req.reason or "Declined in Web UI")
        agent.ledger.save_run(run)
    else:
        raise HTTPException(status_code=400, detail="Decision must be 'approve' or 'reject'")
    
    return run

@router.post("/{run_id}/execute", response_model=ActionRun)
def execute_run(run_id: str):
    try:
        run = agent.execute_run(run_id)
        return run
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{run_id}/proposals/{proposal_id}/decision")
@run_locked
def decide_proposal(run_id: str, proposal_id: str, req: ApprovalDecisionRequest):
    run = get_run(run_id)
    proposal = next((p for p in run.memory_updates if p.proposal_id == proposal_id), None)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    if proposal.status != "PENDING":
        return run
    if req.decision == "approve":
        agent.memory.accept_proposal(proposal)
    elif req.decision == "reject":
        proposal.status = "REJECTED"
    else:
        raise HTTPException(400, "Decision must be approve or reject")
    run.add_event("memory_decided", f"Proposal {proposal_id}: {proposal.status}", payload=proposal.model_dump(mode="json"))
    agent.ledger.save_run(run)
    return run


@router.get("/{run_id}/artifacts/{artifact_id}")
def download_artifact(run_id: str, artifact_id: str):
    from fastapi.responses import Response
    run = get_run(run_id)
    artifact = next((a for a in run.artifacts if a.id == artifact_id), None)
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    return Response(artifact.content_preview or "", media_type=artifact.mime_type,
                    headers={"Content-Disposition": f'attachment; filename="{artifact.id}.txt"'})


@router.post("/{run_id}/rollback")
def rollback_files(run_id: str):
    from pathlib import Path
    from proofbound.core.policy_engine import PolicyEngine
    from proofbound.models.action_run import RollbackInfo
    agent.ledger.claim_run(run_id)
    try:
        run = get_run(run_id)
        if not run.completed_at:
            raise HTTPException(409, "Run has not completed")
        if run.rollback_or_recovery:
            return run
        writes = [s for s in run.plan_steps if s.tool_name in ("workspace_write_file", "workspace_patch_file") and s.result and "previous_content" in s.result]
        if not writes:
            raise HTTPException(400, "No reversible file writes in this run")
        token = PolicyEngine.issue_token(run.id, "rollback", ["workspace:write"])
        for step in writes:
            path = Path(step.result["file_path"])
            allowed, reason = PolicyEngine.evaluate_tool_call("workspace_write_file", {"file_path": str(path)}, token)
            if not allowed:
                raise HTTPException(403, reason)
            if not path.exists() or path.read_text() != step.result["written_content"]:
                raise HTTPException(409, "File changed since execution; rollback would overwrite newer work")
        for step in reversed(writes):
            path = Path(step.result["file_path"])
            if step.result["existed"]:
                path.write_text(step.result["previous_content"], encoding="utf-8")
            else:
                path.unlink()
        run.rollback_or_recovery = RollbackInfo(restored_artifacts=[s.result["file_path"] for s in writes])
        run.add_event("files_rolled_back", "Restored original workspace content")
        agent.ledger.save_run(run)
        return run
    finally:
        agent.ledger.release_run(run_id)
