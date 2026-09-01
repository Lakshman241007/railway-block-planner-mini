"""
Scheduler and Conflict Detection Pydantic schemas (Phase 4).

Defines canonical models for feasible maintenance slots, generated schedules,
spatial-temporal conflict reports, severity levels, and resolution actions.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.unified_data import Priority


class ConflictType(str, Enum):
    """Types of operational conflicts detected in the railway corridor."""
    TRAIN_BLOCK = "Train-Block Overlap"
    BLOCK_BLOCK = "Block-Block Contention"
    SAFETY_BUFFER_VIOLATION = "Safety Buffer Violation"
    RESOURCE_CONTENTION = "Resource Contention"


class ConflictSeverity(str, Enum):
    """Severity ratings for detected operational conflicts."""
    CRITICAL = "Critical"  # Direct collision with passenger train or emergency block
    HIGH = "High"          # Overlap with high-priority train or zero safety buffer
    MEDIUM = "Medium"      # Overlap with flexible goods train or equipment contention
    LOW = "Low"            # Minor buffer compression with low priority traffic


class FeasibleSlot(BaseModel):
    """
    A verified, conflict-free time window on a specific railway section
    that satisfies the required maintenance duration and safety buffers.
    """

    slot_id: str = Field(..., description="Unique identifier for the feasible slot")
    location: str = Field(..., description="Railway section / location description")
    service_date: date = Field(..., description="Date of the slot")
    start_time: str = Field(..., description="Slot start time (HH:MM)")
    end_time: str = Field(..., description="Slot end time (HH:MM)")
    duration_minutes: int = Field(..., gt=0, description="Available window duration in minutes")
    fit_score: float = Field(..., ge=0.0, le=1.0, description="Ranking score based on preferred start match")
    is_preferred_match: bool = Field(default=False, description="True if slot overlaps preferred requested time")

    model_config = {"str_strip_whitespace": True}


class MaintenanceScheduleItem(BaseModel):
    """
    Scheduling assignment decision for a single maintenance or block request.
    """

    schedule_id: str = Field(..., description="Unique schedule assignment ID")
    request_id: str = Field(..., description="Identifier of the originating request (asset_id or block_id)")
    asset_id: Optional[str] = Field(default=None, description="Asset ID if from maintenance request")
    block_id: Optional[str] = Field(default=None, description="Block ID if from block request")
    location: str = Field(..., description="Corridor section or station location")
    priority: Priority = Field(..., description="Urgency priority")
    requested_duration: int = Field(..., gt=0, description="Required work duration in minutes")
    preferred_start: str = Field(..., description="Preferred start time (HH:MM)")
    assigned_slot: Optional[FeasibleSlot] = Field(default=None, description="Primary scheduled feasible slot")
    alternative_slots: List[FeasibleSlot] = Field(default_factory=list, description="Alternative feasible slots")
    status: str = Field(default="Scheduled", description="Scheduled, Unfeasible, or AlternativeSuggested")
    notes: Optional[str] = Field(default=None, description="Scheduling heuristics explanation")

    model_config = {"str_strip_whitespace": True}


class ScheduleResult(BaseModel):
    """
    Full schedule output containing all planned maintenance assignments.
    """

    generated_at: str = Field(..., description="ISO generation timestamp")
    target_date: date = Field(..., description="Target service date")
    total_requested: int = Field(..., ge=0, description="Total requests processed")
    total_scheduled: int = Field(..., ge=0, description="Successfully scheduled requests")
    total_unfeasible: int = Field(..., ge=0, description="Requests with no feasible slot")
    scheduled_items: List[MaintenanceScheduleItem] = Field(default_factory=list)
    unfeasible_items: List[MaintenanceScheduleItem] = Field(default_factory=list)

    model_config = {"str_strip_whitespace": True}


class ConflictItem(BaseModel):
    """
    A single detected operational or spatial-temporal conflict.
    """

    conflict_id: str = Field(..., description="Unique conflict identifier")
    conflict_type: ConflictType = Field(..., description="Category of conflict")
    severity: ConflictSeverity = Field(..., description="Severity grading")
    location: str = Field(..., description="Corridor / section where conflict occurs")
    service_date: date = Field(..., description="Date of occurrence")
    start_time: str = Field(..., description="Conflict start time (HH:MM)")
    end_time: str = Field(..., description="Conflict end time (HH:MM)")
    overlap_minutes: int = Field(default=0, ge=0, description="Duration of physical overlap in minutes")
    entity1_type: str = Field(..., description="Type of first entity (e.g. Train, Block, Maintenance)")
    entity1_id: str = Field(..., description="Identifier of first entity")
    entity2_type: str = Field(..., description="Type of second entity")
    entity2_id: str = Field(..., description="Identifier of second entity")
    description: str = Field(..., description="Human-readable description of conflict")
    suggested_action: Optional[str] = Field(default=None, description="Rule-based resolution recommendation")

    model_config = {"str_strip_whitespace": True}


class ConflictReport(BaseModel):
    """
    Comprehensive conflict detection audit report.
    """

    generated_at: str = Field(..., description="ISO generation timestamp")
    target_date: date = Field(..., description="Target service date")
    total_conflicts: int = Field(..., ge=0, description="Total detected conflicts")
    critical_count: int = Field(default=0, ge=0, description="Count of Critical severity conflicts")
    high_count: int = Field(default=0, ge=0, description="Count of High severity conflicts")
    medium_count: int = Field(default=0, ge=0, description="Count of Medium severity conflicts")
    low_count: int = Field(default=0, ge=0, description="Count of Low severity conflicts")
    is_conflict_free: bool = Field(default=True, description="True if 0 conflicts detected")
    conflicts: List[ConflictItem] = Field(default_factory=list, description="List of conflict details")

    model_config = {"str_strip_whitespace": True}


class ScheduleRequest(BaseModel):
    """
    Request payload for maintenance scheduling.
    """

    target_date: Optional[date] = Field(default=None, description="Service date to schedule (default: today)")
    priority_filter: Optional[str] = Field(default=None, description="Filter requests by priority")
    location_filter: Optional[str] = Field(default=None, description="Filter requests by section/location")
    buffer_minutes: int = Field(default=15, ge=0, le=60, description="Safety headway buffer in minutes")
