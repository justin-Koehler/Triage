"""FastAPI-Einstieg. Eigene DB = Wahrheit, Static UI, Outbox im Hintergrund."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api import auth, jira_lookup, requests, sessions
from app.api import settings as settings_api
from app.config import get_settings
from app.db import Base, SessionLocal, engine, ensure_columns, ensure_default_actor, get_db
from app.ports import get_ticket_port
from app.security import read_session
from app.services.settings_service import get_runtime_config
from app.sync.outbox import process_pending

log = logging.getLogger("triage")


class _JsonLog(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    if get_settings().app_env == "dev":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(_JsonLog())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_logging()


async def _outbox_loop(stop: asyncio.Event) -> None:
    settings = get_settings()
    while not stop.is_set():
        try:
            get_ticket_port.cache_clear()
            port = get_ticket_port()
            with SessionLocal() as db:
                stats = process_pending(db, port)
                if any(stats.values()):
                    log.info("outbox %s", stats)
        except Exception:
            log.exception("outbox poll fehlgeschlagen")
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.outbox_poll_seconds)
        except TimeoutError:
            continue


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Models registrieren
    import app.models  # noqa: F401

    settings = get_settings()
    # SQLite: create_all für lokale Dev/Tests. Postgres: Schema kommt von Alembic.
    if settings.is_sqlite:
        Base.metadata.create_all(bind=engine)
        ensure_columns(engine)
    ensure_default_actor(engine)
    stop = asyncio.Event()
    task = asyncio.create_task(_outbox_loop(stop))
    log.info("CRITR ready (%s)", settings.llm_label)
    try:
        yield
    finally:
        stop.set()
        try:
            await asyncio.wait_for(task, timeout=25)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()


app = FastAPI(title="CRITR", lifespan=lifespan)

_PUBLIC_EXACT = {
    "/login",
    "/api/live",
    "/api/ready",
    "/api/health",
    "/api/auth/me",
    "/api/auth/config",
    "/api/auth/login",
    "/api/auth/logout",
    "/styles.css",
    "/favicon.ico",
}


def _is_public(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    if path.startswith("/api/auth/cidaas"):
        return True
    if path.startswith("/aufwand/"):
        return True
    if path.startswith("/static/"):
        return True
    return path.endswith((".css", ".js", ".ico", ".png", ".svg", ".woff2"))


@app.middleware("http")
async def cidaas_gate(request: Request, call_next):
    settings = get_settings()
    if not settings.cidaas_enabled:
        return await call_next(request)
    if request.method == "OPTIONS" or _is_public(request.url.path):
        return await call_next(request)
    token = request.cookies.get(settings.session_cookie)
    if token and read_session(token, settings):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Anmeldung erforderlich"}, status_code=401)
    nxt = request.url.path
    if request.url.query:
        nxt = f"{nxt}?{request.url.query}"
    return RedirectResponse(url=f"/login?next={quote(nxt, safe='')}", status_code=302)


@app.get("/api/live")
def live() -> dict:
    """Liveness: Prozess lebt, ohne DB."""
    return {"ok": True}


@app.get("/api/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Readiness inkl. DB und Runtime-Info."""
    settings = get_settings()
    runtime = get_runtime_config(db)
    db.execute(text("SELECT 1"))
    return {
        "ok": True,
        "env": settings.app_env,
        "llm": runtime.llm_label,
        "ticketPort": runtime.ticket_port,
    }


@app.get("/api/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    """Alias für Readiness-Probes."""
    return health(db)


app.include_router(auth.router)
app.include_router(sessions.router)
app.include_router(sessions.share_router)
app.include_router(requests.router)
app.include_router(settings_api.router)
app.include_router(jira_lookup.router)

settings = get_settings()
STATIC = settings.legacy_static
NO_STORE = {"Cache-Control": "no-store"}


def _html(name: str) -> FileResponse:
    return FileResponse(STATIC / name, headers=NO_STORE)


def _asset(name: str, media_type: str) -> FileResponse:
    return FileResponse(STATIC / name, media_type=media_type, headers=NO_STORE)


@app.get("/login")
def login_page() -> FileResponse:
    return _html("login.html")


@app.get("/")
def index() -> FileResponse:
    return _html("workspace.html")


@app.get("/settings")
def settings_page() -> FileResponse:
    return _html("settings.html")


@app.get("/workspace")
def workspace_page() -> FileResponse:
    return _html("workspace.html")


@app.get("/workspace/{request_id}")
def workspace_detail_page(request_id: str) -> FileResponse:
    # Tiefer Link, das Panel oeffnet workspace.js anhand der URL.
    return _html("workspace.html")


@app.get("/effort-sheet")
def effort_sheet_editor() -> FileResponse:
    return _html("effort-sheet.html")


@app.get("/effort-sheet.js")
def effort_sheet_js() -> FileResponse:
    return _asset("effort-sheet.js", "application/javascript")


@app.get("/auth.js")
def auth_js() -> FileResponse:
    return _asset("auth.js", "application/javascript")


@app.get("/app.js")
def app_js() -> FileResponse:
    return _asset("app.js", "application/javascript")


@app.get("/settings.js")
def settings_js() -> FileResponse:
    return _asset("settings.js", "application/javascript")


@app.get("/workspace.js")
def workspace_js() -> FileResponse:
    return _asset("workspace.js", "application/javascript")


@app.get("/styles.css")
def styles() -> FileResponse:
    return _asset("styles.css", "text/css")


# Dateien unter /static nur als Fallback
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
