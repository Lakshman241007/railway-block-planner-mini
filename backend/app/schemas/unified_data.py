"""
Unified Data Schema for Railway Block Planner.

This module defines the canonical data models used across the entire
railway block planning system. All data sources (SMMS, TMS, TDMS, COA,
BDMS, etc.) are normalized into these unified models before being used
by downstream modules such as the scheduler, conflict detector, or
optimizer.

The MaintenanceRecord model is the central contract:
    Source CSV → Collector → Validator → Normalizer → MaintenanceRecord

Any future data source must ultimately produce MaintenanceRecord objects
so that downstream consumers remain source-agnostic.
"""

from __future__ import annotations

from datetime import date, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    """Allowed maintenance priority levels, ordered by urgency."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class MaintenanceStatus(str, Enum):
    """Allowed lifecycle statuses for a maintenance record."""
    PENDING = "Pending"
    APPROVED = "Approved"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


# ---------------------------------------------------------------------------
# Unified Maintenance Record
# ---------------------------------------------------------------------------

class MaintenanceRecord(BaseModel):
    """
    Canonical representation of a single maintenance activity.

    Every data source must normalize its records into this model.
    The schema is intentionally kept generic so that future sources
    (TMS, TDMS, COA, BDMS, timetable data, etc.) can coexist with
    the same downstream pipeline.

    Attributes:
        asset_id:               Unique identifier for the railway asset.
        asset_type:             Category of the asset (Track, Signal, Bridge, …).
        location:               Human-readable location or section description.
        maintenance_type:       Kind of maintenance (Preventive, Repair, …).
        maintenance_required:   Whether maintenance is actually needed.
        priority:               Urgency level.
        duration_minutes:       Expected duration of the work in minutes.
        requested_date:         Date the maintenance was requested for.
        preferred_start:        Preferred start time on that date.
        required_resources:     Number of personnel / resource units required.
        equipment:              Equipment needed for the maintenance.
        status:                 Current lifecycle status of the request.
        source:                 Name of the originating data source.
    """

    asset_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the railway asset",
    )
    asset_type: str = Field(
        ...,
        min_length=1,
        description="Category of the asset (e.g. Track, Signal, Bridge)",
    )
    location: str = Field(
        ...,
        min_length=1,
        description="Human-readable location or section description",
    )
    maintenance_type: str = Field(
        ...,
        min_length=1,
        description="Kind of maintenance (e.g. Preventive, Repair, Inspection)",
    )
    maintenance_required: bool = Field(
        ...,
        description="Whether maintenance is actually needed",
    )
    priority: Priority = Field(
        ...,
        description="Urgency level of the maintenance request",
    )
    duration_minutes: int = Field(
        ...,
        gt=0,
        description="Expected duration of the work in minutes",
    )
    requested_date: date = Field(
        ...,
        description="Date the maintenance was requested for",
    )
    preferred_start: time = Field(
        ...,
        description="Preferred start time on the requested date",
    )
    required_resources: int = Field(
        ...,
        gt=0,
        description="Number of personnel / resource units required",
    )
    equipment: str = Field(
        ...,
        min_length=1,
        description="Equipment needed for the maintenance",
    )
    status: MaintenanceStatus = Field(
        ...,
        description="Current lifecycle status of the request",
    )
    source: Optional[str] = Field(
        default=None,
        description="Name of the originating data source (e.g. 'smms')",
    )

    # --- extra validators -------------------------------------------------

    @field_validator("duration_minutes")
    @classmethod
    def duration_must_be_positive(cls, value: int) -> int:
        """Ensure duration is a positive integer."""
        if value <= 0:
            raise ValueError("duration_minutes must be a positive integer")
        return value

    @field_validator("required_resources")
    @classmethod
    def resources_must_be_positive(cls, value: int) -> int:
        """Ensure required_resources is a positive integer."""
        if value <= 0:
            raise ValueError("required_resources must be a positive integer")
        return value

    model_config = {
        "str_strip_whitespace": True,
    }


# ---------------------------------------------------------------------------
# Phase 2 — Additional Enumerations
# ---------------------------------------------------------------------------

class TrainStatus(str, Enum):
    """Allowed operational statuses for a train."""
    RUNNING = "Running"
    DELAYED = "Delayed"
    SCHEDULED = "Scheduled"
    TERMINATED = "Terminated"
    CANCELLED = "Cancelled"


class BlockStatus(str, Enum):
    """Allowed statuses for a block/disconnection request."""
    REQUESTED = "Requested"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


class BlockType(str, Enum):
    """Types of block/disconnection."""
    MAINTENANCE = "Maintenance"
    EMERGENCY = "Emergency"
    NON_INTERLOCKED = "Non-Interlocked"
    TRAFFIC = "Traffic"


# ---------------------------------------------------------------------------
# Phase 2 — Unified Train Record (TMS / TDMS)
# ---------------------------------------------------------------------------

class TrainRecord(BaseModel):
    """
    Canonical representation of a train's operational state.

    Produced by normalizing TMS and/or TDMS data.  When records from
    both sources refer to the same ``train_id``, they may be merged
    by the Merger.
    """

    train_id: str = Field(..., min_length=1, description="Unique train identifier")
    train_type: str = Field(..., min_length=1, description="Goods, Passenger, etc.")
    origin: str = Field(..., min_length=1, description="Origin station")
    destination: str = Field(..., min_length=1, description="Destination station")
    status: TrainStatus = Field(..., description="Current operational status")

    # Optional fields — may come from TMS, TDMS, or both
    current_station: Optional[str] = Field(default=None, description="Station the train is currently at")
    next_station: Optional[str] = Field(default=None, description="Next station in the journey")
    route_id: Optional[str] = Field(default=None, description="Route identifier (from TDMS)")
    priority: Optional[Priority] = Field(default=None, description="Operational priority (from TDMS)")

    scheduled_arrival: Optional[str] = Field(default=None, description="Scheduled arrival time (HH:MM)")
    scheduled_departure: Optional[str] = Field(default=None, description="Scheduled departure time (HH:MM)")
    actual_arrival: Optional[str] = Field(default=None, description="Actual arrival time (HH:MM)")
    actual_departure: Optional[str] = Field(default=None, description="Actual departure time (HH:MM)")
    expected_arrival: Optional[str] = Field(default=None, description="Expected arrival (TDMS)")
    expected_departure: Optional[str] = Field(default=None, description="Expected departure (TDMS)")

    source: Optional[str] = Field(default=None, description="Originating data source(s)")

    model_config = {"str_strip_whitespace": True}


# ---------------------------------------------------------------------------
# Phase 2 — Unified Movement Record (COA)
# ---------------------------------------------------------------------------

class MovementRecord(BaseModel):
    """
    Canonical representation of a corridor/section movement.

    Produced by normalizing COA data.  Describes whether a particular
    section of track is occupied, clear, or approaching.
    """

    train_id: str = Field(..., min_length=1, description="Train using this section")
    route_id: str = Field(..., min_length=1, description="Route identifier")
    section: str = Field(..., min_length=1, description="Track section (e.g. Chennai-Perambur)")
    direction: str = Field(..., min_length=1, description="Up or Down direction")
    movement_status: str = Field(..., min_length=1, description="Occupied, Clear, Approaching, Scheduled")
    entry_time: str = Field(..., description="Entry time into the section (HH:MM)")
    exit_time: str = Field(..., description="Exit time from the section (HH:MM)")
    line: str = Field(..., min_length=1, description="Main line or Loop")

    source: Optional[str] = Field(default=None, description="Originating data source")

    model_config = {"str_strip_whitespace": True}


# ---------------------------------------------------------------------------
# Phase 2 — Unified Block Record (BDMS)
# ---------------------------------------------------------------------------

class BlockRecord(BaseModel):
    """
    Canonical representation of a block/disconnection request.

    Produced by normalizing BDMS data.  Represents a planned or
    requested block on a section of railway for maintenance or other
    purposes.
    """

    block_id: str = Field(..., min_length=1, description="Unique block request identifier")
    location: str = Field(..., min_length=1, description="Location or section for the block")
    block_type: BlockType = Field(..., description="Type of block")
    requested_date: date = Field(..., description="Date the block is requested for")
    requested_start: str = Field(..., description="Requested start time (HH:MM)")
    requested_end: str = Field(..., description="Requested end time (HH:MM)")
    reason: str = Field(..., min_length=1, description="Reason for the block request")
    priority: Priority = Field(..., description="Priority of the block request")
    status: BlockStatus = Field(..., description="Current status of the block request")

    source: Optional[str] = Field(default=None, description="Originating data source")

    model_config = {"str_strip_whitespace": True}


# ---------------------------------------------------------------------------
# Phase 2 — Unified Timetable Record
# ---------------------------------------------------------------------------

class TimetableRecord(BaseModel):
    """
    Canonical representation of a single timetable entry.

    Each record represents one train's stop at one station.
    Multiple records form the full journey of a train.
    """

    train_id: str = Field(..., min_length=1, description="Train identifier")
    service_date: date = Field(..., description="Date of service")
    station_code: str = Field(..., min_length=1, description="Station code")
    arrival_time: Optional[str] = Field(default=None, description="Arrival time (HH:MM) or None for origin")
    departure_time: Optional[str] = Field(default=None, description="Departure time (HH:MM) or None for terminus")
    platform: Optional[int] = Field(default=None, gt=0, description="Platform number")
    sequence: int = Field(..., gt=0, description="Stop sequence number in the journey")

    source: Optional[str] = Field(default=None, description="Originating data source")

    model_config = {"str_strip_whitespace": True}
