from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import dspy

from ..planner.dspy_config import configure_dspy
from .schemas import TravelPlannerItinerary
from .signatures import (
    GenerateTravelPlanBaseline,
    GenerateTravelPlanBDI,
    RepairTravelPlan,
)


@dataclass
class TravelPlannerGenerationResult:
    itinerary: TravelPlannerItinerary
    raw: Any


class TravelPlannerGenerator:
    def __init__(self):
        configure_dspy()
        self._baseline = dspy.Predict(GenerateTravelPlanBaseline)
        self._bdi = dspy.ChainOfThought(GenerateTravelPlanBDI)
        self._repair = dspy.ChainOfThought(RepairTravelPlan)

    def generate_baseline(self, beliefs: str, desire: str, domain_context: str) -> TravelPlannerGenerationResult:
        pred = self._baseline(beliefs=beliefs, desire=desire, domain_context=domain_context or '')
        return TravelPlannerGenerationResult(itinerary=pred.itinerary, raw=pred)

    def generate_bdi(self, beliefs: str, desire: str, domain_context: str) -> TravelPlannerGenerationResult:
        pred = self._bdi(beliefs=beliefs, desire=desire, domain_context=domain_context or '')
        return TravelPlannerGenerationResult(itinerary=pred.itinerary, raw=pred)

    def repair(
        self,
        beliefs: str,
        desire: str,
        domain_context: str,
        previous_itinerary: TravelPlannerItinerary,
        evaluator_feedback: str,
    ) -> TravelPlannerGenerationResult:
        pred = self._repair(
            beliefs=beliefs,
            desire=desire,
            domain_context=domain_context or '',
            previous_itinerary_json=json.dumps(previous_itinerary.model_dump(), ensure_ascii=False, indent=2),
            evaluator_feedback=evaluator_feedback,
        )
        return TravelPlannerGenerationResult(itinerary=pred.itinerary, raw=pred)
