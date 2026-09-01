"""
Unit and integration tests for Phase 4 Goods Train Forecasting Engine.
"""

from __future__ import annotations

from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database.connection import Base
from backend.app.database.repositories import (
    MovementRepository,
    TimetableRepository,
    TrainRepository,
)
from backend.app.forecast.data_loader import ForecastDataLoader
from backend.app.forecast.forecast import GoodsTrainForecaster
from backend.app.forecast.schemas import (
    ForecastConfidenceLevel,
    GoodsForecastResult,
)
from backend.app.schemas.unified_data import (
    MovementRecord,
    TimetableRecord,
    TrainRecord,
    TrainStatus,
)


@pytest.fixture
def mock_goods_trains():
    return [
        TrainRecord(
            train_id="G123",
            train_type="Goods",
            origin="Chennai",
            destination="Arakkonam",
            current_station="Chennai",
            next_station="AJJ",
            status=TrainStatus.RUNNING,
            route_id="R-CHN-AJJ",
            scheduled_arrival="09:30",
            scheduled_departure="09:35",
            actual_arrival="09:32",
            actual_departure="09:37",
        ),
        TrainRecord(
            train_id="G456",
            train_type="Goods",
            origin="Arakkonam",
            destination="Renigunta",
            current_station="AJJ",
            next_station="RU",
            status=TrainStatus.RUNNING,
            route_id="R-AJJ-RU",
            scheduled_arrival="11:00",
            scheduled_departure="11:10",
            actual_arrival="11:05",
            actual_departure="11:15",
        ),
        TrainRecord(
            train_id="G234",
            train_type="Goods",
            origin="Renigunta",
            destination="Arakkonam",
            current_station="RU",
            next_station="AJJ",
            status=TrainStatus.DELAYED,
            route_id="R-RU-AJJ",
            scheduled_arrival="15:00",
            scheduled_departure="15:05",
            actual_arrival="15:20",
            actual_departure="15:25",
        ),
        TrainRecord(
            train_id="P204",
            train_type="Passenger",
            origin="Chennai",
            destination="Bengaluru",
            status=TrainStatus.RUNNING,
            scheduled_departure="10:05",
        ),
        TrainRecord(
            train_id="G890",
            train_type="Goods",
            origin="Arakkonam",
            destination="Chennai",
            status=TrainStatus.TERMINATED,
        ),
    ]


@pytest.fixture
def mock_movements():
    return [
        MovementRecord(
            train_id="G123",
            route_id="R-CHN-AJJ",
            section="Chennai-Perambur",
            direction="Up",
            movement_status="Occupied",
            entry_time="09:30",
            exit_time="09:40",
            line="Main",
        ),
        MovementRecord(
            train_id="G123",
            route_id="R-CHN-AJJ",
            section="Perambur-AJJ",
            direction="Up",
            movement_status="Approaching",
            entry_time="09:40",
            exit_time="10:10",
            line="Main",
        ),
        MovementRecord(
            train_id="G456",
            route_id="R-AJJ-RU",
            section="AJJ-Walajah",
            direction="Up",
            movement_status="Occupied",
            entry_time="11:00",
            exit_time="11:30",
            line="Loop",
        ),
    ]


