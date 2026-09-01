"""
Goods Train Forecasting API endpoints (Phase 4).

Exposes routes to run on-demand goods train movement predictions and fetch
corridor transit window forecasts with confidence scoring.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.database.repositories import (
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.forecast.forecast import GoodsTrainForecaster
from backend.app.forecast.schemas import ForecastRequest, GoodsForecastResult

router = APIRouter(prefix="/forecast", tags=["Goods Train Forecast"])


@router.get(
    "",
    summary="Get goods train forecast",
    response_model=GoodsForecastResult,
)
def get_goods_forecast(
    target_date: Optional[date] = Query(None, description="Service date to forecast (default: today)"),
    horizon_hours: int = Query(24, ge=1, le=72, description="Forecasting horizon in hours"),
    train_id: Optional[str] = Query(None, description="Filter for specific train ID"),
    section: Optional[str] = Query(None, description="Filter for specific section"),
    db: Session = Depends(get_db),
) -> GoodsForecastResult:
    """
    Generate or retrieve goods train movement forecasts from database entities.
    """
    trains = [t.to_pydantic() for t in TrainRepository(db).get_all(limit=1000)]
    movements = [m.to_pydantic() for m in MovementRepository(db).get_all(limit=1000)]
    timetables = [tt.to_pydantic() for tt in TimetableRepository(db).get_all(limit=1000)]

    forecaster = GoodsTrainForecaster(trains=trains, movements=movements, timetables=timetables)
    return forecaster.predict(
        target_date=target_date,
        horizon_hours=horizon_hours,
        filter_train_id=train_id,
        filter_section=section,
    )


@router.post(
    "/run",
    summary="Trigger customized goods train forecast",
    response_model=GoodsForecastResult,
)
def run_goods_forecast(
    request: ForecastRequest,
    db: Session = Depends(get_db),
) -> GoodsForecastResult:
    """
    Trigger goods train forecasting with structured request parameters.
    """
    trains = [t.to_pydantic() for t in TrainRepository(db).get_all(limit=1000)]
    movements = [m.to_pydantic() for m in MovementRepository(db).get_all(limit=1000)]
    timetables = [tt.to_pydantic() for tt in TimetableRepository(db).get_all(limit=1000)]

    forecaster = GoodsTrainForecaster(trains=trains, movements=movements, timetables=timetables)
    return forecaster.predict(
        target_date=request.target_date,
        horizon_hours=request.horizon_hours,
        filter_train_id=request.train_id,
        filter_section=request.section,
    )
