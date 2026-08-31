"""
BDMS Validator — validates raw BDMS block/disconnection records.

Responsibility
--------------
Raw dict (from the collector)  →  (is_valid, list_of_errors)

Usage
-----
    from backend.app.data_integration.validators.bdms_validator import BDMSValidator

    validator = BDMSValidator()
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
    "block_id",
    "location",
    "block_type",
    "requested_date",
    "requested_start",
    "requested_end",
    "reason",
    "priority",
    "status",
]

ALLOWED_BLOCK_TYPES = {"Maintenance", "Emergency", "Non-Interlocked", "Traffic"}

ALLOWED_PRIORITIES = {"Low", "Medium", "High", "Critical"}

ALLOWED_STATUSES = {"Requested", "Approved", "Rejected", "Completed", "Cancelled"}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class BDMSValidator:
    """Validates a single raw BDMS record."""

    def validate(self, record: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate a raw BDMS record.

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
        block_type = record.get("block_type", "").strip()
        if block_type and block_type not in ALLOWED_BLOCK_TYPES:
            errors.append(
                f"Invalid block_type value: '{block_type}'. "
                f"Allowed: {sorted(ALLOWED_BLOCK_TYPES)}"
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

        # 3. Date / time format checks
        self._validate_date(record, "requested_date", errors)
        self._validate_time(record, "requested_start", errors)
        self._validate_time(record, "requested_end", errors)

        is_valid = len(errors) == 0

        if not is_valid:
            block_id = record.get("block_id", "<unknown>")
            logger.warning(
                "Validation failed for BDMS record '%s': %s",
                block_id,
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
