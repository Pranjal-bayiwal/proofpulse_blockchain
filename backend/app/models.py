from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    organization: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="user")  # user | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Record(Base):
    __tablename__ = "records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="document")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    visibility: Mapped[str] = mapped_column(String(10), default="private")  # public | private
    status: Mapped[str] = mapped_column(String(24), default="REGISTERED")
    # REGISTERED | PENDING_APPROVAL | APPROVED | REJECTED | REVOKED
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    revoked_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    integrity_failures: Mapped[int] = mapped_column(Integer, default=0)
    trust_score: Mapped[int] = mapped_column(Integer, default=0)
    trust_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    owner: Mapped[User] = relationship(foreign_keys=[owner_id], lazy="joined")
    versions: Mapped[list["RecordVersion"]] = relationship(
        back_populates="record", order_by="RecordVersion.version_no", cascade="all, delete-orphan"
    )


class RecordVersion(Base):
    __tablename__ = "record_versions"
    __table_args__ = (UniqueConstraint("record_id", "version_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    mime: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    metadata_hash: Mapped[str] = mapped_column(String(64))
    text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    minhash: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dhash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(8), default="LOW")
    risk_report: Mapped[dict] = mapped_column(JSON, default=dict)
    change_note: Mapped[str] = mapped_column(String(300), default="")
    stored_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # On-chain anchor
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chain_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    record: Mapped[Record] = relationship(back_populates="versions")
    author: Mapped[User] = relationship(foreign_keys=[created_by], lazy="joined")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (UniqueConstraint("record_id", "version_no", "approver_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("records.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    approver_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(10), default="PENDING")  # PENDING | APPROVED | REJECTED
    comment: Mapped[str] = mapped_column(String(500), default="")
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    block_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    record: Mapped[Record] = relationship(lazy="joined")
    approver: Mapped[User] = relationship(foreign_keys=[approver_id], lazy="joined")
    requester: Mapped[User] = relationship(foreign_keys=[requested_by], lazy="joined")


class AuditLog(Base):
    """Tamper-evident off-chain audit trail: every entry hashes the previous one."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_name: Mapped[str] = mapped_column(String(64), default="system")
    action: Mapped[str] = mapped_column(String(48), index=True)
    record_public_id: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    tx_hash: Mapped[str | None] = mapped_column(String(66), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24), default="info")  # info | success | warning | danger
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(String(400), default="")
    record_public_id: Mapped[str | None] = mapped_column(String(24), nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class VerificationEvent(Base):
    """Every public verification attempt (used for dashboard analytics)."""

    __tablename__ = "verification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_public_id: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    verdict: Mapped[str] = mapped_column(String(24))
    used_file: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
