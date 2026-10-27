import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models  # noqa: F401  (register tables)
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .models import Record, User
from .routers import admin, approvals, audit, auth, dashboard, notifications, records, verify
from .security import hash_password, user_from_token
from .services import anchor
from .services import audit as audit_service
from .services.blockchain import ChainError, chain
from .services.events import manager

log = logging.getLogger("proofpulse")
settings = get_settings()


def seed_admin() -> None:
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == "admin").limit(1)):
            return
        admin_user = User(username=settings.admin_username, email=settings.admin_email.lower(), full_name=settings.admin_full_name,
                          password_hash=hash_password(settings.admin_password), role="admin")
        db.add(admin_user)
        db.commit()
        audit_service.log(db, "ADMIN_SEEDED", admin_user, details={"username": admin_user.username})
        log.warning("Seeded administrator '%s'. Change the password after first login.", admin_user.username)


def connect_chain() -> None:
    try:
        chain.connect()
        log.info("Blockchain connected (%s) contract=%s", chain.mode, chain.contract.address)
        if chain.freshly_deployed and settings.auto_reanchor:
            with SessionLocal() as db:
                if db.scalar(select(func.count(Record.id))):
                    result = anchor.reanchor_all(db)
                    audit_service.log(db, "REANCHORED", None, details=result)
                    log.info("Fresh chain: re-anchored %s", result)
    except ChainError as exc:
        log.error("Blockchain unavailable: %s", exc)
    except Exception as exc:  # pragma: no cover
        log.exception("Blockchain setup failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    seed_admin()
    manager.loop = asyncio.get_running_loop()
    await asyncio.get_running_loop().run_in_executor(None, connect_chain)
    yield


app = FastAPI(title="ProofPulse API", version="1.0.0", lifespan=lifespan,
              description="AI-powered blockchain authenticity & provenance platform")

app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=False,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"],
                   expose_headers=["Content-Disposition", "X-Integrity"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(ChainError)
async def chain_error_handler(request: Request, exc: ChainError):
    return JSONResponse({"detail": str(exc)}, status_code=502)


for r in (auth, records, verify, approvals, audit, notifications, dashboard, admin):
    app.include_router(r.router)


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    st = chain.status() if chain.contract else {"connected": False}
    return {"status": "ok" if st.get("connected") else "degraded", "database": "ok", "blockchain": st}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: str = ""):
    with SessionLocal() as db:
        user = user_from_token(db, token)
        if not user:
            await ws.close(code=4401)
            return
        uid, is_admin = user.id, user.role == "admin"
    await manager.connect(ws, uid, is_admin)
    try:
        await ws.send_text('{"event":"connected","data":{}}')
        while True:
            await ws.receive_text()  # keep-alive pings from the client
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(ws, uid)
