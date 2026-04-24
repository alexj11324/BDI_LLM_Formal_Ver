from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from ..planning_task import PlanningTask, TaskAdapter
from .reference_info import grounding_hint_summary, parse_budget_from_query, reference_summary
from .spec import load_travelplanner_spec


@lru_cache(maxsize=1)
def _default_domain_context() -> str:
    spec = load_travelplanner_spec()
    return "TravelPlanner sole-planning benchmark. Follow the output spec exactly.\n\n" + spec


class TravelPlannerTaskAdapter(TaskAdapter):
    """Convert official TravelPlanner samples into `PlanningTask`."""

    def __init__(self, domain_context: str | None = None):
        self.domain_context = domain_context or _default_domain_context()

    @staticmethod
    def _stringify_reference_information(reference_information: Any) -> str:
        if isinstance(reference_information, str):
            return reference_information.strip()
        return json.dumps(reference_information, ensure_ascii=False, indent=2)

    def to_planning_task(self, raw_input: Any) -> PlanningTask:
        if not isinstance(raw_input, dict):
            raise TypeError(f"Unsupported raw_input type: {type(raw_input)}")

        idx = raw_input.get("idx") or raw_input.get("id") or raw_input.get("task_id")
        if idx is None:
            raise ValueError("TravelPlanner sample missing stable id/index")

        query = str(raw_input.get("query", "")).strip()
        if not query:
            raise ValueError("TravelPlanner sample missing query")

        raw_reference_information = raw_input.get("reference_information", "")
        reference_information = self._stringify_reference_information(raw_reference_information)
        query_budget = parse_budget_from_query(query)
        public_digest = reference_summary(
            raw_reference_information,
            query=query,
            days=raw_input.get("days"),
            org=raw_input.get("org"),
            dest=raw_input.get("dest"),
        )
        candidate_digest = grounding_hint_summary(
            raw_reference_information,
            org=raw_input.get("org"),
            dest=raw_input.get("dest"),
            budget=query_budget,
        )
        beliefs = (
            "TRAVELPLANNER SOLE-PLANNING TASK\n\n"
            f"User query:\n{query}\n\n"
            f"{public_digest}\n\n"
            f"{candidate_digest}\n\n"
            "Reference information (sandbox facts):\n"
            f"{reference_information}"
        )
        desire = (
            "Produce a complete day-by-day travel itinerary that satisfies the user request, "
            "budget, timing, route, and local constraints. Return enough information for official "
            "TravelPlanner validation."
        )

        metadata = {
            "raw_sample": raw_input,
            "split": raw_input.get("split"),
            "days": raw_input.get("days"),
            "level": raw_input.get("level"),
            "org": raw_input.get("org"),
            "dest": raw_input.get("dest"),
            "date": raw_input.get("date"),
            "reference_information": raw_input.get("reference_information"),
            "query": query,
        }

        return PlanningTask(
            task_id=str(idx),
            domain_name="travelplanner",
            beliefs=beliefs,
            desire=desire,
            domain_context=self.domain_context,
            metadata=metadata,
        )
