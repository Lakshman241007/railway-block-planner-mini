"""
Repository layer providing CRUD and specialized query operations for
unified railway entities.

Keeps database queries encapsulated and separate from API route handlers.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.database.models import (
    Block,
    Maintenance,
    Movement,
    Timetable,
    Train,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    MaintenanceRecord,
    MovementRecord,
    TimetableRecord,
    TrainRecord,
)


# ===========================================================================
# Train Repository
# ===========================================================================

class TrainRepository:
    """Repository handling CRUD and queries for Train entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, train: Union[TrainRecord, Dict[str, Any]]) -> Train:
        """Create and persist a new train record."""
        data = train.model_dump() if isinstance(train, TrainRecord) else dict(train)
        # Convert enums to string values if necessary
        if "status" in data and hasattr(data["status"], "value"):
            data["status"] = data["status"].value
        if "priority" in data and hasattr(data["priority"], "value"):
            data["priority"] = data["priority"].value

        record = Train(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, train_id: str) -> Optional[Train]:
        """Fetch a single train by its unique identifier."""
        return self.db.query(Train).filter(Train.train_id == train_id).first()

    def get_all(
        self,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Train]:
        """Fetch trains with optional status filtering and pagination."""
        query = self.db.query(Train)
        if status:
            query = query.filter(func.lower(Train.status) == status.lower())
        return query.order_by(Train.train_id).offset(skip).limit(limit).all()

    def count(self, status: Optional[str] = None) -> int:
        """Return total count of trains matching the filter."""
        query = self.db.query(func.count(Train.train_id))
        if status:
            query = query.filter(func.lower(Train.status) == status.lower())
        return query.scalar() or 0

    def update(self, train_id: str, values: Dict[str, Any]) -> Optional[Train]:
        """Update train attributes and return the updated entity."""
        record = self.get_by_id(train_id)
        if not record:
            return None
        for key, val in values.items():
            if hasattr(record, key):
                setattr(record, key, val)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, train_id: str) -> bool:
        """Delete a train by ID. Returns True if deleted, False if not found."""
        record = self.get_by_id(train_id)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True


# ===========================================================================
# Maintenance Repository
# ===========================================================================

