"""
SMMS Integrator — end-to-end pipeline from CSV to MaintenanceRecord.

Responsibility
--------------
    CSV file
        ↓   SMMSCollector
    Raw dicts
        ↓   SMMSValidator
    Validated dicts
        ↓   SMMSNormalizer
    Normalized dicts
        ↓   MaintenanceRecord (Pydantic)
    Unified records

This module wires the collector, validator, and normalizer together
into a single, easy-to-run pipeline.  It is deliberately limited to
**SMMS only** for Phase 1.

Usage
-----
    from backend.app.data_integration.integrator import SMMSIntegrator
    from pathlib import Path

    integrator = SMMSIntegrator(csv_path=Path("data/raw/smms/mock_smms.csv"))
    records = integrator.run()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple

from backend.app.data_integration.collectors.smms_collector import SMMSCollector
from backend.app.data_integration.normalizer import SMMSNormalizer
from backend.app.data_integration.validators.smms_validator import SMMSValidator
from backend.app.schemas.unified_data import MaintenanceRecord

logger = logging.getLogger(__name__)


class SMMSIntegrator:
    """
    Orchestrates the SMMS data-integration pipeline.

    Parameters
    ----------
    csv_path : Path | str
        Path to the SMMS mock CSV file.
    """

    def __init__(self, csv_path: Path | str) -> None:
        self.csv_path = Path(csv_path)
        self.collector = SMMSCollector(file_path=self.csv_path)
        self.validator = SMMSValidator()
        self.normalizer = SMMSNormalizer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> Tuple[List[MaintenanceRecord], List[Dict]]:
        """
        Execute the full SMMS integration pipeline.

        Returns
        -------
        tuple[list[MaintenanceRecord], list[dict]]
            A 2-tuple of:
              • A list of valid, normalized ``MaintenanceRecord`` objects.
              • A list of rejected records, each containing the original
                raw dict and the validation errors.
        """
        # Step 1 — Collect --------------------------------------------------
        logger.info("Step 1: Collecting raw SMMS records …")
        raw_records = self.collector.collect()
        logger.info("  → %d raw records collected", len(raw_records))

        # Step 2 — Validate -------------------------------------------------
        logger.info("Step 2: Validating records …")
        valid_raw: List[Dict[str, str]] = []
        rejected: List[Dict] = []

        for record in raw_records:
            is_valid, errors = self.validator.validate(record)
            if is_valid:
                valid_raw.append(record)
            else:
                rejected.append({
                    "record": record,
                    "errors": errors,
                })

        logger.info(
            "  → %d valid, %d rejected", len(valid_raw), len(rejected)
        )

        # Step 3 — Normalize ------------------------------------------------
        logger.info("Step 3: Normalizing validated records …")
        normalized = [self.normalizer.normalize(r) for r in valid_raw]

        # Step 4 — Build Pydantic models ------------------------------------
        logger.info("Step 4: Creating MaintenanceRecord objects …")
        maintenance_records = [
            MaintenanceRecord(**data) for data in normalized
        ]

        logger.info(
            "Pipeline complete: %d MaintenanceRecord(s) produced",
            len(maintenance_records),
        )
        return maintenance_records, rejected


# ---------------------------------------------------------------------------
# CLI demonstration
# ---------------------------------------------------------------------------

def _print_demo() -> None:
    """Run the pipeline and print a human-friendly summary."""
    # Resolve CSV path relative to the project root.
    # Assumes execution from the repository root, e.g.:
    #   python -m backend.app.data_integration.integrator
    project_root = Path(__file__).resolve().parents[3]
    csv_path = project_root / "data" / "raw" / "smms" / "mock_smms.csv"

    print("=" * 50)
    print(" Railway Block Planner — Phase 1")
    print(" SMMS Data Integration Demo")
    print("=" * 50)
    print()

    integrator = SMMSIntegrator(csv_path=csv_path)
    records, rejected = integrator.run()

    total = len(records) + len(rejected)
    print(f"Records loaded:   {total}")
    print(f"Valid records:    {len(records)}")
    print(f"Invalid records:  {len(rejected)}")
    print()

    if rejected:
        print("--- Rejected Records ---")
        for item in rejected:
            asset = item["record"].get("asset_id", "<unknown>")
            print(f"  {asset}: {'; '.join(item['errors'])}")
        print()

    print("--- Normalized Maintenance Records ---")
    print()

    for rec in records:
        print(f"  {rec.asset_id} | {rec.asset_type} | {rec.location}")
        print(f"    Priority:   {rec.priority.value}")
        print(f"    Duration:   {rec.duration_minutes} minutes")
        print(f"    Requested:  {rec.requested_date} {rec.preferred_start}")
        print(f"    Required:   {'Yes' if rec.maintenance_required else 'No'}")
        print(f"    Status:     {rec.status.value}")
        print()

    print("=" * 50)
    print(" Phase 1 pipeline completed successfully.")
    print("=" * 50)





# ---------------------------------------------------------------------------
# Phase 2 — Multi-Source Data Integrator
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as dc_field
from typing import Any

from backend.app.data_integration.collectors.tms_collector import TMSCollector
from backend.app.data_integration.collectors.tdms_collector import TDMSCollector
from backend.app.data_integration.collectors.coa_collector import COACollector
from backend.app.data_integration.collectors.bdms_collector import BDMSCollector
from backend.app.data_integration.collectors.timetable_provider import TimetableProvider

from backend.app.data_integration.validators.tms_validator import TMSValidator
from backend.app.data_integration.validators.tdms_validator import TDMSValidator
from backend.app.data_integration.validators.coa_validator import COAValidator
from backend.app.data_integration.validators.bdms_validator import BDMSValidator
from backend.app.data_integration.validators.timetable_validator import TimetableValidator

from backend.app.data_integration.normalizer import (
    TMSNormalizer,
    TDMSNormalizer,
    COANormalizer,
    BDMSNormalizer,
    TimetableNormalizer,
)
from backend.app.data_integration.entity_mapper import EntityMapper
from backend.app.data_integration.merger import DataMerger
from backend.app.data_integration.conflict_resolver import DataConflictResolver

from backend.app.schemas.unified_data import (
    TrainRecord,
    MovementRecord,
    BlockRecord,
    TimetableRecord,
)


@dataclass
class IntegrationResult:
    """
    Structured result of the multi-source integration pipeline.

    Contains records by entity type and comprehensive statistics
    suitable for consumption by future phases.
    """

    # --- Records by entity type ---
    train_records: List[TrainRecord] = dc_field(default_factory=list)
    maintenance_records: List[MaintenanceRecord] = dc_field(default_factory=list)
    movement_records: List[MovementRecord] = dc_field(default_factory=list)
    block_records: List[BlockRecord] = dc_field(default_factory=list)
    timetable_records: List[TimetableRecord] = dc_field(default_factory=list)

    # --- Statistics ---
    source_stats: Dict[str, int] = dc_field(default_factory=dict)
    validation_stats: Dict[str, int] = dc_field(default_factory=dict)
    mapping_stats: Dict[str, int] = dc_field(default_factory=dict)
    merge_stats: Dict[str, int] = dc_field(default_factory=dict)
    conflict_stats: Dict[str, int] = dc_field(default_factory=dict)

    # --- Rejected records ---
    rejected: List[Dict] = dc_field(default_factory=list)


class RailwayDataIntegrator:
    """
    Orchestrates the complete multi-source data integration pipeline.

    Pipeline:
        TMS / TDMS / SMMS / COA / BDMS / Timetable
            ↓  Collectors
        Raw records
            ↓  Validators
        Validated records
            ↓  Normalizers
        Normalized records
            ↓  Entity Mapper
        Grouped entities
            ↓  Merger
        Merged records
            ↓  Conflict Resolver
        Unified Railway Dataset

    Parameters
    ----------
    data_dir : Path | str
        Root directory containing ``raw/<source>/`` subdirectories.
    """

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)

    def run(self) -> IntegrationResult:
        """
        Execute the full multi-source integration pipeline.

        Returns
        -------
        IntegrationResult
            Records by entity type with comprehensive statistics.
        """
        result = IntegrationResult()

        # ============================================================
        # STEP 1 — Collect raw records from all sources
        # ============================================================
        logger.info("Step 1: Collecting raw records from all sources ...")

        raw: Dict[str, List[Dict[str, str]]] = {}
        source_stats: Dict[str, int] = {}

        raw["tms"] = self._safe_collect(
            TMSCollector(self.data_dir / "raw" / "tms" / "mock_tms.csv")
        )
        raw["tdms"] = self._safe_collect(
            TDMSCollector(self.data_dir / "raw" / "tdms" / "mock_tdms.csv")
        )
        raw["smms"] = self._safe_collect(
            SMMSCollector(self.data_dir / "raw" / "smms" / "mock_smms.csv")
        )
        raw["coa"] = self._safe_collect(
            COACollector(self.data_dir / "raw" / "coa" / "mock_coa.csv")
        )
        raw["bdms"] = self._safe_collect(
            BDMSCollector(self.data_dir / "raw" / "bdms" / "mock_bdms.csv")
        )
        raw["timetable"] = self._safe_collect(
            TimetableProvider(self.data_dir / "raw" / "timetable" / "mock_timetable.csv")
        )

        for src, records in raw.items():
            source_stats[src] = len(records)
            logger.info("  %s: %d records", src.upper(), len(records))

        result.source_stats = source_stats

        # ============================================================
        # STEP 2 — Validate all records
        # ============================================================
        logger.info("Step 2: Validating records ...")

        validators = {
            "tms": TMSValidator(),
            "tdms": TDMSValidator(),
            "smms": SMMSValidator(),
            "coa": COAValidator(),
            "bdms": BDMSValidator(),
            "timetable": TimetableValidator(),
        }

        validated: Dict[str, List[Dict[str, str]]] = {}
        total_valid = 0
        total_invalid = 0

        for source_name, records in raw.items():
            validator = validators[source_name]
            valid_records: List[Dict[str, str]] = []

            for record in records:
                is_valid, errors = validator.validate(record)
                if is_valid:
                    valid_records.append(record)
                    total_valid += 1
                else:
                    result.rejected.append({
                        "source": source_name,
                        "record": record,
                        "errors": errors,
                    })
                    total_invalid += 1

            validated[source_name] = valid_records
            logger.info(
                "  %s: %d valid, %d invalid",
                source_name.upper(),
                len(valid_records),
                len(records) - len(valid_records),
            )

        result.validation_stats = {
            "valid": total_valid,
            "invalid": total_invalid,
        }

        # ============================================================
        # STEP 3 — Normalize validated records
        # ============================================================
        logger.info("Step 3: Normalizing validated records ...")

        normalizers = {
            "tms": TMSNormalizer(),
            "tdms": TDMSNormalizer(),
            "smms": SMMSNormalizer(),
            "coa": COANormalizer(),
            "bdms": BDMSNormalizer(),
            "timetable": TimetableNormalizer(),
        }

        normalized: Dict[str, List[Dict[str, Any]]] = {}
        for source_name, records in validated.items():
            norm = normalizers[source_name]
            normalized[source_name] = [norm.normalize(r) for r in records]

        # ============================================================
        # STEP 4 — Entity Mapping
        # ============================================================
        logger.info("Step 4: Mapping entities across sources ...")

        mapper = EntityMapper()
        entity_map = mapper.map_all(
            tms_records=normalized.get("tms", []),
            tdms_records=normalized.get("tdms", []),
            timetable_records=normalized.get("timetable", []),
            coa_records=normalized.get("coa", []),
            smms_records=normalized.get("smms", []),
            bdms_records=normalized.get("bdms", []),
        )

        result.mapping_stats = entity_map.stats

        # ============================================================
        # STEP 5 — Merge records
        # ============================================================
        logger.info("Step 5: Merging records ...")

        merger = DataMerger()
        merge_result = merger.merge_all(
            entity_map=entity_map,
            smms_records=normalized.get("smms", []),
            coa_records=normalized.get("coa", []),
            bdms_records=normalized.get("bdms", []),
            timetable_records=normalized.get("timetable", []),
        )

        result.merge_stats = merge_result.stats

        # ============================================================
        # STEP 6 — Conflict Resolution
        # ============================================================
        logger.info("Step 6: Resolving data conflicts ...")

        resolver = DataConflictResolver()
        conflict_result = resolver.resolve_all(merge_result)

        result.conflict_stats = conflict_result.stats

        # ============================================================
        # STEP 7 — Build Pydantic models
        # ============================================================
        logger.info("Step 7: Building unified Pydantic models ...")

        # Train records
        for train_data in conflict_result.resolved_trains:
            try:
                result.train_records.append(TrainRecord(**train_data))
            except Exception as exc:
                logger.warning("Failed to create TrainRecord: %s", exc)

        # Maintenance records (SMMS)
        for maint_data in conflict_result.maintenance_records:
            try:
                result.maintenance_records.append(MaintenanceRecord(**maint_data))
            except Exception as exc:
                logger.warning("Failed to create MaintenanceRecord: %s", exc)

        # Movement records (COA)
        for move_data in conflict_result.movement_records:
            try:
                result.movement_records.append(MovementRecord(**move_data))
            except Exception as exc:
                logger.warning("Failed to create MovementRecord: %s", exc)

        # Block records (BDMS)
        for block_data in conflict_result.block_records:
            try:
                result.block_records.append(BlockRecord(**block_data))
            except Exception as exc:
                logger.warning("Failed to create BlockRecord: %s", exc)

        # Timetable records
        for tt_data in conflict_result.timetable_records:
            try:
                result.timetable_records.append(TimetableRecord(**tt_data))
            except Exception as exc:
                logger.warning("Failed to create TimetableRecord: %s", exc)

        logger.info(
            "Pipeline complete: %d trains, %d maintenance, %d movements, "
            "%d blocks, %d timetable entries",
            len(result.train_records),
            len(result.maintenance_records),
            len(result.movement_records),
            len(result.block_records),
            len(result.timetable_records),
        )

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_collect(collector: Any) -> List[Dict[str, str]]:
        """Collect records, returning empty list on failure."""
        try:
            return collector.collect()
        except (FileNotFoundError, ValueError) as exc:
            logger.warning("Collection failed: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Phase 2 CLI demonstration
# ---------------------------------------------------------------------------

def _print_phase2_demo() -> None:
    """Run the full multi-source pipeline and print a summary."""
    project_root = Path(__file__).resolve().parents[3]
    data_dir = project_root / "data"

    print("=" * 50)
    print(" Railway Block Planner")
    print(" Phase 2 - Multi-Source Data Integration")
    print("=" * 50)
    print()

    integrator = RailwayDataIntegrator(data_dir=data_dir)
    result = integrator.run()

    print("SOURCE SUMMARY")
    print("-" * 50)
    for src, count in result.source_stats.items():
        print(f"  {src.upper():15s}: {count} records")
    print()

    print("VALIDATION")
    print("-" * 50)
    print(f"  Valid records   : {result.validation_stats.get('valid', 0)}")
    print(f"  Invalid records : {result.validation_stats.get('invalid', 0)}")
    print()

    print("ENTITY MAPPING")
    print("-" * 50)
    print(f"  Train entities mapped  : {result.mapping_stats.get('train_entities', 0)}")
    print(f"  Multi-source trains    : {result.mapping_stats.get('multi_source_trains', 0)}")
    print(f"  Location entities      : {result.mapping_stats.get('location_entities', 0)}")
    print(f"  Multi-source locations : {result.mapping_stats.get('multi_source_locations', 0)}")
    print()

    print("MERGING")
    print("-" * 50)
    print(f"  Unified trains         : {result.merge_stats.get('total_trains', 0)}")
    print(f"  Maintenance records    : {result.merge_stats.get('maintenance_records', 0)}")
    print(f"  Movement records       : {result.merge_stats.get('movement_records', 0)}")
    print(f"  Block records          : {result.merge_stats.get('block_records', 0)}")
    print(f"  Timetable records      : {result.merge_stats.get('timetable_records', 0)}")
    print()

    print("CONFLICTS")
    print("-" * 50)
    print(f"  Detected               : {result.conflict_stats.get('detected', 0)}")
    print(f"  Resolved               : {result.conflict_stats.get('resolved', 0)}")
    print(f"  Unresolved             : {result.conflict_stats.get('unresolved', 0)}")
    print()

    print("UNIFIED DATASET")
    print("-" * 50)
    print(f"  TrainRecord(s)         : {len(result.train_records)}")
    print(f"  MaintenanceRecord(s)   : {len(result.maintenance_records)}")
    print(f"  MovementRecord(s)      : {len(result.movement_records)}")
    print(f"  BlockRecord(s)         : {len(result.block_records)}")
    print(f"  TimetableRecord(s)     : {len(result.timetable_records)}")
    print()

    if result.rejected:
        print("REJECTED RECORDS")
        print("-" * 50)
        for item in result.rejected:
            src = item.get("source", "?")
            rec = item.get("record", {})
            ident = rec.get("train_id") or rec.get("asset_id") or rec.get("block_id") or "<unknown>"
            print(f"  [{src.upper()}] {ident}: {'; '.join(item['errors'])}")
        print()

    print("=" * 50)
    print(" [SUCCESS] PHASE 2 INTEGRATION COMPLETE")
    print("=" * 50)



if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if "--phase1" in sys.argv:
        _print_demo()
    else:
        _print_phase2_demo()

