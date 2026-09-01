"""
Block Planner Facade for Railway Block Planner (Phase 4).

Coordinates the end-to-end Phase 4 workflow:
    GoodsTrainForecaster → MaintenanceScheduler → ConflictDetector → AutoResolver
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import logging
from typing import List, Optional
import uuid
from sqlalchemy.orm import Session

from backend.app.block_planner.schemas import BlockPlanRequest, BlockPlanResult
from backend.app.database.repositories import (
    BlockRepository,
    MaintenanceRepository,
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.forecast.forecast import GoodsTrainForecaster
from backend.app.forecast.schemas import GoodsForecastItem, GoodsForecastResult
from backend.app.optimizer.cp_sat_optimizer import CP_SAT_Optimizer
from backend.app.optimizer.schemas import OptimizationRequest, OptimizationResult
from backend.app.scheduler.auto_resolver import AutoResolver
from backend.app.scheduler.conflict_detector import ConflictDetector
from backend.app.scheduler.scheduler import MaintenanceScheduler
from backend.app.scheduler.schemas import ConflictReport, ScheduleResult
from backend.app.schemas.unified_data import (
    BlockRecord,
    MaintenanceRecord,
    MovementRecord,
    TimetableRecord,
    TrainRecord,
)

logger = logging.getLogger(__name__)


class BlockPlanner:
    """
    Unified planning facade executing the Phase 4 & Phase 5 pipelines.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        trains: Optional[List[TrainRecord]] = None,
        movements: Optional[List[MovementRecord]] = None,
        timetables: Optional[List[TimetableRecord]] = None,
        maintenance_records: Optional[List[MaintenanceRecord]] = None,
        block_records: Optional[List[BlockRecord]] = None,
    ) -> None:
        self.db = db
        self.trains = trains
        self.movements = movements
        self.timetables = timetables
        self.maintenance_records = maintenance_records
        self.block_records = block_records

    def _ensure_data_loaded(self) -> None:
        """Load data from database repositories if not provided in constructor."""
        if self.db:
            if self.trains is None:
                self.trains = [t.to_pydantic() for t in TrainRepository(self.db).get_all(limit=1000)]
            if self.movements is None:
                self.movements = [m.to_pydantic() for m in MovementRepository(self.db).get_all(limit=1000)]
            if self.timetables is None:
                self.timetables = [tt.to_pydantic() for tt in TimetableRepository(self.db).get_all(limit=1000)]
            if self.maintenance_records is None:
                self.maintenance_records = [m.to_pydantic() for m in MaintenanceRepository(self.db).get_all(limit=1000)]
            if self.block_records is None:
                self.block_records = [b.to_pydantic() for b in BlockRepository(self.db).get_all(limit=1000)]
        else:
            self.trains = self.trains or []
            self.movements = self.movements or []
            self.timetables = self.timetables or []
            self.maintenance_records = self.maintenance_records or []
            self.block_records = self.block_records or []

    def generate_plan(self, request: Optional[BlockPlanRequest] = None) -> BlockPlanResult:
        """
        Execute end-to-end Phase 4 block planning for the requested date.
        """
        req = request or BlockPlanRequest()
        target_d = req.target_date or date.today()

        self._ensure_data_loaded()

        forecast_result: Optional[GoodsForecastResult] = None
        forecast_items: List[GoodsForecastItem] = []
        forecast_summary: Optional[dict] = None

        # Step 1: Goods Train Forecast
        if req.include_forecast:
            forecaster = GoodsTrainForecaster(
                trains=self.trains,
                movements=self.movements,
                timetables=self.timetables,
            )
            forecast_result = forecaster.predict(target_date=target_d, horizon_hours=24)
            forecast_items = forecast_result.forecasts
            forecast_summary = {
                "total_trains_forecasted": forecast_result.total_trains_forecasted,
                "total_section_windows": forecast_result.total_section_windows,
                "average_confidence": forecast_result.average_confidence,
                "summary_by_section": forecast_result.summary_by_section,
            }

        # Step 2: Maintenance Scheduler
        scheduler = MaintenanceScheduler(
            maintenance_records=self.maintenance_records,
            block_records=self.block_records,
            timetables=self.timetables,
            goods_forecasts=forecast_items,
            movements=self.movements,
            buffer_minutes=req.buffer_minutes,
        )
        schedule_result = scheduler.schedule(
            target_date=target_d,
            priority_filter=req.priority_filter,
            location_filter=req.location_filter,
        )

        # Step 3: Conflict Detection & Resolution
        conflict_report: Optional[ConflictReport] = None
        resolutions: List[dict] = []

        if req.include_conflicts:
            detector = ConflictDetector(
                trains=self.trains,
                timetables=self.timetables,
                goods_forecasts=forecast_items,
                movements=self.movements,
                maintenance_records=self.maintenance_records,
                block_records=self.block_records,
                buffer_minutes=req.buffer_minutes,
            )
            conflict_report = detector.detect_conflicts(
                target_date=target_d,
                proposed_schedule=schedule_result,
            )

            resolver = AutoResolver()
            resolutions = resolver.generate_resolution_plan(conflict_report)

        plan_id = f"PLAN-{uuid.uuid4().hex[:8].upper()}"

        return BlockPlanResult(
            plan_id=plan_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            target_date=target_d,
            phase="Phase 4 - Forecast + Scheduler + Conflict Detection",
            forecast_summary=forecast_summary,
            schedule=schedule_result,
            conflict_report=conflict_report,
            resolution_recommendations=resolutions,
        )

    def optimize_plan(self, request: Optional[OptimizationRequest] = None) -> OptimizationResult:
        """
        Execute end-to-end Phase 5 CP-SAT mathematical optimization:
        Forecast → Multi-Day Candidate Slots → CP-SAT Optimizer.
        """
        req = request or OptimizationRequest()
        target_d = req.target_date or date.today()

        self._ensure_data_loaded()

        forecast_items: List[GoodsForecastItem] = []
        if req.include_forecast:
            forecaster = GoodsTrainForecaster(
                trains=self.trains,
                movements=self.movements,
                timetables=self.timetables,
            )
            # Forecast across the horizon days
            for d_offset in range(req.horizon_days):
                day_date = target_d + timedelta(days=d_offset)
                fc_res = forecaster.predict(target_date=day_date, horizon_hours=24)
                forecast_items.extend(fc_res.forecasts)

        optimizer = CP_SAT_Optimizer(
            maintenance_records=self.maintenance_records,
            block_records=self.block_records,
            timetables=self.timetables,
            goods_forecasts=forecast_items,
            movements=self.movements,
        )

        return optimizer.optimize(request=req)

