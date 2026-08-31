"""
COA Validator — validates raw COA corridor/section occupancy records.

Responsibility
--------------
Raw dict (from the collector)  →  (is_valid, list_of_errors)

Usage
-----
    from backend.app.data_integration.validators.coa_validator import COAValidator

    validator = COAValidator()
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
    "route_id",
    "section",
    "direction",
    "movement_status",
    "entry_time",
    "exit_time",
    "line",
]

ALLOWED_DIRECTIONS = {"Up", "Down"}

ALLOWED_MOVEMENT_STATUSES = {"Occupied", "Clear", "Approaching", "Scheduled"}

ALLOWED_LINES = {"Main", "Loop"}


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class COAValidator:
    """Validates a single raw COA record."""

    def validate(self, record: Dict[str, str]) -> Tuple[bool, List[str]]:
        """
        Validate a raw COA record.

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
        direction = record.get("direction", "").strip()
        if direction and direction not in ALLOWED_DIRECTIONS:
            errors.append(
                f"Invalid direction value: '{direction}'. "
                f"Allowed: {sorted(ALLOWED_DIRECTIONS)}"
            )

        movement = record.get("movement_status", "").strip()
        if movement and movement not in ALLOWED_MOVEMENT_STATUSES:
            errors.append(
                f"Invalid movement_status value: '{movement}'. "
                f"Allowed: {sorted(ALLOWED_MOVEMENT_STATUSES)}"
            )

        line = record.get("line", "").strip()
        if line and line not in ALLOWED_LINES:
            errors.append(
                f"Invalid line value: '{line}'. "
                f"Allowed: {sorted(ALLOWED_LINES)}"
            )

        # 3. Time format checks
        self._validate_time(record, "entry_time", errors)
        self._validate_time(record, "exit_time", errors)

        is_valid = len(errors) == 0

        if not is_valid:
            train_id = record.get("train_id", "<unknown>")
            logger.warning(
                "Validation failed for COA record '%s': %s",
                train_id,
                "; ".join(errors),
            )

        return is_valid, errors

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
