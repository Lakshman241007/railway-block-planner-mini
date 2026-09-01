"""
Block Planner Schemas for Railway Block Planner (Phase 4).

Defines unified request and response models for the end-to-end block planning
pipeline connecting forecasting, scheduling, and conflict detection.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.forecast.schemas import GoodsForecastResult
from backend.app.scheduler.schemas import (
    ConflictReport,
    MaintenanceScheduleItem,
    ScheduleResult,
)


class BlockPlanRequest(BaseModel):
    """
    Request model to generate an end-to-end maintenance block plan.
    """

    target_date: Optional[date] = Field(default=None, description="Date to plan maintenance for (default: today)")
    priority_filter: Optional[str] = Field(default=None, description="Optional priority filter")
    location_filter: Optional[str] = Field(default=None, description="Optional corridor/section filter")
    buffer_minutes: int = Field(default=15, ge=0, le=60, description="Safety headway buffer in minutes")
    include_forecast: bool = Field(default=True, description="Whether to include goods train forecasting")
    include_conflicts: bool = Field(default=True, description="Whether to perform conflict detection")

    model_config = {"str_strip_whitespace": True}


class BlockPlanResult(BaseModel):
    """
    Unified end-to-end block planning response.
    """

    plan_id: str = Field(..., description="Unique plan generation identifier")
    generated_at: str = Field(..., description="ISO timestamp")
    target_date: date = Field(..., description="Service date of the plan")
    phase: str = Field(default="Phase 4 - Forecast + Scheduler + Conflict Detection")
    forecast_summary: Optional[Dict[str, Any]] = Field(default=None, description="Goods train forecast summary")
    schedule: ScheduleResult = Field(..., description="Heuristic maintenance schedule")
    conflict_report: Optional[ConflictReport] = Field(default=None, description="Conflict detection results")
    resolution_recommendations: List[Dict[str, str]] = Field(
        default_factory=list, description="Rule-based heuristic resolution suggestions"
    )

    model_config = {"str_strip_whitespace": True}
