"""Conexión, creación de la base (solo local) y migraciones al arrancar."""

import logging
from collections.abc import Iterator
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_LOCK_KEY = 8_311_442


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite"):
        # Una sola conexión compartida: la base en memoria vive mientras viva el engine.
        return create_engine(
            database_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_engine(database_url, pool_pre_ping=True, pool_size=5, max_overflow=5)


def ensure_database(database_url: str) -> None:
    """Crea la base si no existe (útil con un volumen local preexistente)."""
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql") or not url.database:
        return
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
            logger.info("base %s creada", url.database)
    admin.dispose()


def migrate(engine: Engine) -> None:
    """Postgres: Alembic bajo advisory lock (seguro con varias instancias). SQLite: create_all."""
    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(engine)
        return
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _MIGRATION_LOCK_KEY})
        try:
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _MIGRATION_LOCK_KEY})


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
