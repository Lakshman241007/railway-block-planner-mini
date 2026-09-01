"""
CP-SAT Hard Constraints Engine (Phase 5).

Formulates and adds mathematical constraints to the OR-Tools CP-SAT model:
1. Slot Assignment (at most one slot per maintenance request)
2. Location/Track Mutual Exclusion (no concurrent blocks on the same section)
3. Train Movement & Safety Protection
4. Specialized Equipment & Resource Capacity Limits
5. Planning Horizon Bounding

PROTOTYPE DISCLAIMER:
Constraint models and capacities are prototype assumptions for the hackathon
demonstration and are NOT official railway operating rules.
"""

from __future__ import annotations

from datetime import date
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from ortools.sat.python import cp_model

from backend.app.scheduler.scheduler import _locations_match, _parse_time_to_minutes

logger = logging.getLogger(__name__)


def add_slot_assignment_constraints(
    model: cp_model.CpModel,
    slot_vars: Dict[Tuple[str, str], cp_model.IntVar],
    requests_to_slots: Dict[str, List[str]],
) -> int:
    """
    Constraint B: Feasible-window & Uniqueness constraint.
    Each maintenance request i can be assigned to AT MOST ONE candidate slot.
    sum_{s in CandidateSlots(i)} x[i, s] <= 1
    """
    constraint_count = 0
    for req_id, slot_ids in requests_to_slots.items():
        vars_for_req = [slot_vars[(req_id, s_id)] for s_id in slot_ids if (req_id, s_id) in slot_vars]
        if vars_for_req:
            model.Add(sum(vars_for_req) <= 1)
            constraint_count += 1
    return constraint_count


def add_track_overlap_constraints(
    model: cp_model.CpModel,
    slot_vars: Dict[Tuple[str, str], cp_model.IntVar],
    slot_metadata: Dict[str, Dict[str, Any]],
) -> int:
    """
    Constraint C: Location/Track exclusive possession constraint.
    Two incompatible maintenance blocks on the same track section/corridor
    CANNOT overlap in absolute time, including overnight spans across calendar days.
    
    If slot s1 (for request i) and slot s2 (for request j) overlap on the same section:
    x[i, s1] + x[j, s2] <= 1
    """
    constraint_count = 0
    slot_list = list(slot_metadata.items())
    num_slots = len(slot_list)
    if num_slots == 0:
        return 0

    base_date = min(meta["service_date"] for _, meta in slot_list)

    for i in range(num_slots):
        s1_id, meta1 = slot_list[i]
        req1 = meta1["request_id"]
        loc1 = meta1["location"]
        day_diff1 = (meta1["service_date"] - base_date).days
        abs_start1 = day_diff1 * 1440 + meta1["start_minutes"]
        abs_end1 = day_diff1 * 1440 + meta1["end_minutes"]

        var1 = slot_vars.get((req1, s1_id))
        if var1 is None:
            continue

        for j in range(i + 1, num_slots):
            s2_id, meta2 = slot_list[j]
            req2 = meta2["request_id"]
            if req1 == req2:
                continue

            loc2 = meta2["location"]
            day_diff2 = (meta2["service_date"] - base_date).days
            abs_start2 = day_diff2 * 1440 + meta2["start_minutes"]
            abs_end2 = day_diff2 * 1440 + meta2["end_minutes"]

            var2 = slot_vars.get((req2, s2_id))
            if var2 is None:
                continue

            # Check track section overlap
            if _locations_match(loc1, loc2):
                # Check temporal interval overlap in absolute minutes
                if max(abs_start1, abs_start2) < min(abs_end1, abs_end2):
                    model.Add(var1 + var2 <= 1)
                    constraint_count += 1

    return constraint_count


def add_equipment_capacity_constraints(
    model: cp_model.CpModel,
    slot_vars: Dict[Tuple[str, str], cp_model.IntVar],
    slot_metadata: Dict[str, Dict[str, Any]],
    resource_capacities: Dict[str, int],
) -> int:
    """
    Constraint F: Resource & Specialized Equipment capacity constraint.
    
    For each equipment type (e.g. 'Track Tamper', 'OHE Car') with capacity C_eq:
    At any point in absolute time across the planning horizon, the sum of active
    maintenance blocks requiring that equipment cannot exceed C_eq.
    """
    constraint_count = 0
    if not resource_capacities or not slot_metadata:
        return 0

    base_date = min(meta["service_date"] for meta in slot_metadata.values())

    # Group slots by equipment_type across the horizon
    equip_groups: Dict[str, List[Tuple[str, Dict[str, Any], int, int]]] = {}

    for s_id, meta in slot_metadata.items():
        eq = meta.get("equipment")
        if eq and str(eq).strip().lower() not in ("none", "", "nil"):
            norm_eq = str(eq).strip()
            cap = _get_equipment_capacity(norm_eq, resource_capacities)
            if cap is not None:
                day_diff = (meta["service_date"] - base_date).days
                abs_start = day_diff * 1440 + meta["start_minutes"]
                abs_end = day_diff * 1440 + meta["end_minutes"]
                equip_groups.setdefault(norm_eq, []).append((s_id, meta, abs_start, abs_end))

    for eq_name, items in equip_groups.items():
        cap = _get_equipment_capacity(eq_name, resource_capacities)
        if cap is None or len(items) <= cap:
            continue

        # Extract absolute time events (start/end) for sweep-line contention intervals
        time_points: Set[int] = set()
        for _, _, abs_s, abs_e in items:
            time_points.add(abs_s)
            time_points.add(abs_e)

        sorted_times = sorted(list(time_points))
        for t_idx in range(len(sorted_times) - 1):
            t_start = sorted_times[t_idx]
            t_end = sorted_times[t_idx + 1]

            concurrent_vars = []
            for s_id, meta, abs_s, abs_e in items:
                if abs_s <= t_start and abs_e >= t_end:
                    var = slot_vars.get((meta["request_id"], s_id))
                    if var is not None:
                        concurrent_vars.append(var)

            if len(concurrent_vars) > cap:
                model.Add(sum(concurrent_vars) <= cap)
                constraint_count += 1

    return constraint_count


def _get_equipment_capacity(equipment_name: str, capacities: Dict[str, int]) -> Optional[int]:
    """Helper to match equipment name against configured capacity map."""
    eq_lower = equipment_name.lower()
    for cap_name, cap_val in capacities.items():
        if cap_name.lower() in eq_lower or eq_lower in cap_name.lower():
            return cap_val
    return capacities.get("General", None)


def add_mandatory_scheduling_constraints(
    model: cp_model.CpModel,
    slot_vars: Dict[Tuple[str, str], cp_model.IntVar],
    mandatory_request_ids: Set[str],
    requests_to_slots: Dict[str, List[str]],
) -> int:
    """
    Optional Hard constraint to force certain critical/emergency requests to be scheduled.
    Used for testing INFEASIBLE scenarios or emergency possessing.
    """
    constraint_count = 0
    for req_id in mandatory_request_ids:
        slot_ids = requests_to_slots.get(req_id, [])
        vars_for_req = [slot_vars[(req_id, s_id)] for s_id in slot_ids if (req_id, s_id) in slot_vars]
        if vars_for_req:
            model.Add(sum(vars_for_req) == 1)
            constraint_count += 1
        else:
            # Forcing a request with 0 candidate slots renders the model infeasible
            model.Add(1 == 0)
            constraint_count += 1
    return constraint_count
