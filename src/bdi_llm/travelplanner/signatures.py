from __future__ import annotations

import dspy

from .schemas import TravelPlannerItinerary


class GenerateTravelPlanBaseline(dspy.Signature):
    """Generate a direct structured itinerary for TravelPlanner sole-planning."""

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Structured day-by-day travel itinerary.'
    )


class GenerateTravelPlanBDI(dspy.Signature):
    __doc__ = """
    You are a travel planning agent. Build the itinerary day by day.
    Keep track of current city transitions, transportation feasibility, accommodation continuity,
    and whether breakfast/lunch/dinner/attractions are filled appropriately.
    Return a structured itinerary only.
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Structured day-by-day travel itinerary.'
    )


class RepairTravelPlan(dspy.Signature):
    __doc__ = """
    You are repairing a TravelPlanner itinerary after official validation failed.
    Fix only the failing days or constraints when possible. Preserve already-valid parts.
    Return a corrected structured itinerary only.
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    previous_itinerary_json: str = dspy.InputField()
    evaluator_feedback: str = dspy.InputField(default='')
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Corrected structured day-by-day travel itinerary.'
    )