class MaintenanceRepository:
    """Repository handling CRUD and queries for Maintenance entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, maint: Union[MaintenanceRecord, Dict[str, Any]]) -> Maintenance:
        """Create and persist a new maintenance record."""
        data = maint.model_dump() if isinstance(maint, MaintenanceRecord) else dict(maint)
        if "priority" in data and hasattr(data["priority"], "value"):
            data["priority"] = data["priority"].value
        if "status" in data and hasattr(data["status"], "value"):
            data["status"] = data["status"].value
        if "preferred_start" in data and hasattr(data["preferred_start"], "strftime"):
            data["preferred_start"] = data["preferred_start"].strftime("%H:%M")
        elif "preferred_start" in data:
            data["preferred_start"] = str(data["preferred_start"])
        if isinstance(data.get("requested_date"), str):
            data["requested_date"] = date.fromisoformat(data["requested_date"])

        record = Maintenance(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, id_: int) -> Optional[Maintenance]:
        """Fetch a single maintenance record by internal integer ID."""
        return self.db.query(Maintenance).filter(Maintenance.id == id_).first()

    def get_by_asset_id(self, asset_id: str) -> List[Maintenance]:
        """Fetch all maintenance records for a given asset ID."""
        return (
            self.db.query(Maintenance)
            .filter(Maintenance.asset_id == asset_id)
            .order_by(Maintenance.requested_date)
            .all()
        )

    def get_all(
        self,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        asset_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Maintenance]:
        """Fetch maintenance records with optional filters and pagination."""
        query = self.db.query(Maintenance)
        if priority:
            query = query.filter(func.lower(Maintenance.priority) == priority.lower())
        if status:
            query = query.filter(func.lower(Maintenance.status) == status.lower())
        if asset_id:
            query = query.filter(Maintenance.asset_id == asset_id)
        return query.order_by(Maintenance.id).offset(skip).limit(limit).all()

    def get_pending(self) -> List[Maintenance]:
        """Convenience method to retrieve all pending maintenance requests."""
        return self.get_all(status="Pending", limit=1000)

    def count(
        self,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> int:
        """Return total count of maintenance records matching filters."""
        query = self.db.query(func.count(Maintenance.id))
        if priority:
            query = query.filter(func.lower(Maintenance.priority) == priority.lower())
        if status:
            query = query.filter(func.lower(Maintenance.status) == status.lower())
        if asset_id:
            query = query.filter(Maintenance.asset_id == asset_id)
        return query.scalar() or 0

    def update(self, id_: int, values: Dict[str, Any]) -> Optional[Maintenance]:
        """Update maintenance record by ID."""
        record = self.get_by_id(id_)
        if not record:
            return None
        for key, val in values.items():
            if hasattr(record, key):
                setattr(record, key, val)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, id_: int) -> bool:
        """Delete a maintenance record by ID."""
        record = self.get_by_id(id_)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True


# ===========================================================================
# Movement Repository
# ===========================================================================

class MovementRepository:
    """Repository handling CRUD and queries for corridor Movement entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, move: Union[MovementRecord, Dict[str, Any]]) -> Movement:
        """Create and persist a new movement record."""
        data = move.model_dump() if isinstance(move, MovementRecord) else dict(move)
        record = Movement(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, id_: int) -> Optional[Movement]:
        """Fetch a single movement by ID."""
        return self.db.query(Movement).filter(Movement.id == id_).first()

    def get_by_train_id(self, train_id: str) -> List[Movement]:
        """Fetch movements for a specific train."""
        return (
            self.db.query(Movement)
            .filter(Movement.train_id == train_id)
            .order_by(Movement.entry_time)
            .all()
        )

    def get_by_section(self, section: str) -> List[Movement]:
        """Fetch movements for a specific section/corridor."""
        return (
            self.db.query(Movement)
            .filter(func.lower(Movement.section) == section.lower())
            .order_by(Movement.entry_time)
            .all()
        )

    def get_all(
        self,
        train_id: Optional[str] = None,
        section: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Movement]:
        """Fetch movement records with optional filters and pagination."""
        query = self.db.query(Movement)
        if train_id:
            query = query.filter(Movement.train_id == train_id)
        if section:
            query = query.filter(func.lower(Movement.section) == section.lower())
        return query.order_by(Movement.id).offset(skip).limit(limit).all()

    def count(
        self,
        train_id: Optional[str] = None,
        section: Optional[str] = None,
    ) -> int:
        """Return total count of movement records."""
        query = self.db.query(func.count(Movement.id))
        if train_id:
            query = query.filter(Movement.train_id == train_id)
        if section:
            query = query.filter(func.lower(Movement.section) == section.lower())
        return query.scalar() or 0

    def update(self, id_: int, values: Dict[str, Any]) -> Optional[Movement]:
        """Update movement record by ID."""
        record = self.get_by_id(id_)
        if not record:
            return None
        for key, val in values.items():
            if hasattr(record, key):
                setattr(record, key, val)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, id_: int) -> bool:
        """Delete a movement record by ID."""
        record = self.get_by_id(id_)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True


# ===========================================================================
# Block Repository
# ===========================================================================

