"""
Tests for the SMMS Integrator (end-to-end pipeline).

Covers:
  • Full pipeline: CSV → Collector → Validator → Normalizer → MaintenanceRecord
  • Output consists of valid MaintenanceRecord Pydantic objects
  • Records with invalid data are properly rejected
  • Missing CSV file produces a clear error
"""

from __future__ import annotations

import textwrap
from datetime import date, time
from pathlib import Path

import pytest

from backend.app.data_integration.integrator import SMMSIntegrator
from backend.app.schemas.unified_data import MaintenanceRecord, Priority, MaintenanceStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def valid_csv(tmp_path: Path) -> Path:
    """Create a minimal valid SMMS CSV and return its path."""
    content = textwrap.dedent("""\
        asset_id,asset_type,location,maintenance_type,maintenance_required,priority,required_duration,requested_date,preferred_start,required_resources,equipment,status
        TRK-1025,Track,Chennai-Arakkonam,Preventive,Yes,High,120,2026-09-05,10:00,8,Tamping Machine,Pending
        SIG-2041,Signal,Station_A,Inspection,Yes,Medium,60,2026-09-05,12:00,3,Signal Testing Kit,Approved
    """)
    csv_file = tmp_path / "test_smms.csv"
    csv_file.write_text(content, encoding="utf-8")
    return csv_file


@pytest.fixture()
def csv_with_invalid_row(tmp_path: Path) -> Path:
    """CSV containing one valid and one invalid row."""
    content = textwrap.dedent("""\
        asset_id,asset_type,location,maintenance_type,maintenance_required,priority,required_duration,requested_date,preferred_start,required_resources,equipment,status
        TRK-1025,Track,Chennai-Arakkonam,Preventive,Yes,High,120,2026-09-05,10:00,8,Tamping Machine,Pending
        BAD-0001,Track,Somewhere,Repair,Maybe,Extreme,-5,not-a-date,99:99,zero,Hammer,Unknown
    """)
    csv_file = tmp_path / "mixed_smms.csv"
    csv_file.write_text(content, encoding="utf-8")
    return csv_file


# ---------------------------------------------------------------------------
# Tests — end-to-end pipeline
# ---------------------------------------------------------------------------

class TestSMMSIntegrator:
    """Integration tests for the full SMMS pipeline."""

    def test_pipeline_produces_maintenance_records(
        self, valid_csv: Path
    ) -> None:
        """Every output element must be a MaintenanceRecord."""
        integrator = SMMSIntegrator(csv_path=valid_csv)
        records, rejected = integrator.run()

        assert len(records) == 2
        assert len(rejected) == 0

        for rec in records:
            assert isinstance(rec, MaintenanceRecord)

    def test_record_fields_are_correct(self, valid_csv: Path) -> None:
        """Spot-check that normalized values are correct."""
        integrator = SMMSIntegrator(csv_path=valid_csv)
        records, _ = integrator.run()

        first = records[0]
        assert first.asset_id == "TRK-1025"
        assert first.asset_type == "Track"
        assert first.location == "Chennai-Arakkonam"
        assert first.maintenance_type == "Preventive"
        assert first.maintenance_required is True
        assert first.priority == Priority.HIGH
        assert first.duration_minutes == 120
        assert first.requested_date == date(2026, 9, 5)
        assert first.preferred_start == time(10, 0)
        assert first.required_resources == 8
        assert first.equipment == "Tamping Machine"
        assert first.status == MaintenanceStatus.PENDING
        assert first.source == "smms"

    def test_invalid_rows_are_rejected(
        self, csv_with_invalid_row: Path
    ) -> None:
        """Invalid rows go into the rejected list, not the records list."""
        integrator = SMMSIntegrator(csv_path=csv_with_invalid_row)
        records, rejected = integrator.run()

        assert len(records) == 1
        assert len(rejected) == 1

        # The rejected item should contain the original record and errors
        assert "record" in rejected[0]
        assert "errors" in rejected[0]
        assert len(rejected[0]["errors"]) > 0

    def test_missing_csv_raises_error(self, tmp_path: Path) -> None:
        """A missing CSV file must raise FileNotFoundError."""
        integrator = SMMSIntegrator(
            csv_path=tmp_path / "nonexistent.csv"
        )
        with pytest.raises(FileNotFoundError):
            integrator.run()

    def test_full_mock_csv_pipeline(self) -> None:
        """Run the full pipeline against the actual mock_smms.csv."""
        project_root = Path(__file__).resolve().parents[2]
        csv_path = project_root / "data" / "raw" / "smms" / "mock_smms.csv"
        if not csv_path.exists():
            pytest.skip("mock_smms.csv not found at expected location")

        integrator = SMMSIntegrator(csv_path=csv_path)
        records, rejected = integrator.run()

        # We expect at least 10 records (per spec)
        assert len(records) >= 10

        # Every record must be a valid MaintenanceRecord
        for rec in records:
            assert isinstance(rec, MaintenanceRecord)
            assert rec.source == "smms"
            assert rec.required_resources > 0


# ===========================================================================
# Phase 2 — Multi-Source Railway Data Integrator Tests
# ===========================================================================

from backend.app.data_integration.integrator import RailwayDataIntegrator
from backend.app.schemas.unified_data import (
    TrainRecord,
    MovementRecord,
    BlockRecord,
    TimetableRecord,
)


class TestRailwayDataIntegrator:
    """Tests for the full multi-source pipeline :class:`RailwayDataIntegrator`."""

    def test_full_pipeline_run(self) -> None:
        """Run the full multi-source pipeline and verify all entity types are produced."""
        project_root = Path(__file__).resolve().parents[2]
        data_dir = project_root / "data"

        integrator = RailwayDataIntegrator(data_dir=data_dir)
        result = integrator.run()

        # Check source statistics
        assert result.source_stats.get("tms", 0) >= 10
        assert result.source_stats.get("tdms", 0) >= 10
        assert result.source_stats.get("smms", 0) >= 10
        assert result.source_stats.get("coa", 0) >= 10
        assert result.source_stats.get("bdms", 0) >= 10
        assert result.source_stats.get("timetable", 0) >= 10

        # Check records produced by entity type
        assert len(result.train_records) >= 10
        assert len(result.maintenance_records) >= 10
        assert len(result.movement_records) >= 10
        assert len(result.block_records) >= 10
        assert len(result.timetable_records) >= 10

        # Verify types
        for train in result.train_records:
            assert isinstance(train, TrainRecord)
        for maint in result.maintenance_records:
            assert isinstance(maint, MaintenanceRecord)
        for move in result.movement_records:
            assert isinstance(move, MovementRecord)
        for block in result.block_records:
            assert isinstance(block, BlockRecord)
        for tt in result.timetable_records:
            assert isinstance(tt, TimetableRecord)

        # Check mapping and merge stats
        assert result.mapping_stats.get("train_entities", 0) > 0
        assert result.merge_stats.get("total_trains", 0) > 0

        # Check conflict stats (we deliberately put G123 status conflict)
        assert result.conflict_stats.get("detected", 0) >= 1
        assert result.conflict_stats.get("resolved", 0) >= 1

