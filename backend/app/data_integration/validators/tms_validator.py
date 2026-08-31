"""
TMS Validator — validates raw TMS train movement records.

Responsibility
--------------
Raw dict (from the collector)  →  (is_valid, list_of_errors)

Checks every field for:
  • Presence   – all required fields must exist and be non-empty.
  • Allowed values – status must match a known set.
  • Type       – time fields must parse correctly.

Usage
-----
    from backend.app.data_integration.validators.tms_validator import TMSValidator

    validator = TMSValidator()
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
    "train_type",
    "origin",
    "destination",
    "current_station",
    "next_station",
    "status",
    "scheduled_arrival",
    "scheduled_departure",
]

ALLOWED_STATUSES = {"Running", "Delayed", "Scheduled", "Terminated", "Cancelled"}

ALLOWED_TRAIN_TYPES = {"Goods", "Passenger", "Express", "Freight", "Mixed"}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class TMSValidator:
    """Validates a single raw TMS record (a plain dictionary of strings)."""

    def validate(self, record: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate a raw TMS record.

        Parameters
        ----------
        record : dict[str, str]
            A single row read by the collector.

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

        # 2. Allowed-value checks
        status = record.get("status", "").strip()
        if status and status not in ALLOWED_STATUSES:
            errors.append(
                f"Invalid status value: '{status}'. "
                f"Allowed: {sorted(ALLOWED_STATUSES)}"
            )

        train_type = record.get("train_type", "").strip()
        if train_type and train_type not in ALLOWED_TRAIN_TYPES:
            errors.append(
                f"Invalid train_type value: '{train_type}'. "
                f"Allowed: {sorted(ALLOWED_TRAIN_TYPES)}"
            )

        # 3. Time format checks
        self._validate_time(record, "scheduled_arrival", errors)
        self._validate_time(record, "scheduled_departure", errors)
        self._validate_time_optional(record, "actual_arrival", errors)
        self._validate_time_optional(record, "actual_departure", errors)

        is_valid = len(errors) == 0

        if not is_valid:
            train_id = record.get("train_id", "<unknown>")
            logger.warning(
                "Validation failed for TMS record '%s': %s",
                train_id,
                "; ".join(errors),
            )

        return is_valid, errors

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_time(
        record: Dict[str, str],
        field: str,
        errors: List[str],
    ) -> None:
        """Check that *field* is a valid 24-hour time (HH:MM)."""
        raw = record.get(field, "").strip()
        if not raw:
            return
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError:
            errors.append(
                f"'{field}' must be a valid 24-hour time (HH:MM), got: '{raw}'"
            )

    @staticmethod
    def _validate_time_optional(
        record: Dict[str, str],
        field: str,
        errors: List[str],
    ) -> None:
        """Check optional time field — blank is acceptable."""
        raw = record.get(field, "").strip()
        if not raw:
            return  # optional field, blank is OK
        try:
            datetime.strptime(raw, "%H:%M")
        except ValueError:
            errors.append(
                f"'{field}' must be a valid 24-hour time (HH:MM), got: '{raw}'"
            )
