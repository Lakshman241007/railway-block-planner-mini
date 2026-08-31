"""
Tests for the SMMS Collector.

Covers:
  • Successful CSV loading
  • Correct number of records returned
  • Correct field values read from CSV
  • Missing-file error handling
  • Empty-file error handling
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from backend.app.data_integration.collectors.smms_collector import SMMSCollector


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_csv(tmp_path: Path) -> Path:
    """Create a minimal valid SMMS CSV file and return its path."""
    content = textwrap.dedent("""\
        asset_id,asset_type,location,maintenance_type,maintenance_required,priority,required_duration,requested_date,preferred_start,required_resources,equipment,status
        TRK-1025,Track,Chennai-Arakkonam,Preventive,Yes,High,120,2026-09-05,10:00,8,Tamping Machine,Pending
        SIG-2041,Signal,Station_A,Inspection,Yes,Medium,60,2026-09-05,12:00,3,Signal Testing Kit,Pending
    """)
    csv_file = tmp_path / "test_smms.csv"
    csv_file.write_text(content, encoding="utf-8")
    return csv_file


@pytest.fixture()
def empty_csv(tmp_path: Path) -> Path:
    """Create an empty CSV file (header only) and return its path."""
    content = "asset_id,asset_type,location,maintenance_type,maintenance_required,priority,required_duration,requested_date,preferred_start,required_resources,equipment,status\n"
    csv_file = tmp_path / "empty_smms.csv"
    csv_file.write_text(content, encoding="utf-8")
    return csv_file


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSMMSCollector:
    """Tests for :class:`SMMSCollector`."""

    def test_csv_loads_correctly(self, sample_csv: Path) -> None:
        """The collector should return a non-empty list of dicts."""
        collector = SMMSCollector(file_path=sample_csv)
        records = collector.collect()
        assert isinstance(records, list)
        assert len(records) > 0

    def test_multiple_records_returned(self, sample_csv: Path) -> None:
        """Two data rows should produce exactly two records."""
        collector = SMMSCollector(file_path=sample_csv)
        records = collector.collect()
        assert len(records) == 2

    def test_fields_read_correctly(self, sample_csv: Path) -> None:
        """Field values must match the CSV content."""
        collector = SMMSCollector(file_path=sample_csv)
        records = collector.collect()
        first = records[0]

        assert first["asset_id"] == "TRK-1025"
        assert first["asset_type"] == "Track"
        assert first["location"] == "Chennai-Arakkonam"
        assert first["maintenance_type"] == "Preventive"
        assert first["maintenance_required"] == "Yes"
        assert first["priority"] == "High"
        assert first["required_duration"] == "120"
        assert first["requested_date"] == "2026-09-05"
        assert first["preferred_start"] == "10:00"
        assert first["required_resources"] == "8"
        assert first["equipment"] == "Tamping Machine"
        assert first["status"] == "Pending"

    def test_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        """A missing CSV must raise FileNotFoundError."""
        collector = SMMSCollector(file_path=tmp_path / "nonexistent.csv")
        with pytest.raises(FileNotFoundError):
            collector.collect()

    def test_empty_csv_raises_value_error(self, empty_csv: Path) -> None:
        """A CSV with only a header (no data rows) must raise ValueError."""
        collector = SMMSCollector(file_path=empty_csv)
        with pytest.raises(ValueError, match="empty"):
            collector.collect()

    def test_mock_csv_loads_from_project(self) -> None:
        """The actual mock_smms.csv in the repo must load successfully."""
        project_root = Path(__file__).resolve().parents[2]
        csv_path = project_root / "data" / "raw" / "smms" / "mock_smms.csv"
        if not csv_path.exists():
            pytest.skip("mock_smms.csv not found at expected location")

        collector = SMMSCollector(file_path=csv_path)
        records = collector.collect()
        assert len(records) >= 10  # spec requires at least 10
