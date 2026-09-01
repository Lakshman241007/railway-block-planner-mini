"""
Database Seeding Script for Railway Block Planner.

Executes the Phase 2 Multi-Source RailwayDataIntegrator pipeline and
persists the resulting unified records into the relational database via
the Repository layer.

Usage
-----
    python -m backend.app.database.seed
    python -m backend.app.database.seed --reset
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.app.data_integration.integrator import (
    IntegrationResult,
    RailwayDataIntegrator,
)
from backend.app.database.connection import SessionLocal, init_db, reset_db
from backend.app.database.models import (
    Block,
    Maintenance,
    Movement,
    Timetable,
    Train,
)
from backend.app.database.repositories import (
    BlockRepository,
    MaintenanceRepository,
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)

logger = logging.getLogger(__name__)


def seed_database(
    data_dir: Optional[Path | str] = None,
    session: Optional[Session] = None,
    reset: bool = False,
) -> Dict[str, Any]:
    """
    Seed the database using unified records from the Phase 2 Integrator.

    Parameters
    ----------
    data_dir : Path | str, optional
        Root directory of raw data files (default: project_root / data).
    session : Session, optional
        Active SQLAlchemy session (if None, creates and manages one).
    reset : bool, default False
        If True, drops and recreates all tables before seeding.

    Returns
    -------
    dict
        Statistics of integration source counts and database insertions.
    """
    project_root = Path(__file__).resolve().parents[3]
    actual_data_dir = Path(data_dir) if data_dir else project_root / "data"

    if reset:
        reset_db()
    else:
        init_db()

    # Step 1: Execute Phase 2 Integrator to obtain unified dataset
    integrator = RailwayDataIntegrator(data_dir=actual_data_dir)
    result: IntegrationResult = integrator.run()

    managed_session = session is None
    db = session or SessionLocal()

    stats = {
        "unified_trains": len(result.train_records),
        "unified_maintenance": len(result.maintenance_records),
        "unified_movements": len(result.movement_records),
        "unified_blocks": len(result.block_records),
        "unified_timetable": len(result.timetable_records),
        "inserted_trains": 0,
        "inserted_maintenance": 0,
        "inserted_movements": 0,
        "inserted_blocks": 0,
        "inserted_timetable": 0,
    }

    try:
        train_repo = TrainRepository(db)
        maint_repo = MaintenanceRepository(db)
        move_repo = MovementRepository(db)
        block_repo = BlockRepository(db)
        tt_repo = TimetableRepository(db)

        # Insert / Upsert Trains
        for tr in result.train_records:
            existing = train_repo.get_by_id(tr.train_id)
            if existing:
                train_repo.update(tr.train_id, tr.model_dump())
            else:
                train_repo.create(tr)
            stats["inserted_trains"] += 1

        # Insert Maintenance records
        for mr in result.maintenance_records:
            # Check duplicate to ensure idempotency
            existing = (
                db.query(Maintenance)
                .filter(
                    Maintenance.asset_id == mr.asset_id,
                    Maintenance.requested_date == mr.requested_date,
                    Maintenance.preferred_start == (
                        mr.preferred_start.strftime("%H:%M")
                        if hasattr(mr.preferred_start, "strftime")
                        else str(mr.preferred_start)
                    ),
                )
                .first()
            )
            if not existing:
                maint_repo.create(mr)
            stats["inserted_maintenance"] += 1

        # Insert Movements
        for mov in result.movement_records:
            existing = (
                db.query(Movement)
                .filter(
                    Movement.train_id == mov.train_id,
                    Movement.section == mov.section,
                    Movement.entry_time == mov.entry_time,
                )
                .first()
            )
            if not existing:
                move_repo.create(mov)
            stats["inserted_movements"] += 1

        # Insert Blocks
        for blk in result.block_records:
            existing = block_repo.get_by_id(blk.block_id)
            if existing:
                block_repo.update(blk.block_id, blk.model_dump())
            else:
                block_repo.create(blk)
            stats["inserted_blocks"] += 1

        # Insert Timetable
        for tt in result.timetable_records:
            existing = (
                db.query(Timetable)
                .filter(
                    Timetable.train_id == tt.train_id,
                    Timetable.service_date == tt.service_date,
                    Timetable.sequence == tt.sequence,
                )
                .first()
            )
            if not existing:
                tt_repo.create(tt)
            stats["inserted_timetable"] += 1

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if managed_session:
            db.close()

    return stats


def main() -> None:
    """CLI entrypoint for database seeding."""
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Seed the Railway Block Planner database with Phase 2 unified data."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate all tables before seeding.",
    )
    args = parser.parse_args()

    print("==================================================")
    print(" Railway Block Planner")
    print(" Phase 3 — Database Seeding")
    print("==================================================")
    print()

    stats = seed_database(reset=args.reset)

    print(f"Train records       : {stats['unified_trains']}")
    print(f"Maintenance records : {stats['unified_maintenance']}")
    print(f"Movement records    : {stats['unified_movements']}")
    print(f"Block records       : {stats['unified_blocks']}")
    print(f"Timetable records   : {stats['unified_timetable']}")
    print()
    print("Database insertion")
    print("------------------")
    print(f"Trains inserted     : {stats['inserted_trains']}")
    print(f"Maintenance         : {stats['inserted_maintenance']}")
    print(f"Movements           : {stats['inserted_movements']}")
    print(f"Blocks              : {stats['inserted_blocks']}")
    print(f"Timetable           : {stats['inserted_timetable']}")
    print()
    try:
        print("✅ Database seed complete")
    except UnicodeEncodeError:
        print("[SUCCESS] Database seed complete")


if __name__ == "__main__":
    main()

