"""
Data Conflict Resolver — resolves conflicting field values when records
from multiple sources describe the same entity differently.

Responsibility
--------------
Merged records with potential conflicts  →  resolved records + conflict log

This is a **data integration** conflict resolver.  It is NOT the future
scheduler's conflict resolver for block/train scheduling.

Strategy (documented prototype rules)
--------------------------------------
Source priority for train operational data:
    TMS  >  TDMS  >  Timetable  >  COA

When two sources disagree on a field value:
  1. The higher-priority source's value is used.
  2. The conflict is logged with both values.
  3. If a conflict cannot be confidently resolved, it is preserved
     as an unresolved conflict rather than silently deleted.

These precedence rules are prototype decisions and do NOT represent
official railway operational rules.

Usage
-----
    from backend.app.data_integration.conflict_resolver import DataConflictResolver

    resolver = DataConflictResolver()
    resolved, conflict_log = resolver.resolve_all(merge_result)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.app.data_integration.merger import MergeResult

logger = logging.getLogger(__name__)


@dataclass
class Conflict:
    """A single detected data conflict."""

    entity_id: str
    field_name: str
    source_a: str
    value_a: str
    source_b: str
    value_b: str
    resolved: bool
    resolved_value: str | None = None
    resolution_reason: str | None = None


@dataclass
class ConflictResolutionResult:
    """
    Result of conflict resolution across all merged records.

    Attributes
    ----------
    resolved_trains : list[dict]
        Train records after conflict resolution.
    maintenance_records : list[dict]
        Pass-through from merge (no cross-source conflicts).
    movement_records : list[dict]
        Pass-through from merge.
    block_records : list[dict]
        Pass-through from merge.
    timetable_records : list[dict]
        Pass-through from merge.
    conflicts : list[Conflict]
        Log of all detected conflicts.
    stats : dict[str, int]
        Conflict statistics.
    """

    resolved_trains: List[Dict[str, Any]] = field(default_factory=list)
    maintenance_records: List[Dict[str, Any]] = field(default_factory=list)
    movement_records: List[Dict[str, Any]] = field(default_factory=list)
    block_records: List[Dict[str, Any]] = field(default_factory=list)
    timetable_records: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Conflict] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


class DataConflictResolver:
    """
    Resolves data-integration conflicts using documented precedence rules.

    Source priority for train data: TMS > TDMS > Timetable > COA
    """

    def resolve_all(self, merge_result: MergeResult) -> ConflictResolutionResult:
        """
        Scan merged records for conflicts and resolve them.

        Parameters
        ----------
        merge_result : MergeResult
            Output from the DataMerger.

        Returns
        -------
        ConflictResolutionResult
            Records with conflicts resolved + conflict log.
        """
        result = ConflictResolutionResult()
        all_conflicts: List[Conflict] = []

        # --- Resolve train conflicts ---
        for train_record in merge_result.merged_trains:
            resolved_record, conflicts = self._resolve_train_conflicts(train_record)
            result.resolved_trains.append(resolved_record)
            all_conflicts.extend(conflicts)

        # --- Pass-through (no cross-source conflicts) ---
        result.maintenance_records = list(merge_result.maintenance_records)
        result.movement_records = list(merge_result.movement_records)
        result.block_records = list(merge_result.block_records)
        result.timetable_records = list(merge_result.timetable_records)

        # --- Statistics ---
        result.conflicts = all_conflicts
        detected = len(all_conflicts)
        resolved_count = sum(1 for c in all_conflicts if c.resolved)
        unresolved_count = detected - resolved_count

        result.stats = {
            "detected": detected,
            "resolved": resolved_count,
            "unresolved": unresolved_count,
        }

        logger.info(
            "Conflict resolution complete: %d detected, %d resolved, %d unresolved",
            detected,
            resolved_count,
            unresolved_count,
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_train_conflicts(
        train_record: Dict[str, Any],
    ) -> tuple[Dict[str, Any], List[Conflict]]:
        """
        Check a merged train record for conflicts between TMS and TDMS.

        The merger stores the TDMS status in ``_tdms_status`` when both
        sources provide data for the same train.

        Precedence: TMS > TDMS (TMS is the primary movement system).
        """
        resolved = dict(train_record)
        conflicts: List[Conflict] = []

        tdms_status = resolved.pop("_tdms_status", None)

        if tdms_status is not None and tdms_status != resolved.get("status"):
            # Detected conflict: TMS and TDMS disagree on status
            conflict = Conflict(
                entity_id=resolved.get("train_id", "<unknown>"),
                field_name="status",
                source_a="tms",
                value_a=str(resolved.get("status", "")),
                source_b="tdms",
                value_b=str(tdms_status),
                resolved=True,
                resolved_value=str(resolved.get("status", "")),
                resolution_reason="TMS has higher source priority than TDMS",
            )
            conflicts.append(conflict)

            logger.info(
                "Conflict resolved for train '%s': status = '%s' (TMS) vs '%s' (TDMS) "
                "-> using TMS value",
                resolved.get("train_id"),
                resolved.get("status"),
                tdms_status,
            )

        return resolved, conflicts
