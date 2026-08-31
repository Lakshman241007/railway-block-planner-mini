"""
Tests for the Data Merger.

Covers:
  • TMS + TDMS records for the same train merge correctly
  • TDMS-specific fields are overlaid onto TMS base
  • Source attribution is preserved as 'tms+tdms'
  • Single-source trains pass through unchanged
  • Pass-through entity types are preserved
"""

from __future__ import annotations

import pytest

from backend.app.data_integration.entity_mapper import EntityMap
from backend.app.data_integration.merger import DataMerger


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def merger() -> DataMerger:
    return DataMerger()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDataMerger:
    """Tests for the DataMerger."""

    def test_tms_tdms_merge_combines_fields(self, merger: DataMerger) -> None:
        """Merging TMS + TDMS should combine their fields."""
        entity_map = EntityMap(
            train_groups={
                "G123": [
                    {
                        "train_id": "G123",
                        "train_type": "Goods",
                        "origin": "Chennai",
                        "destination": "Arakkonam",
                        "status": "Running",
                        "current_station": "Chennai",
                        "next_station": "AJJ",
                        "source": "tms",
                    },
                    {
                        "train_id": "G123",
                        "train_type": "Goods",
                        "origin": "Chennai",
                        "destination": "Arakkonam",
                        "status": "Delayed",
                        "route_id": "R-CHN-AJJ",
                        "priority": "High",
                        "expected_arrival": "09:45",
                        "expected_departure": "09:50",
                        "source": "tdms",
                    },
                ]
            }
        )

        result = merger.merge_all(entity_map)
        assert len(result.merged_trains) == 1

        merged = result.merged_trains[0]
        # TMS base fields
        assert merged["train_id"] == "G123"
        assert merged["status"] == "Running"  # TMS value kept as base
        assert merged["current_station"] == "Chennai"
        # TDMS overlaid fields
        assert merged["route_id"] == "R-CHN-AJJ"
        assert merged["priority"] == "High"
        assert merged["expected_arrival"] == "09:45"

    def test_source_attribution_combined(self, merger: DataMerger) -> None:
        """Merged trains should show source as 'tms+tdms'."""
        entity_map = EntityMap(
            train_groups={
                "G123": [
                    {"train_id": "G123", "status": "Running", "source": "tms"},
                    {"train_id": "G123", "status": "Delayed", "source": "tdms",
                     "route_id": "R1", "priority": "High"},
                ]
            }
        )

        result = merger.merge_all(entity_map)
        assert result.merged_trains[0]["source"] == "tms+tdms"

    def test_single_source_train_passes_through(self, merger: DataMerger) -> None:
        """A train from only one source should pass through unchanged."""
        entity_map = EntityMap(
            train_groups={
                "P204": [
                    {"train_id": "P204", "status": "Running", "source": "tms"}
                ]
            }
        )

        result = merger.merge_all(entity_map)
        assert len(result.merged_trains) == 1
        assert result.merged_trains[0]["source"] == "tms"

    def test_passthrough_records_preserved(self, merger: DataMerger) -> None:
        """Maintenance, movement, block, timetable records pass through."""
        entity_map = EntityMap()

        smms = [{"asset_id": "TRK-1025", "source": "smms"}]
        coa = [{"section": "Chennai-Perambur", "source": "coa"}]
        bdms = [{"block_id": "BLK-001", "source": "bdms"}]
        timetable = [{"station_code": "Chennai", "source": "timetable"}]

        result = merger.merge_all(
            entity_map, smms_records=smms, coa_records=coa,
            bdms_records=bdms, timetable_records=timetable,
        )

        assert len(result.maintenance_records) == 1
        assert len(result.movement_records) == 1
        assert len(result.block_records) == 1
        assert len(result.timetable_records) == 1

    def test_merge_statistics(self, merger: DataMerger) -> None:
        """Statistics should reflect merged vs single-source counts."""
        entity_map = EntityMap(
            train_groups={
                "G123": [
                    {"train_id": "G123", "status": "Running", "source": "tms"},
                    {"train_id": "G123", "status": "Delayed", "source": "tdms",
                     "route_id": "R1", "priority": "High"},
                ],
                "P204": [
                    {"train_id": "P204", "status": "Running", "source": "tms"},
                ],
            }
        )

        result = merger.merge_all(entity_map)
        assert result.stats["merged_trains"] == 1
        assert result.stats["single_source_trains"] == 1
        assert result.stats["total_trains"] == 2
