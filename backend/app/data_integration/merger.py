"""
Data Merger — combines compatible records from multiple sources into
unified representations.

Responsibility
--------------
Entity-mapped record groups  →  merged unified records

The merger takes grouped records (from the EntityMapper) and produces
a single merged record per entity where possible, preserving source
attribution.

Strategy
--------
For trains with data from multiple sources (TMS, TDMS):
  • Start with the TMS record as the base.
  • Overlay TDMS-specific fields (route_id, priority, expected times).
  • Preserve both source attributions.

For other entity types (maintenance, movements, blocks, timetable):
  • Records pass through as-is since they don't overlap across sources.

Usage
-----
    from backend.app.data_integration.merger import DataMerger

    merger = DataMerger()
    result = merger.merge_all(entity_map, smms_records, coa_records, bdms_records, timetable_records)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from backend.app.data_integration.entity_mapper import EntityMap

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """
    Result of merging records from multiple sources.

    Attributes
    ----------
    merged_trains : list[dict]
        Unified train records after merging TMS + TDMS data.
    maintenance_records : list[dict]
        SMMS maintenance records (pass-through).
    movement_records : list[dict]
        COA movement records (pass-through).
    block_records : list[dict]
        BDMS block records (pass-through).
    timetable_records : list[dict]
        Timetable records (pass-through).
    stats : dict[str, int]
        Merge statistics.
    """

    merged_trains: List[Dict[str, Any]] = field(default_factory=list)
    maintenance_records: List[Dict[str, Any]] = field(default_factory=list)
    movement_records: List[Dict[str, Any]] = field(default_factory=list)
    block_records: List[Dict[str, Any]] = field(default_factory=list)
    timetable_records: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


class DataMerger:
    """
    Combines records from multiple sources into unified representations.
    """

    def merge_all(
        self,
        entity_map: EntityMap,
        smms_records: List[Dict[str, Any]] | None = None,
        coa_records: List[Dict[str, Any]] | None = None,
        bdms_records: List[Dict[str, Any]] | None = None,
        timetable_records: List[Dict[str, Any]] | None = None,
    ) -> MergeResult:
        """
        Merge all entity-mapped records.

        Parameters
        ----------
        entity_map : EntityMap
            The result of entity mapping.
        smms_records, coa_records, bdms_records, timetable_records
            Normalized records from each source (pass-through types).

        Returns
        -------
        MergeResult
            Combined records with merge statistics.
        """
        result = MergeResult()

        # --- Merge trains (TMS + TDMS) ---
        merged_count = 0
        single_source_count = 0

        for train_id, records in entity_map.train_groups.items():
            # Separate by source type — only TMS and TDMS records are merged
            tms_records_for_train = [r for r in records if r.get("source") == "tms"]
            tdms_records_for_train = [r for r in records if r.get("source") == "tdms"]

            if tms_records_for_train and tdms_records_for_train:
                # Merge TMS + TDMS for this train
                merged = self._merge_train_records(
                    tms_records_for_train[0],
                    tdms_records_for_train[0],
                )
                result.merged_trains.append(merged)
                merged_count += 1
            elif tms_records_for_train:
                result.merged_trains.append(tms_records_for_train[0])
                single_source_count += 1
            elif tdms_records_for_train:
                result.merged_trains.append(tdms_records_for_train[0])
                single_source_count += 1

        # --- Pass-through records ---
        result.maintenance_records = list(smms_records or [])
        result.movement_records = list(coa_records or [])
        result.block_records = list(bdms_records or [])
        result.timetable_records = list(timetable_records or [])

        # --- Statistics ---
        result.stats = {
            "total_trains": len(result.merged_trains),
            "merged_trains": merged_count,
            "single_source_trains": single_source_count,
            "maintenance_records": len(result.maintenance_records),
            "movement_records": len(result.movement_records),
            "block_records": len(result.block_records),
            "timetable_records": len(result.timetable_records),
        }

        logger.info(
            "Merge complete: %d trains (%d merged, %d single-source), "
            "%d maintenance, %d movements, %d blocks, %d timetable",
            result.stats["total_trains"],
            merged_count,
            single_source_count,
            result.stats["maintenance_records"],
            result.stats["movement_records"],
            result.stats["block_records"],
            result.stats["timetable_records"],
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_train_records(
        tms_record: Dict[str, Any],
        tdms_record: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge a TMS and TDMS record for the same train.

        Uses TMS as the base, then overlays TDMS-specific fields.
        Fields present in both sources are preserved with their
        TMS values (conflicts handled separately by the resolver).
        """
        merged: Dict[str, Any] = dict(tms_record)

        # TDMS-specific fields that TMS doesn't have
        if tdms_record.get("route_id"):
            merged["route_id"] = tdms_record["route_id"]

        if tdms_record.get("priority"):
            merged["priority"] = tdms_record["priority"]

        if tdms_record.get("expected_arrival"):
            merged["expected_arrival"] = tdms_record["expected_arrival"]

        if tdms_record.get("expected_departure"):
            merged["expected_departure"] = tdms_record["expected_departure"]

        # Track source attribution
        merged["source"] = "tms+tdms"

        # Preserve the original TDMS status for conflict detection
        merged["_tdms_status"] = tdms_record.get("status")

        return merged
