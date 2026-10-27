from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApprovalRequest, AuditLog, Record, RecordVersion, User, VerificationEvent
from ..security import get_current_user
from ..serializers import audit_dict, record_dict
from ..utils import utcnow

router = APIRouter(prefix="/api", tags=["dashboard"])


def daily_counts(db: Session, column, days: int, *filters) -> list[dict]:
    start = (utcnow() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = db.execute(select(func.date(column), func.count()).where(column >= start, *filters).group_by(func.date(column))).all()
    by_day = {str(d): c for d, c in rows}
    return [{"date": (start + timedelta(days=i)).date().isoformat(),
             "count": by_day.get((start + timedelta(days=i)).date().isoformat(), 0)} for i in range(days)]


def risk_distribution(db: Session, owner_id: int | None = None) -> dict:
    stmt = select(RecordVersion.risk_level, func.count()).join(Record, Record.id == RecordVersion.record_id).where(
        RecordVersion.version_no == Record.current_version)
    if owner_id:
        stmt = stmt.where(Record.owner_id == owner_id)
    dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for level, n in db.execute(stmt.group_by(RecordVersion.risk_level)).all():
        dist[level] = n
    return dist


@router.get("/dashboard")
def my_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    mine = Record.owner_id == user.id
    statuses = {s: 0 for s in ("REGISTERED", "PENDING_APPROVAL", "APPROVED", "REJECTED", "REVOKED")}
    for s, n in db.execute(select(Record.status, func.count()).where(mine).group_by(Record.status)).all():
        statuses[s] = n
    total = sum(statuses.values())
    avg_trust = db.scalar(select(func.avg(Record.trust_score)).where(mine, Record.status != "REVOKED"))
    recent = db.scalars(select(Record).where(mine).order_by(Record.created_at.desc()).limit(5)).unique().all()
    activity = db.scalars(select(AuditLog).where(AuditLog.actor_id == user.id).order_by(AuditLog.seq.desc()).limit(8)).all()
    my_ids = select(Record.public_id).where(mine)
    return {
        "totals": {
            "records": total,
            "versions": db.scalar(select(func.count(RecordVersion.id)).join(Record, Record.id == RecordVersion.record_id).where(mine)) or 0,
            "avg_trust": round(avg_trust or 0),
            "pending_reviews": db.scalar(select(func.count(ApprovalRequest.id)).where(
                ApprovalRequest.approver_id == user.id, ApprovalRequest.status == "PENDING")) or 0,
            "verifications_of_mine": db.scalar(select(func.count(VerificationEvent.id)).where(
                VerificationEvent.record_public_id.in_(my_ids))) or 0,
        },
        "status_distribution": statuses,
        "risk_distribution": risk_distribution(db, user.id),
        "registrations_per_day": daily_counts(db, Record.created_at, 14, mine),
        "recent_records": [record_dict(r, db, user) for r in recent],
        "recent_activity": [audit_dict(e) for e in activity],
    }
