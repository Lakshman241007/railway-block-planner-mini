"""
Block API endpoints.

Exposes REST endpoints for querying persistent block / disconnection records.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.database.repositories import BlockRepository

router = APIRouter(prefix="/blocks", tags=["Blocks"])


@router.get(
    "",
    summary="List block requests",
    response_description="List of block records and total count",
)
def get_blocks(
    date: Optional[str] = Query(None, description="Filter by requested date (YYYY-MM-DD)"),
    location: Optional[str] = Query(None, description="Filter by section / location keyword"),
    status: Optional[str] = Query(None, description="Filter by block status (Requested, Approved, etc.)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of records to return"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve block requests with optional date, location, and status filters."""
    repo = BlockRepository(db)
    blocks = repo.get_all(date_filter=date, location=location, status=status, skip=skip, limit=limit)
    total_count = repo.count(date_filter=date, location=location, status=status)
    return {
        "data": [b.to_dict() for b in blocks],
        "count": len(blocks),
        "total": total_count,
    }


@router.get(
    "/{block_id}",
    summary="Get block by ID",
    response_description="Single block record",
)
def get_block_by_id(
    block_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve details of a single block by its block_id."""
    repo = BlockRepository(db)
    block = repo.get_by_id(block_id)
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Block request '{block_id}' not found",
        )
    return {
        "data": block.to_dict()
    }
