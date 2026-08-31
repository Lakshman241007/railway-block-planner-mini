"""
Timetable Validator — validates raw timetable records.

Responsibility
--------------
Raw dict (from the provider)  →  (is_valid, list_of_errors)

Usage
-----
    from backend.app.data_integration.validators.timetable_validator import TimetableValidator

    validator = TimetableValidator()
    is_valid, errors = validator.validate(record)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FIELDS: List[str] = [
    "train_id",
    "service_date",
    "station_code",
    "sequence",
]

# arrival_time and departure_time are semi-optional:
# origin stations have no arrival, terminus stations have no departure.
# We use "--" as a sentinel for "not applicable".


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class TimetableValidator:
    """Validates a single raw timetable record."""

    def validate(self, record: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate a raw timetable record.

        Returns
        -------
        tuple[bool, list[str]]
            ``(True, [])`` when valid; ``(False, [errors])`` otherwise.
        """
        errors: List[str] = []

        # 1. Required-field checks
        for field in REQUIRED_FIELDS:
            value = record.get(field, "").strip()
            if not value:
                errors.append(f"Missing or empty required field: '{field}'")

        # 2. Date format check
        self._validate_date(record, "service_date", errors)

        # 3. Time format checks (allow "--" as "not applicable")
        self._validate_time_or_dash(record, "arrival_time", errors)
        self._validate_time_or_dash(record, "departure_time", errors)

        # 4. Sequence must be a positive integer
        self._validate_positive_integer(record, "sequence", errors)

        # 5. Platform must be a positive integer if present
        platform = record.get("platform", "").strip()
        if platform:
            self._validate_positive_integer(record, "platform", errors)

        is_valid = len(errors) == 0

        if not is_valid:
            train_id = record.get("train_id", "<unknown>")
            station = record.get("station_code", "<unknown>")
            logger.warning(
                "Validation failed for timetable record '%s@%s': %s",
                train_id,
                station,
                "; ".join(errors),
            )

        return is_valid, errors

    @staticmethod
    def _validate_date(
        record: Dict[str, str],
        field: str,
        errors: List[str],
    ) -> None:
        """Check that *field* is a valid ISO-8601 date (YYYY-MM-DD)."""
        raw = record.get(field, "").strip()
        if not raw:
            return
        try:
            datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            errors.append(
                f"'{field}' must be a valid date (YYYY-MM-DD), got: '{raw}'"
            )

    @staticmethod
    def _validate_time_or_dash(
        record: Dict[str, str],
        field: str,
        errors: List[str],
    ) -> None:
        """Check that *field* is a valid time (HH:MM) or '--' for N/A."""
        raw = record.get(field, "").strip()
        if not raw or raw == "--":
            return  # blank or dash sentinel is acceptable
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError:
            errors.append(
                f"'{field}' must be a valid 24-hour time (HH:MM) or '--', got: '{raw}'"
            )

    @staticmethod
    def _validate_positive_integer(
        record: Dict[str, str],
        field: str,
        errors: List[str],
    ) -> None:
        """Check that *field* is a positive integer."""
        raw = record.get(field, "").strip()
        if not raw:
            return
        try:
            value = int(raw)
        except ValueError:
            errors.append(f"'{field}' must be an integer, got: '{raw}'")
            return
        if value <= 0:
            errors.append(f"'{field}' must be a positive integer, got: {value}")
