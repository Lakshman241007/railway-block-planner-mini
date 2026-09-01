"""
Unit tests for the Repository layer covering CRUD and specialized queries.
"""

from __future__ import annotations

from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.connection import Base
from backend.app.database.repositories import (
    BlockRepository,
    MaintenanceRepository,
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    BlockType,
    MaintenanceRecord,
    MaintenanceStatus,
    MovementRecord,
    Priority,
    TimetableRecord,
    TrainRecord,
    TrainStatus,
)


@pytest.fixture
def repo_session():
    """Create isolated SQLite database session for repository testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_train_repository(repo_session):
    """Test TrainRepository CRUD operations and status filtering."""
    repo = TrainRepository(repo_session)

    t1 = TrainRecord(
        train_id="T1",
        train_type="Express",
        origin="MAS",
        destination="SBC",
        status=TrainStatus.RUNNING,
    )
    t2 = TrainRecord(
        train_id="T2",
        train_type="Passenger",
        origin="MAS",
        destination="AJJ",
        status=TrainStatus.DELAYED,
    )

    created1 = repo.create(t1)
    created2 = repo.create(t2)
    assert created1.train_id == "T1"
    assert created2.train_id == "T2"

    # Get by ID
    fetched = repo.get_by_id("T1")
    assert fetched is not None
    assert fetched.train_id == "T1"

    # Get non-existent
    assert repo.get_by_id("NONEXISTENT") is None

    # Get all & count
    all_trains = repo.get_all()
    assert len(all_trains) == 2
    assert repo.count() == 2

    # Filter by status
    running_trains = repo.get_all(status="Running")
    assert len(running_trains) == 1
    assert running_trains[0].train_id == "T1"
    assert repo.count(status="Running") == 1

    # Update
    updated = repo.update("T1", {"status": "Delayed", "current_station": "KPD"})
    assert updated is not None
    assert updated.status == "Delayed"
    assert updated.current_station == "KPD"

    # Delete
    assert repo.delete("T1") is True
    assert repo.get_by_id("T1") is None
    assert repo.delete("T1") is False


def test_maintenance_repository(repo_session):
    """Test MaintenanceRepository CRUD and query operations."""
    repo = MaintenanceRepository(repo_session)

    m1 = MaintenanceRecord(
        asset_id="AST-01",
        asset_type="Track",
        location="KM 10-12",
        maintenance_type="Inspection",
        maintenance_required=True,
        priority=Priority.HIGH,
        duration_minutes=60,
        requested_date=date(2026, 9, 5),
        preferred_start="03:00",
        required_resources=2,
        equipment="Track Trolley",
        status=MaintenanceStatus.PENDING,
        source="smms",
    )
    m2 = MaintenanceRecord(
        asset_id="AST-02",
        asset_type="Signal",
        location="MAS Junction",
        maintenance_type="Preventive",
        maintenance_required=True,
        priority=Priority.LOW,
        duration_minutes=30,
        requested_date=date(2026, 9, 6),
        preferred_start="04:00",
        required_resources=1,
        equipment="Signal Toolkit",
        status=MaintenanceStatus.APPROVED,
        source="smms",
    )

    rec1 = repo.create(m1)
    rec2 = repo.create(m2)

    # Get by ID & asset_id
    assert repo.get_by_id(rec1.id) is not None
    assert len(repo.get_by_asset_id("AST-01")) == 1

    # Get all & count
    assert repo.count() == 2
    assert len(repo.get_all(priority="High")) == 1
    assert len(repo.get_all(status="Approved")) == 1

    # Pending
    pending = repo.get_pending()
    assert len(pending) == 1
    assert pending[0].asset_id == "AST-01"

    # Update & Delete
    updated = repo.update(rec1.id, {"status": "Completed"})
    assert updated.status == "Completed"
    assert repo.delete(rec1.id) is True
    assert repo.get_by_id(rec1.id) is None


def test_movement_repository(repo_session):
    """Test MovementRepository CRUD and queries."""
    repo = MovementRepository(repo_session)

    mov = MovementRecord(
        train_id="TR-50",
        route_id="R-1",
        section="MAS-PER",
        direction="Up",
        movement_status="Occupied",
        entry_time="10:00",
        exit_time="10:15",
        line="Main",
        source="coa",
    )

    created = repo.create(mov)
    assert created.id is not None

    by_train = repo.get_by_train_id("TR-50")
    assert len(by_train) == 1

    by_sec = repo.get_by_section("MAS-PER")
    assert len(by_sec) == 1

    assert repo.count(train_id="TR-50") == 1
    assert repo.delete(created.id) is True
    assert repo.get_by_id(created.id) is None


def test_block_repository(repo_session):
    """Test BlockRepository CRUD and filtering."""
    repo = BlockRepository(repo_session)

    blk1 = BlockRecord(
        block_id="BLK-A",
        location="Section Alpha",
        block_type=BlockType.MAINTENANCE,
        requested_date=date(2026, 9, 5),
        requested_start="02:00",
        requested_end="05:00",
        reason="OHE Work",
        priority=Priority.HIGH,
        status="Requested",
        source="bdms",
    )
    blk2 = BlockRecord(
        block_id="BLK-B",
        location="Section Beta",
        block_type=BlockType.EMERGENCY,
        requested_date=date(2026, 9, 6),
        requested_start="06:00",
        requested_end="08:00",
        reason="Signal Fault",
        priority=Priority.CRITICAL,
        status="Approved",
        source="bdms",
    )

    repo.create(blk1)
    repo.create(blk2)

    assert repo.get_by_id("BLK-A") is not None
    assert len(repo.get_by_date("2026-09-05")) == 1
    assert len(repo.get_by_location("Alpha")) == 1
    assert len(repo.get_all(status="Approved")) == 1
    assert repo.count() == 2

    repo.update("BLK-A", {"status": "Approved"})
    assert repo.get_by_id("BLK-A").status == "Approved"

    assert repo.delete("BLK-A") is True
    assert repo.get_by_id("BLK-A") is None


def test_timetable_repository(repo_session):
    """Test TimetableRepository CRUD and train stops query."""
    repo = TimetableRepository(repo_session)

    tt1 = TimetableRecord(
        train_id="T100",
        service_date=date(2026, 9, 5),
        station_code="MAS",
        departure_time="06:00",
        sequence=1,
    )
    tt2 = TimetableRecord(
        train_id="T100",
        service_date=date(2026, 9, 5),
        station_code="AJJ",
        arrival_time="07:00",
        departure_time="07:05",
        sequence=2,
    )

    repo.create(tt1)
    repo.create(tt2)

    stops = repo.get_by_train_id("T100")
    assert len(stops) == 2
    assert stops[0].station_code == "MAS"
    assert stops[1].station_code == "AJJ"

    assert repo.count(train_id="T100") == 2
    assert len(repo.get_all(service_date="2026-09-05")) == 2

    # Delete
    assert repo.delete(stops[0].id) is True
    assert len(repo.get_by_train_id("T100")) == 1
