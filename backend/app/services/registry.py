"""Core business logic shared by the API routes and the seed script."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApprovalRequest, Record, RecordVersion, User
from ..utils import canonical_json, new_public_id, safe_filename, sha256_hex
from . import audit, risk, similarity, storage, trust
from .analysis import inspect_file
from .blockchain import ChainError, actor_id, chain
from .events import manager


def fingerprint(filename: str, data: bytes) -> dict:
    ins = inspect_file(filename, data)
    return {
        "sha256": sha256_hex(data),
        "ins": ins,
        "text_hash": similarity.text_hash(ins.text) if ins.text else None,
        "minhash": similarity.minhash(ins.text) if ins.text else None,
        "dhash": similarity.dhash(data) if ins.ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"} else None,
    }


def analyse_upload(db: Session, user: User, filename: str, data: bytes, exclude_record_id: int | None = None) -> tuple[dict, dict]:
    fp = fingerprint(filename, data)
    report = risk.analyse(
        db, filename=filename, data=data, sha256=fp["sha256"], ins=fp["ins"], user_id=user.id,
        text_hash=fp["text_hash"], minhash=fp["minhash"], dhash=fp["dhash"], exclude_record_id=exclude_record_id,
    )
    return fp, report


def metadata_hash(rec: Record, version_no: int, filename: str, size: int, sha: str, author_id: int) -> str:
    return sha256_hex(canonical_json({
        "public_id": rec.public_id, "version": version_no, "filename": filename, "size": size,
        "sha256": sha, "title": rec.title, "category": rec.category, "actor": actor_id(author_id),
    }))


def recompute_status(db: Session, rec: Record) -> str:
    if rec.status == "REVOKED":
        return rec.status
    reqs = db.scalars(select(ApprovalRequest).where(
        ApprovalRequest.record_id == rec.id, ApprovalRequest.version_no == rec.current_version)).all()
    if not reqs:
        rec.status = "REGISTERED"
    elif any(r.status == "REJECTED" for r in reqs):
        rec.status = "REJECTED"
    elif any(r.status == "PENDING" for r in reqs):
        rec.status = "PENDING_APPROVAL"
    else:
        rec.status = "APPROVED"
    return rec.status


def _chain_time(ts: int) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


def create_record(
    db: Session, user: User, *, filename: str, data: bytes, mime: str, title: str, description: str,
    category: str, tags: list[str], visibility: str, store_file: bool, ip: str | None = None,
) -> Record:
    filename = safe_filename(filename)
    fp, report = analyse_upload(db, user, filename, data)

    rec = Record(public_id=new_public_id(), owner_id=user.id, title=title, description=description,
                 category=category, tags=tags, visibility=visibility, status="REGISTERED", current_version=1)
    rec.owner = user
    while db.scalar(select(Record.id).where(Record.public_id == rec.public_id)):
        rec.public_id = new_public_id()

    meta = metadata_hash(rec, 1, filename, len(data), fp["sha256"], user.id)
    anchor = chain.register(rec.public_id, fp["sha256"], meta, actor_id(user.id))  # raises ChainError

    ver = RecordVersion(
        version_no=1, filename=filename, size=len(data), mime=mime or "application/octet-stream",
        sha256=fp["sha256"], metadata_hash=meta, text_hash=fp["text_hash"], minhash=fp["minhash"], dhash=fp["dhash"],
        risk_score=report["score"], risk_level=report["level"], risk_report=report, change_note="Initial registration",
        created_by=user.id, tx_hash=anchor["tx_hash"], block_number=anchor["block_number"],
        chain_timestamp=_chain_time(anchor["timestamp"]),
        stored_path=storage.save_encrypted(data) if store_file else None,
    )
    rec.versions.append(ver)
    db.add(rec)
    db.flush()
    trust.refresh(db, rec)
    db.commit()

    audit.log(db, "RECORD_REGISTERED", user, rec.public_id,
              {"title": rec.title, "sha256": fp["sha256"], "risk": report["score"], "stored": store_file}, anchor["tx_hash"], ip)
    level = {"LOW": "success", "MEDIUM": "warning", "HIGH": "danger"}[report["level"]]
    audit.notify(db, user.id, f"Registered {rec.public_id}", f"Anchored in block {anchor['block_number']}. Risk: {report['level'].lower()}.", level, rec.public_id)
    for m in report["matches"]:
        if m["kind"] in ("exact", "same_text", "near") and not m["own"]:
            other = db.scalar(select(Record).where(Record.public_id == m["public_id"]))
            if other:
                audit.notify(db, other.owner_id, "Possible copy of your record detected",
                             f"A new submission resembles {other.public_id} ({round(m['similarity'] * 100)}% similar).", "warning", other.public_id)
    manager.publish("stats", {"reason": "record_registered", "record": rec.public_id}, user_ids=None)
    return rec


def add_version(
    db: Session, user: User, rec: Record, *, filename: str, data: bytes, mime: str, note: str, store_file: bool,
    ip: str | None = None,
) -> RecordVersion:
    filename = safe_filename(filename)
    fp, report = analyse_upload(db, user, filename, data, exclude_record_id=rec.id)
    next_no = len(rec.versions) + 1

    if any(v.sha256 == fp["sha256"] for v in rec.versions):
        raise ValueError("This exact file is already one of this record's versions.")

    meta = metadata_hash(rec, next_no, filename, len(data), fp["sha256"], user.id)
    anchor = chain.add_version(rec.public_id, fp["sha256"], meta, actor_id(user.id))

    ver = RecordVersion(
        record_id=rec.id, version_no=next_no, filename=filename, size=len(data),
        mime=mime or "application/octet-stream", sha256=fp["sha256"], metadata_hash=meta, text_hash=fp["text_hash"],
        minhash=fp["minhash"], dhash=fp["dhash"], risk_score=report["score"], risk_level=report["level"],
        risk_report=report, change_note=note, created_by=user.id, tx_hash=anchor["tx_hash"],
        block_number=anchor["block_number"], chain_timestamp=_chain_time(anchor["timestamp"]),
        stored_path=storage.save_encrypted(data) if store_file else None,
    )
    db.add(ver)
    rec.current_version = next_no
    rec.status = "REGISTERED"
    db.flush()
    db.refresh(rec)
    trust.refresh(db, rec)
    db.commit()

    audit.log(db, "VERSION_ADDED", user, rec.public_id,
              {"version": next_no, "sha256": fp["sha256"], "note": note, "risk": report["score"]}, anchor["tx_hash"], ip)
    audit.notify(db, rec.owner_id, f"Version {next_no} anchored", f"{rec.public_id} now has {next_no} versions.", "success", rec.public_id)
    manager.publish("stats", {"reason": "version_added", "record": rec.public_id}, user_ids=None)
    return ver
