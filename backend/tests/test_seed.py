"""
Unit tests for Phase 3 database seeding from Phase 2 integration output.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.connection import Base
from backend.app.database.models import (
    Block,
    Maintenance,
    Movement,
    Timetable,
    Train,
)
from backend.app.database.seed import seed_database


@pytest.fixture
def seed_session():
    """Isolated database session for seed tests."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_seed_database_execution(seed_session):
    """Verify that seed_database populates all tables with expected record counts."""
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"

    stats = seed_database(data_dir=data_dir, session=seed_session)

    # Check stats returned
    assert stats["unified_trains"] > 0
    assert stats["unified_maintenance"] > 0
    assert stats["unified_movements"] > 0
    assert stats["unified_blocks"] > 0
    assert stats["unified_timetable"] > 0

    # Query DB to verify persistence
    train_count = seed_session.query(Train).count()
    maint_count = seed_session.query(Maintenance).count()
    move_count = seed_session.query(Movement).count()
    block_count = seed_session.query(Block).count()
    tt_count = seed_session.query(Timetable).count()

    assert train_count == stats["unified_trains"]
    assert maint_count == stats["unified_maintenance"]
    assert move_count == stats["unified_movements"]
    assert block_count == stats["unified_blocks"]
    assert tt_count == stats["unified_timetable"]


def test_seed_database_idempotent(seed_session):
    """Verify that running seed twice does not create duplicate entries."""
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / "data"

    # First run
    seed_database(data_dir=data_dir, session=seed_session)
    train_count_1 = seed_session.query(Train).count()
    block_count_1 = seed_session.query(Block).count()

    # Second run without reset
    seed_database(data_dir=data_dir, session=seed_session)
    train_count_2 = seed_session.query(Train).count()
    block_count_2 = seed_session.query(Block).count()

    assert train_count_1 == train_count_2
    assert block_count_1 == block_count_2
