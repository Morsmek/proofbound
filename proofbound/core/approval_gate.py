from typing import Optional
from proofbound.models.action_run import ActionRun, ApprovalState, RiskLevel
from proofbound.config import settings

class ApprovalGate:
    @classmethod
    def process_initial_approval(cls, run: ActionRun) -> ApprovalState:
        if run.risk_level == RiskLevel.LOW and settings.auto_approve_low_risk:
            run.approval_state = ApprovalState.AUTO_APPROVED
            run.add_event(
                event_type="approval_auto_granted",
                message=f"Low risk operation auto-approved by policy. Scopes: {', '.join(run.requested_scopes)}",
                severity="INFO",
                payload={"risk_level": run.risk_level.value, "scopes": run.requested_scopes}
            )
            return ApprovalState.AUTO_APPROVED
        else:
            run.approval_state = ApprovalState.PENDING
            run.add_event(
                event_type="approval_requested",
                message=f"Action paused. Approval required for {run.risk_level.value} risk operation. Scopes requested: {', '.join(run.requested_scopes)}",
                severity="WARNING",
                payload={
                    "risk_level": run.risk_level.value,
                    "plan_step_count": len(run.plan_steps),
                    "requested_scopes": run.requested_scopes
                }
            )
            return ApprovalState.PENDING

    @classmethod
    def grant_approval(cls, run: ActionRun, approver: str = "user", notes: Optional[str] = None) -> bool:
        if run.completed_at or run.approval_state in [ApprovalState.REJECTED, ApprovalState.CANCELLED]:
            raise PermissionError("A rejected or completed run cannot be approved")
        if run.approval_state in [ApprovalState.APPROVED, ApprovalState.AUTO_APPROVED]:
            return True
        
        run.approval_state = ApprovalState.APPROVED
        run.add_event(
            event_type="approval_granted",
            message=f"Approval explicitly granted by {approver}. {notes or ''}".strip(),
            severity="INFO",
            payload={"approver": approver, "notes": notes}
        )
        return True

    @classmethod
    def reject_approval(cls, run: ActionRun, approver: str = "user", reason: str = "User declined") -> bool:
        if run.completed_at:
            raise PermissionError("A completed run cannot be rejected")
        run.approval_state = ApprovalState.REJECTED
        run.mark_completed()
        run.add_event(
            event_type="approval_rejected",
            message=f"Action execution rejected by {approver}. Reason: {reason}",
            severity="WARNING",
            payload={"approver": approver, "reason": reason}
        )
        return True
