from __future__ import annotations

import json
from typing import Any

from ..planning_task import PlanningTask, TaskAdapter


class TravelPlannerTaskAdapter(TaskAdapter):
    """Convert official TravelPlanner samples into `PlanningTask`."""

    def __init__(self, domain_context: str | None = None):
        self.domain_context = domain_context or (
            'TravelPlanner sole-planning benchmark. Output a structured multi-day itinerary. '
            'For each day include current_city, transportation, breakfast, attraction, '
            'lunch, dinner, and accommodation. Respect budget, day count, route coherence, '
            'hotel continuity, commonsense constraints, and hard constraints.'
        )

    @staticmethod
    def _stringify_reference_information(reference_information: Any) -> str:
        if isinstance(reference_information, str):
            return reference_information.strip()
        return json.dumps(reference_information, ensure_ascii=False, indent=2)

    def to_planning_task(self, raw_input: Any) -> PlanningTask:
        if not isinstance(raw_input, dict):
            raise TypeError(f'Unsupported raw_input type: {type(raw_input)}')

        idx = raw_input.get('idx') or raw_input.get('id') or raw_input.get('task_id')
        if idx is None:
            raise ValueError('TravelPlanner sample missing stable id/index')

        query = str(raw_input.get('query', '')).strip()
        if not query:
            raise ValueError('TravelPlanner sample missing query')

        reference_information = self._stringify_reference_information(
            raw_input.get('reference_information', '')
        )
        beliefs = (
            'TRAVELPLANNER SOLE-PLANNING TASK\n\n'
            f'User query:\n{query}\n\n'
            'Reference information (sandbox facts):\n'
            f'{reference_information}'
        )
        desire = (
            'Produce a complete day-by-day travel itinerary that satisfies the user request, '
            'budget, timing, route, and local constraints. Return enough information for official '
            'TravelPlanner validation.'
        )

        metadata = {
            'raw_sample': raw_input,
            'split': raw_input.get('split'),
            'days': raw_input.get('days'),
            'level': raw_input.get('level'),
            'org': raw_input.get('org'),
            'dest': raw_input.get('dest'),
            'date': raw_input.get('date'),
            'reference_information': raw_input.get('reference_information'),
            'query': query,
        }

        return PlanningTask(
            task_id=str(idx),
            domain_name='travelplanner',
            beliefs=beliefs,
            desire=desire,
            domain_context=self.domain_context,
            metadata=metadata,
        )
