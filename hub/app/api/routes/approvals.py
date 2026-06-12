"""Approval decisions (Epic 03 · 3.3). The owner approves / edits / rejects a
pending auto-reply; on approve the hub sends it AS the agent, server-side."""

from fastapi import APIRouter, Depends

from app.api.deps import get_approval_service, get_current_user
from app.models.user import User
from app.schemas.approval import ApprovalDecision, ApprovalOut
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


@router.post("/{approval_id}/decision", response_model=ApprovalOut)
async def decide(
    approval_id: int,
    body: ApprovalDecision,
    user: User = Depends(get_current_user),
    svc: ApprovalService = Depends(get_approval_service),
) -> ApprovalOut:
    # ApprovalService enforces owner/admin authz and sends server-side on approve
    # (the injected sender persists + pushes to the recipient in real time).
    approval, _msg = await svc.decide(user, approval_id, body.decision, body.body)
    return ApprovalOut.model_validate(approval)
