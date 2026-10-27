from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ApprovalRequest, Record, RecordVersion, User
from ..schemas import RevokeIn
from ..security import client_ip, get_current_user, get_optional_user, rate_limit
from ..serializers import approval_dict, can_view_full, record_dict, version_dict
from ..services import audit, certificate, registry, storage, trust
from ..services.blockchain import ChainError, actor_id, chain
from ..services.events import manager
from ..utils import sha256_hex
from .common import CATEGORIES, clean_text, get_record_or_404, parse_tags, read_upload, require_chain

router = APIRouter(prefix="/api", tags=["records"])


def _full_or_404(db: Session, rec: Record, user: User) -> None:
    if not can_view_full(db, rec, user):
        raise HTTPException(404, "Record not found")


@router.post("/analyze", dependencies=[Depends(rate_limit("analyze", 60, 600))])
def analyze(file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Dry-run: fingerprint + risk/similarity analysis without registering anything."""
    data = read_upload(file)
    fp, report = registry.analyse_upload(db, user, file.filename or "file", data)
    return {"sha256": fp["sha256"], "filename": file.filename, "size": len(data), "risk": report}


@router.post("/records", status_code=201, dependencies=[Depends(require_chain), Depends(rate_limit("register-record", 60, 600))])
def create_record(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("document"),
    tags: str = Form(""),
    visibility: str = Form("private"),
    store_file: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    title = clean_text(title, "Title", 2, 200)
    description = clean_text(description, "Description", 0, 2000)
    if category not in CATEGORIES:
        raise HTTPException(422, f"Category must be one of: {', '.join(sorted(CATEGORIES))}")
    if visibility not in ("public", "private"):
        raise HTTPException(422, "Visibility must be 'public' or 'private'")
    data = read_upload(file)
    try:
        rec = registry.create_record(
            db, user, filename=file.filename or "file", data=data, mime=file.content_type or "", title=title,
            description=description, category=category, tags=parse_tags(tags), visibility=visibility,
            store_file=store_file, ip=client_ip(request))
    except ChainError as exc:
        raise HTTPException(502, str(exc))
    return record_dict(rec, db, user, detail=True)


@router.get("/records")
def list_records(
    scope: str = Query("mine", pattern="^(mine|reviewing|public|all)$"),
    q: str = "", status: str = "", category: str = "", risk: str = "",
    sort: str = Query("new", pattern="^(new|old|trust|risk)$"),
    page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=50),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    stmt = select(Record)
    if scope == "mine":
        stmt = stmt.where(Record.owner_id == user.id)
    elif scope == "reviewing":
        stmt = stmt.where(Record.id.in_(select(ApprovalRequest.record_id).where(ApprovalRequest.approver_id == user.id)))
    elif scope == "public":
        stmt = stmt.where(Record.visibility == "public")
    elif scope == "all":
        if user.role != "admin":
            raise HTTPException(403, "Administrator access required")
    if q.strip():
        like = f"%{q.strip().lower()}%"
        cond = [func.lower(Record.public_id).like(like), func.lower(Record.title).like(like), func.lower(Record.description).like(like)]
        stmt = stmt.where(or_(*cond))
    if status:
        stmt = stmt.where(Record.status == status.upper())
    if category:
        stmt = stmt.where(Record.category == category)
    if risk:
        sub = select(RecordVersion.record_id).join(Record, Record.id == RecordVersion.record_id).where(
            RecordVersion.version_no == Record.current_version, RecordVersion.risk_level == risk.upper())
        stmt = stmt.where(Record.id.in_(sub))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = {"new": Record.created_at.desc(), "old": Record.created_at.asc(), "trust": Record.trust_score.desc(),
             "risk": Record.trust_score.asc()}[sort]
    rows = db.scalars(stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).unique().all()
    return {"items": [record_dict(r, db, user) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/records/{public_id}")
def get_record(rec: Record = Depends(get_record_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not can_view_full(db, rec, user) and rec.visibility != "public":
        raise HTTPException(404, "Record not found")
    d = record_dict(rec, db, user, detail=True)
    if d["can_manage"]:
        reqs = db.scalars(select(ApprovalRequest).where(ApprovalRequest.record_id == rec.id).order_by(ApprovalRequest.id)).all()
        d["approvals"] = [approval_dict(a) for a in reqs]
    return d


@router.post("/records/{public_id}/versions", status_code=201,
             dependencies=[Depends(require_chain), Depends(rate_limit("version", 60, 600))])
def add_version(
    request: Request,
    rec: Record = Depends(get_record_or_404),
    file: UploadFile = File(...),
    note: str = Form(""),
    store_file: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if rec.owner_id != user.id:
        raise HTTPException(403 if can_view_full(db, rec, user) else 404, "Only the owner can add versions")
    if rec.status == "REVOKED":
        raise HTTPException(409, "This record has been revoked")
    note = clean_text(note, "Change note", 0, 300) or "New version"
    data = read_upload(file)
    try:
        registry.add_version(db, user, rec, filename=file.filename or "file", data=data, mime=file.content_type or "",
                             note=note, store_file=store_file, ip=client_ip(request))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    except ChainError as exc:
        raise HTTPException(502, str(exc))
    db.refresh(rec)
    return record_dict(rec, db, user, detail=True)


@router.get("/records/{public_id}/versions")
def list_versions(rec: Record = Depends(get_record_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _full_or_404(db, rec, user)
    return [version_dict(v, with_risk=True) for v in rec.versions]


@router.get("/records/{public_id}/versions/{version_no}/file")
def download_file(version_no: int, rec: Record = Depends(get_record_or_404), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if not (rec.owner_id == user.id or user.role == "admin"):
        raise HTTPException(404, "Record not found")
    ver = next((v for v in rec.versions if v.version_no == version_no), None)
    if not ver or not ver.stored_path:
        raise HTTPException(404, "No stored copy for this version (only the fingerprint was registered)")
    data = storage.load_decrypted(ver.stored_path)
    if data is None:
        raise HTTPException(500, "Stored copy could not be decrypted")
    ok = sha256_hex(data) == ver.sha256
    audit.log(db, "FILE_DOWNLOADED", user, rec.public_id, {"version": version_no, "integrity_ok": ok})
    return Response(data, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{ver.filename}"', "X-Integrity": "ok" if ok else "FAILED"})


@router.post("/records/{public_id}/integrity")
def check_integrity(rec: Record = Depends(get_record_or_404), user: User = Depends(get_current_user),
                    db: Session = Depends(get_db), _=Depends(require_chain)):
    """Re-hash stored copies and compare with both the database and the chain."""
    if not (rec.owner_id == user.id or user.role == "admin"):
        raise HTTPException(404, "Record not found")
    chain_rec = chain.get_record(rec.public_id)
    results, failures = [], 0
    for v in rec.versions:
        entry = {"version_no": v.version_no, "stored": bool(v.stored_path), "stored_matches": None, "chain_matches": None}
        if chain_rec and v.version_no <= len(chain_rec["versions"]):
            entry["chain_matches"] = chain_rec["versions"][v.version_no - 1]["content_hash"] == v.sha256
        if v.stored_path:
            data = storage.load_decrypted(v.stored_path)
            entry["stored_matches"] = data is not None and sha256_hex(data) == v.sha256
        if entry["chain_matches"] is False or entry["stored_matches"] is False:
            failures += 1
        results.append(entry)
    rec.integrity_failures = failures
    trust.refresh(db, rec)
    db.commit()
    audit.log(db, "INTEGRITY_CHECK", user, rec.public_id, {"failures": failures})
    if failures:
        audit.notify(db, rec.owner_id, "Integrity failure detected", f"{rec.public_id}: {failures} version(s) failed verification.", "danger", rec.public_id)
    return {"ok": failures == 0, "failures": failures, "versions": results}


@router.get("/records/{public_id}/certificate")
def certificate_pdf(version: int | None = None, rec: Record = Depends(get_record_or_404),
                    user: User | None = Depends(get_optional_user), db: Session = Depends(get_db), _=Depends(require_chain)):
    full = can_view_full(db, rec, user)
    if not full and rec.visibility != "public":
        raise HTTPException(404, "Record not found")
    ver = next((v for v in rec.versions if v.version_no == (version or rec.current_version)), None)
    if not ver:
        raise HTTPException(404, "Version not found")
    t = rec.trust_breakdown or trust.compute(db, rec)
    pdf = certificate.build_certificate(rec, ver, t, include_title=True)
    audit.log(db, "CERTIFICATE_ISSUED", user, rec.public_id, {"version": ver.version_no})
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="ProofPulse-{rec.public_id}-v{ver.version_no}.pdf"'})


@router.get("/records/{public_id}/qr.png")
def qr_code(rec: Record = Depends(get_record_or_404)):
    return Response(certificate.qr_png(rec.public_id), media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.post("/records/{public_id}/revoke", dependencies=[Depends(require_chain)])
def revoke(body: RevokeIn, request: Request, rec: Record = Depends(get_record_or_404),
           user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not (rec.owner_id == user.id or user.role == "admin"):
        raise HTTPException(404, "Record not found")
    if rec.status == "REVOKED":
        raise HTTPException(409, "Record is already revoked")
    try:
        anchor = chain.revoke(rec.public_id, actor_id(user.id), sha256_hex(body.reason))
    except ChainError as exc:
        raise HTTPException(502, str(exc))
    rec.status = "REVOKED"
    rec.revoked_reason = body.reason
    trust.refresh(db, rec)
    db.commit()
    audit.log(db, "RECORD_REVOKED", user, rec.public_id, {"reason": body.reason}, anchor["tx_hash"], client_ip(request))
    notify_ids = {rec.owner_id} | {a.approver_id for a in db.scalars(select(ApprovalRequest).where(ApprovalRequest.record_id == rec.id))}
    for uid in notify_ids:
        audit.notify(db, uid, f"{rec.public_id} was revoked", body.reason, "danger", rec.public_id)
    manager.publish("stats", {"reason": "revoked", "record": rec.public_id}, user_ids=None)
    return record_dict(rec, db, user, detail=True)
