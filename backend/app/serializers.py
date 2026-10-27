from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import ApprovalRequest, AuditLog, Notification, Record, RecordVersion, User
from .utils import iso


def user_dict(u: User) -> dict:
    return {
        "id": u.id, "username": u.username, "email": u.email, "full_name": u.full_name,
        "organization": u.organization, "role": u.role, "is_active": u.is_active,
        "created_at": iso(u.created_at), "last_login": iso(u.last_login),
    }


def user_brief(u: User) -> dict:
    return {"id": u.id, "username": u.username, "full_name": u.full_name}


def version_dict(v: RecordVersion, with_risk: bool = False, has_file: bool | None = None) -> dict:
    d = {
        "version_no": v.version_no, "filename": v.filename, "size": v.size, "mime": v.mime, "sha256": v.sha256,
        "metadata_hash": v.metadata_hash, "change_note": v.change_note, "created_at": iso(v.created_at),
        "author": user_brief(v.author), "tx_hash": v.tx_hash, "block_number": v.block_number,
        "chain_timestamp": iso(v.chain_timestamp), "risk_score": v.risk_score, "risk_level": v.risk_level,
        "stored": bool(v.stored_path),
    }
    if with_risk:
        d["risk_report"] = v.risk_report
    return d


def approval_dict(a: ApprovalRequest) -> dict:
    return {
        "id": a.id, "record_public_id": a.record.public_id, "record_title": a.record.title, "version_no": a.version_no,
        "approver": user_brief(a.approver), "requested_by": user_brief(a.requester), "status": a.status,
        "comment": a.comment, "tx_hash": a.tx_hash, "block_number": a.block_number,
        "requested_at": iso(a.requested_at), "decided_at": iso(a.decided_at),
    }


def is_reviewer(db: Session, rec: Record, user: User | None) -> bool:
    if not user:
        return False
    return db.scalar(select(ApprovalRequest.id).where(
        ApprovalRequest.record_id == rec.id, ApprovalRequest.approver_id == user.id).limit(1)) is not None


def can_view_full(db: Session, rec: Record, user: User | None) -> bool:
    return bool(user) and (rec.owner_id == user.id or user.role == "admin" or is_reviewer(db, rec, user))


def record_dict(rec: Record, db: Session, viewer: User | None, detail: bool = False) -> dict:
    full = can_view_full(db, rec, viewer)
    cur = next((v for v in rec.versions if v.version_no == rec.current_version), rec.versions[-1])
    d = {
        "public_id": rec.public_id,
        "title": rec.title if (full or rec.visibility == "public") else None,
        "description": rec.description if (full or rec.visibility == "public") else None,
        "category": rec.category, "tags": rec.tags if full or rec.visibility == "public" else [],
        "visibility": rec.visibility, "status": rec.status, "current_version": rec.current_version,
        "version_count": len(rec.versions), "created_at": iso(rec.created_at), "updated_at": iso(rec.updated_at),
        "owner": user_brief(rec.owner) if (full or rec.visibility == "public") else None,
        "is_owner": bool(viewer) and rec.owner_id == viewer.id,
        "trust_score": rec.trust_score, "risk_score": cur.risk_score, "risk_level": cur.risk_level,
        "sha256": cur.sha256, "filename": cur.filename if full else None, "size": cur.size,
        "tx_hash": cur.tx_hash, "block_number": cur.block_number, "revoked_reason": rec.revoked_reason,
        "can_manage": full,
    }
    if detail and full:
        d["versions"] = [version_dict(v, with_risk=(v.version_no == rec.current_version)) for v in rec.versions]
        d["trust"] = rec.trust_breakdown
    return d


def audit_dict(e: AuditLog) -> dict:
    return {
        "seq": e.seq, "ts": iso(e.ts), "actor": e.actor_name, "actor_id": e.actor_id, "action": e.action,
        "record": e.record_public_id, "details": e.details, "tx_hash": e.tx_hash, "ip": e.ip,
        "entry_hash": e.entry_hash, "prev_hash": e.prev_hash,
    }


def notification_dict(n: Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "title": n.title, "body": n.body, "record": n.record_public_id,
            "read": n.read, "created_at": iso(n.created_at)}
