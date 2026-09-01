"""
Scheduler and Conflict Detection API endpoints (Phase 4).

Exposes routes for finding feasible maintenance slots, detecting spatial-temporal
conflicts, and generating conflict-free maintenance schedules.
"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.database.repositories import (
    BlockRepository,
    MaintenanceRepository,
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.forecast.forecast import GoodsTrainForecaster
from backend.app.scheduler.conflict_detector import ConflictDetector
from backend.app.scheduler.scheduler import MaintenanceScheduler
from backend.app.scheduler.schemas import (
    ConflictReport,
    FeasibleSlot,
    ScheduleRequest,
    ScheduleResult,
)

router = APIRouter(prefix="/scheduler", tags=["Maintenance Scheduler & Conflict Detection"])


class FeasibleSlotQuery(BaseModel):
    """Query payload to find feasible slots for a specific location and duration."""
    location: str = Field(..., description="Railway section / location description")
    duration_minutes: int = Field(..., gt=0, description="Required work duration in minutes")
    preferred_start: str = Field(default="10:00", description="Preferred start time (HH:MM)")
    target_date: Optional[date] = Field(default=None, description="Date for maintenance")
    buffer_minutes: int = Field(default=15, ge=0, le=60, description="Safety headway buffer")


@router.post(
    "/feasible-slots",
    summary="Find feasible maintenance slots",
    response_model=List[FeasibleSlot],
)
def find_feasible_slots(
    query: FeasibleSlotQuery,
    db: Session = Depends(get_db),
) -> List[FeasibleSlot]:
    """
    Search for conflict-free maintenance windows on a given track section.
    """
    target_d = query.target_date or date.today()
    trains = [t.to_pydantic() for t in TrainRepository(db).get_all(limit=1000)]
    movements = [m.to_pydantic() for m in MovementRepository(db).get_all(limit=1000)]
    timetables = [tt.to_pydantic() for tt in TimetableRepository(db).get_all(limit=1000)]
    blocks = [b.to_pydantic() for b in BlockRepository(db).get_all(limit=1000)]

    forecaster = GoodsTrainForecaster(trains=trains, movements=movements, timetables=timetables)
    fc_result = forecaster.predict(target_date=target_d)

    scheduler = MaintenanceScheduler(
        block_records=blocks,
        timetables=timetables,
        goods_forecasts=fc_result.forecasts,
        movements=movements,
        buffer_minutes=query.buffer_minutes,
    )
    return scheduler.find_feasible_slots(
        location=query.location,
        duration_minutes=query.duration_minutes,
        preferred_start=query.preferred_start,
        target_date=target_d,
    )


@router.post(
    "/conflicts",
    summary="Detect operational conflicts",
    response_model=ConflictReport,
)
def detect_conflicts(
    target_date: Optional[date] = Query(None, description="Target service date (default: today)"),
    buffer_minutes: int = Query(15, ge=0, le=60, description="Safety headway buffer in minutes"),
    db: Session = Depends(get_db),
) -> ConflictReport:
    """
    Scan all operational entities, train timetables, goods forecasts, and maintenance requests
    for spatial-temporal collisions and safety buffer violations.
    """
    target_d = target_date or date.today()
    trains = [t.to_pydantic() for t in TrainRepository(db).get_all(limit=1000)]
    movements = [m.to_pydantic() for m in MovementRepository(db).get_all(limit=1000)]
    timetables = [tt.to_pydantic() for tt in TimetableRepository(db).get_all(limit=1000)]
    maintenance = [m.to_pydantic() for m in MaintenanceRepository(db).get_all(limit=1000)]
    blocks = [b.to_pydantic() for b in BlockRepository(db).get_all(limit=1000)]

    forecaster = GoodsTrainForecaster(trains=trains, movements=movements, timetables=timetables)
    fc_result = forecaster.predict(target_date=target_d)

    detector = ConflictDetector(
        trains=trains,
        timetables=timetables,
        goods_forecasts=fc_result.forecasts,
        movements=movements,
        maintenance_records=maintenance,
        block_records=blocks,
        buffer_minutes=buffer_minutes,
    )
    return detector.detect_conflicts(target_date=target_d)


@router.post(
    "/schedule",
    summary="Generate maintenance schedule",
    response_model=ScheduleResult,
)
def generate_schedule(
    request: ScheduleRequest,
    db: Session = Depends(get_db),
) -> ScheduleResult:
    """
    Generate heuristic feasible schedule assignments for all active maintenance and block requests.
    """
    target_d = request.target_date or date.today()
    trains = [t.to_pydantic() for t in TrainRepository(db).get_all(limit=1000)]
    movements = [m.to_pydantic() for m in MovementRepository(db).get_all(limit=1000)]
    timetables = [tt.to_pydantic() for tt in TimetableRepository(db).get_all(limit=1000)]
    maintenance = [m.to_pydantic() for m in MaintenanceRepository(db).get_all(limit=1000)]
    blocks = [b.to_pydantic() for b in BlockRepository(db).get_all(limit=1000)]

    forecaster = GoodsTrainForecaster(trains=trains, movements=movements, timetables=timetables)
    fc_result = forecaster.predict(target_date=target_d)

    scheduler = MaintenanceScheduler(
        maintenance_records=maintenance,
        block_records=blocks,
        timetables=timetables,
        goods_forecasts=fc_result.forecasts,
        movements=movements,
        buffer_minutes=request.buffer_minutes,
    )
    return scheduler.schedule(
        target_date=target_d,
        priority_filter=request.priority_filter,
        location_filter=request.location_filter,
    )
