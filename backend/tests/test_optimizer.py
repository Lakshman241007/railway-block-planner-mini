"""
Tests for Phase 5: CP-SAT Optimization and Block Planner Integration.

Covers:
1. Basic successful optimization
2. High-priority preference over low-priority under contention
3. Mutual exclusion of track possessions (no location overlap)
4. Train movement protection and safety headway
5. Equipment & resource capacity limits
6. Duration preservation
7. Planning horizon bounds
8. Alternative slot selection
9. Unscheduled block diagnostics
10. Infeasible status handling
11. Feasible vs Optimal solver status distinction
12. Deterministic reproducibility
13. Weekly horizon (7 days) planning
14. Monthly horizon (30 days) planning
15. FastAPI endpoint POST /api/plans/optimize
"""

from datetime import date, time, timedelta
import pytest
from fastapi.testclient import TestClient

from backend.app.block_planner.planner import BlockPlanner
from backend.app.main import app
from backend.app.optimizer.cp_sat_optimizer import CP_SAT_Optimizer
from backend.app.optimizer.schemas import (
    ObjectiveWeights,
    OptimizationRequest,
    OptimizationResult,
    OptimizationStatus,
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
def base_date() -> date:
    return date(2026, 9, 1)


@pytest.fixture
def sample_maintenance_request(base_date: date) -> MaintenanceRecord:
    return MaintenanceRecord(
        asset_id="TRK-M-001",
        asset_type="Track",
        location="Chennai-Arakkonam",
        maintenance_type="Preventive",
        maintenance_required=True,
        priority=Priority.HIGH,
        duration_minutes=120,
        requested_date=base_date,
        preferred_start=time(2, 0),
        required_resources=2,
        equipment="Track Tamper",
        status=MaintenanceStatus.APPROVED,
    )


@pytest.fixture
def passenger_timetable(base_date: date) -> list[TimetableRecord]:
    return [
        TimetableRecord(
            train_id="12601",
            service_date=base_date,
            station_code="Chennai",
            arrival_time=None,
            departure_time="06:00",
            platform=1,
            sequence=1,
        ),
        TimetableRecord(
            train_id="12601",
            service_date=base_date,
            station_code="Arakkonam",
            arrival_time="07:00",
            departure_time="07:05",
            platform=2,
            sequence=2,
        ),
    ]


class TestCPSATOptimizer:
    """Core mathematical optimization test suite."""

    def test_basic_optimization_success(self, base_date: date, sample_maintenance_request: MaintenanceRecord):
        """1. Basic successful optimization: Schedules a single request into a valid slot."""
        optimizer = CP_SAT_Optimizer(
            maintenance_records=[sample_maintenance_request],
        )
        req = OptimizationRequest(
            target_date=base_date,
            horizon_days=1,
        )
        result = optimizer.optimize(req)

        assert result.status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE)
        assert len(result.scheduled_blocks) == 1
        assert len(result.unscheduled_blocks) == 0
        scheduled = result.scheduled_blocks[0]
        assert scheduled.request_id == "TRK-M-001"
        assert scheduled.duration_minutes == 120
        assert scheduled.location == "Chennai-Arakkonam"
        assert scheduled.status == "Scheduled"
        assert result.solver_statistics.num_scheduled == 1

    def test_priority_preference_under_contention(self, base_date: date):
        """2. High-priority request preferred over low-priority when there is track contention."""
        # Both requests are on the same section and preferred start time, but only 1 slot is available
        critical_req = MaintenanceRecord(
            asset_id="CRITICAL-01",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Emergency Repair",
            maintenance_required=True,
            priority=Priority.CRITICAL,
            duration_minutes=120,
            requested_date=base_date,
            preferred_start=time(2, 0),
            required_resources=2,
            equipment="Track Tamper",
            status=MaintenanceStatus.APPROVED,
        )
        low_req = MaintenanceRecord(
            asset_id="LOW-01",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Routine Inspection",
            maintenance_required=True,
            priority=Priority.LOW,
            duration_minutes=120,
            requested_date=base_date,
            preferred_start=time(2, 0),
            required_resources=1,
            equipment="Track Tamper",
            status=MaintenanceStatus.APPROVED,
        )
        # Add train traffic occupying the rest of the day, leaving only 1 free slot (01:00 - 04:00)
        timetables = [
            TimetableRecord(
                train_id="T1",
                service_date=base_date,
                station_code="Chennai",
                arrival_time="04:15",
                departure_time="23:45",
                sequence=1,
            )
        ]

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[critical_req, low_req],
            timetables=timetables,
        )
        req = OptimizationRequest(target_date=base_date, horizon_days=1)
        result = optimizer.optimize(req)

        # Critical must be scheduled
        sched_ids = [b.request_id for b in result.scheduled_blocks]
        assert "CRITICAL-01" in sched_ids

    def test_track_overlap_mutual_exclusion(self, base_date: date):
        """3. Two blocks at the same location cannot overlap in time."""
        req1 = MaintenanceRecord(
            asset_id="BLOCK-A",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Track Relaying",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=180,
            requested_date=base_date,
            preferred_start=time(1, 0),
            required_resources=2,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )
        req2 = MaintenanceRecord(
            asset_id="BLOCK-B",
            asset_type="Signal",
            location="Chennai-Arakkonam",
            maintenance_type="Signal Cable Laying",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=180,
            requested_date=base_date,
            preferred_start=time(2, 0),
            required_resources=2,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[req1, req2],
        )
        req = OptimizationRequest(target_date=base_date, horizon_days=1)
        result = optimizer.optimize(req)

        # Check all scheduled blocks on the same date and location for non-overlap
        for i in range(len(result.scheduled_blocks)):
            for j in range(i + 1, len(result.scheduled_blocks)):
                b1 = result.scheduled_blocks[i]
                b2 = result.scheduled_blocks[j]
                if b1.location == b2.location and b1.service_date == b2.service_date:
                    s1 = int(b1.start_time.split(":")[0]) * 60 + int(b1.start_time.split(":")[1])
                    e1 = int(b1.end_time.split(":")[0]) * 60 + int(b1.end_time.split(":")[1])
                    s2 = int(b2.start_time.split(":")[0]) * 60 + int(b2.start_time.split(":")[1])
                    e2 = int(b2.end_time.split(":")[0]) * 60 + int(b2.end_time.split(":")[1])
                    # Must not overlap
                    assert max(s1, s2) >= min(e1, e2)

    def test_train_movement_protection(self, base_date: date):
        """4. Maintenance blocks do not overlap protected train movement intervals."""
        m_req = MaintenanceRecord(
            asset_id="TRK-PROT",
            asset_type="Track",
            location="Chennai",
            maintenance_type="Tamping",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=120,
            requested_date=base_date,
            preferred_start=time(10, 0),
            required_resources=2,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )
        # Train occupies Chennai from 09:30 to 11:30 (with 15 min buffer: 09:15 to 11:45)
        timetables = [
            TimetableRecord(
                train_id="EXPRESS-101",
                service_date=base_date,
                station_code="Chennai",
                arrival_time="09:30",
                departure_time="11:30",
                sequence=1,
            )
        ]

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[m_req],
            timetables=timetables,
        )
        req = OptimizationRequest(target_date=base_date, horizon_days=1, buffer_minutes=15)
        result = optimizer.optimize(req)

        assert len(result.scheduled_blocks) == 1
        scheduled = result.scheduled_blocks[0]
        s_min = int(scheduled.start_time.split(":")[0]) * 60 + int(scheduled.start_time.split(":")[1])
        e_min = int(scheduled.end_time.split(":")[0]) * 60 + int(scheduled.end_time.split(":")[1])
        train_start_buf = 9 * 60 + 30 - 15  # 555 min
        train_end_buf = 11 * 60 + 30 + 15   # 705 min

        # Must not overlap with train buffer window [555, 705]
        assert (e_min <= train_start_buf) or (s_min >= train_end_buf)

    def test_equipment_capacity_constraint(self, base_date: date):
        """5. Equipment capacity limits prevent concurrent operations exceeding machine count."""
        # Two jobs on different sections (so no track conflict), but requiring same equipment "OHE Car" (capacity=1)
        req1 = MaintenanceRecord(
            asset_id="OHE-SEC-1",
            asset_type="OHE",
            location="Chennai-Arakkonam",
            maintenance_type="OHE Inspection",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=180,
            requested_date=base_date,
            preferred_start=time(2, 0),
            required_resources=2,
            equipment="OHE Car",
            status=MaintenanceStatus.APPROVED,
        )
        req2 = MaintenanceRecord(
            asset_id="OHE-SEC-2",
            asset_type="OHE",
            location="Tambaram-Chengalpattu",
            maintenance_type="OHE Inspection",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=180,
            requested_date=base_date,
            preferred_start=time(2, 0),
            required_resources=2,
            equipment="OHE Car",
            status=MaintenanceStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[req1, req2],
        )
        # Force capacity of OHE Car to 1
        req = OptimizationRequest(
            target_date=base_date,
            horizon_days=1,
            custom_capacities={"OHE Car": 1},
        )
        result = optimizer.optimize(req)

        # Both may be scheduled sequentially, but cannot overlap in time
        if len(result.scheduled_blocks) == 2:
            b1 = result.scheduled_blocks[0]
            b2 = result.scheduled_blocks[1]
            s1 = int(b1.start_time.split(":")[0]) * 60 + int(b1.start_time.split(":")[1])
            e1 = int(b1.end_time.split(":")[0]) * 60 + int(b1.end_time.split(":")[1])
            s2 = int(b2.start_time.split(":")[0]) * 60 + int(b2.start_time.split(":")[1])
            e2 = int(b2.end_time.split(":")[0]) * 60 + int(b2.end_time.split(":")[1])
            assert max(s1, s2) >= min(e1, e2)

    def test_duration_preservation(self, base_date: date):
        """6. Start time and end time of scheduled block preserve the exact required duration."""
        durations = [45, 90, 180, 240]
        records = [
            MaintenanceRecord(
                asset_id=f"DUR-{d}",
                asset_type="Track",
                location=f"Section-{d}",
                maintenance_type="Preventive",
                maintenance_required=True,
                priority=Priority.MEDIUM,
                duration_minutes=d,
                requested_date=base_date,
                preferred_start=time(1, 0),
                required_resources=1,
                equipment="None",
                status=MaintenanceStatus.APPROVED,
            )
            for d in durations
        ]
        optimizer = CP_SAT_Optimizer(maintenance_records=records)
        result = optimizer.optimize(OptimizationRequest(target_date=base_date, horizon_days=1))

        for block in result.scheduled_blocks:
            s_min = int(block.start_time.split(":")[0]) * 60 + int(block.start_time.split(":")[1])
            e_min = int(block.end_time.split(":")[0]) * 60 + int(block.end_time.split(":")[1])
            assert (e_min - s_min) == block.duration_minutes

    def test_planning_horizon_bounds(self, base_date: date):
        """7. Optimizer only schedules blocks within the requested horizon [D, D+H)."""
        inside_req = MaintenanceRecord(
            asset_id="REQ-IN-HORIZON",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Preventive",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=120,
            requested_date=base_date + timedelta(days=2),
            preferred_start=time(2, 0),
            required_resources=1,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )
        outside_req = MaintenanceRecord(
            asset_id="REQ-OUTSIDE-HORIZON",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Preventive",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=120,
            requested_date=base_date + timedelta(days=10),
            preferred_start=time(2, 0),
            required_resources=1,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(maintenance_records=[inside_req, outside_req])
        # 7-day horizon starting base_date
        req = OptimizationRequest(target_date=base_date, horizon_days=7)
        result = optimizer.optimize(req)

        sched_ids = [b.request_id for b in result.scheduled_blocks]
        assert "REQ-IN-HORIZON" in sched_ids
        assert "REQ-OUTSIDE-HORIZON" not in sched_ids

    def test_alternative_slot_selection(self, base_date: date):
        """8. When preferred start time is blocked, the optimizer selects an alternative feasible slot."""
        req = MaintenanceRecord(
            asset_id="ALT-REQ",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Repair",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=120,
            requested_date=base_date,
            preferred_start=time(6, 0),  # Preferred 06:00
            required_resources=1,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )
        # Train occupies track from 05:30 to 08:30 (blocking preferred 06:00)
        timetables = [
            TimetableRecord(
                train_id="T-PEAK",
                service_date=base_date,
                station_code="Chennai",
                arrival_time="05:30",
                departure_time="08:30",
                sequence=1,
            )
        ]

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[req],
            timetables=timetables,
        )
        result = optimizer.optimize(OptimizationRequest(target_date=base_date, horizon_days=1))

        assert len(result.scheduled_blocks) == 1
        scheduled = result.scheduled_blocks[0]
        # Should be scheduled in a free window (e.g. before 05:00 or after 08:45)
        assert scheduled.start_time != "06:00"
        assert scheduled.status == "Scheduled"

    def test_unscheduled_block_reporting(self, base_date: date):
        """9. Unscheduled blocks are reported with diagnostic causal reasons."""
        oversized_req = MaintenanceRecord(
            asset_id="OVERSIZED-REQ",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Major Overhaul",
            maintenance_required=True,
            priority=Priority.LOW,
            duration_minutes=1400,  # 23+ hours on busy section
            requested_date=base_date,
            preferred_start=time(1, 0),
            required_resources=5,
            equipment="Track Tamper",
            status=MaintenanceStatus.APPROVED,
        )
        # Busy corridor with train in afternoon
        timetables = [
            TimetableRecord(
                train_id="T-MIDDAY",
                service_date=base_date,
                station_code="Chennai",
                arrival_time="12:00",
                departure_time="13:00",
                sequence=1,
            )
        ]

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[oversized_req],
            timetables=timetables,
        )
        result = optimizer.optimize(OptimizationRequest(target_date=base_date, horizon_days=1))

        assert len(result.scheduled_blocks) == 0
        assert len(result.unscheduled_blocks) == 1
        unsched = result.unscheduled_blocks[0]
        assert unsched.request_id == "OVERSIZED-REQ"
        assert "No feasible" in unsched.reason or "headroom" in unsched.reason

    def test_infeasible_status_handling(self, base_date: date):
        """10. Mathematical solver returns INFEASIBLE status when mandatory constraints cannot be satisfied."""
        req = MaintenanceRecord(
            asset_id="IMPOSSIBLE-REQ",
            asset_type="Track",
            location="Chennai",
            maintenance_type="Emergency",
            maintenance_required=True,
            priority=Priority.CRITICAL,
            duration_minutes=600,
            requested_date=base_date,
            preferred_start=time(12, 0),
            required_resources=1,
            equipment="None",
            status=MaintenanceStatus.APPROVED,
        )
        # Train occupies entire day leaving 0 slots
        timetables = [
            TimetableRecord(
                train_id="ALL-DAY-TRAIN",
                service_date=base_date,
                station_code="Chennai",
                arrival_time="00:01",
                departure_time="23:59",
                sequence=1,
            )
        ]

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[req],
            timetables=timetables,
        )
        # Force mandatory scheduling of this impossible request
        result = optimizer.optimize(
            request=OptimizationRequest(target_date=base_date, horizon_days=1),
            mandatory_request_ids={"IMPOSSIBLE-REQ"},
        )

        assert result.status == OptimizationStatus.INFEASIBLE
        assert len(result.scheduled_blocks) == 0

    def test_solver_status_optimal_vs_feasible(self, base_date: date, sample_maintenance_request: MaintenanceRecord):
        """11. Correctly distinguishes OPTIMAL solver status."""
        optimizer = CP_SAT_Optimizer(
            maintenance_records=[sample_maintenance_request],
        )
        result = optimizer.optimize(OptimizationRequest(target_date=base_date, horizon_days=1))

        assert result.status == OptimizationStatus.OPTIMAL
        assert result.objective_value is not None
        assert result.objective_value > 0

    def test_deterministic_results(self, base_date: date):
        """12. Two optimization runs with identical input produce identical output."""
        records = [
            MaintenanceRecord(
                asset_id=f"DET-{i}",
                asset_type="Track",
                location=f"Location-{i % 3}",
                maintenance_type="Routine",
                maintenance_required=True,
                priority=Priority.HIGH if i % 2 == 0 else Priority.MEDIUM,
                duration_minutes=120,
                requested_date=base_date,
                preferred_start=time(2, 0),
                required_resources=1,
                equipment="Track Tamper" if i % 2 == 0 else "None",
                status=MaintenanceStatus.APPROVED,
            )
            for i in range(5)
        ]

        opt1 = CP_SAT_Optimizer(maintenance_records=records)
        res1 = opt1.optimize(OptimizationRequest(target_date=base_date, horizon_days=1))

        opt2 = CP_SAT_Optimizer(maintenance_records=records)
        res2 = opt2.optimize(OptimizationRequest(target_date=base_date, horizon_days=1))

        assert len(res1.scheduled_blocks) == len(res2.scheduled_blocks)
        for b1, b2 in zip(res1.scheduled_blocks, res2.scheduled_blocks):
            assert b1.request_id == b2.request_id
            assert b1.start_time == b2.start_time
            assert b1.end_time == b2.end_time
            assert b1.fit_score == b2.fit_score

    def test_weekly_horizon_planning(self, base_date: date):
        """13. Weekly horizon (7 days) schedules multi-day requests across the window."""
        records = []
        for day in range(7):
            records.append(
                MaintenanceRecord(
                    asset_id=f"WEEKLY-JOB-{day}",
                    asset_type="Track",
                    location="Chennai-Arakkonam",
                    maintenance_type="Tamping",
                    maintenance_required=True,
                    priority=Priority.HIGH,
                    duration_minutes=120,
                    requested_date=base_date + timedelta(days=day),
                    preferred_start=time(2, 0),
                    required_resources=1,
                    equipment="Track Tamper",
                    status=MaintenanceStatus.APPROVED,
                )
            )

        optimizer = CP_SAT_Optimizer(maintenance_records=records)
        result = optimizer.optimize(OptimizationRequest(target_date=base_date, horizon_days=7))

        assert result.horizon_days == 7
        assert len(result.scheduled_blocks) == 7
        # Ensure all 7 distinct dates were scheduled
        scheduled_dates = {b.service_date for b in result.scheduled_blocks}
        assert len(scheduled_dates) == 7

    def test_monthly_horizon_planning(self, base_date: date):
        """14. Monthly horizon (30 days) optimization execution."""
        records = []
        for day in range(30):
            records.append(
                MaintenanceRecord(
                    asset_id=f"MONTHLY-JOB-{day}",
                    asset_type="Signal",
                    location=f"Station-{day % 5}",
                    maintenance_type="Inspection",
                    maintenance_required=True,
                    priority=Priority.MEDIUM,
                    duration_minutes=60,
                    requested_date=base_date + timedelta(days=day),
                    preferred_start=time(3, 0),
                    required_resources=1,
                    equipment="None",
                    status=MaintenanceStatus.APPROVED,
                )
            )

        optimizer = CP_SAT_Optimizer(maintenance_records=records)
        result = optimizer.optimize(
            OptimizationRequest(
                target_date=base_date,
                horizon_days=30,
                time_limit_seconds=10.0,
            )
        )

        assert result.horizon_days == 30
        assert result.status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE)
        assert len(result.scheduled_blocks) == 30

    def test_block_planner_facade_integration(self, base_date: date, sample_maintenance_request: MaintenanceRecord):
        """Integration test for BlockPlanner.optimize_plan facade."""
        planner = BlockPlanner(
            maintenance_records=[sample_maintenance_request],
        )
        opt_res = planner.optimize_plan(OptimizationRequest(target_date=base_date, horizon_days=1))
        assert isinstance(opt_res, OptimizationResult)
        assert opt_res.status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE)
        assert len(opt_res.scheduled_blocks) == 1


