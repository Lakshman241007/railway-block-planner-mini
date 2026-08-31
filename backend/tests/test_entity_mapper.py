"""
Tests for the Entity Mapper.

Covers:
  • Same train_id from TMS + TDMS → same entity group
  • Same location from SMMS + BDMS → same location group
  • Statistics are computed correctly
  • Empty inputs produce empty mappings
"""

from __future__ import annotations

import pytest

from backend.app.data_integration.entity_mapper import EntityMapper


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mapper() -> EntityMapper:
    return EntityMapper()


# ---------------------------------------------------------------------------
# Tests — train entity mapping
# ---------------------------------------------------------------------------

class TestTrainEntityMapping:
    """Records with the same train_id should be grouped together."""

    def test_same_train_id_mapped_together(self, mapper: EntityMapper) -> None:
        """TMS and TDMS records with the same train_id group into one entity."""
        tms = [{"train_id": "G123", "status": "Running", "source": "tms"}]
        tdms = [{"train_id": "G123", "status": "Delayed", "source": "tdms"}]

        result = mapper.map_all(tms_records=tms, tdms_records=tdms)

        assert "G123" in result.train_groups
        assert len(result.train_groups["G123"]) == 2

    def test_different_train_ids_separate(self, mapper: EntityMapper) -> None:
        """Different train_ids go to separate groups."""
        tms = [
            {"train_id": "G123", "source": "tms"},
            {"train_id": "P204", "source": "tms"},
        ]

        result = mapper.map_all(tms_records=tms)

        assert len(result.train_groups) == 2
        assert "G123" in result.train_groups
        assert "P204" in result.train_groups

    def test_multi_source_trains_counted(self, mapper: EntityMapper) -> None:
        """Multi-source train count reflects trains appearing in >1 source."""
        tms = [{"train_id": "G123", "source": "tms"}]
        tdms = [{"train_id": "G123", "source": "tdms"}]

        result = mapper.map_all(tms_records=tms, tdms_records=tdms)

        assert result.stats["multi_source_trains"] == 1

    def test_timetable_and_coa_included(self, mapper: EntityMapper) -> None:
        """Timetable and COA records also contribute to train groups."""
        tms = [{"train_id": "G123", "source": "tms"}]
        timetable = [{"train_id": "G123", "source": "timetable"}]
        coa = [{"train_id": "G123", "source": "coa"}]

        result = mapper.map_all(
            tms_records=tms,
            timetable_records=timetable,
            coa_records=coa,
        )

        assert len(result.train_groups["G123"]) == 3

    def test_empty_inputs(self, mapper: EntityMapper) -> None:
        """No records should produce empty mappings."""
        result = mapper.map_all()

        assert result.train_groups == {}
        assert result.stats["train_entities"] == 0


# ---------------------------------------------------------------------------
# Tests — location entity mapping
# ---------------------------------------------------------------------------

class TestLocationEntityMapping:
    """Records with the same location should be grouped together."""

    def test_same_location_mapped_together(self, mapper: EntityMapper) -> None:
        """SMMS and BDMS records at the same location are grouped."""
        smms = [{"location": "Chennai-Arakkonam", "source": "smms"}]
        bdms = [{"location": "Chennai-Arakkonam", "source": "bdms"}]

        result = mapper.map_all(smms_records=smms, bdms_records=bdms)

        assert "Chennai-Arakkonam" in result.location_groups
        assert len(result.location_groups["Chennai-Arakkonam"]) == 2

    def test_multi_source_locations_counted(self, mapper: EntityMapper) -> None:
        """Multi-source location count is correct."""
        smms = [{"location": "KM40-42", "source": "smms"}]
        bdms = [{"location": "KM40-42", "source": "bdms"}]

        result = mapper.map_all(smms_records=smms, bdms_records=bdms)

        assert result.stats["multi_source_locations"] == 1

    def test_different_locations_separate(self, mapper: EntityMapper) -> None:
        """Different locations go to separate groups."""
        smms = [
            {"location": "Chennai-Arakkonam", "source": "smms"},
            {"location": "Pamban Bridge", "source": "smms"},
        ]

        result = mapper.map_all(smms_records=smms)

        assert len(result.location_groups) == 2
