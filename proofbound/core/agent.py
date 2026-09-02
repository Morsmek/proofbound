import os
import re
import json
import uuid
import httpx
from typing import Optional, List, Dict, Any
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
from proofbound.workers.mock_worker import MockWorker

class ProofboundAgent:
    def __init__(
        self,
        ledger: Optional[ActionLedger] = None,
        memory: Optional[MemoryEngine] = None,
    ):
        self.ledger = ledger or ActionLedger()
        self.memory = memory or MemoryEngine()
        
        self.browser_worker = BrowserWorker()
        self.workspace_worker = WorkspaceWorker()
        self.draft_worker = DraftWorker()
        self.mock_worker = MockWorker()

    def create_run(self, intent: str, user_id: str = "user-default") -> ActionRun:
        run_id = f"run-{uuid.uuid4().hex[:10]}"
        assessment = PolicyEngine.evaluate_intent(intent)
        plan_steps = self._formulate_plan(run_id, intent, assessment)

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
            payload=assessment.model_dump()
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
        url_match = re.search(r'https?://[^\s]+', intent)
        extracted_url = url_match.group(0) if url_match else ""

        # Extract target file paths if present
        file_match = re.search(r'[\w\-./]+\.(?:txt|json|md|py|js|yaml|toml|html|css)', intent)
        target_file = file_match.group(0) if file_match else "./workspace_sandbox/config.txt"

        if "draft" in lower or "compose email" in lower or ("email" in lower and "research" not in lower) or "queue message" in lower:
            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', intent)
            recipient = email_match.group(0) if email_match else "team@proofbound.org"
            
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Stage Non-Destructive Reversible Draft for {recipient}",
                description="Compose email/message body and stage without triggering direct transmission.",
                tool_name="draft_create_email",
                parameters={
                    "recipient": recipient,
                    "subject": f"Operational Brief: {intent[:30]}",
                    "body": f"Proposed draft content generated for:\\n\\n'{intent}'\\n\\nPrepared under Proofbound Policy Gate."
                },
                estimated_risk=RiskLevel.MEDIUM
            ))

        elif "patch" in lower or "edit file" in lower or "write file" in lower or "modify file" in lower or ("patch" in lower and "file" in lower):
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Search Workspace Files for {os.path.basename(target_file)}",
                description="Locate target file in sandboxed workspace directory.",
                tool_name="workspace_search",
                parameters={"pattern": os.path.basename(target_file)},
                estimated_risk=RiskLevel.LOW
            ))
            steps.append(PlanStep(
                id="step-2",
                step_index=2,
                title=f"Apply Unified File Patch to {os.path.basename(target_file)}",
                description="Write modifications to target file and record diff for rollback.",
                tool_name="workspace_write_file",
                parameters={
                    "file_path": target_file,
                    "content": f"# Proofbound Auto-Config\\n# Updated for: {intent}\\nstatus=active\\n"
                },
                estimated_risk=RiskLevel.HIGH
            ))

        elif "workspace" in lower or "find file" in lower or ("search" in lower and "file" in lower):
            search_pattern = file_match.group(0) if file_match else (intent.split()[-1] if intent.split() else "config")
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
            target_url = extracted_url or f"https://wikipedia.org/wiki/{query_topic.replace(' ', '_')}"
            
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title=f"Perform Evidence-Based Web Research: {query_topic[:40]}",
                description="Query authorized domains and extract source citations.",
                tool_name="browser_research",
                parameters={"query": query_topic, "url": target_url},
                estimated_risk=RiskLevel.LOW
            ))
            steps.append(PlanStep(
                id="step-2",
                step_index=2,
                title="Synthesize Research & Propose Memory Update",
                description="Extract verified factual findings and formulate source-linked memory proposal.",
                tool_name="memory_propose",
                parameters={"topic": query_topic},
                estimated_risk=RiskLevel.LOW
            ))

        else:
            steps.append(PlanStep(
                id="step-1",
                step_index=1,
                title="Standard Operations Execution",
                description="Execute read-only workspace and knowledge query.",
                tool_name="workspace_search",
                parameters={"pattern": intent[:10]},
                estimated_risk=RiskLevel.LOW
            ))

        return steps

    def execute_run(self, run_id: str) -> ActionRun:
        run = self.ledger.get_run(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found")

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

            result = self._dispatch_tool(step.tool_name, step.parameters, token, run)

            if result.success:
                step.status = StepStatus.COMPLETED
                step.result = result.data
                
                for cit in result.citations:
                    run.citations.append(cit)
                    run.add_event(
                        event_type="citation_extracted",
                        step_index=step.step_index,
                        message=f"Captured citation: '{cit.title}' from {cit.source_uri}",
                        payload=cit.model_dump()
                    )

                for art in result.artifacts:
                    run.artifacts.append(art)
                    run.add_event(
                        event_type="artifact_created",
                        step_index=step.step_index,
                        message=f"Created artifact: '{art.name}' ({art.artifact_type})",
                        payload=art.model_dump()
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
                break

        if run.citations and not run.memory_updates:
            top_cit = run.citations[0]
            proposal = self.memory.propose_fact(
                run_id=run.id,
                content=f"Verified knowledge: {top_cit.snippet[:120]}",
                source=top_cit.source_uri,
                confidence=top_cit.confidence,
                justification=f"Extracted from verified citation {top_cit.id}"
            )
            run.memory_updates.append(proposal)
            run.add_event(
                event_type="memory_proposed",
                message=f"Proposed source-linked memory update ({proposal.proposal_id}). Staged for user acceptance.",
                payload=proposal.model_dump()
            )

        run.mark_completed()
        run.add_event(
            event_type="run_completed",
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
            from proofbound.workers.base import WorkerResult
            return WorkerResult(success=True, data={"memory_proposal_staged": True})
        else:
            return self.mock_worker.execute_tool(tool_name, parameters, token)
