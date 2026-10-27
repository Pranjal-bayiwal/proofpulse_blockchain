"""Public verification endpoints: no account needed."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApprovalRequest, Record, RecordVersion, VerificationEvent
from ..schemas import HashVerifyIn
from ..security import rate_limit
from ..services import certificate
from ..services.blockchain import chain
from ..services.events import manager
from ..services.registry import sha256_hex
from ..utils import PUBLIC_ID_RE, iso, utcnow
from .common import read_upload, require_chain

router = APIRouter(prefix="/api", tags=["verify"], dependencies=[Depends(rate_limit("verify", 90, 60))])

HEADLINES = {
    "AUTHENTIC": ("Authentic", "This file is byte-for-byte identical to the latest registered version, and the on-chain record matches."),
    "OUTDATED_VERSION": ("Authentic but outdated", "This file matches an earlier version. A newer version has since been registered."),
    "TAMPERED": ("Tampered or unregistered", "This file does not match any version registered under this ID. It has been altered or is a different file."),
    "REVOKED": ("Revoked", "The owner or an administrator revoked this record. Do not rely on it."),
    "NOT_FOUND": ("Not found", "No record with this ID exists on the ProofPulse contract."),
    "REGISTERED": ("Registered on chain", "A valid record exists. Upload the file to confirm it has not been changed."),
    "ANCHOR_MISMATCH": ("Database does not match the chain", "Off-chain data disagrees with the blockchain. The blockchain is the source of truth; treat the database copy as compromised."),
    "ON_CHAIN_ONLY": ("Found on chain only", "The blockchain holds this record but the platform database does not. Provenance is intact."),
}


def _iso_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat() + "Z"


def _consistency(rec: Record | None, chain_rec: dict) -> dict:
    issues = []
    if rec is not None:
        if len(rec.versions) != chain_rec["version_count"]:
            issues.append(f"Database has {len(rec.versions)} version(s) but the chain has {chain_rec['version_count']}.")
        for v in rec.versions:
            if v.version_no <= len(chain_rec["versions"]) and chain_rec["versions"][v.version_no - 1]["content_hash"] != v.sha256:
                issues.append(f"Version {v.version_no}: database hash differs from on-chain hash.")
        if (rec.status == "REVOKED") != chain_rec["revoked"]:
            issues.append("Revocation status differs between database and chain.")
    return {"ok": not issues, "issues": issues}


def build(db: Session, public_id: str, file_hash: str | None = None, record_event: bool = True) -> dict:
    public_id = public_id.strip().upper()
    out: dict = {"public_id": public_id, "checked_at": iso(utcnow()), "file_check": None, "record": None, "trust": None,
                 "approvals": None, "chain": {"found": False}, "consistency": {"ok": True, "issues": []}, "seal": None}

    chain_rec = chain.get_record(public_id) if PUBLIC_ID_RE.match(public_id) else None
    rec = db.scalar(select(Record).where(Record.public_id == public_id)) if PUBLIC_ID_RE.match(public_id) else None

    if not chain_rec:
        verdict = "NOT_FOUND"
        if rec is not None:  # DB claims it exists but chain does not know it
            verdict = "ANCHOR_MISMATCH"
            out["consistency"] = {"ok": False, "issues": ["The database lists this record but it is absent from the blockchain."]}
    else:
        out["chain"] = {
            "found": True,
            "revoked": chain_rec["revoked"],
            "created_at": _iso_ts(chain_rec["created_at"]),
            "version_count": chain_rec["version_count"],
            "contract_address": chain.contract.address,
            "network": f"{chain.mode}:{chain.w3.eth.chain_id}",
            "versions": [],
            "history": [],
        }
        tx_by_version = {v.version_no: v for v in rec.versions} if rec else {}
        for v in chain_rec["versions"]:
            dbv = tx_by_version.get(v["version_no"])
            out["chain"]["versions"].append({
                "version_no": v["version_no"], "content_hash": v["content_hash"], "timestamp": _iso_ts(v["timestamp"]),
                "approvals": v["approvals"], "rejections": v["rejections"],
                "tx_hash": dbv.tx_hash if dbv else None, "block_number": dbv.block_number if dbv else None,
            })
        out["chain"]["history"] = [
            {**e, "timestamp": _iso_ts(e["timestamp"]) if e.get("timestamp") else None} for e in chain.history(public_id)]
        out["consistency"] = _consistency(rec, chain_rec)

        latest = chain_rec["versions"][-1]
        if file_hash:
            matched = next((v for v in reversed(chain_rec["versions"]) if v["content_hash"] == file_hash), None)
            out["file_check"] = {
                "sha256": file_hash, "matches": matched is not None,
                "matched_version": matched["version_no"] if matched else None,
                "is_latest": bool(matched and matched["version_no"] == latest["version_no"]),
                "expected_latest": latest["content_hash"],
            }
        if chain_rec["revoked"]:
            verdict = "REVOKED"
        elif not out["consistency"]["ok"]:
            verdict = "ANCHOR_MISMATCH"
        elif file_hash:
            fc = out["file_check"]
            verdict = ("AUTHENTIC" if fc["is_latest"] else "OUTDATED_VERSION") if fc["matches"] else "TAMPERED"
        else:
            verdict = "REGISTERED" if rec else "ON_CHAIN_ONLY"
        if verdict == "AUTHENTIC" and chain_rec["versions"][-1]["rejections"] > 0:
            out["warning"] = "At least one reviewer rejected this version."

        if rec is not None:
            public = rec.visibility == "public"
            cur = next(v for v in rec.versions if v.version_no == rec.current_version)
            reqs = db.scalars(select(ApprovalRequest).where(
                ApprovalRequest.record_id == rec.id, ApprovalRequest.version_no == rec.current_version)).all()
            out["record"] = {
                "title": rec.title if public else None, "description": rec.description if public else None,
                "owner": rec.owner.full_name if public else None, "category": rec.category, "visibility": rec.visibility,
                "status": rec.status, "registered_at": iso(rec.created_at), "tags": rec.tags if public else [],
                "filename": cur.filename if public else None, "size": cur.size,
                "risk_level": cur.risk_level, "risk_score": cur.risk_score,
            }
            out["trust"] = {"score": rec.trust_score, "label": (rec.trust_breakdown or {}).get("label")}
            out["approvals"] = {
                "requested": len(reqs), "approved": sum(r.status == "APPROVED" for r in reqs),
                "rejected": sum(r.status == "REJECTED" for r in reqs), "pending": sum(r.status == "PENDING" for r in reqs)}
            out["seal"] = certificate.seal(rec.public_id, cur.sha256, cur.tx_hash)
            out["certificate_url"] = f"/api/records/{rec.public_id}/certificate"

    headline, message = HEADLINES[verdict]
    out.update({"verdict": verdict, "headline": headline, "message": message})
    if record_event:
        db.add(VerificationEvent(record_public_id=public_id if PUBLIC_ID_RE.match(public_id) else None,
                                 verdict=verdict, used_file=bool(file_hash)))
        db.commit()
        manager.publish("verification", {"record": public_id, "verdict": verdict}, user_ids=[rec.owner_id] if rec else [])
    return out


@router.get("/verify/{public_id}", dependencies=[Depends(require_chain)])
def verify_by_id(public_id: str, db: Session = Depends(get_db)):
    return build(db, public_id)


@router.post("/verify/{public_id}/file", dependencies=[Depends(require_chain)])
def verify_file(public_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    return build(db, public_id, sha256_hex(read_upload(file)))


@router.post("/verify/{public_id}/hash", dependencies=[Depends(require_chain)])
def verify_hash(public_id: str, body: HashVerifyIn, db: Session = Depends(get_db)):
    """Verify using only a SHA-256 hash, so the file never has to leave the verifier's computer."""
    return build(db, public_id, body.sha256)


