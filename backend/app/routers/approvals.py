from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApprovalRequest, Record, User
from ..schemas import ApprovalRequestIn, DecisionIn
from ..security import client_ip, get_current_user
from ..serializers import approval_dict, can_view_full, record_dict
from ..services import audit, registry, trust
from ..services.blockchain import ChainError, actor_id, chain
from ..services.events import manager
from ..utils import sha256_hex, utcnow
from .common import get_record_or_404, require_chain

router = APIRouter(prefix="/api", tags=["approvals"])


@router.post("/records/{public_id}/approvals", status_code=201)
def request_approvals(body: ApprovalRequestIn, request: Request, rec: Record = Depends(get_record_or_404),
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if rec.owner_id != user.id:
        raise HTTPException(403 if can_view_full(db, rec, user) else 404, "Only the owner can request approvals")
    if rec.status == "REVOKED":
        raise HTTPException(409, "This record has been revoked")
    version_no = body.version_no or rec.current_version
    if version_no != rec.current_version:
        raise HTTPException(409, "Approvals can only be requested for the current version")

    created = []
    for name in dict.fromkeys(n.strip().lower() for n in body.approvers):
        approver = db.scalar(select(User).where(func.lower(User.username) == name, User.is_active.is_(True)))
        if not approver:
            raise HTTPException(404, f"User '{name}' was not found")
        if approver.id == user.id:
            raise HTTPException(422, "You cannot request approval from yourself")
        exists = db.scalar(select(ApprovalRequest.id).where(
            ApprovalRequest.record_id == rec.id, ApprovalRequest.version_no == version_no, ApprovalRequest.approver_id == approver.id))
        if exists:
            continue
        a = ApprovalRequest(record_id=rec.id, version_no=version_no, approver_id=approver.id, requested_by=user.id)
        db.add(a)
        created.append(approver)
    if not created:
        raise HTTPException(409, "All of those reviewers were already asked for this version")
    db.flush()
    registry.recompute_status(db, rec)
    trust.refresh(db, rec)
    db.commit()
    for approver in created:
        audit.log(db, "APPROVAL_REQUESTED", user, rec.public_id, {"approver": approver.username, "version": version_no}, ip=client_ip(request))
        audit.notify(db, approver.id, "Approval requested", f"{user.full_name} asked you to review {rec.public_id} (v{version_no}).", "info", rec.public_id)
    manager.publish("approvals", {"record": rec.public_id}, user_ids=[a.id for a in created] + [user.id])
    reqs = db.scalars(select(ApprovalRequest).where(ApprovalRequest.record_id == rec.id).order_by(ApprovalRequest.id)).all()
    return {"record": record_dict(rec, db, user, detail=True), "approvals": [approval_dict(a) for a in reqs]}


@router.get("/approvals/inbox")
def inbox(status: str = Query("PENDING", pattern="^(PENDING|APPROVED|REJECTED|ALL)$"), user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    stmt = select(ApprovalRequest).where(ApprovalRequest.approver_id == user.id)
    if status != "ALL":
        stmt = stmt.where(ApprovalRequest.status == status)
    rows = db.scalars(stmt.order_by(ApprovalRequest.requested_at.desc()).limit(100)).unique().all()
    out = []
    for a in rows:
        d = approval_dict(a)
        cur = next((v for v in a.record.versions if v.version_no == a.version_no), None)
        d["version"] = {"filename": cur.filename, "sha256": cur.sha256, "risk_level": cur.risk_level, "risk_score": cur.risk_score,
                        "size": cur.size, "note": cur.change_note} if cur else None
        d["superseded"] = a.version_no != a.record.current_version
        out.append(d)
    return out


@router.get("/approvals/sent")
def sent(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.requested_by == user.id)
                      .order_by(ApprovalRequest.requested_at.desc()).limit(100)).unique().all()
    return [approval_dict(a) for a in rows]


@router.post("/approvals/{approval_id}/decision", dependencies=[Depends(require_chain)])
def decide(approval_id: int, body: DecisionIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    a = db.get(ApprovalRequest, approval_id)
    if not a or a.approver_id != user.id:
        raise HTTPException(404, "Approval request not found")
    if a.status != "PENDING":
        raise HTTPException(409, "You already decided on this request")
    rec = a.record
    if rec.status == "REVOKED":
        raise HTTPException(409, "This record has been revoked")
    if a.version_no != rec.current_version:
        raise HTTPException(409, "This request is for an older version that has since been superseded")
    if not body.approve and len(body.comment.strip()) < 3:
        raise HTTPException(422, "Please explain why you are rejecting (at least 3 characters)")
    try:
        anchor = chain.decision(rec.public_id, a.version_no, actor_id(user.id), body.approve, sha256_hex(body.comment))
    except ChainError as exc:
        raise HTTPException(502, str(exc))
    a.status = "APPROVED" if body.approve else "REJECTED"
    a.comment = body.comment.strip()
    a.decided_at = utcnow()
    a.tx_hash, a.block_number = anchor["tx_hash"], anchor["block_number"]
    db.flush()
    registry.recompute_status(db, rec)
    trust.refresh(db, rec)
    db.commit()
    audit.log(db, "APPROVAL_APPROVED" if body.approve else "APPROVAL_REJECTED", user, rec.public_id,
              {"version": a.version_no, "comment": a.comment}, anchor["tx_hash"], client_ip(request))
    audit.notify(db, rec.owner_id, f"{user.full_name} {'approved' if body.approve else 'rejected'} {rec.public_id}",
                 a.comment or f"Record is now {rec.status.replace('_', ' ').lower()}.", "success" if body.approve else "danger", rec.public_id)
    manager.publish("approvals", {"record": rec.public_id, "status": rec.status}, user_ids=[rec.owner_id, user.id])
    manager.publish("stats", {"reason": "decision"}, user_ids=None)
    return approval_dict(a) | {"record_status": rec.status}


@router.get("/records/{public_id}/approvals")
def record_approvals(rec: Record = Depends(get_record_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can_view_full(db, rec, user):
        raise HTTPException(404, "Record not found")
    rows = db.scalars(select(ApprovalRequest).where(ApprovalRequest.record_id == rec.id).order_by(ApprovalRequest.id)).all()
    return [approval_dict(a) for a in rows]
