"""
Goods Train Forecasting Engine for Railway Block Planner.

Predicts future goods/freight train movements, ETAs, delays, section occupancies,
and confidence scores across operational corridors.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Dict, List, Optional, Tuple

from backend.app.forecast.schemas import (
    ForecastConfidenceLevel,
    GoodsForecastItem,
    GoodsForecastResult,
)
from backend.app.schemas.unified_data import (
    MovementRecord,
    TimetableRecord,
    TrainRecord,
    TrainStatus,
)

logger = logging.getLogger(__name__)


def _parse_time_to_minutes(time_str: Optional[str]) -> Optional[int]:
    """Convert HH:MM or HH:MM:SS string to minutes from midnight."""
    if not time_str or time_str.strip() in ("", "--", "None"):
        return None
    try:
        parts = [int(p) for p in time_str.strip().split(":")[:2]]
        return parts[0] * 60 + parts[1]
    except Exception:
        return None


def _format_minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to HH:MM format (modulo 24 hours)."""
    norm = minutes % 1440
    h = norm // 60
    m = norm % 60
    return f"{h:02d}:{m:02d}"


# Standard section segment definitions for corridor expansion when timetable is sparse
DEFAULT_CORRIDOR_SECTIONS = {
    "R-CHN-AJJ": [
        ("Chennai-Perambur", 15),
        ("Perambur-AJJ", 30),
    ],
    "R-AJJ-RU": [
        ("AJJ-Walajah", 25),
        ("Walajah-RU", 30),
    ],
    "R-RU-AJJ": [
        ("Renigunta-Walajah", 35),
        ("Walajah-AJJ", 25),
    ],
    "R-TBM-CGL": [
        ("Tambaram-CGL", 25),
    ],
    "R-CHN-TBM": [
        ("Chennai-TBM", 20),
    ],
    "R-VM-CHN": [
        ("Villupuram-TLGP", 40),
        ("TLGP-CGL", 35),
        ("CGL-TBM", 25),
        ("TBM-Chennai", 25),
    ],
}


