"""
Plans API endpoints (Phase 3 Read-Only View).

Exposes persistent block planning records. Scheduling algorithms,
conflict detection, and CP-SAT optimization are strictly deferred
to Phase 4 and Phase 5.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.database.repositories import BlockRepository

router = APIRouter(prefix="/plans", tags=["Plans"])


@router.get(
    "",
    summary="Get planned maintenance blocks (Phase 3 Read-Only)",
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

    Note: This is a read-only database view for Phase 3. Automated block
    scheduling and mathematical optimization will be added in Phase 4/5.
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