class BlockRepository:
    """Repository handling CRUD and queries for Block / disconnection entities."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, block: Union[BlockRecord, Dict[str, Any]]) -> Block:
        """Create and persist a new block record."""
        data = block.model_dump() if isinstance(block, BlockRecord) else dict(block)
        if "block_type" in data and hasattr(data["block_type"], "value"):
            data["block_type"] = data["block_type"].value
        if "priority" in data and hasattr(data["priority"], "value"):
            data["priority"] = data["priority"].value
        if "status" in data and hasattr(data["status"], "value"):
            data["status"] = data["status"].value
        if isinstance(data.get("requested_date"), str):
            data["requested_date"] = date.fromisoformat(data["requested_date"])

        record = Block(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, block_id: str) -> Optional[Block]:
        """Fetch a single block by its block_id."""
        return self.db.query(Block).filter(Block.block_id == block_id).first()

    def get_by_date(self, requested_date: Union[date, str]) -> List[Block]:
        """Fetch blocks requested for a specific date."""
        d = date.fromisoformat(requested_date) if isinstance(requested_date, str) else requested_date
        return self.db.query(Block).filter(Block.requested_date == d).all()

    def get_by_location(self, location: str) -> List[Block]:
        """Fetch blocks for a specific location."""
        return (
            self.db.query(Block)
            .filter(func.lower(Block.location).contains(location.lower()))
            .all()
        )

    def get_all(
        self,
        date_filter: Optional[Union[date, str]] = None,
        location: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Block]:
        """Fetch blocks with optional date, location, and status filters."""
        query = self.db.query(Block)
        if date_filter:
            d = date.fromisoformat(date_filter) if isinstance(date_filter, str) else date_filter
            query = query.filter(Block.requested_date == d)
        if location:
            query = query.filter(func.lower(Block.location).contains(location.lower()))
        if status:
            query = query.filter(func.lower(Block.status) == status.lower())
        return query.order_by(Block.block_id).offset(skip).limit(limit).all()

    def count(
        self,
        date_filter: Optional[Union[date, str]] = None,
        location: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """Return total count of block records."""
        query = self.db.query(func.count(Block.block_id))
        if date_filter:
            d = date.fromisoformat(date_filter) if isinstance(date_filter, str) else date_filter
            query = query.filter(Block.requested_date == d)
        if location:
            query = query.filter(func.lower(Block.location).contains(location.lower()))
        if status:
            query = query.filter(func.lower(Block.status) == status.lower())
        return query.scalar() or 0

    def update(self, block_id: str, values: Dict[str, Any]) -> Optional[Block]:
        """Update block record by block_id."""
        record = self.get_by_id(block_id)
        if not record:
            return None
        for key, val in values.items():
            if hasattr(record, key):
                setattr(record, key, val)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, block_id: str) -> bool:
        """Delete a block record by block_id."""
        record = self.get_by_id(block_id)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True


# ===========================================================================
# Timetable Repository
# ===========================================================================

class TimetableRepository:
    """Repository handling CRUD and queries for Timetable entries."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, tt: Union[TimetableRecord, Dict[str, Any]]) -> Timetable:
        """Create and persist a new timetable entry."""
        data = tt.model_dump() if isinstance(tt, TimetableRecord) else dict(tt)
        if isinstance(data.get("service_date"), str):
            data["service_date"] = date.fromisoformat(data["service_date"])

        record = Timetable(**data)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_by_id(self, id_: int) -> Optional[Timetable]:
        """Fetch a single timetable stop by ID."""
        return self.db.query(Timetable).filter(Timetable.id == id_).first()

    def get_by_train_id(self, train_id: str) -> List[Timetable]:
        """Fetch all scheduled stops for a train, ordered by sequence."""
        return (
            self.db.query(Timetable)
            .filter(Timetable.train_id == train_id)
            .order_by(Timetable.sequence)
            .all()
        )

    def get_all(
        self,
        train_id: Optional[str] = None,
        service_date: Optional[Union[date, str]] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Timetable]:
        """Fetch timetable entries with optional filters and pagination."""
        query = self.db.query(Timetable)
        if train_id:
            query = query.filter(Timetable.train_id == train_id)
        if service_date:
            d = date.fromisoformat(service_date) if isinstance(service_date, str) else service_date
            query = query.filter(Timetable.service_date == d)
        return query.order_by(Timetable.train_id, Timetable.sequence).offset(skip).limit(limit).all()

    def count(
        self,
        train_id: Optional[str] = None,
        service_date: Optional[Union[date, str]] = None,
    ) -> int:
        """Return total count of timetable entries."""
        query = self.db.query(func.count(Timetable.id))
        if train_id:
            query = query.filter(Timetable.train_id == train_id)
        if service_date:
            d = date.fromisoformat(service_date) if isinstance(service_date, str) else service_date
            query = query.filter(Timetable.service_date == d)
        return query.scalar() or 0

    def update(self, id_: int, values: Dict[str, Any]) -> Optional[Timetable]:
        """Update timetable entry by ID."""
        record = self.get_by_id(id_)
        if not record:
            return None
        for key, val in values.items():
            if hasattr(record, key):
                setattr(record, key, val)
        self.db.commit()
        self.db.refresh(record)
        return record

    def delete(self, id_: int) -> bool:
        """Delete a timetable entry by ID."""
        record = self.get_by_id(id_)
        if not record:
            return False
        self.db.delete(record)
        self.db.commit()
        return True
