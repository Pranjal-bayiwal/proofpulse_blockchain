from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApprovalRequest, AuditLog, Record, RecordVersion, User, VerificationEvent
from ..schemas import UserAdminPatch
from ..security import client_ip, require_admin
from ..serializers import record_dict, user_dict
from ..services import anchor, audit, storage, trust
from ..services.blockchain import ChainError, chain
from ..services.events import manager
from ..utils import iso, sha256_hex
from .common import require_chain
from .dashboard import daily_counts, risk_distribution

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    statuses = {s: 0 for s in ("REGISTERED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "REVOKED")}
    for s, n in db.execute(select(Record.status, func.count()).group_by(Record.status)).all():
        statuses[s] = n
    verdicts = {v: n for v, n in db.execute(select(VerificationEvent.verdict, func.count()).group_by(VerificationEvent.verdict)).all()}
    risky = db.execute(
        select(Record, RecordVersion).join(RecordVersion, RecordVersion.record_id == Record.id)
        .where(RecordVersion.version_no == Record.current_version).order_by(RecordVersion.risk_score.desc()).limit(6)).unique().all()
    st = chain.status() if chain.contract else {"connected": False}
    return {
        "totals": {
            "users": db.scalar(select(func.count(User.id))) or 0,
            "records": sum(statuses.values()),
            "versions": db.scalar(select(func.count(RecordVersion.id))) or 0,
            "approvals_pending": db.scalar(select(func.count(ApprovalRequest.id)).where(ApprovalRequest.status == "PENDING")) or 0,
            "verifications": sum(verdicts.values()),
            "tamper_detections": verdicts.get("TAMPERED", 0) + verdicts.get("ANCHOR_MISMATCH", 0),
            "audit_entries": db.scalar(select(func.count(AuditLog.id))) or 0,
        },
        "status_distribution": statuses,
        "risk_distribution": risk_distribution(db),
        "verdict_distribution": verdicts,
        "registrations_per_day": daily_counts(db, Record.created_at, 14),
        "verifications_per_day": daily_counts(db, VerificationEvent.created_at, 14),
        "top_risk": [{"public_id": r.public_id, "title": r.title, "risk_score": v.risk_score, "risk_level": v.risk_level,
                      "owner": r.owner.username} for r, v in risky],
        "chain": st,
    }


@router.get("/users")
def users(db: Session = Depends(get_db)):
    counts = dict(db.execute(select(Record.owner_id, func.count()).group_by(Record.owner_id)).all())
    return [user_dict(u) | {"records": counts.get(u.id, 0)} for u in db.scalars(select(User).order_by(User.id))]


@router.patch("/users/{user_id}")
def patch_user(user_id: int, body: UserAdminPatch, request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == admin.id and (body.is_active is False or (body.role and body.role != "admin")):
        raise HTTPException(409, "You cannot deactivate or demote your own account")
    changes = {}
    if body.is_active is not None and body.is_active != target.is_active:
        target.is_active = body.is_active
        changes["is_active"] = body.is_active
    if body.role and body.role != target.role:
        target.role = body.role
        changes["role"] = body.role
    db.commit()
    if changes:
        audit.log(db, "USER_UPDATED", admin, details={"user": target.username, **changes}, ip=client_ip(request))
    return user_dict(target)


@router.get("/records")
def all_records(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.scalars(select(Record).order_by(Record.created_at.desc()).limit(200)).unique().all()
    return [record_dict(r, db, admin) for r in rows]


@router.get("/chain", dependencies=[Depends(require_chain)])
def chain_status():
    return chain.status()


@router.post("/integrity-scan", dependencies=[Depends(require_chain)])
def integrity_scan(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Compare every record: database vs chain, and stored (encrypted) files vs both."""
    issues, scanned = [], 0
    for rec in db.scalars(select(Record)).unique().all():
        scanned += 1
        chain_rec = chain.get_record(rec.public_id)
        failures = 0
        if not chain_rec:
            issues.append({"record": rec.public_id, "problem": "Missing from blockchain"})
            failures += 1
        else:
            for v in rec.versions:
                if v.version_no > len(chain_rec["versions"]) or chain_rec["versions"][v.version_no - 1]["content_hash"] != v.sha256:
                    issues.append({"record": rec.public_id, "version": v.version_no, "problem": "Database hash differs from on-chain hash"})
                    failures += 1
                if v.stored_path:
                    data = storage.load_decrypted(v.stored_path)
                    if data is None or sha256_hex(data) != v.sha256:
                        issues.append({"record": rec.public_id, "version": v.version_no, "problem": "Stored file no longer matches its fingerprint"})
                        failures += 1
        if rec.integrity_failures != failures:
            rec.integrity_failures = failures
            trust.refresh(db, rec)
    db.commit()
    audit.log(db, "INTEGRITY_SCAN", admin, details={"scanned": scanned, "issues": len(issues)}, ip=client_ip(request))
    return {"scanned": scanned, "issues": issues, "ok": not issues}


@router.post("/reanchor", dependencies=[Depends(require_chain)])
def reanchor(request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Replay all database records onto the current chain. Only for local/dev chains that were reset."""
    existing = chain.status().get("total_records", 0)
    if existing:
        raise HTTPException(409, f"The chain already holds {existing} record(s); re-anchoring would create duplicates.")
    try:
        result = anchor.reanchor_all(db)
    except ChainError as exc:
        raise HTTPException(502, str(exc))
    audit.log(db, "REANCHORED", admin, details=result, ip=client_ip(request))
    manager.publish("stats", {"reason": "reanchor"}, user_ids=None)
    return result
