"""Replay database records onto a fresh chain (embedded mode restarts, or a reset local node)."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApprovalRequest, Record
from ..utils import sha256_hex
from .blockchain import actor_id, chain


def _ct(ts: int):
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def reanchor_all(db: Session) -> dict:
    records = db.scalars(select(Record).order_by(Record.id)).all()
    n_rec = n_ver = n_dec = 0
    for rec in records:
        versions = sorted(rec.versions, key=lambda v: v.version_no)
        if not versions:
            continue
        v1 = versions[0]
        r = chain.register(rec.public_id, v1.sha256, v1.metadata_hash, actor_id(rec.owner_id))
        v1.tx_hash, v1.block_number, v1.chain_timestamp = r["tx_hash"], r["block_number"], _ct(r["timestamp"])
        n_rec += 1
        n_ver += 1
        for v in versions[1:]:
            r = chain.add_version(rec.public_id, v.sha256, v.metadata_hash, actor_id(v.created_by))
            v.tx_hash, v.block_number, v.chain_timestamp = r["tx_hash"], r["block_number"], _ct(r["timestamp"])
            n_ver += 1
        decided = db.scalars(select(ApprovalRequest).where(
            ApprovalRequest.record_id == rec.id, ApprovalRequest.status != "PENDING")).all()
        for a in sorted(decided, key=lambda x: x.decided_at or x.requested_at):
            r = chain.decision(rec.public_id, a.version_no, actor_id(a.approver_id), a.status == "APPROVED", sha256_hex(a.comment or ""))
            a.tx_hash, a.block_number = r["tx_hash"], r["block_number"]
            n_dec += 1
        if rec.status == "REVOKED":
            chain.revoke(rec.public_id, actor_id(rec.owner_id), sha256_hex(rec.revoked_reason or ""))
    db.commit()
    return {"records": n_rec, "versions": n_ver, "decisions": n_dec}
