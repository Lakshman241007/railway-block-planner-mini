"""
Normalizer — transforms validated source records into unified form.

Responsibility
--------------
Validated raw dict (strings)  →  normalized dict (native Python types)

The normalizer converts source-specific field names and string
representations into the standardized types expected by
:class:`~backend.app.schemas.unified_data.MaintenanceRecord`.

Key transformations for SMMS:
  • ``required_duration`` (str)  →  ``duration_minutes``  (int)
  • ``required_resources`` (str) →  ``required_resources`` (int)
  • ``requested_date``    (str)  →  ``requested_date``    (date)
  • ``preferred_start``   (str)  →  ``preferred_start``   (time)
  • ``maintenance_required`` ("Yes"/"No")  →  ``maintenance_required`` (bool)

The normalizer does NOT perform validation — it trusts that the
validator has already approved the record.  It also does NOT perform
scheduling, optimization, or any other business logic.

Usage
-----
    from backend.app.data_integration.normalizer import SMMSNormalizer

    normalizer = SMMSNormalizer()
    normalized = normalizer.normalize(validated_record)
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SMMSNormalizer:
    """
    Converts a validated SMMS record (dict of strings) into a
    normalized dict with native Python types, ready to be passed to
    the :class:`MaintenanceRecord` Pydantic model.
    """

    # Mapping from raw CSV "Yes"/"No" to Python bool
    _BOOL_MAP: Dict[str, bool] = {
        "Yes": True,
        "No": False,
    }

    def normalize(self, record: Dict[str, str]) -> Dict[str, Any]:
        """
        Normalize a single validated SMMS record.

        Parameters
        ----------
        record : dict[str, str]
            A validated raw record from the collector / validator.

        Returns
        -------
        dict[str, Any]
            A dictionary whose keys and types align with
            ``MaintenanceRecord`` fields.
        """
        normalized: Dict[str, Any] = {
            # --- pass-through string fields --------------------------------
            "asset_id": record["asset_id"].strip(),
            "asset_type": record["asset_type"].strip(),
            "location": record["location"].strip(),
            "maintenance_type": record["maintenance_type"].strip(),
            "equipment": record["equipment"].strip(),

            # --- boolean conversion ----------------------------------------
            "maintenance_required": self._to_bool(
                record["maintenance_required"]
            ),

            # --- enum string fields (kept as strings; Pydantic handles it) -
            "priority": record["priority"].strip(),
            "status": record["status"].strip(),

            # --- numeric conversions ---------------------------------------
            "duration_minutes": self._to_positive_int(
                record["required_duration"], "required_duration"
            ),
            "required_resources": self._to_positive_int(
                record["required_resources"], "required_resources"
            ),

            # --- date / time conversions -----------------------------------
            "requested_date": self._to_date(record["requested_date"]),
            "preferred_start": self._to_time(record["preferred_start"]),

            # --- provenance ------------------------------------------------
            "source": "smms",
        }

        logger.debug("Normalized record: %s", normalized["asset_id"])
        return normalized

    # ------------------------------------------------------------------
    # Private conversion helpers
    # ------------------------------------------------------------------

    def _to_bool(self, raw: str) -> bool:
        """Convert ``"Yes"`` / ``"No"`` to a Python bool."""
        return self._BOOL_MAP[raw.strip()]

    @staticmethod
    def _to_positive_int(raw: str, field_name: str) -> int:
        """Convert a numeric string to a positive int."""
        value = int(raw.strip())
        if value <= 0:
            raise ValueError(
                f"{field_name} must be positive, got {value}"
            )
        return value

    @staticmethod
    def _to_date(raw: str) -> date:
        """Parse an ISO-8601 date string (YYYY-MM-DD)."""
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()

    @staticmethod
    def _to_time(raw: str) -> time:
        """Parse a 24-hour time string (HH:MM)."""
        return datetime.strptime(raw.strip(), "%H:%M").time()