def _lookup(db: Session, sha: str) -> dict:
    rows = db.execute(select(RecordVersion, Record).join(Record, Record.id == RecordVersion.record_id)
                      .where(RecordVersion.sha256 == sha).order_by(RecordVersion.created_at)).all()
    matches = [{
        "public_id": rec.public_id, "version_no": ver.version_no, "is_latest": ver.version_no == rec.current_version,
        "registered_at": iso(ver.created_at), "status": rec.status, "block_number": ver.block_number,
        "title": rec.title if rec.visibility == "public" else None,
    } for ver, rec in rows]
    first_on_chain = chain.first_record_for_hash(sha) if chain.contract else None
    return {"sha256": sha, "registered": bool(matches), "matches": matches,
            "earliest": matches[0] if matches else None, "chain_priority_record_hash": first_on_chain,
            "message": (f"Registered {len(matches)} time(s). Earliest: {matches[0]['public_id']} on {matches[0]['registered_at']}."
                        if matches else "This exact file has never been registered on ProofPulse.")}


@router.post("/verify-lookup/file", dependencies=[Depends(require_chain)])
def lookup_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """No ID? Upload the file and find out whether (and by whom, when) it was registered first."""
    return _lookup(db, sha256_hex(read_upload(file)))


@router.post("/verify-lookup/hash", dependencies=[Depends(require_chain)])
def lookup_hash(body: HashVerifyIn, db: Session = Depends(get_db)):
    return _lookup(db, body.sha256)


@router.get("/public/stats")
def public_stats(db: Session = Depends(get_db)):
    st = chain.status() if chain.contract else {"connected": False}
    return {
        "records": db.scalar(select(func.count(Record.id))) or 0,
        "versions": db.scalar(select(func.count(RecordVersion.id))) or 0,
        "verifications": db.scalar(select(func.count(VerificationEvent.id))) or 0,
        "chain": {k: st.get(k) for k in ("connected", "mode", "block_number", "network_id", "contract_address", "persistent")},
    }
