import os
import pytest
from proofbound.workers.workspace_worker import WorkspaceWorker
from proofbound.workers.draft_worker import DraftWorker
from proofbound.core.policy_engine import CapabilityToken

def test_workspace_diff_and_isolation():
    worker = WorkspaceWorker()
    token = CapabilityToken(
        token_id="tok-01",
        run_id="run-wk-01",
        worker_id="test",
        granted_scopes=["workspace:read", "workspace:write"],
        allowed_paths=["./workspace_sandbox"]
    )
    
    target_path = "./workspace_sandbox/unit_test.txt"
    res = worker.execute_tool("workspace_write_file", {"file_path": target_path, "content": "hello world"}, token)
    assert res.success
    assert len(res.artifacts) == 1

def test_draft_worker_reversibility():
    worker = DraftWorker()
    token = CapabilityToken(
        token_id="tok-02",
        run_id="run-dr-01",
        worker_id="test",
        granted_scopes=["draft:create"]
    )
    
    res = worker.execute_tool("draft_create_email", {"recipient": "admin@example.com", "subject": "Test", "body": "Hello"}, token)
    assert res.success
    assert res.data["status"] == "staged_reversible"
    assert len(res.artifacts) == 1
