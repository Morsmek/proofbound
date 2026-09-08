import os
import re
import json
import uuid
import httpx
from typing import Optional, List, Dict, Any
from proofbound.config import settings
from pathlib import Path
from proofbound.workers.base import WorkerResult
from proofbound.models.action_run import (
    ActionRun,
    PlanStep,
    RiskLevel,
    ApprovalState,
    StepStatus,
)
from proofbound.core.policy_engine import PolicyEngine, CapabilityToken
from proofbound.core.approval_gate import ApprovalGate
from proofbound.core.ledger import ActionLedger
from proofbound.memory.engine import MemoryEngine
from proofbound.workers.browser_worker import BrowserWorker
from proofbound.workers.workspace_worker import WorkspaceWorker
from proofbound.workers.draft_worker import DraftWorker

class ProofboundAgent:
    def __init__(
        self,
        ledger: Optional[ActionLedger] = None,
        memory: Optional[MemoryEngine] = None,
        workspace_root: Optional[Path] = None,
        browser_transport=None,
    ):
        self.ledger = ledger or ActionLedger()
        self.memory = memory or MemoryEngine()
        
        self.workspace_root = (workspace_root or settings.workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.browser_worker = BrowserWorker(transport=browser_transport)
        self.workspace_worker = WorkspaceWorker()
        self.draft_worker = DraftWorker()

    def create_run(self, intent: str, user_id: str = "user-default") -> ActionRun:
        if not intent.strip():
            raise ValueError("Intent must not be empty")
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        assessment = PolicyEngine.evaluate_intent(intent)
        plan_steps = self._formulate_plan(run_id, intent, assessment)
        if not assessment.is_blocked:
            scopes = set(assessment.identified_scopes)
            ranks = list(RiskLevel)
            for step in plan_steps:
                prefix = step.tool_name.split("_")[0]
                scope = {"browser": "browser:read", "draft": "draft:create", "workspace": "workspace:read"}.get(prefix)
                if scope:
                    scopes.add(scope)
                if step.tool_name in ("workspace_write_file", "workspace_patch_file"):
                    scopes.add("workspace:write")
                if ranks.index(step.estimated_risk) > ranks.index(assessment.risk_level):
                    assessment.risk_level = step.estimated_risk
            assessment.identified_scopes = sorted(scopes)

        run = ActionRun(
            id=run_id,
            user_id=user_id,
            intent=intent,
            plan_steps=plan_steps,
            requested_scopes=assessment.identified_scopes,
            risk_level=assessment.risk_level,
            approval_state=ApprovalState.PENDING,
            worker="proofbound_core"
        )

        run.add_event(
            event_type="intent_received",
            message=f"Received intent: '{intent}'",
            severity="INFO",
            payload={"intent": intent, "user_id": user_id}
        )

        run.add_event(
            event_type="risk_assessed",
            message=assessment.explanation,
            severity="WARNING" if assessment.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL] else "INFO",
            payload=assessment.model_dump(mode="json")
        )

        if assessment.is_blocked:
            run.approval_state = ApprovalState.REJECTED
            run.mark_completed()
            run.add_event(
                event_type="execution_blocked",
                message=f"Execution blocked by Policy Engine: {assessment.block_reason}",
                severity="CRITICAL",
                payload={"reason": assessment.block_reason}
            )
            self.ledger.save_run(run)
            return run

        ApprovalGate.process_initial_approval(run)
        self.ledger.save_run(run)
        return run

    def _formulate_plan(self, run_id: str, intent: str, assessment: Any) -> List[PlanStep]:
        lower = intent.lower()
        steps = []
        
        # Extract explicit URLs if present
        urls = [u.rstrip(".,;)") for u in re.findall(r'https?://[^\s]+', intent)]
        url_match = re.search(r'https?://[^\s]+', intent)
        extracted_url = url_match.group(0) if url_match else ""

        # Extract target file paths if present
        file_match = re.search(r'[\w\-./]+\.(?:txt|json|md|py|js|yaml|toml|html|css)', intent)
        target_file = file_match.group(0) if file_match else str(self.workspace_root / "config.txt")
        if not Path(target_file).is_absolute():
            path = Path(target_file)
            if path.parts and path.parts[0] == "workspace_sandbox":
                path = Path(*path.parts[1:])
            target_file = str(self.workspace_root / path)

        if "workspace:delete" in assessment.identified_scopes:
            return [PlanStep(id="step-1", step_index=1, title="Unsupported destructive operation", description="Deletion is not implemented", tool_name="unsupported_delete", estimated_risk=RiskLevel.CRITICAL)]

        if "draft" in lower or "compose email" in lower or ("email" in lower and "research" not in lower) or "queue message" in lower:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', intent)
            recipient = email_match.group(0) if email_match else ""
            body_match = re.search(r"body\s*:\s*(.*)$", intent, re.IGNORECASE | re.DOTALL)
            
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Stage Non-Destructive Reversible Draft for {recipient}",
                description="Compose email/message body and stage without triggering direct transmission.",
                tool_name="draft_create_email",
                parameters={
                    "recipient": recipient,
                    "subject": f"Operational Brief: {intent[:30]}",
                    "body": body_match.group(1) if body_match else f"Proposed draft content generated for:\n\n'{intent}'\n\nPrepared under Proofbound Policy Gate."
                },
                estimated_risk=RiskLevel.MEDIUM
            ))

        elif "create file" in lower or "patch" in lower or "edit file" in lower or "write file" in lower or "modify file" in lower or ("patch" in lower and "file" in lower):
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Search Workspace Files for {os.path.basename(target_file)}",
                description="Locate target file in sandboxed workspace directory.",
                tool_name="workspace_search",
                parameters={"pattern": os.path.basename(target_file)},
                estimated_risk=RiskLevel.LOW
            ))
            literal = re.search(r'content\s*:\s*(.*)$', intent, flags=re.IGNORECASE | re.DOTALL)
            replacement = re.search(r'replace\s+"([^"\n]*)"\s+with\s+"([^"\n]*)"', intent, flags=re.IGNORECASE)
            changes = {"content": literal.group(1)} if literal else ({"old": replacement.group(1), "new": replacement.group(2)} if replacement else {})
            steps.append(PlanStep(
                id="step-2",
                step_index=2,
                title=f"Apply Unified File Patch to {os.path.basename(target_file)}",
                description="Write modifications to target file and record diff for rollback.",
                tool_name="workspace_write_file",
                parameters={
                    "file_path": target_file,
                    **changes
                },
                estimated_risk=RiskLevel.HIGH
            ))

        elif "read file" in lower:
            steps.append(PlanStep(id="step-1", step_index=1, title=f"Read {os.path.basename(target_file)}", description="Read a text file inside the workspace", tool_name="workspace_read_file", parameters={"file_path": target_file}))

        elif "workspace" in lower or "find file" in lower or ("search" in lower and "file" in lower):
            search_pattern = os.path.basename(file_match.group(0)) if file_match else (intent.split()[-1] if intent.split() else "config")
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Search Workspace for '{search_pattern}'",
                description="Locate target file in sandboxed workspace directory.",
                tool_name="workspace_search",
                parameters={"pattern": search_pattern},
                estimated_risk=RiskLevel.LOW
            ))

        elif "research" in lower or "browse" in lower or "search" in lower or "web" in lower or extracted_url:
            query_topic = re.sub(r'^(research|browse|search|lookup|find)\s+', '', intent, flags=re.IGNORECASE).strip()
            if not urls:
                return [PlanStep(id="step-1", step_index=1, title="Source URL required", description="Provide one or more allowed HTTP(S) source URLs for research", tool_name="unsupported_research_without_url")]
            target_url = urls[0]
            
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Perform Evidence-Based Web Research: {query_topic[:40]}",
                description="Query authorized domains and extract source citations.",
                tool_name="browser_research",
                parameters={"query": query_topic, "url": target_url},
                estimated_risk=RiskLevel.LOW
            ))
            for index, url in enumerate(urls[1:], start=2):
                steps.append(PlanStep(id=f"step-{index}", step_index=index, title=f"Read source {url}", description="Capture source excerpt", tool_name="browser_research", parameters={"url": url, "query": query_topic}))
            steps.append(PlanStep(
                id=f"step-{len(steps)+1}",
                step_index=len(steps)+1,
                title="Stage source-linked memory proposal",
                description="Offer an inspected source excerpt for memory acceptance.",
                tool_name="memory_propose",
                parameters={"topic": query_topic},
                estimated_risk=RiskLevel.LOW
            ))

        else:
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title="Unsupported operation",
                description="Supported tasks: source URL research, workspace file search, literal file edits, and email drafts.",
                tool_name="unsupported_intent",
                parameters={"intent": intent},
                estimated_risk=RiskLevel.LOW
            ))

        return steps

    def execute_run(self, run_id: str) -> ActionRun:
        self.ledger.claim_run(run_id)
        try:
            return self._execute_run(run_id)
        finally:
            self.ledger.release_run(run_id)

    def _execute_run(self, run_id: str) -> ActionRun:
        run = self.ledger.get_run(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found")

        if run.completed_at and run.approval_state in [ApprovalState.APPROVED, ApprovalState.AUTO_APPROVED]:
            return run

        if run.approval_state not in [ApprovalState.APPROVED, ApprovalState.AUTO_APPROVED]:
            raise PermissionError(f"Cannot execute Run '{run_id}' in approval state '{run.approval_state.value}'. Approval required.")

        run.add_event(
            event_type="execution_started",
            message=f"Starting step-by-step execution of {len(run.plan_steps)} plan steps.",
            severity="INFO"
        )

        token = PolicyEngine.issue_token(
            run_id=run.id,
            worker_id="proofbound_core_worker",
            allowed_paths=[str(self.workspace_root)],
            scopes=run.requested_scopes
        )

        for step in run.plan_steps:
            if step.status == StepStatus.COMPLETED:
                continue

            step.status = StepStatus.RUNNING
            run.add_event(
                event_type="tool_started",
                step_index=step.step_index,
                message=f"Executing tool '{step.tool_name}' for step '{step.title}'",
                payload={"tool_name": step.tool_name, "parameters": step.parameters}
            )

            self.ledger.save_run(run)
            try:
                result = self._dispatch_tool(step.tool_name, step.parameters, token, run)
            except Exception as exc:
                result = WorkerResult(success=False, error=str(exc))

            if result.success:
                step.status = StepStatus.COMPLETED
                step.result = result.data
                
                for cit in result.citations:
                    run.citations.append(cit)
                    run.add_event(
                        event_type="citation_extracted",
                        step_index=step.step_index,
                        message=f"Captured citation: '{cit.title}' from {cit.source_uri}",
                        payload=cit.model_dump(mode="json")
                    )

                for art in result.artifacts:
                    run.artifacts.append(art)
                    run.add_event(
                        event_type="artifact_created",
                        step_index=step.step_index,
                        message=f"Created artifact: '{art.name}' ({art.artifact_type})",
                        payload=art.model_dump(mode="json")
                    )

                run.add_event(
                    event_type="tool_completed",
                    step_index=step.step_index,
                    message=f"Step {step.step_index} '{step.title}' completed successfully.",
                    payload=result.data
                )
            else:
                step.status = StepStatus.FAILED
                step.error = result.error
                run.add_event(
                    event_type="tool_failed",
                    step_index=step.step_index,
                    message=f"Step {step.step_index} failed: {result.error}",
                    severity="ERROR",
                    payload={"error": result.error}
                )
                for remaining in run.plan_steps:
                    if remaining.status == StepStatus.PENDING:
                        remaining.status = StepStatus.SKIPPED
                break

        if run.citations and not run.memory_updates:
            top_cit = run.citations[0]
            proposal = self.memory.propose_fact(
                run_id=run.id,
                content=f"Source excerpt: {top_cit.snippet}",
                source=top_cit.source_uri,
                confidence=top_cit.confidence,
                justification=f"Extracted from verified citation {top_cit.id}"
            )
            run.memory_updates.append(proposal)
            run.add_event(
                event_type="memory_proposed",
                message=f"Proposed source-linked memory update ({proposal.proposal_id}). Staged for user acceptance.",
                payload=proposal.model_dump(mode="json")
            )

        run.mark_completed()
        run.add_event(
            event_type="run_failed" if any(s.status == StepStatus.FAILED for s in run.plan_steps) else "run_completed",
            message=f"ActionRun {run.id} finished execution with {len(run.events)} verifiable audit events.",
            severity="INFO"
        )

        self.ledger.save_run(run)
        return run

    def _dispatch_tool(self, tool_name: str, parameters: dict[str, Any], token: CapabilityToken, run: ActionRun):
        if tool_name.startswith("browser_"):
            return self.browser_worker.execute_tool(tool_name, parameters, token)
        elif tool_name.startswith("workspace_"):
            return self.workspace_worker.execute_tool(tool_name, parameters, token)
        elif tool_name.startswith("draft_"):
            return self.draft_worker.execute_tool(tool_name, parameters, token)
        elif tool_name == "memory_propose":
            return WorkerResult(success=True, data={"memory_proposal_staged": True})
        else:
            message = "Provide one or more allowed HTTP(S) source URLs for research" if tool_name == "unsupported_research_without_url" else f"Unsupported operation: {run.intent}. Use source URL research, file search/read, literal file edits, or email drafts."
            return WorkerResult(success=False, error=message)
