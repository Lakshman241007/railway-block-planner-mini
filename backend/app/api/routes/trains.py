"""
Train API endpoints.

Exposes REST endpoints for querying persistent train records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.database.repositories import TrainRepository
from backend.app.schemas.unified_data import TrainRecord

router = APIRouter(prefix="/trains", tags=["Trains"])


@router.get(
    "",
    summary="List all trains",
    response_description="List of train records and total count",
)
def get_trains(
    status: Optional[str] = Query(None, description="Filter trains by operational status (e.g. Running, Scheduled, Delayed)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve train records with optional status filtering and pagination."""
    repo = TrainRepository(db)
    trains = repo.get_all(status=status, skip=skip, limit=limit)
    total_count = repo.count(status=status)
    return {
        "data": [t.to_pydantic().model_dump() for t in trains],
        "count": len(trains),
        "total": total_count,
    }


@router.get(
    "/{train_id}",
    summary="Get train by ID",
    response_description="Single train record",
)
def get_train_by_id(
    train_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve details of a single train by its train_id."""
    repo = TrainRepository(db)
    train = repo.get_by_id(train_id)
    if not train:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Train with ID '{train_id}' not found",
        )
    return {
        "data": train.to_pydantic().model_dump()
    }
