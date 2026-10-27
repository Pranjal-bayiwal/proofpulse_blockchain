import re

from fastapi import Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import Record
from ..services.blockchain import chain
from ..utils import PUBLIC_ID_RE

settings = get_settings()

CATEGORIES = {"document", "dataset", "research", "project", "code", "media", "other"}


def require_chain():
    if chain.contract is None:
        raise HTTPException(503, "Blockchain is not connected. Check the backend log and your blockchain settings.")


def read_upload(file: UploadFile) -> bytes:
    limit = settings.max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds the {settings.max_upload_mb} MB limit")
    if not data:
        raise HTTPException(400, "The uploaded file is empty")
    return data


def clean_text(value: str, name: str, min_len: int, max_len: int) -> str:
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (value or "")).strip()
    if len(value) < min_len:
        raise HTTPException(422, f"{name} must be at least {min_len} characters")
    if len(value) > max_len:
        raise HTTPException(422, f"{name} must be at most {max_len} characters")
    return value


def parse_tags(raw: str) -> list[str]:
    tags = []
    for t in (raw or "").split(","):
        t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE).strip().lower()[:32]
        if t and t not in tags:
            tags.append(t)
    return tags[:10]


def get_record_or_404(public_id: str, db: Session = Depends(get_db)) -> Record:
    rec = None
    if PUBLIC_ID_RE.match(public_id.upper()):
        rec = db.scalar(select(Record).where(Record.public_id == public_id.upper()))
    if not rec:
        raise HTTPException(404, "Record not found")
    return rec
