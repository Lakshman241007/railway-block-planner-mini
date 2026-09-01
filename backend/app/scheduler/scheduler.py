"""
Maintenance Scheduler Engine for Railway Block Planner.

Generates feasible, conflict-free maintenance block slots by evaluating
infrastructure maintenance requests against passenger train timetables,
active track movements, and goods train forecasts.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Dict, List, Optional, Set, Tuple, Union

from backend.app.forecast.schemas import GoodsForecastItem
from backend.app.scheduler.schemas import (
    FeasibleSlot,
    MaintenanceScheduleItem,
    ScheduleResult,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    BlockStatus,
    MaintenanceRecord,
    MovementRecord,
    Priority,
    TimetableRecord,
)

logger = logging.getLogger(__name__)

# Priority sorting rank
PRIORITY_RANK = {
    Priority.CRITICAL: 4,
    Priority.HIGH: 3,
    Priority.MEDIUM: 2,
    Priority.LOW: 1,
}

# Corridor location normalization map for matching sub-stations and chainages to sections
LOCATION_ALIASES = {
    "chennai-arakkonam": ["chennai", "perambur", "ajj", "arakkonam", "km40-42", "basin bridge"],
    "arakkonam-renigunta": ["arakkonam", "ajj", "walajah", "ru", "renigunta", "km85-87"],
    "chennai-villupuram": ["chennai", "tambaram", "tbm", "cgl", "chengalpattu", "vm", "villupuram", "tlgp"],
    "tambaram-chengalpattu": ["tambaram", "tbm", "cgl", "chengalpattu"],
    "villupuram-chengalpattu": ["villupuram", "vm", "cgl", "chengalpattu", "tlgp"],
}


def _parse_time_to_minutes(time_val: Union[str, time, None]) -> Optional[int]:
    """Convert time object or HH:MM string to minutes from midnight."""
    if time_val is None:
        return None
    if isinstance(time_val, time):
        return time_val.hour * 60 + time_val.minute
    s = str(time_val).strip()
    if not s or s in ("--", "None"):
        return None
    try:
        parts = [int(p) for p in s.split(":")[:2]]
        return parts[0] * 60 + parts[1]
    except Exception:
        return None


def _calculate_duration_minutes(
    start_val: Union[str, time, None],
    end_val: Union[str, time, None],
    default_start: int = 480,
    default_end: int = 600,
) -> int:
    """
    Calculate required duration in minutes, correctly handling overnight spans
    where end time is numerically earlier than start time (crossing midnight).
    """
    start_m = _parse_time_to_minutes(start_val)
    if start_m is None:
        start_m = default_start
    end_m = _parse_time_to_minutes(end_val)
    if end_m is None:
        end_m = default_end

    if end_m < start_m:
        end_m += 1440
    dur = end_m - start_m
    return max(30, dur)


def _format_minutes_to_time(minutes: int) -> str:
    """Convert minutes to HH:MM format (modulo 24 hours for overnight rollover)."""
    norm = minutes % 1440
    h = norm // 60
    m = norm % 60
    return f"{h:02d}:{m:02d}"


def _locations_match(loc1: str, loc2: str) -> bool:
    """Determine if two location/section descriptions refer to overlapping trackage."""
    l1 = loc1.lower().strip()
    l2 = loc2.lower().strip()
    if l1 == l2:
        return True
    if l1 in l2 or l2 in l1:
        return True

    # Check aliases
    for corridor, aliases in LOCATION_ALIASES.items():
        in_l1 = (corridor in l1) or any(a in l1 for a in aliases)
        in_l2 = (corridor in l2) or any(a in l2 for a in aliases)
        if in_l1 and in_l2:
            return True
    return False


class MaintenanceScheduler:
    """
    Rule-based heuristic scheduler for railway maintenance blocks.
    """

    def __init__(
        self,
        maintenance_records: Optional[List[MaintenanceRecord]] = None,
        block_records: Optional[List[BlockRecord]] = None,
        timetables: Optional[List[TimetableRecord]] = None,
        goods_forecasts: Optional[List[GoodsForecastItem]] = None,
        movements: Optional[List[MovementRecord]] = None,
        buffer_minutes: int = 15,
    ) -> None:
        self.maintenance_records = maintenance_records or []
        self.block_records = block_records or []
        self.timetables = timetables or []
        self.goods_forecasts = goods_forecasts or []
        self.movements = movements or []
        self.buffer_minutes = max(0, buffer_minutes)

    def _build_location_occupancy(
        self, target_date: date, location: str
    ) -> List[Tuple[int, int, str]]:
        """
        Collect all occupied time intervals [start_mins, end_mins, description]
        for the given location including safety buffers, supporting overnight
        spans across target_date and next calendar day.
        """
        occupied: List[Tuple[int, int, str]] = []
        next_date = target_date + timedelta(days=1)
        prev_date = target_date - timedelta(days=1)

        # 1. Check Passenger / Fixed Timetable stops on target_date and next_date
        train_tts: Dict[Tuple[date, str], List[TimetableRecord]] = {}
        for tt in self.timetables:
            if tt.service_date in (target_date, next_date):
                train_tts.setdefault((tt.service_date, tt.train_id), []).append(tt)

        for (s_date, tid), stops in train_tts.items():
            day_offset = (s_date - target_date).days * 1440
            stops_sorted = sorted(stops, key=lambda s: s.sequence)
            for stop in stops_sorted:
                if _locations_match(stop.station_code, location):
                    arr = _parse_time_to_minutes(stop.arrival_time)
                    dep = _parse_time_to_minutes(stop.departure_time)
                    t_start = arr if arr is not None else (dep - 5 if dep is not None else 600)
                    t_end = dep if dep is not None else (arr + 5 if arr is not None else 605)
                    start_buf = max(0, day_offset + t_start - self.buffer_minutes)
                    end_buf = day_offset + t_end + self.buffer_minutes
                    occupied.append((start_buf, end_buf, f"Train {tid} at {stop.station_code}"))

        # 2. Check Goods Train Forecasts
        for fc in self.goods_forecasts:
            if fc.service_date in (target_date, next_date) and _locations_match(fc.section, location):
                day_offset = (fc.service_date - target_date).days * 1440
                f_start = _parse_time_to_minutes(fc.forecasted_entry)
                f_end = _parse_time_to_minutes(fc.forecasted_exit)
                if f_start is not None and f_end is not None:
                    if f_end < f_start:
                        f_end += 1440
                    start_buf = max(0, day_offset + f_start - self.buffer_minutes)
                    end_buf = day_offset + f_end + self.buffer_minutes
                    occupied.append((start_buf, end_buf, f"Goods Forecast {fc.train_id} ({fc.section})"))

        # 3. Check Active Movements
        for m in self.movements:
            if _locations_match(m.section, location):
                m_start = _parse_time_to_minutes(m.entry_time)
                m_end = _parse_time_to_minutes(m.exit_time)
                if m_start is not None and m_end is not None:
                    if m_end < m_start:
                        m_end += 1440
                    start_buf = max(0, m_start - self.buffer_minutes)
                    end_buf = m_end + self.buffer_minutes
                    occupied.append((start_buf, end_buf, f"Movement {m.train_id} ({m.section})"))

        # 4. Check Approved Existing Blocks
        for b in self.block_records:
            if b.status == BlockStatus.APPROVED and _locations_match(b.location, location):
                b_start = _parse_time_to_minutes(b.requested_start)
                b_end = _parse_time_to_minutes(b.requested_end)
                if b_start is not None and b_end is not None:
                    dur = _calculate_duration_minutes(b.requested_start, b.requested_end)
                    if b.requested_date == target_date:
                        occupied.append((b_start, b_start + dur, f"Approved Block {b.block_id}"))
                    elif b.requested_date == next_date:
                        occupied.append((1440 + b_start, 1440 + b_start + dur, f"Next Day Approved Block {b.block_id}"))
                    elif b.requested_date == prev_date:
                        if b_start + dur > 1440:
                            occupied.append((0, (b_start + dur) - 1440, f"Previous Day Approved Block {b.block_id}"))

        # Merge overlapping intervals
        if not occupied:
            return []

        occupied.sort(key=lambda x: x[0])
        merged: List[Tuple[int, int, str]] = []
        curr_start, curr_end, curr_desc = occupied[0]

        for s, e, desc in occupied[1:]:
            if s <= curr_end:
                curr_end = max(curr_end, e)
                curr_desc += f", {desc}"
            else:
                merged.append((curr_start, curr_end, curr_desc))
                curr_start, curr_end, curr_desc = s, e, desc
        merged.append((curr_start, curr_end, curr_desc))

        return merged

    def find_feasible_slots(
        self,
        location: str,
        duration_minutes: int,
        preferred_start: str,
        target_date: date,
        max_slots: int = 5,
    ) -> List[FeasibleSlot]:
        """
        Identify free time windows on the target date satisfying the requested duration,
        supporting continuous overnight windows crossing midnight up to early morning (08:00).
        """
        if duration_minutes <= 0 or duration_minutes > 1440:
            return []

        occupied = self._build_location_occupancy(target_date, location)
        pref_mins = _parse_time_to_minutes(preferred_start) or 600

        # Timeline limit covers target_date (1440) plus early morning window up to 08:00 (480 mins)
        timeline_limit = 1440 + min(duration_minutes, 480)

        free_windows: List[Tuple[int, int]] = []
        current_cursor = 0

        for occ_start, occ_end, _ in occupied:
            if occ_start > current_cursor:
                free_windows.append((current_cursor, min(timeline_limit, occ_start)))
            current_cursor = max(current_cursor, occ_end)

        if current_cursor < timeline_limit:
            free_windows.append((current_cursor, timeline_limit))

        # Filter windows that can accommodate the required duration
        candidate_slots: List[FeasibleSlot] = []
        slot_idx = 1

        for w_start, w_end in free_windows:
            window_len = w_end - w_start
            if window_len >= duration_minutes:
                # 1. Check if preferred start fits directly inside this window
                if w_start <= pref_mins and (pref_mins + duration_minutes) <= min(w_end, timeline_limit) and pref_mins < 1440:
                    s_start = pref_mins
                    s_end = pref_mins + duration_minutes
                    is_match = True
                    fit = 1.0
                    slot = FeasibleSlot(
                        slot_id=f"SLOT-{slot_idx:03d}",
                        location=location,
                        service_date=target_date,
                        start_time=_format_minutes_to_time(s_start),
                        end_time=_format_minutes_to_time(s_end),
                        duration_minutes=duration_minutes,
                        fit_score=fit,
                        is_preferred_match=is_match,
                    )
                    candidate_slots.append(slot)
                    slot_idx += 1

                # 2. Also add window start slot (must start on target_date and end within timeline)
                if w_start < 1440 and (w_start + duration_minutes) <= timeline_limit:
                    s_start = w_start
                    s_end = w_start + duration_minutes
                    dist = abs(s_start - pref_mins)
                    fit = max(0.1, round(1.0 - (dist / 1440.0), 3))
                    slot = FeasibleSlot(
                        slot_id=f"SLOT-{slot_idx:03d}",
                        location=location,
                        service_date=target_date,
                        start_time=_format_minutes_to_time(s_start),
                        end_time=_format_minutes_to_time(s_end),
                        duration_minutes=duration_minutes,
                        fit_score=fit,
                        is_preferred_match=(dist <= 15),
                    )
                    candidate_slots.append(slot)
                    slot_idx += 1

                # 3. If window is large enough, also add an end-aligned slot (must start on target_date)
                if window_len > duration_minutes + 30:
                    s_start = w_end - duration_minutes
                    s_end = w_end
                    if 0 <= s_start < 1440:
                        dist = abs(s_start - pref_mins)
                        fit = max(0.1, round(1.0 - (dist / 1440.0), 3))
                        slot = FeasibleSlot(
                            slot_id=f"SLOT-{slot_idx:03d}",
                            location=location,
                            service_date=target_date,
                            start_time=_format_minutes_to_time(s_start),
                            end_time=_format_minutes_to_time(s_end),
                            duration_minutes=duration_minutes,
                            fit_score=fit,
                            is_preferred_match=(dist <= 15),
                        )
                        candidate_slots.append(slot)
                        slot_idx += 1

        # Deduplicate and sort by fit_score descending
        seen_times = set()
        unique_slots: List[FeasibleSlot] = []
        for s in sorted(candidate_slots, key=lambda x: x.fit_score, reverse=True):
            key = (s.start_time, s.end_time, s.duration_minutes)
            if key not in seen_times:
                seen_times.add(key)
                unique_slots.append(s)

        return unique_slots[:max_slots]

    def schedule(
        self,
        target_date: Optional[date] = None,
        priority_filter: Optional[str] = None,
        location_filter: Optional[str] = None,
    ) -> ScheduleResult:
        """
        Generate full schedule assignments for all active maintenance and block requests.
        """
        s_date = target_date or date.today()

        # Combine maintenance records and block records for scheduling
        requests_to_schedule = []

        for m in self.maintenance_records:
            if m.requested_date == s_date and m.maintenance_required:
                if priority_filter and m.priority.value.lower() != priority_filter.lower():
                    continue
                if location_filter and location_filter.lower() not in m.location.lower():
                    continue
                pref_str = (
                    m.preferred_start.strftime("%H:%M")
                    if hasattr(m.preferred_start, "strftime")
                    else str(m.preferred_start)
                )
                requests_to_schedule.append({
                    "type": "maintenance",
                    "id": m.asset_id,
                    "asset_id": m.asset_id,
                    "block_id": None,
                    "location": m.location,
                    "priority": m.priority,
                    "duration": m.duration_minutes,
                    "preferred_start": pref_str,
                })

        for b in self.block_records:
            if b.requested_date == s_date and b.status != BlockStatus.CANCELLED:
                if priority_filter and b.priority.value.lower() != priority_filter.lower():
                    continue
                if location_filter and location_filter.lower() not in b.location.lower():
                    continue
                dur = _calculate_duration_minutes(b.requested_start, b.requested_end)
                requests_to_schedule.append({
                    "type": "block",
                    "id": b.block_id,
                    "asset_id": None,
                    "block_id": b.block_id,
                    "location": b.location,
                    "priority": b.priority,
                    "duration": dur,
                    "preferred_start": b.requested_start,
                })


        # Sort requests by priority (Critical first) and duration descending
        requests_to_schedule.sort(
            key=lambda r: (PRIORITY_RANK.get(r["priority"], 1), r["duration"]),
            reverse=True,
        )

        scheduled_items: List[MaintenanceScheduleItem] = []
        unfeasible_items: List[MaintenanceScheduleItem] = []
        sched_counter = 1

        for req in requests_to_schedule:
            slots = self.find_feasible_slots(
                location=req["location"],
                duration_minutes=req["duration"],
                preferred_start=req["preferred_start"],
                target_date=s_date,
            )

            if slots:
                primary = slots[0]
                alts = slots[1:]
                status = "Scheduled" if primary.is_preferred_match else "AlternativeSuggested"
                item = MaintenanceScheduleItem(
                    schedule_id=f"SCHED-{sched_counter:04d}",
                    request_id=req["id"],
                    asset_id=req["asset_id"],
                    block_id=req["block_id"],
                    location=req["location"],
                    priority=req["priority"],
                    requested_duration=req["duration"],
                    preferred_start=req["preferred_start"],
                    assigned_slot=primary,
                    alternative_slots=alts,
                    status=status,
                    notes="Feasible window identified without timetable conflicts.",
                )
                scheduled_items.append(item)
            else:
                item = MaintenanceScheduleItem(
                    schedule_id=f"SCHED-{sched_counter:04d}",
                    request_id=req["id"],
                    asset_id=req["asset_id"],
                    block_id=req["block_id"],
                    location=req["location"],
                    priority=req["priority"],
                    requested_duration=req["duration"],
                    preferred_start=req["preferred_start"],
                    assigned_slot=None,
                    alternative_slots=[],
                    status="Unfeasible",
                    notes="No conflict-free time window of sufficient duration available on requested date.",
                )
                unfeasible_items.append(item)

            sched_counter += 1

        return ScheduleResult(
            generated_at=datetime.now(timezone.utc).isoformat(),
            target_date=s_date,
            total_requested=len(requests_to_schedule),
            total_scheduled=len(scheduled_items),
            total_unfeasible=len(unfeasible_items),
            scheduled_items=scheduled_items,
            unfeasible_items=unfeasible_items,
        )
