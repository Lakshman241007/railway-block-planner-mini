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
