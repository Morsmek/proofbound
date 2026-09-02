from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from proofbound.core.agent import ProofboundAgent
from proofbound.core.approval_gate import ApprovalGate
from proofbound.models.action_run import ActionRun

router = APIRouter()
agent = ProofboundAgent()

class CreateRunRequest(BaseModel):
    intent: str
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
def handle_decision(run_id: str, req: ApprovalDecisionRequest):
    run = agent.ledger.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    
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
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