class GoodsTrainForecaster:
    """
    Forecasting engine for goods/freight train movements.
    """

    def __init__(
        self,
        trains: Optional[List[TrainRecord]] = None,
        movements: Optional[List[MovementRecord]] = None,
        timetables: Optional[List[TimetableRecord]] = None,
    ) -> None:
        self.trains = trains or []
        self.movements = movements or []
        self.timetables = timetables or []

    def is_goods_train(self, train: TrainRecord) -> bool:
        """Identify if a train record represents a goods/freight train."""
        return (
            train.train_type.lower() in ("goods", "freight")
            or train.train_id.upper().startswith("G")
        )

    def calculate_train_delay(self, train: TrainRecord) -> int:
        """
        Calculate initial delay in minutes based on actual vs scheduled
        or expected vs scheduled timestamps.
        """
        sched_dep = _parse_time_to_minutes(train.scheduled_departure)
        actual_dep = _parse_time_to_minutes(train.actual_departure)
        if sched_dep is not None and actual_dep is not None:
            return max(0, actual_dep - sched_dep)

        sched_arr = _parse_time_to_minutes(train.scheduled_arrival)
        actual_arr = _parse_time_to_minutes(train.actual_arrival)
        if sched_arr is not None and actual_arr is not None:
            return max(0, actual_arr - sched_arr)

        exp_arr = _parse_time_to_minutes(train.expected_arrival)
        if sched_arr is not None and exp_arr is not None:
            return max(0, exp_arr - sched_arr)

        if train.status == TrainStatus.DELAYED:
            return 20  # Default nominal delay if flagged delayed without timestamps

        return 0

    def compute_confidence(
        self,
        train: TrainRecord,
        has_active_movement: bool,
        has_timetable: bool,
        has_tms_actuals: bool,
        forecast_horizon_hours: float,
    ) -> Tuple[float, ForecastConfidenceLevel, Dict[str, float]]:
        """
        Compute deterministic confidence score (0.0 to 1.0) and breakdown factors.
        """
        factors: Dict[str, float] = {}

        # 1. Data richness factor (max 0.35)
        if has_tms_actuals:
            factors["data_richness"] = 0.35
        elif train.expected_arrival or train.expected_departure:
            factors["data_richness"] = 0.25
        elif has_timetable:
            factors["data_richness"] = 0.15
        else:
            factors["data_richness"] = 0.10

        # 2. Operational state certainty (max 0.30)
        if train.status == TrainStatus.RUNNING:
            factors["status_certainty"] = 0.30
        elif train.status == TrainStatus.SCHEDULED:
            factors["status_certainty"] = 0.20
        elif train.status == TrainStatus.DELAYED:
            factors["status_certainty"] = 0.15
        else:
            factors["status_certainty"] = 0.05

        # 3. Temporal horizon proximity (max 0.20)
        if forecast_horizon_hours <= 2.0:
            factors["horizon_proximity"] = 0.20
        elif forecast_horizon_hours <= 6.0:
            factors["horizon_proximity"] = 0.15
        else:
            factors["horizon_proximity"] = 0.05

        # 4. Active corridor tracking (max 0.15)
        if has_active_movement:
            factors["corridor_tracking"] = 0.15
        else:
            factors["corridor_tracking"] = 0.05

        score = round(sum(factors.values()), 3)
        score = min(1.0, max(0.0, score))

        if score >= 0.80:
            level = ForecastConfidenceLevel.HIGH
        elif score >= 0.50:
            level = ForecastConfidenceLevel.MEDIUM
        else:
            level = ForecastConfidenceLevel.LOW

        return score, level, factors

    def predict(
        self,
        target_date: Optional[date] = None,
        horizon_hours: int = 24,
        filter_train_id: Optional[str] = None,
        filter_section: Optional[str] = None,
    ) -> GoodsForecastResult:
        """
        Generate goods train movement forecasts across the railway network.
        """
        f_date = target_date or date.today()
        goods_trains = [t for t in self.trains if self.is_goods_train(t)]
        if filter_train_id:
            goods_trains = [t for t in goods_trains if t.train_id.upper() == filter_train_id.upper()]

        forecast_items: List[GoodsForecastItem] = []
        section_summary: Dict[str, int] = {}
        forecast_counter = 1

        for train in goods_trains:
            if train.status in (TrainStatus.TERMINATED, TrainStatus.CANCELLED):
                continue

            delay = self.calculate_train_delay(train)
            has_tms_actuals = bool(train.actual_departure or train.actual_arrival)

            # Check related COA movements
            train_moves = [m for m in self.movements if m.train_id == train.train_id]
            # Check related timetables
            train_tts = [tt for tt in self.timetables if tt.train_id == train.train_id]

            # 1. Produce forecasts from direct COA movement records if available
            processed_sections = set()
            for move in train_moves:
                entry_mins = _parse_time_to_minutes(move.entry_time)
                exit_mins = _parse_time_to_minutes(move.exit_time)
                if entry_mins is None or exit_mins is None:
                    continue

                # Apply delay adjustment if status is delayed
                if train.status == TrainStatus.DELAYED and delay > 0:
                    entry_mins += delay
                    exit_mins += delay

                entry_str = _format_minutes_to_time(entry_mins)
                exit_str = _format_minutes_to_time(exit_mins)

                conf_score, conf_level, conf_factors = self.compute_confidence(
                    train=train,
                    has_active_movement=True,
                    has_timetable=bool(train_tts),
                    has_tms_actuals=has_tms_actuals,
                    forecast_horizon_hours=entry_mins / 60.0 if entry_mins else 1.0,
                )

                item = GoodsForecastItem(
                    forecast_id=f"FC-{forecast_counter:04d}",
                    train_id=train.train_id,
                    route_id=train.route_id or move.route_id,
                    section=move.section,
                    direction=move.direction,
                    line=move.line,
                    service_date=f_date,
                    forecasted_entry=entry_str,
                    forecasted_exit=exit_str,
                    delay_minutes=delay,
                    confidence_score=conf_score,
                    confidence_level=conf_level,
                    factors=conf_factors,
                )
                forecast_items.append(item)
                processed_sections.add(move.section.lower())
                section_summary[move.section] = section_summary.get(move.section, 0) + 1
                forecast_counter += 1

            # 2. Extrapolate for corridor sections if route is defined but movements only cover initial section
            route_id = train.route_id or (train_moves[0].route_id if train_moves else None)
            if route_id and route_id in DEFAULT_CORRIDOR_SECTIONS:
                last_exit_mins = None
                if train_moves:
                    last_m = train_moves[-1]
                    last_exit_mins = _parse_time_to_minutes(last_m.exit_time)
                    if last_exit_mins is not None and train.status == TrainStatus.DELAYED:
                        last_exit_mins += delay

                if last_exit_mins is None:
                    base_dep = train.actual_departure or train.scheduled_departure or train.expected_departure or "08:00"
                    last_exit_mins = (_parse_time_to_minutes(base_dep) or 480) + delay

                curr_mins = last_exit_mins
                for sec_name, sec_dur in DEFAULT_CORRIDOR_SECTIONS[route_id]:
                    if sec_name.lower() in processed_sections:
                        continue

                    entry_mins = curr_mins
                    exit_mins = curr_mins + sec_dur
                    curr_mins = exit_mins

                    conf_score, conf_level, conf_factors = self.compute_confidence(
                        train=train,
                        has_active_movement=False,
                        has_timetable=bool(train_tts),
                        has_tms_actuals=has_tms_actuals,
                        forecast_horizon_hours=entry_mins / 60.0 if entry_mins else 2.0,
                    )

                    item = GoodsForecastItem(
                        forecast_id=f"FC-{forecast_counter:04d}",
                        train_id=train.train_id,
                        route_id=route_id,
                        section=sec_name,
                        direction="Up" if "CHN" in route_id else "Down",
                        line="Main",
                        service_date=f_date,
                        forecasted_entry=_format_minutes_to_time(entry_mins),
                        forecasted_exit=_format_minutes_to_time(exit_mins),
                        delay_minutes=delay,
                        confidence_score=conf_score,
                        confidence_level=conf_level,
                        factors=conf_factors,
                    )
                    forecast_items.append(item)
                    section_summary[sec_name] = section_summary.get(sec_name, 0) + 1
                    forecast_counter += 1

            # 3. Fallback when train has no route mapping or movements (e.g. Origin-Destination direct corridor)
            if not train_moves and (not route_id or route_id not in DEFAULT_CORRIDOR_SECTIONS):
                origin = train.current_station or train.origin
                dest = train.next_station or train.destination
                sec_name = f"{origin}-{dest}"
                if train.actual_departure:
                    start_mins = _parse_time_to_minutes(train.actual_departure) or 540
                elif train.expected_departure:
                    start_mins = _parse_time_to_minutes(train.expected_departure) or 540
                else:
                    base_dep = train.scheduled_departure or "09:00"
                    start_mins = (_parse_time_to_minutes(base_dep) or 540) + delay
                end_mins = start_mins + 45

                conf_score, conf_level, conf_factors = self.compute_confidence(
                    train=train,
                    has_active_movement=False,
                    has_timetable=bool(train_tts),
                    has_tms_actuals=has_tms_actuals,
                    forecast_horizon_hours=start_mins / 60.0 if start_mins else 3.0,
                )

                item = GoodsForecastItem(
                    forecast_id=f"FC-{forecast_counter:04d}",
                    train_id=train.train_id,
                    route_id=route_id,
                    section=sec_name,
                    direction="Up",
                    line="Main",
                    service_date=f_date,
                    forecasted_entry=_format_minutes_to_time(start_mins),
                    forecasted_exit=_format_minutes_to_time(end_mins),
                    delay_minutes=delay,
                    confidence_score=conf_score,
                    confidence_level=conf_level,
                    factors=conf_factors,
                )
                forecast_items.append(item)
                section_summary[sec_name] = section_summary.get(sec_name, 0) + 1
                forecast_counter += 1

        if filter_section:
            forecast_items = [
                fc for fc in forecast_items if filter_section.lower() in fc.section.lower()
            ]

        avg_conf = (
            round(sum(fc.confidence_score for fc in forecast_items) / len(forecast_items), 3)
            if forecast_items else 0.0
        )

        unique_trains = len(set(fc.train_id for fc in forecast_items))

        return GoodsForecastResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            forecast_date=f_date,
            horizon_hours=horizon_hours,
            total_trains_forecasted=unique_trains,
            total_section_windows=len(forecast_items),
            average_confidence=avg_conf,
            forecasts=forecast_items,
            summary_by_section=section_summary,
        )
