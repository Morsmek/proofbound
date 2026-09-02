from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from proofbound.memory.engine import MemoryEngine
from proofbound.models.memory import ProvenanceFact

router = APIRouter()
memory_engine = MemoryEngine()

class EditFactRequest(BaseModel):
    content: str
    author: Optional[str] = "web-user"
    reason: Optional[str] = "Web UI update"

class RollbackFactRequest(BaseModel):
    revision_id: Optional[str] = None

@router.get("/", response_model=List[ProvenanceFact])
def list_memories(search: Optional[str] = None):
    if search:
        return memory_engine.search_memories(search)
    return memory_engine.storage.list_facts()

@router.get("/{fact_id}", response_model=ProvenanceFact)
def get_fact(fact_id: str):
    fact = memory_engine.storage.get_fact(fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail=f"Fact '{fact_id}' not found")
    return fact

@router.put("/{fact_id}", response_model=ProvenanceFact)
def edit_fact(fact_id: str, req: EditFactRequest):
    try:
        return memory_engine.edit_fact(fact_id, req.content, req.author, req.reason)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{fact_id}/rollback", response_model=ProvenanceFact)
def rollback_fact(fact_id: str, req: RollbackFactRequest):
    try:
        return memory_engine.rollback_fact(fact_id, req.revision_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{fact_id}")
def delete_fact(fact_id: str):
    ok = memory_engine.storage.delete_fact(fact_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Fact '{fact_id}' not found")
    return {"success": True, "deleted_id": fact_id}
