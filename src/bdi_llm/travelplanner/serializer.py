from __future__ import annotations

from typing import Any

from ..planning_task import PlanSerializer, PlanningTask
from .schemas import TravelDayPlan, TravelPlannerItinerary


_PLACEHOLDER_CITY = "You don't need to fill in the information for this or later days."


class TravelPlannerPlanSerializer(PlanSerializer):
    """Convert internal itinerary schema into official TravelPlanner submission rows."""

    def from_bdi_plan(self, plan: TravelPlannerItinerary, task: PlanningTask) -> list[dict[str, Any]]:
        expected_days = int(task.metadata.get('days') or len(plan.plan) or 0)
        rows = sorted(plan.plan, key=lambda day: day.day)
        if expected_days <= 0:
            expected_days = len(rows)

        normalized: list[TravelDayPlan] = []
        for index in range(1, expected_days + 1):
            if index <= len(rows):
                current = rows[index - 1]
                if current.day != index:
                    current = current.model_copy(update={'day': index})
            else:
                current = TravelDayPlan(
                    day=index,
                    current_city=_PLACEHOLDER_CITY,
                    transportation='-',
                    breakfast='-',
                    attraction='-',
                    lunch='-',
                    dinner='-',
                    accommodation='-',
                )
            normalized.append(current)

        return [day.to_submission_dict() for day in normalized]

    def to_submission_record(self, plan: TravelPlannerItinerary, task: PlanningTask) -> dict[str, Any]:
        raw_sample = task.metadata.get('raw_sample') or {}
        return {
            'idx': int(raw_sample.get('idx') or task.task_id),
            'query': raw_sample.get('query') or task.metadata.get('query') or '',
            'plan': self.from_bdi_plan(plan, task),
        }