class TestOptimizerAPI:
    """FastAPI REST API integration tests for Phase 5."""

    def test_api_optimize_endpoint(self, base_date: date):
        """15. POST /api/plans/optimize endpoint returns valid optimization response."""
        client = TestClient(app)
        payload = {
            "target_date": base_date.isoformat(),
            "horizon_days": 7,
            "buffer_minutes": 15,
            "time_limit_seconds": 10.0,
            "num_workers": 2,
        }
        response = client.post("/api/plans/optimize", json=payload)
        assert response.status_code == 200

        data = response.json()
        assert "plan_id" in data
        assert "status" in data
        assert data["status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE")
        assert "solver_statistics" in data
        assert "scheduled_blocks" in data
        assert "unscheduled_blocks" in data
        assert data["phase"] == "Phase 5 - CP-SAT Optimization"
        assert data["horizon_days"] == 7


class TestOvernightHandling:
    """Regression test suite for overnight maintenance blocks crossing midnight."""

    def test_overnight_duration_calculation(self):
        """TEST 1: 22:00 -> 02:00 must produce 240 minutes."""
        from backend.app.scheduler.scheduler import _calculate_duration_minutes

        dur = _calculate_duration_minutes("22:00", "02:00")
        assert dur == 240

    def test_short_overnight_duration(self):
        """TEST 2: 23:30 -> 01:00 must produce 90 minutes."""
        from backend.app.scheduler.scheduler import _calculate_duration_minutes

        dur = _calculate_duration_minutes("23:30", "01:00")
        assert dur == 90

    def test_normal_same_day_duration(self):
        """TEST 3: Normal same-day 10:00 -> 12:00 must remain 120 minutes."""
        from backend.app.scheduler.scheduler import _calculate_duration_minutes

        dur = _calculate_duration_minutes("10:00", "12:00")
        assert dur == 120

    def test_overnight_candidate_slot_generation(self, base_date: date):
        """TEST 4: 240-minute overnight request never receives a candidate slot shorter than 240 minutes."""
        from backend.app.scheduler.scheduler import MaintenanceScheduler

        scheduler = MaintenanceScheduler()
        slots = scheduler.find_feasible_slots(
            location="Basin Bridge-Vyasarpadi",
            duration_minutes=240,
            preferred_start="22:00",
            target_date=base_date,
        )
        assert len(slots) > 0
        for slot in slots:
            assert slot.duration_minutes == 240
        # Preferred slot check
        pref_slot = slots[0]
        assert pref_slot.start_time == "22:00"
        assert pref_slot.end_time == "02:00"
        assert pref_slot.duration_minutes == 240

    def test_cpsat_overnight_duration_preservation(self, base_date: date):
        """TEST 5: BLK-006 overnight block (22:00 -> 02:00) is scheduled with duration_minutes=240."""
        blk_006 = BlockRecord(
            block_id="BLK-006",
            location="Basin Bridge-Vyasarpadi",
            block_type=BlockType.EMERGENCY,
            requested_date=base_date,
            requested_start="22:00",
            requested_end="02:00",
            reason="OHE repair",
            priority=Priority.CRITICAL,
            status=BlockStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(
            block_records=[blk_006],
        )
        result = optimizer.optimize(
            OptimizationRequest(
                target_date=base_date,
                horizon_days=1,
            )
        )

        assert len(result.scheduled_blocks) == 1
        scheduled = result.scheduled_blocks[0]
        assert scheduled.block_request_id == "BLK-006"
        assert scheduled.duration_minutes == 240
        assert scheduled.start_time == "22:00"
        assert scheduled.end_time == "02:00"

    def test_overnight_formatting_no_clamping(self):
        """TEST 6: 1320 -> 1560 must return 22:00 -> 02:00 and not be clamped to 23:59."""
        from backend.app.scheduler.scheduler import _format_minutes_to_time

        assert _format_minutes_to_time(1320) == "22:00"
        assert _format_minutes_to_time(1560) == "02:00"
        assert _format_minutes_to_time(1440) == "00:00"
        assert _format_minutes_to_time(1500) == "01:00"

    def test_overnight_train_conflict(self, base_date: date):
        """TEST 7: Train movement occurring at 01:00 next day conflicts with overnight block 22:00 -> 02:00."""
        from backend.app.scheduler.conflict_detector import ConflictDetector

        next_date = base_date + timedelta(days=1)
        blk = BlockRecord(
            block_id="BLK-NIGHT",
            location="Basin Bridge-Vyasarpadi",
            block_type=BlockType.EMERGENCY,
            requested_date=base_date,
            requested_start="22:00",
            requested_end="02:00",
            reason="OHE repair",
            priority=Priority.CRITICAL,
            status=BlockStatus.APPROVED,
        )
        train_tt = TimetableRecord(
            train_id="NIGHT-EXP-01",
            service_date=next_date,
            station_code="Basin Bridge",
            arrival_time="01:00",
            departure_time="01:15",
            sequence=1,
        )

        detector = ConflictDetector(
            timetables=[train_tt],
            block_records=[blk],
        )
        report = detector.detect_conflicts(target_date=base_date)

        assert report.total_conflicts > 0
        train_conflicts = [c for c in report.conflicts if c.entity1_id == "NIGHT-EXP-01"]
        assert len(train_conflicts) > 0
        assert train_conflicts[0].entity2_id == "BLK-NIGHT"

    def test_overnight_block_conflict(self, base_date: date):
        """TEST 8: Two blocks (Block A: 22:00 -> 02:00, Block B: 01:00 -> 03:00) on same location overlap."""
        from backend.app.scheduler.conflict_detector import ConflictDetector

        next_date = base_date + timedelta(days=1)
        blk_a = BlockRecord(
            block_id="BLK-A",
            location="Basin Bridge-Vyasarpadi",
            block_type=BlockType.MAINTENANCE,
            requested_date=base_date,
            requested_start="22:00",
            requested_end="02:00",
            reason="Track",
            priority=Priority.HIGH,
            status=BlockStatus.APPROVED,
        )
        blk_b = BlockRecord(
            block_id="BLK-B",
            location="Basin Bridge-Vyasarpadi",
            block_type=BlockType.MAINTENANCE,
            requested_date=next_date,
            requested_start="01:00",
            requested_end="03:00",
            reason="Signal",
            priority=Priority.HIGH,
            status=BlockStatus.APPROVED,
        )

        detector = ConflictDetector(
            block_records=[blk_a, blk_b],
        )
        report = detector.detect_conflicts(target_date=base_date)

        assert report.total_conflicts > 0
        bb_conflicts = [c for c in report.conflicts if "BLK-A" in (c.entity1_id, c.entity2_id) and "BLK-B" in (c.entity1_id, c.entity2_id)]
        assert len(bb_conflicts) > 0

    def test_safety_buffer_across_midnight(self, base_date: date):
        """TEST 9: Train/block event within 15-minute buffer around midnight is detected."""
        from backend.app.scheduler.conflict_detector import ConflictDetector

        next_date = base_date + timedelta(days=1)
        # Train departs at 23:55 on base_date
        train_tt = TimetableRecord(
            train_id="MIDNIGHT-TRAIN",
            service_date=base_date,
            station_code="Chennai",
            arrival_time="23:50",
            departure_time="23:55",
            sequence=1,
        )
        # Block starts at 00:05 on next_date (gap = 10 min < 15 min buffer)
        blk = BlockRecord(
            block_id="BLK-EARLY-MORNING",
            location="Chennai",
            block_type=BlockType.MAINTENANCE,
            requested_date=next_date,
            requested_start="00:05",
            requested_end="02:00",
            reason="Tamping",
            priority=Priority.HIGH,
            status=BlockStatus.APPROVED,
        )

        detector = ConflictDetector(
            timetables=[train_tt],
            block_records=[blk],
            buffer_minutes=15,
        )
        report = detector.detect_conflicts(target_date=base_date)

        buf_conflicts = [c for c in report.conflicts if c.conflict_type.value == "Safety Buffer Violation"]
        assert len(buf_conflicts) > 0

    def test_equipment_contention_across_midnight(self, base_date: date):
        """TEST 10: Two blocks using limited equipment across midnight do not bypass capacity."""
        next_date = base_date + timedelta(days=1)
        req1 = MaintenanceRecord(
            asset_id="TAMPER-JOB-1",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Tamping",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=240,
            requested_date=base_date,
            preferred_start=time(22, 0),
            required_resources=2,
            equipment="Track Tamper",
            status=MaintenanceStatus.APPROVED,
        )
        req2 = MaintenanceRecord(
            asset_id="TAMPER-JOB-2",
            asset_type="Track",
            location="Tambaram-Chengalpattu",
            maintenance_type="Tamping",
            maintenance_required=True,
            priority=Priority.HIGH,
            duration_minutes=120,
            requested_date=next_date,
            preferred_start=time(1, 0),
            required_resources=2,
            equipment="Track Tamper",
            status=MaintenanceStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(
            maintenance_records=[req1, req2],
        )
        result = optimizer.optimize(
            OptimizationRequest(
                target_date=base_date,
                horizon_days=2,
                custom_capacities={"Track Tamper": 1},
            )
        )

        # Both jobs cannot overlap during 01:00 -> 02:00 on next_date
        if len(result.scheduled_blocks) == 2:
            b1 = next(b for b in result.scheduled_blocks if b.request_id == "TAMPER-JOB-1")
            b2 = next(b for b in result.scheduled_blocks if b.request_id == "TAMPER-JOB-2")
            abs_s1 = (b1.service_date - base_date).days * 1440 + int(b1.start_time.split(":")[0]) * 60 + int(b1.start_time.split(":")[1])
            abs_e1 = abs_s1 + b1.duration_minutes
            abs_s2 = (b2.service_date - base_date).days * 1440 + int(b2.start_time.split(":")[0]) * 60 + int(b2.start_time.split(":")[1])
            abs_e2 = abs_s2 + b2.duration_minutes
            assert max(abs_s1, abs_s2) >= min(abs_e1, abs_e2)

    def test_weekly_horizon_overnight(self, base_date: date):
        """TEST 11: Overnight request beginning on day 6 is correctly scheduled in 7-day horizon."""
        day6_date = base_date + timedelta(days=6)
        overnight_req = MaintenanceRecord(
            asset_id="WEEKLY-OVERNIGHT",
            asset_type="Track",
            location="Chennai-Arakkonam",
            maintenance_type="Track Renewal",
            maintenance_required=True,
            priority=Priority.CRITICAL,
            duration_minutes=240,
            requested_date=day6_date,
            preferred_start=time(22, 0),
            required_resources=2,
            equipment="Track Tamper",
            status=MaintenanceStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(maintenance_records=[overnight_req])
        result = optimizer.optimize(OptimizationRequest(target_date=base_date, horizon_days=7))

        assert len(result.scheduled_blocks) == 1
        scheduled = result.scheduled_blocks[0]
        assert scheduled.request_id == "WEEKLY-OVERNIGHT"
        assert scheduled.duration_minutes == 240
        assert scheduled.service_date == day6_date

    def test_monthly_horizon_overnight(self, base_date: date):
        """TEST 12: Overnight request within 30-day horizon works correctly without truncation."""
        day20_date = base_date + timedelta(days=20)
        overnight_req = BlockRecord(
            block_id="MONTHLY-OVERNIGHT-BLK",
            location="Basin Bridge-Vyasarpadi",
            block_type=BlockType.EMERGENCY,
            requested_date=day20_date,
            requested_start="22:00",
            requested_end="02:00",
            reason="Emergency OHE Repair",
            priority=Priority.CRITICAL,
            status=BlockStatus.APPROVED,
        )

        optimizer = CP_SAT_Optimizer(block_records=[overnight_req])
        result = optimizer.optimize(
            OptimizationRequest(
                target_date=base_date,
                horizon_days=30,
                time_limit_seconds=10.0,
            )
        )

        assert len(result.scheduled_blocks) == 1
        scheduled = result.scheduled_blocks[0]
        assert scheduled.block_request_id == "MONTHLY-OVERNIGHT-BLK"
        assert scheduled.duration_minutes == 240
        assert scheduled.start_time == "22:00"
        assert scheduled.end_time == "02:00"

