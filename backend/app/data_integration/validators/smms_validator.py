"""
SMMS Validator — validates raw SMMS maintenance records.

Responsibility
--------------
Raw dict (from the collector)  →  (is_valid, list_of_errors)

The validator checks every field for:
  • Presence   – all required fields must exist and be non-empty.
  • Allowed values – enum-like fields must match a known set.
  • Type       – numeric and date/time fields must parse correctly.

The validator never silently modifies data.  If a record is invalid it
returns a list of human-readable error strings explaining each problem.

Usage
-----
    from backend.app.data_integration.validators.smms_validator import SMMSValidator

    validator = SMMSValidator()
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
]

ALLOWED_MAINTENANCE_REQUIRED = {"Yes", "No"}

ALLOWED_PRIORITIES = {"Low", "Medium", "High", "Critical"}

ALLOWED_STATUSES = {"Pending", "Approved", "Completed", "Cancelled"}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class SMMSValidator:
    """
    Validates a single raw SMMS record (a plain dictionary of strings).

    The validator is stateless — call :meth:`validate` once per record.
    """

    def validate(self, record: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate a raw SMMS record.

        Parameters
        ----------
        record : dict[str, str]
            A single row read by the collector.

        Returns
        -------
        tuple[bool, list[str]]
            ``(True, [])`` when the record is valid.
            ``(False, [error1, error2, …])`` when one or more checks fail.
        """
        errors: List[str] = []

        # 1. Required-field checks ------------------------------------------
        for field in REQUIRED_FIELDS:
            value = record.get(field, "").strip()
            if not value:
                errors.append(f"Missing or empty required field: '{field}'")

        # If any required field is missing, the remaining checks may produce
        # misleading messages, but we still run them because partial feedback
        # is more useful than a single "field missing" error.

        # 2. Allowed-value checks -------------------------------------------
        maint_req = record.get("maintenance_required", "").strip()
        if maint_req and maint_req not in ALLOWED_MAINTENANCE_REQUIRED:
            errors.append(
                f"Invalid maintenance_required value: '{maint_req}'. "
                f"Allowed: {sorted(ALLOWED_MAINTENANCE_REQUIRED)}"
            )

        priority = record.get("priority", "").strip()
        if priority and priority not in ALLOWED_PRIORITIES:
            errors.append(
                f"Invalid priority value: '{priority}'. "
                f"Allowed: {sorted(ALLOWED_PRIORITIES)}"
            )

        status = record.get("status", "").strip()
        if status and status not in ALLOWED_STATUSES:
            errors.append(
                f"Invalid status value: '{status}'. "
                f"Allowed: {sorted(ALLOWED_STATUSES)}"
            )

        # 3. Type / format checks -------------------------------------------
        self._validate_positive_integer(record, "required_duration", errors)
        self._validate_positive_integer(record, "required_resources", errors)
        self._validate_date(record, "requested_date", errors)
        self._validate_time(record, "preferred_start", errors)

        is_valid = len(errors) == 0

        if not is_valid:
            asset_id = record.get("asset_id", "<unknown>")
            logger.warning(
                "Validation failed for record '%s': %s",
                asset_id,
                "; ".join(errors),
            )

        return is_valid, errors

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_positive_integer(
        record: Dict[str, str],
        field: str,
        errors: List[str],
    ) -> None:
        """Check that *field* is a positive integer."""
        raw = record.get(field, "").strip()
        if not raw:
            return  # already caught by required-field check
        try:
            value = int(raw)
        except ValueError:
            errors.append(f"'{field}' must be an integer, got: '{raw}'")
            return
        if value <= 0:
            errors.append(f"'{field}' must be a positive integer, got: {value}")

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
