"""
Optimizer Pydantic schemas (Phase 5).

Defines canonical data contracts for CP-SAT mathematical optimization,
decision results, unscheduled diagnostics, solver statistics, and planning horizons.

PROTOTYPE DISCLAIMER:
Optimization models and objective parameters are prototype assumptions for the
hackathon demonstration and are NOT official railway operating rules.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.schemas.unified_data import Priority


class OptimizationStatus(str, Enum):
    """Status returned by the CP-SAT mathematical solver."""
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNKNOWN = "UNKNOWN"
    MODEL_INVALID = "MODEL_INVALID"


class ObjectiveWeights(BaseModel):
    """
    Configurable weights for the multi-objective optimization function.
    """

    weight_scheduled: int = Field(
        default=10000,
        ge=0,
        description="Weight awarded for each successfully scheduled maintenance block",
    )
    weight_priority_critical: int = Field(
        default=5000,
        ge=0,
        description="Bonus weight for scheduling Critical priority maintenance",
    )
    weight_priority_high: int = Field(
        default=2500,
        ge=0,
        description="Bonus weight for scheduling High priority maintenance",
    )
    weight_priority_medium: int = Field(
        default=1000,
        ge=0,
        description="Bonus weight for scheduling Medium priority maintenance",
    )
    weight_priority_low: int = Field(
        default=200,
        ge=0,
        description="Bonus weight for scheduling Low priority maintenance",
    )
    weight_preferred_deviation: int = Field(
        default=5,
        ge=0,
        description="Penalty per minute of deviation from the preferred start time",
    )
    weight_disruption: int = Field(
        default=50,
        ge=0,
        description="Penalty multiplier for scheduling in lower-fit candidate slots",
    )
    weight_resource_contention: int = Field(
        default=100,
        ge=0,
        description="Penalty multiplier for equipment contention pressure",
    )

    model_config = {"str_strip_whitespace": True}


class OptimizationRequest(BaseModel):
    """
    Request model for triggering CP-SAT maintenance block optimization.
    """

    target_date: Optional[date] = Field(
        default=None,
        description="Start date of the optimization planning horizon (default: today)",
    )
    horizon_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Optimization planning horizon in days (e.g. 7 for weekly, 30 for monthly)",
    )
    priority_filter: Optional[str] = Field(
        default=None,
        description="Filter requests by priority (Critical, High, Medium, Low)",
    )
    location_filter: Optional[str] = Field(
        default=None,
        description="Filter requests by corridor / section name",
    )
    buffer_minutes: int = Field(
        default=15,
        ge=0,
        le=60,
        description="Safety headway buffer in minutes",
    )
    time_limit_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description="Maximum solver execution time in seconds",
    )
    num_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Number of parallel search workers for CP-SAT",
    )
    weights: Optional[ObjectiveWeights] = Field(
        default=None,
        description="Optional custom objective weights overriding default configuration",
    )
    custom_capacities: Optional[Dict[str, int]] = Field(
        default=None,
        description="Optional override for equipment/resource capacity limits",
    )
    include_forecast: bool = Field(
        default=True,
        description="Whether to incorporate goods train forecasts during candidate slot generation",
    )
    max_slots_per_request: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum candidate slots generated per maintenance request",
    )

    model_config = {"str_strip_whitespace": True}


class OptimizedBlock(BaseModel):
    """
    A maintenance block assigned and verified by the CP-SAT optimizer.
    """

    block_id: str = Field(..., description="Unique optimized block assignment ID")
    request_id: str = Field(..., description="Originating request ID (asset_id or block_id)")
    asset_id: Optional[str] = Field(default=None, description="Asset ID if from maintenance request")
    block_request_id: Optional[str] = Field(default=None, description="Block ID if from block request")
    location: str = Field(..., description="Corridor section / track location")
    service_date: date = Field(..., description="Scheduled service date")
    start_time: str = Field(..., description="Scheduled start time (HH:MM)")
    end_time: str = Field(..., description="Scheduled end time (HH:MM)")
    duration_minutes: int = Field(..., gt=0, description="Scheduled duration in minutes")
    priority: Priority = Field(..., description="Maintenance urgency priority")
    equipment: Optional[str] = Field(default=None, description="Specialized equipment allocated")
    required_resources: int = Field(default=1, ge=1, description="Resource/manpower units allocated")
    status: str = Field(default="Scheduled", description="Scheduling status")
    assigned_slot_id: str = Field(..., description="Assigned candidate slot identifier")
    fit_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Fit score of assigned slot")
    is_preferred_match: bool = Field(default=True, description="True if scheduled at preferred time")
    deviation_minutes: int = Field(default=0, ge=0, description="Minutes deviated from requested start")

    model_config = {"str_strip_whitespace": True}


class UnscheduledBlock(BaseModel):
    """
    A maintenance request that could not be scheduled by the optimizer,
    along with root-cause diagnostic explanation.
    """

    request_id: str = Field(..., description="Originating request ID")
    asset_id: Optional[str] = Field(default=None, description="Asset ID if applicable")
    block_id: Optional[str] = Field(default=None, description="Block request ID if applicable")
    location: str = Field(..., description="Corridor section requested")
    requested_date: date = Field(..., description="Original requested date")
    preferred_start: str = Field(..., description="Original requested start time (HH:MM)")
    duration_minutes: int = Field(..., gt=0, description="Requested duration in minutes")
    priority: Priority = Field(..., description="Priority level")
    equipment: Optional[str] = Field(default=None, description="Requested specialized equipment")
    required_resources: int = Field(default=1, ge=1, description="Requested resource units")
    reason: str = Field(..., description="Explanation of why request could not be scheduled")

    model_config = {"str_strip_whitespace": True}


class SolverStatistics(BaseModel):
    """
    Mathematical solver telemetry and execution performance metrics.
    """

    status: OptimizationStatus = Field(..., description="Solver status result")
    objective_value: Optional[float] = Field(default=None, description="Final mathematical objective value")
    wall_time_seconds: float = Field(default=0.0, ge=0.0, description="Solver execution time in seconds")
    num_scheduled: int = Field(default=0, ge=0, description="Total maintenance blocks successfully scheduled")
    num_unscheduled: int = Field(default=0, ge=0, description="Total unscheduled maintenance requests")
    num_conflicts_avoided: int = Field(default=0, ge=0, description="Estimated conflicts resolved by solver")
    total_requests: int = Field(default=0, ge=0, description="Total maintenance requests processed")
    num_variables: int = Field(default=0, ge=0, description="Total CP-SAT decision variables created")
    num_constraints: int = Field(default=0, ge=0, description="Total hard constraints enforced")
    num_branches: Optional[int] = Field(default=0, ge=0, description="Search branches explored by CP-SAT")

    model_config = {"str_strip_whitespace": True}


class OptimizationResult(BaseModel):
    """
    Unified CP-SAT maintenance optimization response model.
    """

    plan_id: str = Field(..., description="Unique optimization run identifier")
    generated_at: str = Field(..., description="ISO generation timestamp")
    target_date: date = Field(..., description="Start date of the optimization horizon")
    horizon_days: int = Field(default=7, description="Planning horizon length in days")
    status: OptimizationStatus = Field(..., description="Solver status (OPTIMAL, FEASIBLE, INFEASIBLE)")
    objective_value: Optional[float] = Field(default=None, description="Achieved objective score")
    solver_statistics: SolverStatistics = Field(..., description="Execution telemetry and statistics")
    scheduled_blocks: List[OptimizedBlock] = Field(default_factory=list, description="Optimized scheduled blocks")
    unscheduled_blocks: List[UnscheduledBlock] = Field(
        default_factory=list, description="Unscheduled requests with diagnostics"
    )
    phase: str = Field(default="Phase 5 - CP-SAT Optimization", description="Pipeline phase")
    notes: Optional[str] = Field(default=None, description="Prototype notes and disclaimer summary")

    model_config = {"str_strip_whitespace": True}
