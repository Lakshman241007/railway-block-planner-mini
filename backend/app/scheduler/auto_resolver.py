"""
Rule-Based Conflict Auto-Resolver for Railway Block Planner.

Provides heuristic, rule-based conflict resolution strategies (slot shifting,
loop-line bypassing, priority-based deferral) to assist planners in resolving
detected operational conflicts without mathematical optimization (Phase 5).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from backend.app.scheduler.schemas import (
    ConflictItem,
    ConflictReport,
    ConflictSeverity,
    ConflictType,
    FeasibleSlot,
)


class AutoResolver:
    """
    Rule-based conflict resolver providing actionable heuristics.
    """

    @staticmethod
    def resolve_train_block_conflict(conflict: ConflictItem, buffer_minutes: int = 15) -> Dict[str, str]:
        """Generate resolution recommendation for a Train-Block collision."""
        if conflict.entity1_type == "GoodsForecast":
            return {
                "strategy": "Reroute / Loop Line Possession",
                "recommendation": (
                    f"Reroute goods train {conflict.entity1_id} via Loop line or hold at preceding siding for "
                    f"{conflict.overlap_minutes + buffer_minutes} minutes."
                ),
            }
        else:
            return {
                "strategy": "Shift Maintenance Block",
                "recommendation": (
                    f"Defer maintenance {conflict.entity2_id} to start after train {conflict.entity1_id} "
                    f"clears the section (Shift start time by +{conflict.overlap_minutes + buffer_minutes} mins)."
                ),
            }

    @staticmethod
    def resolve_block_block_conflict(conflict: ConflictItem) -> Dict[str, str]:
        """Generate resolution recommendation for simultaneous track blocks."""
        return {
            "strategy": "Sequential Staggering",
            "recommendation": (
                f"Stagger blocks {conflict.entity1_id} and {conflict.entity2_id} sequentially so "
                f"block 2 begins after block 1 completion."
            ),
        }

    @staticmethod
    def resolve_resource_contention(conflict: ConflictItem) -> Dict[str, str]:
        """Generate resolution recommendation for machinery contention."""
        return {
            "strategy": "Equipment Time-Sharing",
            "recommendation": (
                f"Assign equipment to {conflict.entity1_id} first, then transfer to {conflict.entity2_id} "
                f"following a 60-minute transit and setup window."
            ),
        }

    def generate_resolution_plan(self, report: ConflictReport) -> List[Dict[str, str]]:
        """Generate a complete resolution strategy list for all conflicts in a report."""
        resolutions = []
        for c in report.conflicts:
            if c.conflict_type == ConflictType.TRAIN_BLOCK:
                res = self.resolve_train_block_conflict(c)
            elif c.conflict_type == ConflictType.BLOCK_BLOCK:
                res = self.resolve_block_block_conflict(c)
            elif c.conflict_type == ConflictType.RESOURCE_CONTENTION:
                res = self.resolve_resource_contention(c)
            else:
                res = {
                    "strategy": "Buffer Adjustment",
                    "recommendation": f"Enforce {c.overlap_minutes} min additional buffer clearance.",
                }
            resolutions.append({
                "conflict_id": c.conflict_id,
                "type": c.conflict_type.value,
                "severity": c.severity.value,
                **res,
            })
        return resolutions
