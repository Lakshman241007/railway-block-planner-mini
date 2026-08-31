"""
Entity Mapper — identifies when records from different sources refer
to the same real-world railway entity.

Responsibility
--------------
Normalized records from multiple sources  →  grouped entity mappings

Strategy
--------
Simple deterministic matching:
  • Trains:    matched by ``train_id`` (exact string match)
  • Locations: matched by ``location`` (exact string match)

This is a prototype-level approach.  No machine learning or fuzzy
matching is used.  The mapping is explainable and auditable.

Usage
-----
    from backend.app.data_integration.entity_mapper import EntityMapper

    mapper = EntityMapper()
    entity_map = mapper.map_all(
        tms_records=[...],
        tdms_records=[...],
        timetable_records=[...],
        coa_records=[...],
        smms_records=[...],
        bdms_records=[...],
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class EntityMap:
    """
    Result of entity mapping across sources.

    Attributes
    ----------
    train_groups : dict[str, list[dict]]
        train_id → list of normalized records from various sources
        that refer to the same logical train.
    location_groups : dict[str, list[dict]]
        location → list of normalized records (maintenance + block)
        that relate to the same physical location.
    stats : dict[str, int]
        Summary statistics for the mapping.
    """

    train_groups: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    location_groups: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    stats: Dict[str, int] = field(default_factory=dict)


class EntityMapper:
    """
    Groups normalized records by shared real-world entities.

    The mapper is stateless — call :meth:`map_all` once per pipeline run.
    """

    def map_all(
        self,
        tms_records: List[Dict[str, Any]] | None = None,
        tdms_records: List[Dict[str, Any]] | None = None,
        timetable_records: List[Dict[str, Any]] | None = None,
        coa_records: List[Dict[str, Any]] | None = None,
        smms_records: List[Dict[str, Any]] | None = None,
        bdms_records: List[Dict[str, Any]] | None = None,
    ) -> EntityMap:
        """
        Map all records to logical entities.

        Parameters
        ----------
        tms_records, tdms_records, timetable_records, coa_records
            Train-related normalized records (each has a ``train_id``).
        smms_records, bdms_records
            Location-related normalized records (each has a ``location``).

        Returns
        -------
        EntityMap
            Grouped entity mappings with statistics.
        """
        entity_map = EntityMap()

        # --- Train entity mapping (by train_id) ---
        entity_map.train_groups = self._map_trains(
            tms_records=tms_records or [],
            tdms_records=tdms_records or [],
            timetable_records=timetable_records or [],
            coa_records=coa_records or [],
        )

        # --- Location entity mapping ---
        entity_map.location_groups = self._map_locations(
            smms_records=smms_records or [],
            bdms_records=bdms_records or [],
        )

        # --- Statistics ---
        train_entities = len(entity_map.train_groups)
        multi_source_trains = sum(
            1 for records in entity_map.train_groups.values()
            if len({r.get("source") for r in records}) > 1
        )
        location_entities = len(entity_map.location_groups)
        multi_source_locations = sum(
            1 for records in entity_map.location_groups.values()
            if len({r.get("source") for r in records}) > 1
        )

        entity_map.stats = {
            "train_entities": train_entities,
            "multi_source_trains": multi_source_trains,
            "location_entities": location_entities,
            "multi_source_locations": multi_source_locations,
        }

        logger.info(
            "Entity mapping complete: %d trains (%d multi-source), "
            "%d locations (%d multi-source)",
            train_entities,
            multi_source_trains,
            location_entities,
            multi_source_locations,
        )

        return entity_map

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _map_trains(
        tms_records: List[Dict[str, Any]],
        tdms_records: List[Dict[str, Any]],
        timetable_records: List[Dict[str, Any]],
        coa_records: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group train-related records by train_id."""
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for record in tms_records:
            tid = record.get("train_id", "")
            if tid:
                groups.setdefault(tid, []).append(record)

        for record in tdms_records:
            tid = record.get("train_id", "")
            if tid:
                groups.setdefault(tid, []).append(record)

        for record in timetable_records:
            tid = record.get("train_id", "")
            if tid:
                groups.setdefault(tid, []).append(record)

        for record in coa_records:
            tid = record.get("train_id", "")
            if tid:
                groups.setdefault(tid, []).append(record)

        return groups

    @staticmethod
    def _map_locations(
        smms_records: List[Dict[str, Any]],
        bdms_records: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group location-related records (maintenance + blocks) by location."""
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for record in smms_records:
            loc = record.get("location", "")
            if loc:
                groups.setdefault(loc, []).append(record)

        for record in bdms_records:
            loc = record.get("location", "")
            if loc:
                groups.setdefault(loc, []).append(record)

        return groups
