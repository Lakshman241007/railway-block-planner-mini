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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    _print_demo()
