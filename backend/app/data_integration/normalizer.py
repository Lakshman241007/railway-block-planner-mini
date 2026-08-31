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


# ---------------------------------------------------------------------------
# Phase 2 — TMS Normalizer
# ---------------------------------------------------------------------------

class TMSNormalizer:
    """
    Converts a validated TMS record (dict of strings) into a
    normalized dict ready for :class:`TrainRecord`.
    """

    def normalize(self, record: Dict[str, str]) -> Dict[str, Any]:
        """Normalize a single validated TMS record."""
        normalized: Dict[str, Any] = {
            "train_id": record["train_id"].strip(),
            "train_type": record["train_type"].strip(),
            "origin": record["origin"].strip(),
            "destination": record["destination"].strip(),
            "current_station": record.get("current_station", "").strip() or None,
            "next_station": record.get("next_station", "").strip() or None,
            "status": record["status"].strip(),
            "scheduled_arrival": record.get("scheduled_arrival", "").strip() or None,
            "scheduled_departure": record.get("scheduled_departure", "").strip() or None,
            "actual_arrival": record.get("actual_arrival", "").strip() or None,
            "actual_departure": record.get("actual_departure", "").strip() or None,
            "source": "tms",
        }
        logger.debug("Normalized TMS record: %s", normalized["train_id"])
        return normalized


# ---------------------------------------------------------------------------
# Phase 2 — TDMS Normalizer
# ---------------------------------------------------------------------------

class TDMSNormalizer:
    """
    Converts a validated TDMS record (dict of strings) into a
    normalized dict ready for :class:`TrainRecord`.
    """

    def normalize(self, record: Dict[str, str]) -> Dict[str, Any]:
        """Normalize a single validated TDMS record."""
        normalized: Dict[str, Any] = {
            "train_id": record["train_id"].strip(),
            "train_type": record["train_type"].strip(),
            "route_id": record.get("route_id", "").strip() or None,
            "origin": record["origin"].strip(),
            "destination": record["destination"].strip(),
            "priority": record.get("priority", "").strip() or None,
            "status": record["status"].strip(),
            "expected_arrival": record.get("expected_arrival", "").strip() or None,
            "expected_departure": record.get("expected_departure", "").strip() or None,
            "source": "tdms",
        }
        logger.debug("Normalized TDMS record: %s", normalized["train_id"])
        return normalized


# ---------------------------------------------------------------------------
# Phase 2 — COA Normalizer
# ---------------------------------------------------------------------------

class COANormalizer:
    """
    Converts a validated COA record (dict of strings) into a
    normalized dict ready for :class:`MovementRecord`.
    """

    def normalize(self, record: Dict[str, str]) -> Dict[str, Any]:
        """Normalize a single validated COA record."""
        normalized: Dict[str, Any] = {
            "train_id": record["train_id"].strip(),
            "route_id": record["route_id"].strip(),
            "section": record["section"].strip(),
            "direction": record["direction"].strip(),
            "movement_status": record["movement_status"].strip(),
            "entry_time": record["entry_time"].strip(),
            "exit_time": record["exit_time"].strip(),
            "line": record["line"].strip(),
            "source": "coa",
        }
        logger.debug("Normalized COA record: %s @ %s", normalized["train_id"], normalized["section"])
        return normalized


# ---------------------------------------------------------------------------
# Phase 2 — BDMS Normalizer
# ---------------------------------------------------------------------------

class BDMSNormalizer:
    """
    Converts a validated BDMS record (dict of strings) into a
    normalized dict ready for :class:`BlockRecord`.
    """

    def normalize(self, record: Dict[str, str]) -> Dict[str, Any]:
        """Normalize a single validated BDMS record."""
        normalized: Dict[str, Any] = {
            "block_id": record["block_id"].strip(),
            "location": record["location"].strip(),
            "block_type": record["block_type"].strip(),
            "requested_date": datetime.strptime(
                record["requested_date"].strip(), "%Y-%m-%d"
            ).date(),
            "requested_start": record["requested_start"].strip(),
            "requested_end": record["requested_end"].strip(),
            "reason": record["reason"].strip(),
            "priority": record["priority"].strip(),
            "status": record["status"].strip(),
            "source": "bdms",
        }
        logger.debug("Normalized BDMS record: %s", normalized["block_id"])
        return normalized


# ---------------------------------------------------------------------------
# Phase 2 — Timetable Normalizer
# ---------------------------------------------------------------------------

class TimetableNormalizer:
    """
    Converts a validated timetable record (dict of strings) into a
    normalized dict ready for :class:`TimetableRecord`.
    """

    def normalize(self, record: Dict[str, str]) -> Dict[str, Any]:
        """Normalize a single validated timetable record."""
        arrival = record.get("arrival_time", "").strip()
        departure = record.get("departure_time", "").strip()

        normalized: Dict[str, Any] = {
            "train_id": record["train_id"].strip(),
            "service_date": datetime.strptime(
                record["service_date"].strip(), "%Y-%m-%d"
            ).date(),
            "station_code": record["station_code"].strip(),
            "arrival_time": arrival if arrival and arrival != "--" else None,
            "departure_time": departure if departure and departure != "--" else None,
            "platform": int(record["platform"].strip()) if record.get("platform", "").strip() else None,
            "sequence": int(record["sequence"].strip()),
            "source": "timetable",
        }
        logger.debug(
            "Normalized timetable record: %s @ %s",
            normalized["train_id"],
            normalized["station_code"],
        )
        return normalized
