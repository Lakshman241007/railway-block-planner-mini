"""
Database connection and session management for Railway Block Planner.

Provides SQLAlchemy engine, session factory, base declarative class,
and database initialization utilities. Supports PostgreSQL and SQLite
with environment variable configuration.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ---------------------------------------------------------------------------
# Database URL & Engine Configuration
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./railway_block_planner.db"
)

# Connect args specific to SQLite for multithreaded access
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


# ---------------------------------------------------------------------------
# Session Helpers
# ---------------------------------------------------------------------------

def get_db_session() -> Session:
    """Create and return a new database session."""
    return SessionLocal()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions with automatic commit/rollback.

    Yields
    ------
    Session
        SQLAlchemy database session.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(bind_engine=None) -> None:
    """
    Create all database tables defined in SQLAlchemy models.

    Parameters
    ----------
    bind_engine : Engine, optional
        Custom engine to bind metadata creation against (e.g. in tests).
    """
    # Ensure all models are imported so Base.metadata has table definitions
    from backend.app.database import models  # noqa: F401

    target_engine = bind_engine or engine
    Base.metadata.create_all(bind=target_engine)


def reset_db(bind_engine=None) -> None:
    """Drop and recreate all database tables."""
    from backend.app.database import models  # noqa: F401

    target_engine = bind_engine or engine
    Base.metadata.drop_all(bind=target_engine)
    Base.metadata.create_all(bind=target_engine)
