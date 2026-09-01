"""
Unit and integration tests for Phase 4 Maintenance Scheduler, Conflict Detector,
and Auto-Resolver.
"""

from __future__ import annotations

from datetime import date, time
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.connection import Base
from backend.app.database.repositories import (
    BlockRepository,
    MaintenanceRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.forecast.forecast import GoodsTrainForecaster
from backend.app.forecast.schemas import GoodsForecastItem, ForecastConfidenceLevel
from backend.app.scheduler.auto_resolver import AutoResolver
from backend.app.scheduler.conflict_detector import ConflictDetector
from backend.app.scheduler.scheduler import MaintenanceScheduler
from backend.app.scheduler.schemas import (
    ConflictSeverity,
    ConflictType,
    FeasibleSlot,
    ScheduleResult,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    BlockStatus,
    BlockType,
    MaintenanceRecord,
    MaintenanceStatus,
    MovementRecord,
    Priority,
    TimetableRecord,
    TrainRecord,
    TrainStatus,
)


@pytest.fixture
def mock_timetables():
    return [
        TimetableRecord(
            train_id="P204",
            service_date=date(2026, 9, 5),
            station_code="Chennai",
            arrival_time=None,
            departure_time="10:05",
            platform=1,
            sequence=1,
        ),
        TimetableRecord(
            train_id="P204",
            service_date=date(2026, 9, 5),
            station_code="Perambur",
            arrival_time="10:15",
            departure_time="10:17",
            platform=2,
            sequence=2,
        ),
        TimetableRecord(
            train_id="P204",
            service_date=date(2026, 9, 5),
            station_code="AJJ",
            arrival_time="11:15",
            departure_time="11:20",
            platform=1,
            sequence=3,
        ),
    ]


@pytest.fixture
def mock_maintenance_records():
    return [
        MaintenanceRecord(
            asset_id="TRK-1025",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Preventive",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=120,
            requested_date=date(2026, 9, 5),
            preferred_start=time(14, 0),
            required_resources=8,
            equipment="Tamping Machine",
            status=MaintenanceStatus.PENDING,
        ),
        MaintenanceRecord(
            asset_id="SIG-2041",
            asset_type="Signal",
            location="Perambur Junction",
            maintenance_type="Inspection",
            maintenance_required=True,
            priority=Priority.MEDIUM,
            duration_minutes=60,
            requested_date=date(2026, 9, 5),
            preferred_start=time(12, 0),
            required_resources=3,
            equipment="Signal Testing Kit",
            status=MaintenanceStatus.PENDING,
        ),
    ]


@pytest.fixture
def mock_forecasts():
    return [
        GoodsForecastItem(
            forecast_id="FC-0001",
            train_id="G123",
            route_id="R-CHN-AJJ",
            section="Chennai-Perambur",
            direction="Up",
            line="Main",
            service_date=date(2026, 9, 5),
            forecasted_entry="09:30",
            forecasted_exit="09:45",
            delay_minutes=0,
            confidence_score=0.90,
            confidence_level=ForecastConfidenceLevel.HIGH,
        ),
    ]


@pytest.fixture
def mock_block_records():
    return [
        BlockRecord(
            block_id="BLK-001",
            location="Chennai-Arakkonam",
            block_type=BlockType.MAINTENANCE,
            requested_date=date(2026, 9, 5),
            requested_start="10:00",
            requested_end="12:00",
            reason="Track maintenance",
            priority=Priority.HIGH,
            status=BlockStatus.REQUESTED,
        ),
    ]


def test_find_feasible_slots_empty_corridor():
    scheduler = MaintenanceScheduler(buffer_minutes=15)
    slots = scheduler.find_feasible_slots(
        location="Isolated-Section",
        duration_minutes=120,
        preferred_start="10:00",
        target_date=date(2026, 9, 5),
    )
    assert len(slots) > 0
    assert slots[0].duration_minutes == 120
    assert slots[0].start_time == "10:00"
    assert slots[0].is_preferred_match is True
    assert slots[0].fit_score == 1.0


def test_find_feasible_slots_with_traffic(mock_timetables, mock_forecasts):
    scheduler = MaintenanceScheduler(
        timetables=mock_timetables,
        goods_forecasts=mock_forecasts,
        buffer_minutes=15,
    )
    slots = scheduler.find_feasible_slots(
        location="Chennai-Arakkonam",
        duration_minutes=120,
        preferred_start="10:00",
        target_date=date(2026, 9, 5),
    )
    # Train P204 is active between 10:00 and 11:35 in this section with buffer
    # The scheduler should provide alternative feasible slots that avoid 10:00 - 11:35
    assert len(slots) > 0
    for s in slots:
        assert s.start_time != "10:00" or s.is_preferred_match is False


def test_full_schedule_execution(mock_maintenance_records, mock_timetables, mock_forecasts):
    scheduler = MaintenanceScheduler(
        maintenance_records=mock_maintenance_records,
        timetables=mock_timetables,
        goods_forecasts=mock_forecasts,
    )
    result = scheduler.schedule(target_date=date(2026, 9, 5))

    assert isinstance(result, ScheduleResult)
    assert result.total_requested == 2
    assert result.total_scheduled >= 1
    assert len(result.scheduled_items) >= 1


def test_train_block_conflict_detection(mock_timetables, mock_block_records):
    # BLK-001 is requested 10:00 - 12:00 on Chennai-Arakkonam
    # P204 is at Chennai at 10:05 and Perambur at 10:15
    detector = ConflictDetector(
        timetables=mock_timetables,
        block_records=mock_block_records,
    )
    report = detector.detect_conflicts(target_date=date(2026, 9, 5))

    assert report.is_conflict_free is False
    assert report.total_conflicts >= 1
    assert report.critical_count >= 1

    train_conflicts = [c for c in report.conflicts if c.conflict_type == ConflictType.TRAIN_BLOCK]
    assert len(train_conflicts) >= 1
    assert train_conflicts[0].entity1_id == "P204"
    assert train_conflicts[0].entity2_id == "BLK-001"


def test_block_block_conflict_detection():
    b1 = BlockRecord(
        block_id="BLK-A",
        location="Chennai-Arakkonam",
        block_type=BlockType.MAINTENANCE,
        requested_date=date(2026, 9, 5),
        requested_start="10:00",
        requested_end="12:00",
        reason="Work 1",
        priority=Priority.HIGH,
        status=BlockStatus.REQUESTED,
    )
    b2 = BlockRecord(
        block_id="BLK-B",
        location="Chennai-Arakkonam",
        block_type=BlockType.MAINTENANCE,
        requested_date=date(2026, 9, 5),
        requested_start="11:00",
        requested_end="13:00",
        reason="Work 2",
        priority=Priority.HIGH,
        status=BlockStatus.REQUESTED,
    )
    detector = ConflictDetector(block_records=[b1, b2])
    report = detector.detect_conflicts(target_date=date(2026, 9, 5))

    bb_conflicts = [c for c in report.conflicts if c.conflict_type == ConflictType.BLOCK_BLOCK]
    assert len(bb_conflicts) == 1
    assert bb_conflicts[0].overlap_minutes == 60


def test_resource_contention_detection():
    m1 = MaintenanceRecord(
        asset_id="TRK-1",
        asset_type="Track",
        location="Chennai-Perambur",
        maintenance_type="Preventive",
        maintenance_required=True,
        priority=Priority.HIGH,
        duration_minutes=120,
        requested_date=date(2026, 9, 5),
        preferred_start=time(10, 0),
        required_resources=5,
        equipment="Tamping Machine",
        status=MaintenanceStatus.PENDING,
    )
    m2 = MaintenanceRecord(
        asset_id="TRK-2",
        asset_type="Track",
        location="Tambaram-Chengalpattu",
        maintenance_type="Preventive",
        maintenance_required=True,
        priority=Priority.MEDIUM,
        duration_minutes=120,
        requested_date=date(2026, 9, 5),
        preferred_start=time(10, 30),
        required_resources=5,
        equipment="Tamping Machine",
        status=MaintenanceStatus.PENDING,
    )
    detector = ConflictDetector(maintenance_records=[m1, m2])
    report = detector.detect_conflicts(target_date=date(2026, 9, 5))

    res_conflicts = [c for c in report.conflicts if c.conflict_type == ConflictType.RESOURCE_CONTENTION]
    assert len(res_conflicts) == 1
    assert "Tamping Machine" in res_conflicts[0].description


def test_auto_resolver(mock_timetables, mock_block_records):
    detector = ConflictDetector(
        timetables=mock_timetables,
        block_records=mock_block_records,
    )
    report = detector.detect_conflicts(target_date=date(2026, 9, 5))

    resolver = AutoResolver()
    resolutions = resolver.generate_resolution_plan(report)

    assert len(resolutions) == len(report.conflicts)
    for r in resolutions:
        assert "strategy" in r
        assert "recommendation" in r


def test_scheduler_unfeasible_oversized_duration(mock_timetables):
    """Test that requests with impossible duration return Unfeasible status."""
    scheduler = MaintenanceScheduler(
        maintenance_records=[
            MaintenanceRecord(
                asset_id="TRK-999",
                asset_type="Track",
                location="Chennai-Arakkonam",
                maintenance_type="Renewal",
                maintenance_required=True,
                priority=Priority.CRITICAL,
                duration_minutes=1500,  # > 24 hours
                requested_date=date(2026, 9, 5),
                preferred_start=time(6, 0),
                required_resources=10,
                equipment="Crane",
                status=MaintenanceStatus.PENDING,
            )
        ],
        timetables=mock_timetables,
    )
    result = scheduler.schedule(target_date=date(2026, 9, 5))
    assert result.total_requested == 1
    assert result.total_scheduled == 0
    assert result.total_unfeasible == 1
    assert result.unfeasible_items[0].status == "Unfeasible"


def test_conflict_detector_clean_no_conflicts():
    """Test conflict detector returns is_conflict_free=True when entities are disjoint."""
    tt = [
        TimetableRecord(
            train_id="P1",
            service_date=date(2026, 9, 5),
            station_code="Chennai",
            arrival_time=None,
            departure_time="06:00",
            platform=1,
            sequence=1,
        )
    ]
    blk = [
        BlockRecord(
            block_id="BLK-NIGHT",
            location="Chennai",
            block_type=BlockType.MAINTENANCE,
            requested_date=date(2026, 9, 5),
            requested_start="22:00",
            requested_end="23:30",
            reason="Night inspection",
            priority=Priority.LOW,
            status=BlockStatus.REQUESTED,
        )
    ]
    detector = ConflictDetector(timetables=tt, block_records=blk, buffer_minutes=15)
    report = detector.detect_conflicts(target_date=date(2026, 9, 5))
    assert report.is_conflict_free is True
    assert report.total_conflicts == 0


def test_block_planner_facade_end_to_end(
    mock_timetables, mock_maintenance_records, mock_block_records, mock_forecasts
):
    """Test BlockPlanner facade orchestrating Forecast, Scheduler, Conflict Detector."""
    from backend.app.block_planner.planner import BlockPlanner
    from backend.app.block_planner.schemas import BlockPlanRequest

    planner = BlockPlanner(
        timetables=mock_timetables,
        maintenance_records=mock_maintenance_records,
        block_records=mock_block_records,
    )
    plan = planner.generate_plan(
        BlockPlanRequest(target_date=date(2026, 9, 5), include_forecast=True, include_conflicts=True)
    )

    assert plan.plan_id.startswith("PLAN-")
    assert plan.target_date == date(2026, 9, 5)
    assert plan.schedule.total_requested >= 1
    assert plan.conflict_report is not None
    assert isinstance(plan.resolution_recommendations, list)

