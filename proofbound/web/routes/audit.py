from fastapi import APIRouter, HTTPException, Response
from typing import List, Dict, Any
from proofbound.core.ledger import ActionLedger
from proofbound.models.evidence import ReplaySession

router = APIRouter()
ledger = ActionLedger()

@router.get("/", response_model=List[Dict[str, Any]])
def list_audit_runs(limit: int = 50):
    return ledger.list_runs(limit=limit)

@router.get("/{run_id}/replay", response_model=ReplaySession)
def replay_run(run_id: str):
    try:
        return ledger.replay_run(run_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{run_id}/export/markdown")
def export_markdown(run_id: str):
    md = ledger.export_markdown(run_id)
    return Response(content=md, media_type="text/markdown")

@router.get("/{run_id}/export/json")
def export_json(run_id: str):
    run = ledger.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return run.model_dump()