@pytest.fixture
def db_session():
    """Create isolated SQLite in-memory session."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_is_goods_train():
    forecaster = GoodsTrainForecaster()
    t1 = TrainRecord(train_id="G100", train_type="Freight", origin="A", destination="B", status=TrainStatus.RUNNING)
    t2 = TrainRecord(train_id="P200", train_type="Passenger", origin="A", destination="B", status=TrainStatus.RUNNING)
    t3 = TrainRecord(train_id="12345", train_type="Goods", origin="A", destination="B", status=TrainStatus.RUNNING)

    assert forecaster.is_goods_train(t1) is True
    assert forecaster.is_goods_train(t2) is False
    assert forecaster.is_goods_train(t3) is True


def test_calculate_train_delay():
    forecaster = GoodsTrainForecaster()
    t_delayed = TrainRecord(
        train_id="G1",
        train_type="Goods",
        origin="A",
        destination="B",
        status=TrainStatus.DELAYED,
        scheduled_departure="10:00",
        actual_departure="10:25",
    )
    assert forecaster.calculate_train_delay(t_delayed) == 25

    t_ontime = TrainRecord(
        train_id="G2",
        train_type="Goods",
        origin="A",
        destination="B",
        status=TrainStatus.RUNNING,
        scheduled_departure="10:00",
        actual_departure="10:00",
    )
    assert forecaster.calculate_train_delay(t_ontime) == 0


def test_compute_confidence():
    forecaster = GoodsTrainForecaster()
    t_running = TrainRecord(
        train_id="G1",
        train_type="Goods",
        origin="A",
        destination="B",
        status=TrainStatus.RUNNING,
        scheduled_departure="10:00",
        actual_departure="10:05",
    )
    score, level, factors = forecaster.compute_confidence(
        train=t_running,
        has_active_movement=True,
        has_timetable=True,
        has_tms_actuals=True,
        forecast_horizon_hours=1.5,
    )
    assert 0.80 <= score <= 1.0
    assert level == ForecastConfidenceLevel.HIGH
    assert "data_richness" in factors
    assert "status_certainty" in factors


def test_predict_full_pipeline(mock_goods_trains, mock_movements):
    forecaster = GoodsTrainForecaster(trains=mock_goods_trains, movements=mock_movements)
    target_d = date(2026, 9, 5)
    result = forecaster.predict(target_date=target_d, horizon_hours=24)

    assert isinstance(result, GoodsForecastResult)
    assert result.forecast_date == target_d
    assert result.total_trains_forecasted >= 3  # G123, G456, G234 (G890 terminated, P204 passenger)
    assert result.total_section_windows >= 4
    assert result.average_confidence > 0.0

    # Ensure no passenger or terminated trains in forecasts
    train_ids = {fc.train_id for fc in result.forecasts}
    assert "P204" not in train_ids
    assert "G890" not in train_ids
    assert "G123" in train_ids
    assert "G456" in train_ids


def test_predict_filtering(mock_goods_trains, mock_movements):
    forecaster = GoodsTrainForecaster(trains=mock_goods_trains, movements=mock_movements)
    # Filter by specific train
    res_train = forecaster.predict(filter_train_id="G123")
    assert all(fc.train_id == "G123" for fc in res_train.forecasts)

    # Filter by specific section
    res_sec = forecaster.predict(filter_section="Perambur")
    assert all("perambur" in fc.section.lower() for fc in res_sec.forecasts)


def test_data_loader_integration(db_session, mock_goods_trains, mock_movements):
    train_repo = TrainRepository(db_session)
    for t in mock_goods_trains:
        train_repo.create(t)

    move_repo = MovementRepository(db_session)
    for m in mock_movements:
        move_repo.create(m)

    loader = ForecastDataLoader(db_session)
    goods = loader.get_goods_trains_from_db()
    moves = loader.get_movements_from_db()

    assert len(goods) == 4  # G123, G456, G234, G890
    assert len(moves) == 3

    forecaster = GoodsTrainForecaster(trains=goods, movements=moves)
    result = forecaster.predict()
    assert result.total_trains_forecasted >= 3


def test_forecast_fallback_origin_destination():
    """Test fallback when train has no route mapping or movement records."""
    train = TrainRecord(
        train_id="G999",
        train_type="Goods",
        origin="MAS",
        destination="KPD",
        status=TrainStatus.RUNNING,
        scheduled_departure="14:00",
        actual_departure="14:15",
    )
    forecaster = GoodsTrainForecaster(trains=[train])
    result = forecaster.predict()

    assert result.total_trains_forecasted == 1
    assert result.total_section_windows == 1
    item = result.forecasts[0]
    assert item.train_id == "G999"
    assert item.section == "MAS-KPD"
    assert item.forecasted_entry == "14:15"
    assert item.delay_minutes == 15


def test_forecast_empty_inputs():
    """Test forecast handles empty train inputs gracefully."""
    forecaster = GoodsTrainForecaster()
    result = forecaster.predict()
    assert result.total_trains_forecasted == 0
    assert result.total_section_windows == 0
    assert result.average_confidence == 0.0
    assert len(result.forecasts) == 0

