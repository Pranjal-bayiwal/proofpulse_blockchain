"""Hash-chained audit trail (tamper-evident) + notification helper."""
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog, Notification, User
from ..utils import canonical_json, iso, sha256_hex, utcnow
from .events import manager

_lock = threading.Lock()
GENESIS = "0" * 64


def _entry_hash(prev: str, seq: int, ts, actor_id, action, record, details, tx) -> str:
    payload = f"{prev}|{seq}|{iso(ts)}|{actor_id}|{action}|{record}|{canonical_json(details)}|{tx}"
    return sha256_hex(payload)


def log(
    db: Session,
    action: str,
    actor: User | None = None,
    record_public_id: str | None = None,
    details: dict | None = None,
    tx_hash: str | None = None,
    ip: str | None = None,
) -> AuditLog:
    details = details or {}
    with _lock:
        last = db.scalars(select(AuditLog).order_by(AuditLog.seq.desc()).limit(1)).first()
        seq = (last.seq + 1) if last else 1
        prev = last.entry_hash if last else GENESIS
        ts = utcnow().replace(microsecond=0)
        entry = AuditLog(
            seq=seq,
            ts=ts,
            actor_id=actor.id if actor else None,
            actor_name=actor.username if actor else "system",
            action=action,
            record_public_id=record_public_id,
            details=details,
            tx_hash=tx_hash,
            ip=ip,
            prev_hash=prev,
            entry_hash=_entry_hash(prev, seq, ts, actor.id if actor else None, action, record_public_id, details, tx_hash),
        )
        db.add(entry)
        db.commit()
    manager.publish("audit", {"action": action, "record": record_public_id, "seq": seq}, user_ids=[actor.id] if actor else [])
    return entry


def verify_chain(db: Session) -> dict:
    prev = GENESIS
    count = 0
    for e in db.scalars(select(AuditLog).order_by(AuditLog.seq)):
        expected = _entry_hash(prev, e.seq, e.ts, e.actor_id, e.action, e.record_public_id, e.details, e.tx_hash)
        if e.prev_hash != prev or e.entry_hash != expected:
            return {"valid": False, "entries": count, "broken_at_seq": e.seq,
                    "message": f"Audit entry #{e.seq} does not match its hash - the log was altered."}
        prev = e.entry_hash
        count += 1
    return {"valid": True, "entries": count, "broken_at_seq": None, "head": prev,
            "message": f"All {count} audit entries are intact and correctly chained."}


def notify(db: Session, user_id: int, title: str, body: str = "", kind: str = "info", record_public_id: str | None = None) -> None:
    n = Notification(user_id=user_id, title=title[:120], body=body[:400], kind=kind, record_public_id=record_public_id)
    db.add(n)
    db.commit()
    manager.publish(
        "notification",
        {"id": n.id, "title": n.title, "body": n.body, "kind": n.kind, "record": record_public_id, "created_at": iso(n.created_at)},
        user_ids=[user_id],
        admins=False,
    )
