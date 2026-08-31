"""
COA Collector — reads raw corridor/operational availability data from CSV.

Responsibility
--------------
CSV file  →  list of raw Python dictionaries

Usage
-----
    from backend.app.data_integration.collectors.coa_collector import COACollector

    collector = COACollector(file_path=Path("data/raw/coa/mock_coa.csv"))
    records = collector.collect()
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class COACollector:
    """
    Collects raw COA corridor/section occupancy records from a CSV file.

    Parameters
    ----------
    file_path : Path | str
        Path to the COA CSV file.
    """

    def __init__(self, file_path: Path | str) -> None:
        self.file_path = Path(file_path)

    def collect(self) -> List[Dict[str, str]]:
        """
        Read the CSV and return every row as a dictionary.

        Returns
        -------
        list[dict[str, str]]
            Each dictionary maps column header → cell value.

        Raises
        ------
        FileNotFoundError
            If the CSV file does not exist.
        ValueError
            If the file is empty or contains no data rows.
        """
        if not self.file_path.exists():
            raise FileNotFoundError(
                f"COA CSV file not found: {self.file_path.resolve()}"
            )

        logger.info("Reading COA data from %s", self.file_path.resolve())

        records: List[Dict[str, str]] = []

        with self.file_path.open(mode="r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row_number, row in enumerate(reader, start=2):
                if all(value is None or value.strip() == "" for value in row.values()):
                    logger.warning("Skipping empty row %d", row_number)
                    continue
                cleaned_row: Dict[str, str] = {
                    key: (value.strip() if value else "")
                    for key, value in row.items()
                    if key is not None
                }
                records.append(cleaned_row)

        if not records:
            raise ValueError(
                f"COA CSV file is empty or contains no data rows: "
                f"{self.file_path.resolve()}"
            )

        logger.info("Collected %d raw COA records", len(records))
        return records
