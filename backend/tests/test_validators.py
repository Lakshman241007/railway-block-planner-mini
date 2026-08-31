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


# ===========================================================================
# Phase 2 — TMS Validator Tests
# ===========================================================================

from backend.app.data_integration.validators.tms_validator import TMSValidator


class TestTMSValidator:
    """Tests for :class:`TMSValidator`."""

    @pytest.fixture()
    def validator(self) -> TMSValidator:
        return TMSValidator()

    @pytest.fixture()
    def valid_tms_record(self) -> dict[str, str]:
        return {
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

    def test_valid_record_passes(
        self, validator: TMSValidator, valid_tms_record: dict[str, str]
    ) -> None:
        is_valid, errors = validator.validate(valid_tms_record)
        assert is_valid is True
        assert errors == []

    def test_missing_required_field_fails(
        self, validator: TMSValidator, valid_tms_record: dict[str, str]
    ) -> None:
        valid_tms_record["train_id"] = ""
        is_valid, errors = validator.validate(valid_tms_record)
        assert is_valid is False
        assert any("train_id" in e for e in errors)

    def test_invalid_status_fails(
        self, validator: TMSValidator, valid_tms_record: dict[str, str]
    ) -> None:
        valid_tms_record["status"] = "Derailed"
        is_valid, errors = validator.validate(valid_tms_record)
        assert is_valid is False
        assert any("status" in e for e in errors)

    def test_invalid_time_format_fails(
        self, validator: TMSValidator, valid_tms_record: dict[str, str]
    ) -> None:
        valid_tms_record["scheduled_arrival"] = "9:30 AM"
        is_valid, errors = validator.validate(valid_tms_record)
        assert is_valid is False
        assert any("scheduled_arrival" in e for e in errors)


# ===========================================================================
# Phase 2 — TDMS Validator Tests
# ===========================================================================

from backend.app.data_integration.validators.tdms_validator import TDMSValidator


class TestTDMSValidator:
    """Tests for :class:`TDMSValidator`."""

    @pytest.fixture()
    def validator(self) -> TDMSValidator:
        return TDMSValidator()

    @pytest.fixture()
    def valid_tdms_record(self) -> dict[str, str]:
        return {
            "train_id": "G123",
            "train_type": "Goods",
            "route_id": "R-CHN-AJJ",
            "origin": "Chennai",
            "destination": "Arakkonam",
            "priority": "High",
            "status": "Running",
            "expected_arrival": "09:45",
            "expected_departure": "09:50",
        }

    def test_valid_record_passes(
        self, validator: TDMSValidator, valid_tdms_record: dict[str, str]
    ) -> None:
        is_valid, errors = validator.validate(valid_tdms_record)
        assert is_valid is True
        assert errors == []

    def test_invalid_priority_fails(
        self, validator: TDMSValidator, valid_tdms_record: dict[str, str]
    ) -> None:
        valid_tdms_record["priority"] = "SuperHigh"
        is_valid, errors = validator.validate(valid_tdms_record)
        assert is_valid is False
        assert any("priority" in e for e in errors)

    def test_missing_route_id_fails(
        self, validator: TDMSValidator, valid_tdms_record: dict[str, str]
    ) -> None:
        valid_tdms_record["route_id"] = ""
        is_valid, errors = validator.validate(valid_tdms_record)
        assert is_valid is False
        assert any("route_id" in e for e in errors)


# ===========================================================================
# Phase 2 — COA Validator Tests
# ===========================================================================

from backend.app.data_integration.validators.coa_validator import COAValidator


class TestCOAValidator:
    """Tests for :class:`COAValidator`."""

    @pytest.fixture()
    def validator(self) -> COAValidator:
        return COAValidator()

    @pytest.fixture()
    def valid_coa_record(self) -> dict[str, str]:
        return {
            "train_id": "G123",
            "route_id": "R-CHN-AJJ",
            "section": "Chennai-Perambur",
            "direction": "Up",
            "movement_status": "Occupied",
            "entry_time": "09:30",
            "exit_time": "09:40",
            "line": "Main",
        }

    def test_valid_record_passes(
        self, validator: COAValidator, valid_coa_record: dict[str, str]
    ) -> None:
        is_valid, errors = validator.validate(valid_coa_record)
        assert is_valid is True
        assert errors == []

    def test_invalid_direction_fails(
        self, validator: COAValidator, valid_coa_record: dict[str, str]
    ) -> None:
        valid_coa_record["direction"] = "Left"
        is_valid, errors = validator.validate(valid_coa_record)
        assert is_valid is False
        assert any("direction" in e for e in errors)

    def test_invalid_movement_status_fails(
        self, validator: COAValidator, valid_coa_record: dict[str, str]
    ) -> None:
        valid_coa_record["movement_status"] = "Broken"
        is_valid, errors = validator.validate(valid_coa_record)
        assert is_valid is False
        assert any("movement_status" in e for e in errors)


# ===========================================================================
# Phase 2 — BDMS Validator Tests
# ===========================================================================

from backend.app.data_integration.validators.bdms_validator import BDMSValidator


class TestBDMSValidator:
    """Tests for :class:`BDMSValidator`."""

    @pytest.fixture()
    def validator(self) -> BDMSValidator:
        return BDMSValidator()

    @pytest.fixture()
    def valid_bdms_record(self) -> dict[str, str]:
        return {
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

    def test_valid_record_passes(
        self, validator: BDMSValidator, valid_bdms_record: dict[str, str]
    ) -> None:
        is_valid, errors = validator.validate(valid_bdms_record)
        assert is_valid is True
        assert errors == []

    def test_invalid_block_type_fails(
        self, validator: BDMSValidator, valid_bdms_record: dict[str, str]
    ) -> None:
        valid_bdms_record["block_type"] = "Special"
        is_valid, errors = validator.validate(valid_bdms_record)
        assert is_valid is False
        assert any("block_type" in e for e in errors)

    def test_invalid_date_format_fails(
        self, validator: BDMSValidator, valid_bdms_record: dict[str, str]
    ) -> None:
        valid_bdms_record["requested_date"] = "05/09/2026"
        is_valid, errors = validator.validate(valid_bdms_record)
        assert is_valid is False
        assert any("requested_date" in e for e in errors)


# ===========================================================================
# Phase 2 — Timetable Validator Tests
# ===========================================================================

from backend.app.data_integration.validators.timetable_validator import TimetableValidator


class TestTimetableValidator:
    """Tests for :class:`TimetableValidator`."""

    @pytest.fixture()
    def validator(self) -> TimetableValidator:
        return TimetableValidator()

    @pytest.fixture()
    def valid_timetable_record(self) -> dict[str, str]:
        return {
            "train_id": "G123",
            "service_date": "2026-09-05",
            "station_code": "Chennai",
            "arrival_time": "--",
            "departure_time": "09:35",
            "platform": "3",
            "sequence": "1",
        }

    def test_valid_record_passes(
        self, validator: TimetableValidator, valid_timetable_record: dict[str, str]
    ) -> None:
        is_valid, errors = validator.validate(valid_timetable_record)
        assert is_valid is True
        assert errors == []

    def test_sequence_must_be_positive_int(
        self, validator: TimetableValidator, valid_timetable_record: dict[str, str]
    ) -> None:
        valid_timetable_record["sequence"] = "0"
        is_valid, errors = validator.validate(valid_timetable_record)
        assert is_valid is False
        assert any("sequence" in e for e in errors)

    def test_invalid_time_fails(
        self, validator: TimetableValidator, valid_timetable_record: dict[str, str]
    ) -> None:
        valid_timetable_record["departure_time"] = "invalid_time"
        is_valid, errors = validator.validate(valid_timetable_record)
        assert is_valid is False
        assert any("departure_time" in e for e in errors)

