"""
Tests for the SMMS Normalizer.

Covers:
  • "Yes" → True, "No" → False
  • Duration string → integer
  • Resources string → integer
  • Date string → datetime.date
  • Time string → datetime.time
  • Field renaming (required_duration → duration_minutes)
  • Source provenance is set to "smms"
"""

from __future__ import annotations

import copy
from datetime import date, time

import pytest

from backend.app.data_integration.normalizer import SMMSNormalizer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_RAW_RECORD: dict[str, str] = {
    "asset_id": "TRK-1025",
    "asset_type": "Track",
    "location": "Chennai-Arakkonam",
    "maintenance_type": "Preventive",
    "maintenance_required": "Yes",
    "priority": "High",
    "required_duration": "120",
    "requested_date": "2026-09-05",
    "preferred_start": "10:00",
    "required_resources": "8",
    "equipment": "Tamping Machine",
    "status": "Pending",
}


@pytest.fixture()
def normalizer() -> SMMSNormalizer:
    return SMMSNormalizer()


@pytest.fixture()
def raw_record() -> dict[str, str]:
    return copy.deepcopy(VALID_RAW_RECORD)


# ---------------------------------------------------------------------------
# Tests — boolean conversion
# ---------------------------------------------------------------------------

class TestBooleanConversion:
    """maintenance_required: 'Yes' → True, 'No' → False."""

    def test_yes_becomes_true(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        raw_record["maintenance_required"] = "Yes"
        result = normalizer.normalize(raw_record)
        assert result["maintenance_required"] is True

    def test_no_becomes_false(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        raw_record["maintenance_required"] = "No"
        result = normalizer.normalize(raw_record)
        assert result["maintenance_required"] is False


# ---------------------------------------------------------------------------
# Tests — numeric conversion
# ---------------------------------------------------------------------------

class TestNumericConversion:
    """Duration and resources must become Python ints."""

    def test_duration_becomes_integer(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        raw_record["required_duration"] = "180"
        result = normalizer.normalize(raw_record)
        assert result["duration_minutes"] == 180
        assert isinstance(result["duration_minutes"], int)

    def test_resources_become_integer(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        raw_record["required_resources"] = "12"
        result = normalizer.normalize(raw_record)
        assert result["required_resources"] == 12
        assert isinstance(result["required_resources"], int)


# ---------------------------------------------------------------------------
# Tests — date / time conversion
# ---------------------------------------------------------------------------

class TestDateTimeConversion:
    """Date and time strings must become native Python types."""

    def test_date_becomes_date_object(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        raw_record["requested_date"] = "2026-09-05"
        result = normalizer.normalize(raw_record)
        assert result["requested_date"] == date(2026, 9, 5)
        assert isinstance(result["requested_date"], date)

    def test_time_becomes_time_object(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        raw_record["preferred_start"] = "14:30"
        result = normalizer.normalize(raw_record)
        assert result["preferred_start"] == time(14, 30)
        assert isinstance(result["preferred_start"], time)


# ---------------------------------------------------------------------------
# Tests — field renaming & provenance
# ---------------------------------------------------------------------------

class TestFieldMapping:
    """The normalizer renames required_duration → duration_minutes."""

    def test_duration_field_renamed(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        result = normalizer.normalize(raw_record)
        assert "duration_minutes" in result
        assert "required_duration" not in result

    def test_source_set_to_smms(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        result = normalizer.normalize(raw_record)
        assert result["source"] == "smms"

    def test_passthrough_fields_preserved(
        self, normalizer: SMMSNormalizer, raw_record: dict[str, str]
    ) -> None:
        result = normalizer.normalize(raw_record)
        assert result["asset_id"] == "TRK-1025"
        assert result["asset_type"] == "Track"
        assert result["location"] == "Chennai-Arakkonam"
        assert result["maintenance_type"] == "Preventive"
        assert result["equipment"] == "Tamping Machine"
        assert result["priority"] == "High"
        assert result["status"] == "Pending"


# ===========================================================================
# Phase 2 — TMS Normalizer Tests
# ===========================================================================

from backend.app.data_integration.normalizer import TMSNormalizer


class TestTMSNormalizer:
    """Tests for :class:`TMSNormalizer`."""

    def test_normalize_tms_record(self) -> None:
        normalizer = TMSNormalizer()
        raw = {
            "train_id": "G123",
            "train_type": "Goods",
            "origin": "Chennai",
            "destination": "Arakkonam",
            "current_station": "Chennai",
            "next_station": "AJJ",
            "status": "Running",
            "scheduled_arrival": "09:30",
            "scheduled_departure": "09:35",
            "actual_arrival": "09:32",
            "actual_departure": "09:37",
        }
        res = normalizer.normalize(raw)
        assert res["train_id"] == "G123"
        assert res["source"] == "tms"
        assert res["status"] == "Running"


# ===========================================================================
# Phase 2 — TDMS Normalizer Tests
# ===========================================================================

from backend.app.data_integration.normalizer import TDMSNormalizer


class TestTDMSNormalizer:
    """Tests for :class:`TDMSNormalizer`."""

    def test_normalize_tdms_record(self) -> None:
        normalizer = TDMSNormalizer()
        raw = {
            "train_id": "G123",
            "train_type": "Goods",
            "route_id": "R-CHN-AJJ",
            "origin": "Chennai",
            "destination": "Arakkonam",
            "priority": "High",
            "status": "Delayed",
            "expected_arrival": "09:45",
            "expected_departure": "09:50",
        }
        res = normalizer.normalize(raw)
        assert res["train_id"] == "G123"
        assert res["route_id"] == "R-CHN-AJJ"
        assert res["priority"] == "High"
        assert res["source"] == "tdms"


# ===========================================================================
# Phase 2 — COA Normalizer Tests
# ===========================================================================

from backend.app.data_integration.normalizer import COANormalizer


class TestCOANormalizer:
    """Tests for :class:`COANormalizer`."""

    def test_normalize_coa_record(self) -> None:
        normalizer = COANormalizer()
        raw = {
            "train_id": "G123",
            "route_id": "R-CHN-AJJ",
            "section": "Chennai-Perambur",
            "direction": "Up",
            "movement_status": "Occupied",
            "entry_time": "09:30",
            "exit_time": "09:40",
            "line": "Main",
        }
        res = normalizer.normalize(raw)
        assert res["train_id"] == "G123"
        assert res["section"] == "Chennai-Perambur"
        assert res["source"] == "coa"


# ===========================================================================
# Phase 2 — BDMS Normalizer Tests
# ===========================================================================

from backend.app.data_integration.normalizer import BDMSNormalizer


class TestBDMSNormalizer:
    """Tests for :class:`BDMSNormalizer`."""

    def test_normalize_bdms_record(self) -> None:
        normalizer = BDMSNormalizer()
        raw = {
            "block_id": "BLK-001",
            "location": "KM35-37",
            "block_type": "Maintenance",
            "requested_date": "2026-09-05",
            "requested_start": "10:00",
            "requested_end": "12:00",
            "reason": "Track maintenance",
            "priority": "High",
            "status": "Requested",
        }
        res = normalizer.normalize(raw)
        assert res["block_id"] == "BLK-001"
        assert res["requested_date"] == date(2026, 9, 5)
        assert res["source"] == "bdms"


# ===========================================================================
# Phase 2 — Timetable Normalizer Tests
# ===========================================================================

from backend.app.data_integration.normalizer import TimetableNormalizer


class TestTimetableNormalizer:
    """Tests for :class:`TimetableNormalizer`."""

    def test_normalize_timetable_record(self) -> None:
        normalizer = TimetableNormalizer()
        raw = {
            "train_id": "G123",
            "service_date": "2026-09-05",
            "station_code": "Chennai",
            "arrival_time": "--",
            "departure_time": "09:35",
            "platform": "3",
            "sequence": "1",
        }
        res = normalizer.normalize(raw)
        assert res["train_id"] == "G123"
        assert res["service_date"] == date(2026, 9, 5)
        assert res["arrival_time"] is None
        assert res["departure_time"] == "09:35"
        assert res["platform"] == 3
        assert res["sequence"] == 1
        assert res["source"] == "timetable"

