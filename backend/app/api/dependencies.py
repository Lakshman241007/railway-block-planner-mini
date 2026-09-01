"""
FastAPI dependency injection utilities.

Provides database session lifecycle management for request handlers.
"""

from __future__ import annotations

from typing import Generator

from sqlalchemy.orm import Session

from backend.app.database.connection import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding an isolated database session per request.
    Ensures proper session closure upon request completion.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
