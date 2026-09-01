"""
Unit tests for database connection, session lifecycle, and SQLAlchemy models.
"""

from __future__ import annotations

from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.database.connection import Base
from backend.app.database.models import (
    Block,
    Maintenance,
    Movement,
    Timetable,
    Train,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    BlockType,
    MaintenanceRecord,
    MovementRecord,
    Priority,
    TimetableRecord,
    TrainRecord,
    TrainStatus,
)


@pytest.fixture
def db_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_train_model_crud(db_session):
    """Test Train ORM model creation, persistence, and conversion methods."""
    train = Train(
        train_id="T101",
        train_type="Express",
        origin="MAS",
        destination="SBC",
        status="Running",
        current_station="AJJ",
        next_station="KPD",
        route_id="R-MAS-SBC",
        priority="High",
        scheduled_arrival="10:00",
        scheduled_departure="10:05",
        source="tms,tdms",
    )
    db_session.add(train)
    db_session.commit()

    fetched = db_session.query(Train).filter(Train.train_id == "T101").first()
    assert fetched is not None
    assert fetched.train_id == "T101"
    assert fetched.status == "Running"

    # Test dictionary and pydantic conversion
    d = fetched.to_dict()
    assert d["train_id"] == "T101"
    pyd = fetched.to_pydantic()
    assert isinstance(pyd, TrainRecord)
    assert pyd.train_id == "T101"


def test_maintenance_model_crud(db_session):
    """Test Maintenance ORM model creation and schema conversion."""
    maint = Maintenance(
        asset_id="TRK-MAS-01",
        asset_type="Track",
        location="MAS Yard",
        maintenance_type="Preventive",
        maintenance_required=True,
        priority="Critical",
        duration_minutes=120,
        requested_date=date(2026, 9, 5),
        preferred_start="02:00",
        required_resources=4,
        equipment="Tamping Machine",
        status="Pending",
        source="smms",
    )
    db_session.add(maint)
    db_session.commit()

    fetched = db_session.query(Maintenance).filter(Maintenance.asset_id == "TRK-MAS-01").first()
    assert fetched is not None
    assert fetched.duration_minutes == 120
    assert fetched.priority == "Critical"

    pyd = fetched.to_pydantic()
    assert isinstance(pyd, MaintenanceRecord)
    assert pyd.asset_id == "TRK-MAS-01"


def test_movement_model_crud(db_session):
    """Test Movement ORM model creation and schema conversion."""
    mov = Movement(
        train_id="12626",
        route_id="MAS-NDLS",
        section="MAS-BBQ",
        direction="Up",
        movement_status="Occupied",
        entry_time="08:00",
        exit_time="08:15",
        line="Main Line",
        source="coa",
    )
    db_session.add(mov)
    db_session.commit()

    fetched = db_session.query(Movement).filter(Movement.train_id == "12626").first()
    assert fetched is not None
    assert fetched.section == "MAS-BBQ"

    pyd = fetched.to_pydantic()
    assert isinstance(pyd, MovementRecord)
    assert pyd.train_id == "12626"


def test_block_model_crud(db_session):
    """Test Block ORM model creation and schema conversion."""
    blk = Block(
        block_id="BLK-001",
        location="KM35-37",
        block_type="Maintenance",
        requested_date=date(2026, 9, 5),
        requested_start="01:00",
        requested_end="04:00",
        reason="Track Renewal",
        priority="High",
        status="Requested",
        source="bdms",
    )
    db_session.add(blk)
    db_session.commit()

    fetched = db_session.query(Block).filter(Block.block_id == "BLK-001").first()
    assert fetched is not None
    assert fetched.location == "KM35-37"

    pyd = fetched.to_pydantic()
    assert isinstance(pyd, BlockRecord)
    assert pyd.block_id == "BLK-001"


def test_timetable_model_and_constraint(db_session):
    """Test Timetable model and uniqueness constraint."""
    tt1 = Timetable(
        train_id="12626",
        service_date=date(2026, 9, 5),
        station_code="MAS",
        departure_time="08:00",
        platform=1,
        sequence=1,
        source="timetable",
    )
    db_session.add(tt1)
    db_session.commit()

    fetched = db_session.query(Timetable).filter(Timetable.train_id == "12626").first()
    assert fetched is not None
    assert fetched.station_code == "MAS"

    pyd = fetched.to_pydantic()
    assert isinstance(pyd, TimetableRecord)
    assert pyd.sequence == 1

    # Attempting to insert duplicate sequence for same train and date should violate unique constraint
    tt2 = Timetable(
        train_id="12626",
        service_date=date(2026, 9, 5),
        station_code="MAS-ALT",
        sequence=1,
        source="timetable",
    )
    db_session.add(tt2)
    with pytest.raises(IntegrityError):
        db_session.commit()
