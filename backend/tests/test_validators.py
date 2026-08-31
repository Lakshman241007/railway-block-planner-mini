"""
Tests for the SMMS Validator.

Covers:
  • Valid record passes validation
  • Missing required fields are detected
  • Invalid priority values are rejected
  • Invalid status values are rejected
  • Invalid duration values are rejected
  • Invalid date formats are rejected
  • Invalid time formats are rejected
  • Invalid maintenance_required values are rejected
"""

from __future__ import annotations

import copy

import pytest

from backend.app.data_integration.validators.smms_validator import SMMSValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_RECORD: dict[str, str] = {
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
def validator() -> SMMSValidator:
    """Return a fresh validator instance."""
    return SMMSValidator()


@pytest.fixture()
def valid_record() -> dict[str, str]:
    """Return a deep copy of a known-valid record."""
    return copy.deepcopy(VALID_RECORD)


# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------

class TestSMMSValidatorHappyPath:
    """Validation should pass for well-formed records."""

    def test_valid_record_passes(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is True
        assert errors == []

    def test_all_priorities_accepted(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        for priority in ("Low", "Medium", "High", "Critical"):
            valid_record["priority"] = priority
            is_valid, _ = validator.validate(valid_record)
            assert is_valid, f"Priority '{priority}' should be accepted"

    def test_all_statuses_accepted(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        for status in ("Pending", "Approved", "Completed", "Cancelled"):
            valid_record["status"] = status
            is_valid, _ = validator.validate(valid_record)
            assert is_valid, f"Status '{status}' should be accepted"


# ---------------------------------------------------------------------------
# Tests — missing required fields
# ---------------------------------------------------------------------------

class TestSMMSValidatorMissingFields:
    """Every required field must be checked for presence."""

    @pytest.mark.parametrize("field", [
        "asset_id",
        "asset_type",
        "location",
        "maintenance_type",
        "maintenance_required",
        "priority",
        "required_duration",
        "requested_date",
        "preferred_start",
        "required_resources",
        "equipment",
        "status",
    ])
    def test_missing_required_field_fails(
        self,
        validator: SMMSValidator,
        valid_record: dict[str, str],
        field: str,
    ) -> None:
        valid_record[field] = ""
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any(field in e for e in errors)

    def test_completely_missing_key_fails(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        del valid_record["asset_id"]
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("asset_id" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — invalid allowed values
# ---------------------------------------------------------------------------

class TestSMMSValidatorAllowedValues:
    """Enum-like fields must reject unknown values."""

    def test_invalid_priority_fails(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["priority"] = "Urgent"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("priority" in e for e in errors)

    def test_invalid_status_fails(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["status"] = "InProgress"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("status" in e for e in errors)

    def test_invalid_maintenance_required_fails(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["maintenance_required"] = "Maybe"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("maintenance_required" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests — type / format validation
# ---------------------------------------------------------------------------

class TestSMMSValidatorTypeChecks:
    """Numeric and date/time fields must be well-formed."""

    def test_invalid_duration_not_a_number(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["required_duration"] = "abc"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("required_duration" in e for e in errors)

    def test_invalid_duration_negative(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["required_duration"] = "-10"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("required_duration" in e for e in errors)

    def test_invalid_duration_zero(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["required_duration"] = "0"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("required_duration" in e for e in errors)

    def test_invalid_resources_not_a_number(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["required_resources"] = "many"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("required_resources" in e for e in errors)

    def test_invalid_date_format(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["requested_date"] = "05-09-2026"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("requested_date" in e for e in errors)

    def test_invalid_date_value(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["requested_date"] = "2026-13-40"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("requested_date" in e for e in errors)

    def test_invalid_time_format(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["preferred_start"] = "10:00 AM"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("preferred_start" in e for e in errors)

    def test_invalid_time_value(
        self, validator: SMMSValidator, valid_record: dict[str, str]
    ) -> None:
        valid_record["preferred_start"] = "25:99"
        is_valid, errors = validator.validate(valid_record)
        assert is_valid is False
        assert any("preferred_start" in e for e in errors)
