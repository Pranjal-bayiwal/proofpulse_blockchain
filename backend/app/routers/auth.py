from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..models import User
from ..schemas import LoginIn, PasswordChangeIn, RegisterIn
from ..security import (burn_password_time, client_ip, create_access_token, get_current_user, hash_password,
                        rate_limit, verify_password)
from ..serializers import user_brief, user_dict
from ..services import audit
from ..utils import utcnow

router = APIRouter(prefix="/api", tags=["auth"])
settings = get_settings()


@router.post("/auth/register", status_code=201, dependencies=[Depends(rate_limit("register", 10, 3600))])
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)):
    exists = db.scalar(select(User.id).where(
        or_(func.lower(User.username) == body.username.lower(), func.lower(User.email) == body.email.lower())))
    if exists:
        raise HTTPException(409, "That username or email is already registered")
    user = User(username=body.username, email=body.email.lower(), full_name=body.full_name,
                organization=body.organization, password_hash=hash_password(body.password), role="user")
    db.add(user)
    db.commit()
    audit.log(db, "USER_REGISTERED", user, details={"username": user.username}, ip=client_ip(request))
    return {"token": create_access_token(user), "user": user_dict(user)}


@router.post("/auth/login", dependencies=[Depends(rate_limit("login", 30, 300))])
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)):
    ident = body.identifier.strip().lower()
    user = db.scalar(select(User).where(or_(func.lower(User.username) == ident, func.lower(User.email) == ident)))
    generic = HTTPException(401, "Incorrect username/email or password")
    if not user:
        burn_password_time(body.password)
        raise generic
    if user.locked_until and user.locked_until > utcnow():
        mins = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(423, f"Account temporarily locked after repeated failures. Try again in about {mins} min.")
    if not verify_password(body.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.max_failed_logins:
            user.locked_until = utcnow() + timedelta(minutes=settings.lockout_minutes)
            user.failed_attempts = 0
            db.commit()
            audit.log(db, "ACCOUNT_LOCKED", user, details={"minutes": settings.lockout_minutes}, ip=client_ip(request))
        else:
            db.commit()
        raise generic
    if not user.is_active:
        raise HTTPException(403, "This account has been deactivated")
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login = utcnow()
    db.commit()
    audit.log(db, "LOGIN", user, ip=client_ip(request))
    return {"token": create_access_token(user), "user": user_dict(user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)):
    return user_dict(user)


@router.put("/auth/password")
def change_password(body: PasswordChangeIn, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    audit.log(db, "PASSWORD_CHANGED", user, ip=client_ip(request))
    return {"ok": True}


@router.get("/users/search")
def search_users(q: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = q.strip().lower()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    rows = db.scalars(select(User).where(
        User.is_active.is_(True), User.id != user.id,
        or_(func.lower(User.username).like(like), func.lower(User.full_name).like(like))).limit(8)).all()
    return [user_brief(u) for u in rows]
