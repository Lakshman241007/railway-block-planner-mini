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
