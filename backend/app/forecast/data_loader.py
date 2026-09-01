"""
Data loader helper for goods train forecasting.

Loads train records, movements, and timetables from either database repositories
or in-memory IntegrationResults for the forecasting engine.
"""

from __future__ import annotations

from typing import List, Optional, Union
from sqlalchemy.orm import Session

from backend.app.database.repositories import (
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.schemas.unified_data import (
    MovementRecord,
    TimetableRecord,
    TrainRecord,
)


class ForecastDataLoader:
    """
    Helper to fetch inputs for goods train forecasting.
    """

    def __init__(self, db: Optional[Session] = None) -> None:
        self.db = db

    def get_goods_trains_from_db(self) -> List[TrainRecord]:
        """Fetch all trains identified as Goods trains from database."""
        if not self.db:
            return []
        repo = TrainRepository(self.db)
        all_trains = repo.get_all(limit=1000)
        goods_trains: List[TrainRecord] = []
        for t in all_trains:
            if t.train_type.lower() in ("goods", "freight") or t.train_id.upper().startswith("G"):
                goods_trains.append(t.to_pydantic())
        return goods_trains

    def get_movements_from_db(self, train_id: Optional[str] = None) -> List[MovementRecord]:
        """Fetch corridor movements from database."""
        if not self.db:
            return []
        repo = MovementRepository(self.db)
        if train_id:
            movements = repo.get_by_train_id(train_id)
        else:
            movements = repo.get_all(limit=1000)
        return [m.to_pydantic() for m in movements]

    def get_timetables_from_db(self, train_id: Optional[str] = None) -> List[TimetableRecord]:
        """Fetch timetable records from database."""
        if not self.db:
            return []
        repo = TimetableRepository(self.db)
        if train_id:
            tts = repo.get_by_train_id(train_id)
        else:
            tts = repo.get_all(limit=1000)
        return [tt.to_pydantic() for tt in tts]

    @staticmethod
    def filter_goods_trains(trains: List[TrainRecord]) -> List[TrainRecord]:
        """Filter a list of TrainRecords to only goods/freight trains."""
        return [
            t for t in trains
            if t.train_type.lower() in ("goods", "freight") or t.train_id.upper().startswith("G")
        ]
