"""
CP-SAT Maintenance Block Optimizer Engine (Phase 5).

Provides deterministic, multi-objective mathematical optimization for railway
maintenance possessions and block schedules using Google OR-Tools CP-SAT.

PROTOTYPE DISCLAIMER:
Optimization models and objective weights are prototype assumptions for the
hackathon demonstration and are NOT official railway operating rules.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
from pathlib import Path
import time as pytime
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid
import yaml

from ortools.sat.python import cp_model

from backend.app.forecast.schemas import GoodsForecastItem
from backend.app.optimizer.constraints import (
    add_equipment_capacity_constraints,
    add_mandatory_scheduling_constraints,
    add_slot_assignment_constraints,
    add_track_overlap_constraints,
)
from backend.app.optimizer.objective import build_optimization_objective
from backend.app.optimizer.schemas import (
    ObjectiveWeights,
    OptimizationRequest,
    OptimizationResult,
    OptimizationStatus,
    OptimizedBlock,
    SolverStatistics,
    UnscheduledBlock,
)
from backend.app.scheduler.scheduler import (
    MaintenanceScheduler,
    PRIORITY_RANK,
    _calculate_duration_minutes,
    _format_minutes_to_time,
    _locations_match,
    _parse_time_to_minutes,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    BlockStatus,
    MaintenanceRecord,
    MovementRecord,
    Priority,
    TimetableRecord,
    TrainRecord,
)

logger = logging.getLogger(__name__)

# Default configuration path
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "constraints.yaml"


def load_constraints_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load constraints, capacities, and weights from YAML configuration file.
    Falls back to safe built-in prototype defaults if file is unavailable.
    """
    target_path = config_path or DEFAULT_CONFIG_PATH
    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning("Could not load config from %s: %s. Using defaults.", target_path, exc)

    # Default fallback
    return {
        "horizon": {"default_horizon_days": 7, "max_horizon_days": 30},
        "safety": {"buffer_minutes": 15, "min_block_duration_minutes": 30, "max_block_duration_minutes": 720},
        "resource_capacities": {
            "Track Tamper": 1,
            "Overhead Line Inspection Vehicle": 1,
            "OHE Car": 1,
            "Signal Testing Unit": 1,
            "Ballast Cleaner": 1,
            "Rail Crane": 1,
            "Tower Wagon": 2,
            "Welding Unit": 2,
            "General": 5,
        },
        "objective_weights": {
            "weight_scheduled": 10000,
            "weight_priority_critical": 5000,
            "weight_priority_high": 2500,
            "weight_priority_medium": 1000,
            "weight_priority_low": 200,
            "weight_preferred_deviation": 5,
            "weight_disruption": 50,
            "weight_resource_contention": 100,
        },
        "solver": {
            "time_limit_seconds": 30.0,
            "num_workers": 4,
            "random_seed": 42,
            "log_search_progress": False,
        },
    }


