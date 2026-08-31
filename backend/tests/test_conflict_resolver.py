"""
Tests for the Data Conflict Resolver.

Covers:
  • TMS Running vs TDMS Delayed → TMS wins (higher priority)
  • No conflict when statuses agree
  • Conflict statistics are correct
  • Resolved conflicts are logged
"""

from __future__ import annotations

import pytest

from backend.app.data_integration.conflict_resolver import DataConflictResolver
from backend.app.data_integration.merger import MergeResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def resolver() -> DataConflictResolver:
    return DataConflictResolver()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDataConflictResolver:
    """Tests for the DataConflictResolver."""

    def test_tms_wins_over_tdms_status(self, resolver: DataConflictResolver) -> None:
        """When TMS says Running and TDMS says Delayed, TMS value is kept."""
        merge_result = MergeResult(
            merged_trains=[
                {
                    "train_id": "G123",
                    "train_type": "Goods",
                    "origin": "Chennai",
                    "destination": "Arakkonam",
                    "status": "Running",
                    "source": "tms+tdms",
                    "_tdms_status": "Delayed",
                }
            ]
        )

        result = resolver.resolve_all(merge_result)

        # TMS value should win
        assert result.resolved_trains[0]["status"] == "Running"
        # Conflict should be detected and resolved
        assert len(result.conflicts) == 1
        assert result.conflicts[0].resolved is True
        assert result.conflicts[0].value_a == "Running"
        assert result.conflicts[0].value_b == "Delayed"
        assert result.conflicts[0].resolved_value == "Running"

    def test_no_conflict_when_statuses_agree(
        self, resolver: DataConflictResolver
    ) -> None:
        """No conflict should be detected when both sources agree."""
        merge_result = MergeResult(
            merged_trains=[
                {
                    "train_id": "P204",
                    "train_type": "Passenger",
                    "origin": "Chennai",
                    "destination": "Bengaluru",
                    "status": "Running",
                    "source": "tms+tdms",
                    "_tdms_status": "Running",
                }
            ]
        )

        result = resolver.resolve_all(merge_result)

        assert len(result.conflicts) == 0
        assert result.stats["detected"] == 0

    def test_single_source_train_no_conflict(
        self, resolver: DataConflictResolver
    ) -> None:
        """A train from only one source should have no conflicts."""
        merge_result = MergeResult(
            merged_trains=[
                {
                    "train_id": "G567",
                    "status": "Scheduled",
                    "source": "tms",
                }
            ]
        )

        result = resolver.resolve_all(merge_result)

        assert len(result.conflicts) == 0
        assert result.resolved_trains[0]["status"] == "Scheduled"

    def test_conflict_statistics(self, resolver: DataConflictResolver) -> None:
        """Statistics should correctly count detected, resolved, unresolved."""
        merge_result = MergeResult(
            merged_trains=[
                {
                    "train_id": "G123",
                    "status": "Running",
                    "source": "tms+tdms",
                    "_tdms_status": "Delayed",
                },
                {
                    "train_id": "G789",
                    "status": "Running",
                    "source": "tms+tdms",
                    "_tdms_status": "Delayed",
                },
                {
                    "train_id": "P204",
                    "status": "Running",
                    "source": "tms+tdms",
                    "_tdms_status": "Running",
                },
            ]
        )

        result = resolver.resolve_all(merge_result)

        assert result.stats["detected"] == 2
        assert result.stats["resolved"] == 2
        assert result.stats["unresolved"] == 0

    def test_passthrough_records_preserved(
        self, resolver: DataConflictResolver
    ) -> None:
        """Non-train records should pass through unchanged."""
        merge_result = MergeResult(
            maintenance_records=[{"asset_id": "TRK-1025"}],
            movement_records=[{"section": "Chennai-Perambur"}],
            block_records=[{"block_id": "BLK-001"}],
            timetable_records=[{"station_code": "Chennai"}],
        )

        result = resolver.resolve_all(merge_result)

        assert len(result.maintenance_records) == 1
        assert len(result.movement_records) == 1
        assert len(result.block_records) == 1
        assert len(result.timetable_records) == 1

    def test_tdms_status_field_removed_after_resolution(
        self, resolver: DataConflictResolver
    ) -> None:
        """The internal _tdms_status field should be removed from the output."""
        merge_result = MergeResult(
            merged_trains=[
                {
                    "train_id": "G123",
                    "status": "Running",
                    "source": "tms+tdms",
                    "_tdms_status": "Delayed",
                }
            ]
        )

        result = resolver.resolve_all(merge_result)

        assert "_tdms_status" not in result.resolved_trains[0]
