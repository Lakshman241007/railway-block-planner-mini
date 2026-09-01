"""
Plans API endpoints (Phase 3 Persistence View + Phase 4 Integrated Block Planner).

Exposes persistent block planning records and provides on-demand generation of
integrated maintenance block plans using forecasting, heuristic scheduling,
and conflict detection.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.block_planner.planner import BlockPlanner
from backend.app.block_planner.schemas import BlockPlanRequest, BlockPlanResult
from backend.app.database.repositories import BlockRepository
from backend.app.optimizer.schemas import OptimizationRequest, OptimizationResult

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.get(
    "",
    summary="Get planned maintenance blocks (Phase 3 Persistence View)",
    response_description="List of persisted block plan requests",
)
def get_plans(
    status: Optional[str] = Query(None, description="Filter by status (e.g. Approved, Requested)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Retrieve stored block planning requests from the database.
    """
    repo = BlockRepository(db)
    blocks = repo.get_all(status=status, skip=skip, limit=limit)
    total_count = repo.count(status=status)
    return {
        "message": "Phase 3 persistent block view. Automated scheduling/optimization will be introduced in Phase 4/5.",
        "data": [b.to_dict() for b in blocks],
        "count": len(blocks),
        "total": total_count,
    }


@router.post(
    "/generate",
    summary="Generate Phase 4 integrated maintenance block plan",
    response_model=BlockPlanResult,
)
def generate_block_plan(
    request: Optional[BlockPlanRequest] = None,
    db: Session = Depends(get_db),
) -> BlockPlanResult:
    """
    Generate an end-to-end maintenance block plan orchestrating:
    1. Goods train movement forecast with confidence scoring
    2. Feasible maintenance slot scheduling
    3. Spatial-temporal conflict detection and rule-based resolution recommendations
    """
    planner = BlockPlanner(db=db)
    return planner.generate_plan(request=request or BlockPlanRequest())


@router.post(
    "/optimize",
    summary="Generate Phase 5 CP-SAT optimized maintenance block plan",
    response_model=OptimizationResult,
)
def optimize_block_plan(
    request: Optional[OptimizationRequest] = None,
    db: Session = Depends(get_db),
) -> OptimizationResult:
    """
    Generate a mathematically optimized maintenance block plan using OR-Tools CP-SAT:
    1. Candidate slot generation across weekly/monthly horizon
    2. Hard constraints (train movement protection, track non-overlap, equipment capacity)
    3. Weighted multi-objective maximization (priority, throughput, minimal deviation)
    """
    planner = BlockPlanner(db=db)
    return planner.optimize_plan(request=request or OptimizationRequest())

