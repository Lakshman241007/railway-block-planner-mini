"""
Maintenance API endpoints.

Exposes REST endpoints for querying persistent railway maintenance records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.database.repositories import MaintenanceRepository

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@router.get(
    "",
    summary="List maintenance records",
    response_description="List of maintenance records and total count",
)
def get_maintenance_records(
    priority: Optional[str] = Query(None, description="Filter by priority (Low, Medium, High, Critical)"),
    status: Optional[str] = Query(None, description="Filter by status (Pending, Approved, Completed, Cancelled)"),
    asset_id: Optional[str] = Query(None, description="Filter by asset ID"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve maintenance records with optional filters and pagination."""
    repo = MaintenanceRepository(db)
    records = repo.get_all(priority=priority, status=status, asset_id=asset_id, skip=skip, limit=limit)
    total_count = repo.count(priority=priority, status=status, asset_id=asset_id)
    return {
        "data": [m.to_dict() for m in records],
        "count": len(records),
        "total": total_count,
    }


@router.get(
    "/{asset_id}",
    summary="Get maintenance records for an asset",
    response_description="Maintenance records for the asset",
)
def get_maintenance_by_asset(
    asset_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve all maintenance records associated with a specific asset_id."""
    repo = MaintenanceRepository(db)
    records = repo.get_by_asset_id(asset_id)
    if not records:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No maintenance records found for asset '{asset_id}'",
        )
    return {
        "data": [m.to_dict() for m in records],
        "count": len(records),
    }
