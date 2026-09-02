from typing import Any
from proofbound.workers.base import BaseWorker, WorkerResult
from proofbound.core.policy_engine import CapabilityToken
from proofbound.workers.browser_worker import BrowserWorker
from proofbound.workers.workspace_worker import WorkspaceWorker
from proofbound.workers.draft_worker import DraftWorker

class MockWorker(BaseWorker):
    def __init__(self):
        super().__init__(name="proofbound_mock_worker")
        self.browser = BrowserWorker()
        self.workspace = WorkspaceWorker()
        self.draft = DraftWorker()

    def execute_tool(self, tool_name: str, parameters: dict[str, Any], token: CapabilityToken) -> WorkerResult:
        if tool_name.startswith("browser_"):
            return self.browser.execute_tool(tool_name, parameters, token)
        elif tool_name.startswith("workspace_"):
            return self.workspace.execute_tool(tool_name, parameters, token)
        elif tool_name.startswith("draft_"):
            return self.draft.execute_tool(tool_name, parameters, token)
        else:
            return WorkerResult(
                success=True,
                data={"mock_output": f"Executed {tool_name} with params {parameters}"},
                logs=[f"Mock execution of {tool_name}"]
            )
