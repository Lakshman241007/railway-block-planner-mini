"""
Forecast Pydantic schemas for Railway Block Planner (Phase 4).

Defines canonical data models for predicting goods/freight train movements,
transit windows, section occupancies, delay propagation, and confidence scores.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ForecastConfidenceLevel(str, Enum):
    """Categorized confidence level for forecast items."""
    HIGH = "High"        # >= 0.80
    MEDIUM = "Medium"    # 0.50 - 0.79
    LOW = "Low"          # < 0.50


class GoodsForecastItem(BaseModel):
    """
    Predicted occupancy window and transit parameters for a single goods train
    traversing a specific corridor or station section.
    """

    forecast_id: str = Field(..., description="Unique identifier for this forecast item")
    train_id: str = Field(..., description="Goods train identifier (e.g. G123)")
    route_id: Optional[str] = Field(default=None, description="Route identifier (e.g. R-CHN-AJJ)")
    section: str = Field(..., description="Track section / station corridor")
    direction: str = Field(default="Up", description="Movement direction (Up or Down)")
    line: str = Field(default="Main", description="Track type (Main or Loop)")
    service_date: date = Field(..., description="Date of forecast")
    forecasted_entry: str = Field(..., description="Estimated entry / arrival time (HH:MM)")
    forecasted_exit: str = Field(..., description="Estimated exit / departure time (HH:MM)")
    delay_minutes: int = Field(default=0, ge=0, description="Estimated propagated delay in minutes")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence metric (0.0 to 1.0)")
    confidence_level: ForecastConfidenceLevel = Field(..., description="Categorical confidence")
    factors: Dict[str, float] = Field(default_factory=dict, description="Explanation of confidence components")

    model_config = {"str_strip_whitespace": True}


class GoodsForecastResult(BaseModel):
    """
    Structured outcome of the goods train forecasting pipeline.
    """

    generated_at: str = Field(..., description="ISO timestamp when forecast was generated")
    forecast_date: date = Field(..., description="Target service date for the forecast")
    horizon_hours: int = Field(default=24, ge=1, le=72, description="Forecasting time horizon in hours")
    total_trains_forecasted: int = Field(..., ge=0, description="Number of unique goods trains forecasted")
    total_section_windows: int = Field(..., ge=0, description="Total section occupancy windows predicted")
    average_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Mean confidence score")
    forecasts: List[GoodsForecastItem] = Field(default_factory=list, description="Detailed forecast records")
    summary_by_section: Dict[str, int] = Field(
        default_factory=dict, description="Count of forecasted movements per section"
    )

    model_config = {"str_strip_whitespace": True}


class ForecastRequest(BaseModel):
    """
    Request payload for on-demand goods train forecasting.
    """

    target_date: Optional[date] = Field(default=None, description="Service date to forecast (default: today)")
    horizon_hours: int = Field(default=24, ge=1, le=72, description="Forecasting horizon in hours")
    train_id: Optional[str] = Field(default=None, description="Filter forecast for a specific train")
    section: Optional[str] = Field(default=None, description="Filter forecast for a specific section")
