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
    """Test /api/plans returns read-only block view."""
    response = test_client.get("/api/plans")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert "message" in payload
    assert payload["count"] > 0
