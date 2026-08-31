"""
SMMS Collector — reads raw maintenance records from a CSV file.

Responsibility
--------------
CSV file  →  list of raw Python dictionaries

The collector is intentionally "dumb":
  • It does NOT validate field values.
  • It does NOT normalize or transform data.
  • It does NOT apply business rules.

Those responsibilities belong to the validator and normalizer,
respectively.  The collector's only job is to safely read the CSV
and return the rows as plain dictionaries.

Usage
-----
    from backend.app.data_integration.collectors.smms_collector import SMMSCollector

    collector = SMMSCollector(file_path=Path("data/raw/smms/mock_smms.csv"))
    records = collector.collect()   # list[dict[str, str]]
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


class SMMSCollector:
    """
    Collects raw SMMS maintenance records from a CSV file.

    Parameters
    ----------
    file_path : Path | str
        Path to the SMMS CSV file.  May be absolute or relative to
        the working directory.
    """

    def __init__(self, file_path: Path | str) -> None:
        self.file_path = Path(file_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def collect(self) -> List[Dict[str, str]]:
        """
        Read the CSV and return every row as a dictionary.

        Returns
        -------
        list[dict[str, str]]
            Each dictionary maps column header → cell value.
            All values are returned as raw strings (no type conversion).

        Raises
        ------
        FileNotFoundError
            If the CSV file does not exist at the configured path.
        ValueError
            If the file is empty or contains no data rows.
        """
        # --- check file existence ------------------------------------------
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"SMMS CSV file not found: {self.file_path.resolve()}"
            )

        logger.info("Reading SMMS data from %s", self.file_path.resolve())

        records: List[Dict[str, str]] = []

        with self.file_path.open(mode="r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)

            for row_number, row in enumerate(reader, start=2):  # row 1 = header
                # Skip completely empty rows produced by trailing newlines
                if all(value is None or value.strip() == "" for value in row.values()):
                    logger.warning("Skipping empty row %d", row_number)
                    continue

                # csv.DictReader may place extra fields under a `None` key
                # when a row has more columns than the header.  We drop those.
                cleaned_row: Dict[str, str] = {
                    key: (value.strip() if value else "")
                    for key, value in row.items()
                    if key is not None
                }

                records.append(cleaned_row)

        if not records:
            raise ValueError(
                f"SMMS CSV file is empty or contains no data rows: "
                f"{self.file_path.resolve()}"
            )

        logger.info("Collected %d raw SMMS records", len(records))
        return records
