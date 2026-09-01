"""
API endpoint integration tests for Railway Block Planner FastAPI routes.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.dependencies import get_db
from backend.app.database.connection import Base
from backend.app.database.seed import seed_database
from backend.app.main import app


@pytest.fixture(scope="module")
def test_client():
    """Create a TestClient with an in-memory SQLite database populated with seed data."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Seed test database with Phase 2 data
    seed_session = TestingSessionLocal()
    project_root = Path(__file__).resolve().parents[2]
    seed_database(data_dir=project_root / "data", session=seed_session)
    seed_session.close()

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)


def test_health_endpoint(test_client):
    """Test /health returns ok status and database connectivity."""
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "connected"
    assert "version" in data


def test_root_endpoint(test_client):
    """Test / root endpoint returns metadata."""
    response = test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Railway Block Planner API"
    assert data["docs"] == "/docs"


def test_get_trains_endpoint(test_client):
    """Test /api/trains lists all seeded trains."""
    response = test_client.get("/api/trains")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert payload["count"] > 0
    assert payload["total"] > 0


def test_get_trains_filtered(test_client):
    """Test /api/trains?status=Running filters correctly."""
    response = test_client.get("/api/trains?status=Running")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    for train in payload["data"]:
        assert train["status"].lower() == "running"


def test_get_train_by_id_success(test_client):
    """Test /api/trains/{train_id} returns the specific train."""
    # First get list to find a valid train_id
    list_resp = test_client.get("/api/trains")
    first_train_id = list_resp.json()["data"][0]["train_id"]

    response = test_client.get(f"/api/trains/{first_train_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["train_id"] == first_train_id


def test_get_train_by_id_404(test_client):
    """Test /api/trains/{train_id} returns 404 for unknown train."""
    response = test_client.get("/api/trains/UNKNOWN_9999")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_get_maintenance_endpoint(test_client):
    """Test /api/maintenance lists maintenance records."""
    response = test_client.get("/api/maintenance")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert payload["count"] > 0


def test_get_maintenance_filters(test_client):
    """Test /api/maintenance with priority filter."""
    response = test_client.get("/api/maintenance?priority=High")
    assert response.status_code == 200
    payload = response.json()
    for item in payload["data"]:
        assert item["priority"].lower() == "high"


def test_get_maintenance_by_asset(test_client):
    """Test /api/maintenance/{asset_id} success and 404."""
    list_resp = test_client.get("/api/maintenance")
    first_asset_id = list_resp.json()["data"][0]["asset_id"]

    response = test_client.get(f"/api/maintenance/{first_asset_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) > 0
    assert data[0]["asset_id"] == first_asset_id

    # 404 for unknown asset
    response_404 = test_client.get("/api/maintenance/NONEXISTENT_ASSET")
    assert response_404.status_code == 404


def test_get_blocks_endpoint(test_client):
    """Test /api/blocks lists block requests."""
    response = test_client.get("/api/blocks")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert payload["count"] > 0


def test_get_block_by_id_success_and_404(test_client):
    """Test /api/blocks/{block_id} success and 404."""
    list_resp = test_client.get("/api/blocks")
    first_block_id = list_resp.json()["data"][0]["block_id"]

    response = test_client.get(f"/api/blocks/{first_block_id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["block_id"] == first_block_id

    # 404
    response_404 = test_client.get("/api/blocks/NONEXISTENT_BLOCK")
    assert response_404.status_code == 404


def test_get_plans_endpoint(test_client):
    """Test /api/plans returns persistence block view."""
    response = test_client.get("/api/plans")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert "message" in payload
    assert payload["count"] > 0


# ===========================================================================
# Phase 4 API Tests
# ===========================================================================

def test_get_forecast_endpoint(test_client):
    """Test GET /api/forecast returns forecasted goods movements."""
    response = test_client.get("/api/forecast")
    assert response.status_code == 200
    payload = response.json()
    assert "forecasts" in payload
    assert "total_trains_forecasted" in payload
    assert payload["total_trains_forecasted"] >= 1
    assert payload["average_confidence"] > 0.0


def test_run_forecast_endpoint(test_client):
    """Test POST /api/forecast/run with filters."""
    response = test_client.post(
        "/api/forecast/run",
        json={"target_date": "2026-09-05", "horizon_hours": 12, "train_id": "G123"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "forecasts" in payload
    assert all(fc["train_id"] == "G123" for fc in payload["forecasts"])


def test_scheduler_feasible_slots_endpoint(test_client):
    """Test POST /api/scheduler/feasible-slots finds valid slots."""
    response = test_client.post(
        "/api/scheduler/feasible-slots",
        json={
            "location": "Chennai-Arakkonam",
            "duration_minutes": 60,
            "preferred_start": "14:00",
            "target_date": "2026-09-05",
            "buffer_minutes": 15,
        },
    )
    assert response.status_code == 200
    slots = response.json()
    assert isinstance(slots, list)
    assert len(slots) > 0
    assert slots[0]["duration_minutes"] == 60


def test_scheduler_conflicts_endpoint(test_client):
    """Test POST /api/scheduler/conflicts returns conflict report."""
    response = test_client.post(
        "/api/scheduler/conflicts?target_date=2026-09-05&buffer_minutes=15"
    )
    assert response.status_code == 200
    report = response.json()
    assert "total_conflicts" in report
    assert "conflicts" in report
    assert "is_conflict_free" in report


def test_scheduler_schedule_endpoint(test_client):
    """Test POST /api/scheduler/schedule generates schedule result."""
    response = test_client.post(
        "/api/scheduler/schedule",
        json={"target_date": "2026-09-05", "buffer_minutes": 15},
    )
    assert response.status_code == 200
    result = response.json()
    assert "total_requested" in result
    assert "scheduled_items" in result


def test_plans_generate_endpoint(test_client):
    """Test POST /api/plans/generate runs full Phase 4 BlockPlanner."""
    response = test_client.post(
        "/api/plans/generate",
        json={"target_date": "2026-09-05", "include_forecast": True, "include_conflicts": True},
    )
    assert response.status_code == 200
    plan = response.json()
    assert "plan_id" in plan
    assert "schedule" in plan
    assert "conflict_report" in plan
    assert "resolution_recommendations" in plan

