"""
CP-SAT Soft Multi-Objective Engine (Phase 5).

Formulates the weighted multi-criteria objective function for CP-SAT:
1. Maximize total scheduled maintenance throughput
2. Prioritize Critical and High urgency maintenance requests
3. Minimize temporal deviation from requested preferred start times
4. Penalize operational disruption and suboptimal slot fits

PROTOTYPE DISCLAIMER:
Objective weights and scoring formulations are prototype assumptions for the
hackathon demonstration and are NOT official railway operating rules.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ortools.sat.python import cp_model

from backend.app.optimizer.schemas import ObjectiveWeights
from backend.app.schemas.unified_data import Priority

logger = logging.getLogger(__name__)


def get_priority_weight(priority: Priority, weights: ObjectiveWeights) -> int:
    """Return configured integer weight bonus for given priority level."""
    if priority == Priority.CRITICAL:
        return weights.weight_priority_critical
    elif priority == Priority.HIGH:
        return weights.weight_priority_high
    elif priority == Priority.MEDIUM:
        return weights.weight_priority_medium
    elif priority == Priority.LOW:
        return weights.weight_priority_low
    return weights.weight_priority_low


def compute_slot_coefficient(
    meta: Dict[str, Any],
    weights: ObjectiveWeights,
) -> int:
    """
    Calculate the net integer objective coefficient for assigning a maintenance
    request to a specific candidate slot.
    
    Formula:
        coeff = W_scheduled
              + W_priority(priority)
              - W_dev * abs(start_mins - pref_mins)
              - W_dis * int((1.0 - fit_score) * 10)
    """
    # 1. Base scheduling reward
    coeff = weights.weight_scheduled

    # 2. Priority bonus
    priority = meta.get("priority", Priority.LOW)
    coeff += get_priority_weight(priority, weights)

    # 3. Preferred start time deviation penalty
    start_mins = meta.get("start_minutes", 0)
    pref_mins = meta.get("preferred_start_minutes", start_mins)
    deviation = abs(start_mins - pref_mins)
    coeff -= weights.weight_preferred_deviation * deviation

    # 4. Disruption / slot fit degradation penalty
    fit_score = meta.get("fit_score", 1.0)
    disruption_penalty = int((1.0 - max(0.0, min(1.0, fit_score))) * 100)
    coeff -= (weights.weight_disruption * disruption_penalty) // 10

    return coeff


def build_optimization_objective(
    model: cp_model.CpModel,
    slot_vars: Dict[Tuple[str, str], cp_model.IntVar],
    slot_metadata: Dict[str, Dict[str, Any]],
    weights: ObjectiveWeights,
) -> Dict[Tuple[str, str], int]:
    """
    Constructs and attaches the linear maximization objective to the CP-SAT model.
    
    Returns the dictionary of computed coefficients for telemetry and logging.
    """
    objective_terms = []
    coefficients: Dict[Tuple[str, str], int] = {}

    for (req_id, s_id), var in slot_vars.items():
        meta = slot_metadata.get(s_id, {})
        coeff = compute_slot_coefficient(meta, weights)
        coefficients[(req_id, s_id)] = coeff
        objective_terms.append(coeff * var)

    if objective_terms:
        model.Maximize(sum(objective_terms))
    else:
        model.Maximize(0)

    return coefficients
