"""Database engine, session, and vector helpers."""

from collections.abc import Generator
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.debug and settings.app_env == "development",
    pool_pre_ping=True,
)


def init_db() -> None:
    """Create tables and enable pgvector when available."""
    try:
        with engine.begin() as conn:
            try:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            except Exception:
                # SQLite / local test DBs may not support pgvector
                pass
        SQLModel.metadata.create_all(engine)
    except Exception as exc:
        import logging

        logging.getLogger("resolveai").warning("init_db deferred (DB unavailable): %s", exc)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def get_session_context() -> Session:
    return Session(engine)


def tenant_query(session: Session, model, tenant_id, *, extra_filters: Optional[list] = None):
    """Always scope queries to a tenant."""
    q = session.query(model).filter(model.tenant_id == tenant_id)
    if extra_filters:
        for f in extra_filters:
            q = q.filter(f)
    return q