class CP_SAT_Optimizer:
    """
    Core mathematical optimizer scheduling railway maintenance requests
    using Google OR-Tools CP-SAT.
    """

    def __init__(
        self,
        maintenance_records: Optional[List[MaintenanceRecord]] = None,
        block_records: Optional[List[BlockRecord]] = None,
        timetables: Optional[List[TimetableRecord]] = None,
        goods_forecasts: Optional[List[GoodsForecastItem]] = None,
        movements: Optional[List[MovementRecord]] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        self.maintenance_records = maintenance_records or []
        self.block_records = block_records or []
        self.timetables = timetables or []
        self.goods_forecasts = goods_forecasts or []
        self.movements = movements or []
        self.config = load_constraints_config(config_path)

    def optimize(
        self,
        request: Optional[OptimizationRequest] = None,
        mandatory_request_ids: Optional[Set[str]] = None,
    ) -> OptimizationResult:
        """
        Execute CP-SAT mathematical optimization over the requested horizon.
        """
        start_wall_time = pytime.time()
        req = request or OptimizationRequest()
        base_date = req.target_date or date.today()
        horizon_days = max(1, min(30, req.horizon_days))
        buffer_mins = req.buffer_minutes

        # 1. Resolve Objective Weights & Capacities
        weights = req.weights or ObjectiveWeights(**self.config.get("objective_weights", {}))
        capacities = dict(self.config.get("resource_capacities", {}))
        if req.custom_capacities:
            capacities.update(req.custom_capacities)

        # 2. Extract Candidate Requests across the Planning Horizon
        end_date = base_date + timedelta(days=horizon_days)
        active_requests: List[Dict[str, Any]] = []

        for m in self.maintenance_records:
            if m.maintenance_required:
                if req.priority_filter and m.priority.value.lower() != req.priority_filter.lower():
                    continue
                if req.location_filter and req.location_filter.lower() not in m.location.lower():
                    continue
                # Include if requested within horizon
                if base_date <= m.requested_date < end_date:
                    pref_str = (
                        m.preferred_start.strftime("%H:%M")
                        if hasattr(m.preferred_start, "strftime")
                        else str(m.preferred_start)
                    )
                    active_requests.append({
                        "request_id": m.asset_id,
                        "asset_id": m.asset_id,
                        "block_id": None,
                        "location": m.location,
                        "priority": m.priority,
                        "duration_minutes": m.duration_minutes,
                        "requested_date": m.requested_date,
                        "preferred_start": pref_str,
                        "equipment": m.equipment,
                        "required_resources": m.required_resources,
                    })

        for b in self.block_records:
            if b.status != BlockStatus.CANCELLED:
                if req.priority_filter and b.priority.value.lower() != req.priority_filter.lower():
                    continue
                if req.location_filter and req.location_filter.lower() not in b.location.lower():
                    continue
                if base_date <= b.requested_date < end_date:
                    dur = _calculate_duration_minutes(b.requested_start, b.requested_end)
                    active_requests.append({
                        "request_id": b.block_id,
                        "asset_id": None,
                        "block_id": b.block_id,
                        "location": b.location,
                        "priority": b.priority,
                        "duration_minutes": dur,
                        "requested_date": b.requested_date,
                        "preferred_start": b.requested_start,
                        "equipment": None,
                        "required_resources": 1,
                    })

        # Sort requests deterministically by priority and duration
        active_requests.sort(
            key=lambda r: (
                PRIORITY_RANK.get(r["priority"], 1),
                r["duration_minutes"],
                r["request_id"],
            ),
            reverse=True,
        )

        # 3. Instantiate Candidate Slot Generator using Scheduler
        # Only existing blocks not currently being scheduled should be considered fixed occupancy
        active_block_ids = {r["block_id"] for r in active_requests if r["block_id"]}
        fixed_blocks = [b for b in self.block_records if b.block_id not in active_block_ids]

        scheduler = MaintenanceScheduler(
            maintenance_records=[],
            block_records=fixed_blocks,
            timetables=self.timetables,
            goods_forecasts=self.goods_forecasts if req.include_forecast else [],
            movements=self.movements,
            buffer_minutes=buffer_mins,
        )

        requests_to_slots: Dict[str, List[str]] = {}
        slot_metadata: Dict[str, Dict[str, Any]] = {}
        slot_counter = 1

        for r_item in active_requests:
            req_id = r_item["request_id"]
            r_date = r_item["requested_date"]
            requests_to_slots[req_id] = []

            # Search for feasible candidate slots on the requested date
            slots = scheduler.find_feasible_slots(
                location=r_item["location"],
                duration_minutes=r_item["duration_minutes"],
                preferred_start=r_item["preferred_start"],
                target_date=r_date,
                max_slots=req.max_slots_per_request,
            )

            pref_mins = _parse_time_to_minutes(r_item["preferred_start"]) or 600

            for slot in slots:
                s_id = f"OPT-SLOT-{slot_counter:04d}"
                slot_counter += 1
                requests_to_slots[req_id].append(s_id)

                s_start_min = _parse_time_to_minutes(slot.start_time) or 0
                s_end_min = s_start_min + r_item["duration_minutes"]

                slot_metadata[s_id] = {
                    "slot_id": s_id,
                    "request_id": req_id,
                    "asset_id": r_item["asset_id"],
                    "block_id": r_item["block_id"],
                    "location": r_item["location"],
                    "service_date": r_date,
                    "start_time": slot.start_time,
                    "end_time": slot.end_time,
                    "start_minutes": s_start_min,
                    "end_minutes": s_end_min,
                    "duration_minutes": r_item["duration_minutes"],
                    "preferred_start_minutes": pref_mins,
                    "fit_score": slot.fit_score,
                    "is_preferred_match": slot.is_preferred_match,
                    "priority": r_item["priority"],
                    "equipment": r_item["equipment"],
                    "required_resources": r_item["required_resources"],
                }

        # 4. Build CP-SAT Model
        model = cp_model.CpModel()
        slot_vars: Dict[Tuple[str, str], cp_model.IntVar] = {}

        for req_id, s_ids in requests_to_slots.items():
            for s_id in s_ids:
                clean_name = f"x_{req_id}_{s_id}".replace("-", "_").replace(" ", "_")
                slot_vars[(req_id, s_id)] = model.NewBoolVar(clean_name)

        num_vars = len(slot_vars)
        total_constraints = 0

        # Add Hard Constraints
        total_constraints += add_slot_assignment_constraints(model, slot_vars, requests_to_slots)
        total_constraints += add_track_overlap_constraints(model, slot_vars, slot_metadata)
        total_constraints += add_equipment_capacity_constraints(model, slot_vars, slot_metadata, capacities)

        if mandatory_request_ids:
            total_constraints += add_mandatory_scheduling_constraints(
                model, slot_vars, mandatory_request_ids, requests_to_slots
            )

        # Add Multi-Objective Function
        build_optimization_objective(model, slot_vars, slot_metadata, weights)

        # 5. Execute Solver
        solver = cp_model.CpSolver()
        solver_cfg = self.config.get("solver", {})
        solver.parameters.max_time_in_seconds = req.time_limit_seconds or solver_cfg.get("time_limit_seconds", 30.0)
        solver.parameters.num_workers = req.num_workers or solver_cfg.get("num_workers", 4)
        solver.parameters.random_seed = solver_cfg.get("random_seed", 42)
        solver.parameters.log_search_progress = solver_cfg.get("log_search_progress", False)

        raw_status = solver.Solve(model)
        wall_time = round(pytime.time() - start_wall_time, 4)

        # 6. Map Solver Status
        status_map = {
            cp_model.OPTIMAL: OptimizationStatus.OPTIMAL,
            cp_model.FEASIBLE: OptimizationStatus.FEASIBLE,
            cp_model.INFEASIBLE: OptimizationStatus.INFEASIBLE,
            cp_model.MODEL_INVALID: OptimizationStatus.MODEL_INVALID,
            cp_model.UNKNOWN: OptimizationStatus.UNKNOWN,
        }
        solver_status = status_map.get(raw_status, OptimizationStatus.UNKNOWN)

        # 7. Extract Results
        scheduled_blocks: List[OptimizedBlock] = []
        unscheduled_blocks: List[UnscheduledBlock] = []
        block_out_counter = 1

        for r_item in active_requests:
            req_id = r_item["request_id"]
            s_ids = requests_to_slots.get(req_id, [])
            scheduled_slot_id: Optional[str] = None

            if solver_status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE):
                for s_id in s_ids:
                    var = slot_vars.get((req_id, s_id))
                    if var is not None and solver.Value(var) == 1:
                        scheduled_slot_id = s_id
                        break

            if scheduled_slot_id:
                meta = slot_metadata[scheduled_slot_id]
                pref_mins = _parse_time_to_minutes(r_item["preferred_start"]) or 600
                dev_mins = abs(meta["start_minutes"] - pref_mins)
                opt_block = OptimizedBlock(
                    block_id=f"BLK-OPT-{block_out_counter:04d}",
                    request_id=req_id,
                    asset_id=r_item["asset_id"],
                    block_request_id=r_item["block_id"],
                    location=r_item["location"],
                    service_date=meta["service_date"],
                    start_time=meta["start_time"],
                    end_time=meta["end_time"],
                    duration_minutes=r_item["duration_minutes"],
                    priority=r_item["priority"],
                    equipment=r_item["equipment"],
                    required_resources=r_item["required_resources"],
                    status="Scheduled",
                    assigned_slot_id=scheduled_slot_id,
                    fit_score=meta["fit_score"],
                    is_preferred_match=meta["is_preferred_match"],
                    deviation_minutes=dev_mins,
                )
                scheduled_blocks.append(opt_block)
                block_out_counter += 1
            else:
                # Diagnose unscheduled reason
                if not s_ids:
                    reason = "No feasible conflict-free time window available within timetable / traffic headroom."
                else:
                    reason = "Preempted by higher-priority request or equipment capacity limits."
                unscheduled = UnscheduledBlock(
                    request_id=req_id,
                    asset_id=r_item["asset_id"],
                    block_id=r_item["block_id"],
                    location=r_item["location"],
                    requested_date=r_item["requested_date"],
                    preferred_start=r_item["preferred_start"],
                    duration_minutes=r_item["duration_minutes"],
                    priority=r_item["priority"],
                    equipment=r_item["equipment"],
                    required_resources=r_item["required_resources"],
                    reason=reason,
                )
                unscheduled_blocks.append(unscheduled)

        # Estimate conflicts avoided (overlap pairs constrained)
        num_conflicts_avoided = total_constraints

        stats = SolverStatistics(
            status=solver_status,
            objective_value=float(solver.ObjectiveValue()) if solver_status in (OptimizationStatus.OPTIMAL, OptimizationStatus.FEASIBLE) else None,
            wall_time_seconds=wall_time,
            num_scheduled=len(scheduled_blocks),
            num_unscheduled=len(unscheduled_blocks),
            num_conflicts_avoided=num_conflicts_avoided,
            total_requests=len(active_requests),
            num_variables=num_vars,
            num_constraints=total_constraints,
            num_branches=int(solver.NumBranches()) if hasattr(solver, "NumBranches") else 0,
        )

        plan_id = f"OPT-PLAN-{uuid.uuid4().hex[:8].upper()}"

        return OptimizationResult(
            plan_id=plan_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            target_date=base_date,
            horizon_days=horizon_days,
            status=solver_status,
            objective_value=stats.objective_value,
            solver_statistics=stats,
            scheduled_blocks=scheduled_blocks,
            unscheduled_blocks=unscheduled_blocks,
            phase="Phase 5 - CP-SAT Optimization",
            notes="Optimization rules and objective weights are prototype assumptions and NOT official railway operating rules.",
        )
