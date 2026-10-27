"""Explainable 0-100 trust score for a record. Six transparent components."""
from datetime import timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ApprovalRequest, Record, RecordVersion
from ..utils import utcnow


def label_for(score: int, revoked: bool = False) -> str:
    if revoked:
        return "Revoked"
    return "Excellent" if score >= 80 else "Good" if score >= 60 else "Fair" if score >= 40 else "Poor"


def compute(db: Session, rec: Record) -> dict:
    if rec.status == "REVOKED":
        return {"score": 0, "label": "Revoked", "components": [], "note": "Record revoked by owner or administrator."}

    versions = rec.versions
    current = next((v for v in versions if v.version_no == rec.current_version), versions[-1])
    comps = []

    anchored = current.tx_hash is not None
    comps.append({"key": "anchoring", "label": "Blockchain anchoring", "max": 20, "points": 20 if anchored else 0,
                  "why": "Latest version is anchored on chain." if anchored else "Latest version is not anchored on chain yet."})

    fails = rec.integrity_failures
    pts = max(0, 20 - 10 * fails)
    comps.append({"key": "integrity", "label": "Integrity history", "max": 20, "points": pts,
                  "why": "No integrity failures recorded." if not fails else f"{fails} integrity failure(s) detected by scans."})

    reqs = db.scalars(
        select(ApprovalRequest).where(ApprovalRequest.record_id == rec.id, ApprovalRequest.version_no == current.version_no)
    ).all()
    approved = sum(1 for r in reqs if r.status == "APPROVED")
    rejected = sum(1 for r in reqs if r.status == "REJECTED")
    if not reqs:
        pts, why = 8, "No reviewers requested yet (partial credit)."
    elif rejected:
        pts, why = 0, f"{rejected} reviewer(s) rejected this version."
    else:
        pts = round(25 * approved / len(reqs))
        why = f"{approved} of {len(reqs)} reviewers approved."
    comps.append({"key": "approvals", "label": "Peer approvals", "max": 25, "points": pts, "why": why})

    pts = round(20 * (1 - current.risk_score / 100))
    comps.append({"key": "risk", "label": "Content risk (inverse)", "max": 20, "points": pts,
                  "why": f"Risk engine score {current.risk_score}/100 ({current.risk_level.lower()})."})

    n = len(versions)
    pts = min(10, 4 + 2 * (n - 1))
    comps.append({"key": "provenance", "label": "Provenance depth", "max": 10, "points": pts,
                  "why": f"{n} version(s) with a continuous on-chain history."})

    owner_approved = db.scalar(
        select(func.count(Record.id)).where(Record.owner_id == rec.owner_id, Record.status == "APPROVED")
    ) or 0
    created_at = rec.owner.created_at

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    
    age_ok = created_at < utcnow() - timedelta(days=1)
    pts = (2 if age_ok else 0) + min(3, owner_approved)
    comps.append({"key": "reputation", "label": "Owner reputation", "max": 5, "points": pts,
                  "why": f"{owner_approved} approved record(s) by this owner" + ("; established account." if age_ok else "; new account.")})

    score = sum(c["points"] for c in comps)
    return {"score": score, "label": label_for(score), "components": comps, "note": None}


def refresh(db: Session, rec: Record) -> dict:
    result = compute(db, rec)
    rec.trust_score = result["score"]
    rec.trust_breakdown = result
    return result
