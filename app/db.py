from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True}


settings = get_settings()
engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - Treiber-Hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def ensure_columns(bind: Engine | None = None) -> None:
    """Notnagel fuer nachtraegliche Spalten. Faellt weg, sobald Alembic da ist.

    `create_all` legt nur fehlende Tabellen an, keine fehlenden Spalten. Ohne das
    hier laeuft jede bestehende Datenbank nach einem Modell-Zuwachs auf einen
    OperationalError.
    """
    bind = bind or engine
    added: list[tuple[str, str, str]] = [
        ("intake_sessions", "context", "JSON"),
        ("requests", "responsible", "VARCHAR(80)"),
        ("requests", "company", "VARCHAR(80)"),
        ("requests", "change_lead", "VARCHAR(80)"),
        ("messages", "field_key", "VARCHAR(80)"),
    ]
    with bind.begin() as conn:
        for table, column, coltype in added:
            if bind.dialect.name == "sqlite":
                rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                if not rows or any(row[1] == column for row in rows):
                    continue
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            else:
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {coltype}"
                )


def ensure_default_actor(bind: Engine | None = None) -> None:
    """Stub-Accounts anlegen und authorenlose Anliegen Justin zuweisen."""
    from app.models import Request
    from app.security import default_actor, ensure_dummy_accounts

    bind = bind or engine
    with Session(bind) as db:
        ensure_dummy_accounts(db)
        actor = default_actor(db)
        orphans = db.scalars(select(Request).where(Request.created_by.is_(None))).all()
        for request in orphans:
            request.created_by = actor.id
        db.commit()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
