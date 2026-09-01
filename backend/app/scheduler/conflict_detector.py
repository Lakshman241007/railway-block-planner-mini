"""
Conflict Detection Engine for Railway Block Planner.

Analyzes proposed maintenance windows, block requests, train timetables,
active movements, and goods train forecasts to detect spatial-temporal collisions,
safety buffer violations, and resource contentions.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
import logging
from typing import Dict, List, Optional, Tuple, Union

from backend.app.forecast.schemas import GoodsForecastItem
from backend.app.scheduler.schemas import (
    ConflictItem,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    ScheduleResult,
)
from backend.app.schemas.unified_data import (
    BlockRecord,
    BlockStatus,
    MaintenanceRecord,
    MovementRecord,
    Priority,
    TimetableRecord,
    TrainRecord,
)

logger = logging.getLogger(__name__)

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


def _format_minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to HH:MM format."""
    norm = max(0, min(1439, minutes))
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

    for corridor, aliases in LOCATION_ALIASES.items():
        in_l1 = (corridor in l1) or any(a in l1 for a in aliases)
        in_l2 = (corridor in l2) or any(a in l2 for a in aliases)
        if in_l1 and in_l2:
            return True
    return False


class ConflictDetector:
    """
    Evaluates spatial-temporal conflicts across all railway domain entities.
    """

    def __init__(
        self,
        trains: Optional[List[TrainRecord]] = None,
        timetables: Optional[List[TimetableRecord]] = None,
        goods_forecasts: Optional[List[GoodsForecastItem]] = None,
        movements: Optional[List[MovementRecord]] = None,
        maintenance_records: Optional[List[MaintenanceRecord]] = None,
        block_records: Optional[List[BlockRecord]] = None,
        buffer_minutes: int = 15,
    ) -> None:
        self.trains = trains or []
        self.timetables = timetables or []
        self.goods_forecasts = goods_forecasts or []
        self.movements = movements or []
        self.maintenance_records = maintenance_records or []
        self.block_records = block_records or []
        self.buffer_minutes = max(0, buffer_minutes)

    def detect_conflicts(
        self,
        target_date: Optional[date] = None,
        proposed_schedule: Optional[ScheduleResult] = None,
    ) -> ConflictReport:
        """
        Scan all active entities for operational conflicts on the target date.
        """
        c_date = target_date or date.today()
        conflicts: List[ConflictItem] = []
        conflict_idx = 1

        # Extract blocks & maintenance windows to check
        block_windows: List[Dict] = []

        if proposed_schedule:
            for item in proposed_schedule.scheduled_items:
                if item.assigned_slot:
                    s_min = _parse_time_to_minutes(item.assigned_slot.start_time)
                    e_min = _parse_time_to_minutes(item.assigned_slot.end_time)
                    if s_min is not None and e_min is not None:
                        block_windows.append({
                            "id": item.request_id,
                            "type": "ScheduledBlock",
                            "location": item.location,
                            "start": s_min,
                            "end": e_min,
                            "priority": item.priority,
                            "equipment": getattr(item, "equipment", None),
                        })

        # Also add un-scheduled requested maintenance records
        for m in self.maintenance_records:
            if m.requested_date == c_date and m.maintenance_required:
                p_start = _parse_time_to_minutes(m.preferred_start)
                if p_start is not None:
                    p_end = p_start + m.duration_minutes
                    block_windows.append({
                        "id": m.asset_id,
                        "type": "MaintenanceRequest",
                        "location": m.location,
                        "start": p_start,
                        "end": p_end,
                        "priority": m.priority,
                        "equipment": m.equipment,
                    })

        # Add block records
        for b in self.block_records:
            if b.requested_date == c_date and b.status != BlockStatus.CANCELLED:
                b_start = _parse_time_to_minutes(b.requested_start)
                b_end = _parse_time_to_minutes(b.requested_end)
                if b_start is not None and b_end is not None:
                    block_windows.append({
                        "id": b.block_id,
                        "type": "BlockRequest",
                        "location": b.location,
                        "start": b_start,
                        "end": b_end,
                        "priority": b.priority,
                        "equipment": None,
                    })

        # -------------------------------------------------------------
        # 1. Check Train-Block Conflicts against Timetable stops
        # -------------------------------------------------------------
        tt_stops = [tt for tt in self.timetables if tt.service_date == c_date]
        for tt in tt_stops:
            arr = _parse_time_to_minutes(tt.arrival_time)
            dep = _parse_time_to_minutes(tt.departure_time)
            t_start = arr if arr is not None else (dep - 5 if dep is not None else 600)
            t_end = dep if dep is not None else (arr + 5 if arr is not None else 605)

            for blk in block_windows:
                if _locations_match(tt.station_code, blk["location"]):
                    # Check direct overlap
                    overlap_start = max(t_start, blk["start"])
                    overlap_end = min(t_end, blk["end"])
                    if overlap_start < overlap_end:
                        overlap_dur = overlap_end - overlap_start
                        conflicts.append(ConflictItem(
                            conflict_id=f"CONF-{conflict_idx:04d}",
                            conflict_type=ConflictType.TRAIN_BLOCK,
                            severity=ConflictSeverity.CRITICAL,
                            location=blk["location"],
                            service_date=c_date,
                            start_time=_format_minutes_to_time(overlap_start),
                            end_time=_format_minutes_to_time(overlap_end),
                            overlap_minutes=overlap_dur,
                            entity1_type="Train",
                            entity1_id=tt.train_id,
                            entity2_type=blk["type"],
                            entity2_id=blk["id"],
                            description=f"Train {tt.train_id} scheduled at {tt.station_code} overlaps with {blk['type']} {blk['id']}.",
                            suggested_action=f"Shift {blk['type']} {blk['id']} to clear interval after {_format_minutes_to_time(t_end + 15)}.",
                        ))
                        conflict_idx += 1
                    # Check safety buffer violation
                    elif abs(blk["start"] - t_end) < self.buffer_minutes or abs(t_start - blk["end"]) < self.buffer_minutes:
                        buf_gap = min(abs(blk["start"] - t_end), abs(t_start - blk["end"]))
                        conflicts.append(ConflictItem(
                            conflict_id=f"CONF-{conflict_idx:04d}",
                            conflict_type=ConflictType.SAFETY_BUFFER_VIOLATION,
                            severity=ConflictSeverity.LOW,
                            location=blk["location"],
                            service_date=c_date,
                            start_time=_format_minutes_to_time(min(t_start, blk["start"])),
                            end_time=_format_minutes_to_time(max(t_end, blk["end"])),
                            overlap_minutes=self.buffer_minutes - buf_gap,
                            entity1_type="Train",
                            entity1_id=tt.train_id,
                            entity2_type=blk["type"],
                            entity2_id=blk["id"],
                            description=f"Train {tt.train_id} passes within {buf_gap} min (< {self.buffer_minutes} min safety buffer) of {blk['type']} {blk['id']}.",
                            suggested_action=f"Increase clearance gap to minimum {self.buffer_minutes} minutes.",
                        ))
                        conflict_idx += 1

        # -------------------------------------------------------------
        # 2. Check Train-Block Conflicts against Goods Forecasts
        # -------------------------------------------------------------
        for fc in self.goods_forecasts:
            if fc.service_date == c_date:
                f_start = _parse_time_to_minutes(fc.forecasted_entry)
                f_end = _parse_time_to_minutes(fc.forecasted_exit)
                if f_start is None or f_end is None:
                    continue

                for blk in block_windows:
                    if _locations_match(fc.section, blk["location"]):
                        overlap_start = max(f_start, blk["start"])
                        overlap_end = min(f_end, blk["end"])
                        if overlap_start < overlap_end:
                            overlap_dur = overlap_end - overlap_start
                            sev = ConflictSeverity.HIGH if blk["priority"] in (Priority.CRITICAL, Priority.HIGH) else ConflictSeverity.MEDIUM
                            conflicts.append(ConflictItem(
                                conflict_id=f"CONF-{conflict_idx:04d}",
                                conflict_type=ConflictType.TRAIN_BLOCK,
                                severity=sev,
                                location=blk["location"],
                                service_date=c_date,
                                start_time=_format_minutes_to_time(overlap_start),
                                end_time=_format_minutes_to_time(overlap_end),
                                overlap_minutes=overlap_dur,
                                entity1_type="GoodsForecast",
                                entity1_id=fc.train_id,
                                entity2_type=blk["type"],
                                entity2_id=blk["id"],
                                description=f"Forecasted goods movement {fc.train_id} on {fc.section} overlaps with {blk['type']} {blk['id']}.",
                                suggested_action=f"Route goods train {fc.train_id} via Loop line or shift block window.",
                            ))
                            conflict_idx += 1

        # -------------------------------------------------------------
        # 3. Check Block-Block Contention on Same Trackage
        # -------------------------------------------------------------
        for i in range(len(block_windows)):
            for j in range(i + 1, len(block_windows)):
                b1 = block_windows[i]
                b2 = block_windows[j]
                if b1["id"] == b2["id"]:
                    continue

                if _locations_match(b1["location"], b2["location"]):
                    overlap_start = max(b1["start"], b2["start"])
                    overlap_end = min(b1["end"], b2["end"])
                    if overlap_start < overlap_end:
                        overlap_dur = overlap_end - overlap_start
                        sev = ConflictSeverity.CRITICAL if (b1["priority"] == Priority.CRITICAL or b2["priority"] == Priority.CRITICAL) else ConflictSeverity.HIGH
                        conflicts.append(ConflictItem(
                            conflict_id=f"CONF-{conflict_idx:04d}",
                            conflict_type=ConflictType.BLOCK_BLOCK,
                            severity=sev,
                            location=b1["location"],
                            service_date=c_date,
                            start_time=_format_minutes_to_time(overlap_start),
                            end_time=_format_minutes_to_time(overlap_end),
                            overlap_minutes=overlap_dur,
                            entity1_type=b1["type"],
                            entity1_id=b1["id"],
                            entity2_type=b2["type"],
                            entity2_id=b2["id"],
                            description=f"Simultaneous track blocks {b1['id']} and {b2['id']} collide on section {b1['location']}.",
                            suggested_action=f"Stagger maintenance windows sequentially or consolidate into single unified possession.",
                        ))
                        conflict_idx += 1

        # -------------------------------------------------------------
        # 4. Check Resource / Equipment Contention
        # -------------------------------------------------------------
        for i in range(len(block_windows)):
            for j in range(i + 1, len(block_windows)):
                b1 = block_windows[i]
                b2 = block_windows[j]
                if b1["id"] == b2["id"]:
                    continue
                eq1 = b1.get("equipment")
                eq2 = b2.get("equipment")
                if eq1 and eq2 and eq1.strip().lower() == eq2.strip().lower() and eq1.strip().lower() != "none":
                    overlap_start = max(b1["start"], b2["start"])
                    overlap_end = min(b1["end"], b2["end"])
                    if overlap_start < overlap_end:
                        conflicts.append(ConflictItem(
                            conflict_id=f"CONF-{conflict_idx:04d}",
                            conflict_type=ConflictType.RESOURCE_CONTENTION,
                            severity=ConflictSeverity.MEDIUM,
                            location=f"{b1['location']} & {b2['location']}",
                            service_date=c_date,
                            start_time=_format_minutes_to_time(overlap_start),
                            end_time=_format_minutes_to_time(overlap_end),
                            overlap_minutes=overlap_end - overlap_start,
                            entity1_type=b1["type"],
                            entity1_id=b1["id"],
                            entity2_type=b2["type"],
                            entity2_id=b2["id"],
                            description=f"Specialized equipment '{eq1}' concurrently requested by {b1['id']} and {b2['id']}.",
                            suggested_action=f"Reschedule one activity to share equipment {eq1} sequentially.",
                        ))
                        conflict_idx += 1

        crit = sum(1 for c in conflicts if c.severity == ConflictSeverity.CRITICAL)
        high = sum(1 for c in conflicts if c.severity == ConflictSeverity.HIGH)
        med = sum(1 for c in conflicts if c.severity == ConflictSeverity.MEDIUM)
        low = sum(1 for c in conflicts if c.severity == ConflictSeverity.LOW)

        return ConflictReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            target_date=c_date,
            total_conflicts=len(conflicts),
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            is_conflict_free=(len(conflicts) == 0),
            conflicts=conflicts,
        )
