import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, Record, User
from ..security import get_current_user
from ..serializers import audit_dict
from ..services import audit as audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _filtered(db: Session, user: User, q: str, action: str, actor: str, record: str, date_from: str, date_to: str):
    stmt = select(AuditLog)
    if user.role != "admin":
        mine = select(Record.public_id).where(Record.owner_id == user.id)
        stmt = stmt.where(or_(AuditLog.actor_id == user.id, AuditLog.record_public_id.in_(mine)))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(AuditLog.action).like(like), func.lower(AuditLog.actor_name).like(like),
                              func.lower(AuditLog.record_public_id).like(like), func.lower(AuditLog.tx_hash).like(like),
                              func.lower(cast(AuditLog.details, String)).like(like)))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor:
        stmt = stmt.where(func.lower(AuditLog.actor_name) == actor.lower())
    if record:
        stmt = stmt.where(func.upper(AuditLog.record_public_id) == record.upper())
    try:
        if date_from:
            stmt = stmt.where(AuditLog.ts >= datetime.fromisoformat(date_from))
        if date_to:
            stmt = stmt.where(AuditLog.ts < datetime.fromisoformat(date_to) + timedelta(days=1))
    except ValueError:
        pass
    return stmt


@router.get("")
def search(q: str = "", action: str = "", actor: str = "", record: str = "", date_from: str = "", date_to: str = "",
           page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = _filtered(db, user, q, action, actor, record, date_from, date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(AuditLog.seq.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [audit_dict(e) for e in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/actions")
def actions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return sorted(db.scalars(select(AuditLog.action).distinct()).all())


@router.get("/verify-chain")
def verify_chain(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return audit_service.verify_chain(db)


@router.get("/export.csv")
def export_csv(q: str = "", action: str = "", actor: str = "", record: str = "", date_from: str = "", date_to: str = "",
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt = _filtered(db, user, q, action, actor, record, date_from, date_to)
    rows = db.scalars(stmt.order_by(AuditLog.seq.desc()).limit(5000)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["seq", "timestamp_utc", "actor", "action", "record", "tx_hash", "details", "entry_hash"])
    for e in rows:
        def safe(v):  # neutralise spreadsheet formula injection
            s = "" if v is None else str(v)
            return "'" + s if s[:1] in ("=", "+", "-", "@") else s
        w.writerow([e.seq, e.ts.isoformat() + "Z", safe(e.actor_name), e.action, e.record_public_id or "", e.tx_hash or "",
                    safe(e.details), e.entry_hash])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="proofpulse-audit.csv"'})
