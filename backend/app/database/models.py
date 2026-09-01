"""
SQLAlchemy ORM models representing unified railway domain entities.

These models correspond directly to the canonical Pydantic schemas in
``backend.app.schemas.unified_data`` and persist the unified outputs
produced by the Phase 2 multi-source integration pipeline.
"""

from __future__ import annotations

from datetime import datetime, date, time
from typing import Any, Dict

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)

from backend.app.database.connection import Base
from backend.app.schemas.unified_data import (
    BlockRecord,
    MaintenanceRecord,
    MovementRecord,
    TimetableRecord,
    TrainRecord,
)


class Train(Base):
    """
    Persistent model representing a train's operational state.
    """

    __tablename__ = "trains"

    train_id = Column(String(50), primary_key=True, index=True, nullable=False)
    train_type = Column(String(50), nullable=False)
    origin = Column(String(50), nullable=False)
    destination = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False, index=True)

    current_station = Column(String(50), nullable=True)
    next_station = Column(String(50), nullable=True)
    route_id = Column(String(50), nullable=True)
    priority = Column(String(20), nullable=True)

    scheduled_arrival = Column(String(20), nullable=True)
    scheduled_departure = Column(String(20), nullable=True)
    actual_arrival = Column(String(20), nullable=True)
    actual_departure = Column(String(20), nullable=True)
    expected_arrival = Column(String(20), nullable=True)
    expected_departure = Column(String(20), nullable=True)

    source = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "train_id": self.train_id,
            "train_type": self.train_type,
            "origin": self.origin,
            "destination": self.destination,
            "status": self.status,
            "current_station": self.current_station,
            "next_station": self.next_station,
            "route_id": self.route_id,
            "priority": self.priority,
            "scheduled_arrival": self.scheduled_arrival,
            "scheduled_departure": self.scheduled_departure,
            "actual_arrival": self.actual_arrival,
            "actual_departure": self.actual_departure,
            "expected_arrival": self.expected_arrival,
            "expected_departure": self.expected_departure,
            "source": self.source,
        }

    def to_pydantic(self) -> TrainRecord:
        """Convert ORM model to unified Pydantic schema."""
        return TrainRecord(**self.to_dict())

    def __repr__(self) -> str:
        return f"<Train(train_id={self.train_id!r}, status={self.status!r})>"


class Maintenance(Base):
    """
    Persistent model representing a maintenance request or requirement.
    """

    __tablename__ = "maintenance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    asset_id = Column(String(50), index=True, nullable=False)
    asset_type = Column(String(50), nullable=False)
    location = Column(String(100), index=True, nullable=False)
    maintenance_type = Column(String(50), nullable=False)
    maintenance_required = Column(Boolean, nullable=False, default=True)
    priority = Column(String(20), index=True, nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    requested_date = Column(Date, index=True, nullable=False)
    preferred_start = Column(String(20), nullable=False)
    required_resources = Column(Integer, nullable=False)
    equipment = Column(String(100), nullable=False)
    status = Column(String(20), index=True, nullable=False)

    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "asset_type": self.asset_type,
            "location": self.location,
            "maintenance_type": self.maintenance_type,
            "maintenance_required": self.maintenance_required,
            "priority": self.priority,
            "duration_minutes": self.duration_minutes,
            "requested_date": self.requested_date.isoformat() if isinstance(self.requested_date, (date, datetime)) else str(self.requested_date),
            "preferred_start": self.preferred_start,
            "required_resources": self.required_resources,
            "equipment": self.equipment,
            "status": self.status,
            "source": self.source,
        }

    def to_pydantic(self) -> MaintenanceRecord:
        """Convert ORM model to unified Pydantic schema."""
        data = self.to_dict()
        data.pop("id", None)
        return MaintenanceRecord(**data)

    def __repr__(self) -> str:
        return f"<Maintenance(asset_id={self.asset_id!r}, priority={self.priority!r}, status={self.status!r})>"


class Movement(Base):
    """
    Persistent model representing a section movement / occupancy state.
    """

    __tablename__ = "movements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    train_id = Column(String(50), index=True, nullable=False)
    route_id = Column(String(50), nullable=False)
    section = Column(String(100), index=True, nullable=False)
    direction = Column(String(20), nullable=False)
    movement_status = Column(String(30), nullable=False)
    entry_time = Column(String(20), nullable=False)
    exit_time = Column(String(20), nullable=False)
    line = Column(String(50), nullable=False)

    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "train_id": self.train_id,
            "route_id": self.route_id,
            "section": self.section,
            "direction": self.direction,
            "movement_status": self.movement_status,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
            "line": self.line,
            "source": self.source,
        }

    def to_pydantic(self) -> MovementRecord:
        """Convert ORM model to unified Pydantic schema."""
        data = self.to_dict()
        data.pop("id", None)
        return MovementRecord(**data)

    def __repr__(self) -> str:
        return f"<Movement(train_id={self.train_id!r}, section={self.section!r})>"


class Block(Base):
    """
    Persistent model representing a block / disconnection request.
    """

    __tablename__ = "blocks"

    block_id = Column(String(50), primary_key=True, index=True, nullable=False)
    location = Column(String(100), index=True, nullable=False)
    block_type = Column(String(50), nullable=False)
    requested_date = Column(Date, index=True, nullable=False)
    requested_start = Column(String(20), nullable=False)
    requested_end = Column(String(20), nullable=False)
    reason = Column(String(255), nullable=False)
    priority = Column(String(20), nullable=False)
    status = Column(String(20), index=True, nullable=False)

    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "block_id": self.block_id,
            "location": self.location,
            "block_type": self.block_type,
            "requested_date": self.requested_date.isoformat() if isinstance(self.requested_date, (date, datetime)) else str(self.requested_date),
            "requested_start": self.requested_start,
            "requested_end": self.requested_end,
            "reason": self.reason,
            "priority": self.priority,
            "status": self.status,
            "source": self.source,
        }

    def to_pydantic(self) -> BlockRecord:
        """Convert ORM model to unified Pydantic schema."""
        return BlockRecord(**self.to_dict())

    def __repr__(self) -> str:
        return f"<Block(block_id={self.block_id!r}, location={self.location!r}, status={self.status!r})>"


class Timetable(Base):
    """
    Persistent model representing a scheduled stop in a train's timetable.
    """

    __tablename__ = "timetable"
    __table_args__ = (
        UniqueConstraint("train_id", "service_date", "sequence", name="uq_train_service_seq"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    train_id = Column(String(50), index=True, nullable=False)
    service_date = Column(Date, index=True, nullable=False)
    station_code = Column(String(20), nullable=False)
    arrival_time = Column(String(20), nullable=True)
    departure_time = Column(String(20), nullable=True)
    platform = Column(Integer, nullable=True)
    sequence = Column(Integer, nullable=False)

    source = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> Dict[str, Any]:
        """Convert ORM model to dictionary."""
        return {
            "id": self.id,
            "train_id": self.train_id,
            "service_date": self.service_date.isoformat() if isinstance(self.service_date, (date, datetime)) else str(self.service_date),
            "station_code": self.station_code,
            "arrival_time": self.arrival_time,
            "departure_time": self.departure_time,
            "platform": self.platform,
            "sequence": self.sequence,
            "source": self.source,
        }

    def to_pydantic(self) -> TimetableRecord:
        """Convert ORM model to unified Pydantic schema."""
        data = self.to_dict()
        data.pop("id", None)
        return TimetableRecord(**data)

    def __repr__(self) -> str:
        return f"<Timetable(train_id={self.train_id!r}, station={self.station_code!r}, seq={self.sequence})>"
