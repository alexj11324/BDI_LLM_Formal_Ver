from __future__ import annotations

import dspy

from .schemas import (
    TravelPlanCritique,
    TravelPlanPatch,
    TravelGroundingShortlist,
    TravelPlannerItinerary,
    TravelPlanningChecklist,
)


class GenerateTravelPlanBaseline(dspy.Signature):
    """Generate a direct structured itinerary for TravelPlanner sole-planning."""

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Structured day-by-day travel itinerary.'
    )


class GenerateTravelPlanBDILegacy(dspy.Signature):
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


class GenerateTravelPlanBDI(dspy.Signature):
    __doc__ = """
    You are solving the TravelPlanner benchmark in sole-planning mode.
    This is NOT the benchmark's two-stage tool-use setting.

    You must plan using only the user request, the provided reference information,
    and the public output specification.

    Build the itinerary day by day while maintaining a latent state table:
    - current city at the start and end of each day
    - whether the day is a travel day or a stay-in-city day
    - which transportation event changes the city
    - accommodation continuity across consecutive city days
    - meal / attraction / accommodation grounding from the reference information

    Hard planning doctrine:
    1. Copy grounded entities from the provided reference information whenever possible.
       Do not invent generic filler entries just to make the table look complete.
    2. If `current_city` is written as `from A to B`, `transportation` must be concrete and non-`-`.
    3. If the day is not a travel-transition day, do not force an inter-city transportation string.
    4. Avoid placeholder phrases like "local transit within city" unless they are genuinely needed.
    5. Preserve day-by-day city consistency: meals, attractions, and accommodation should match the city actually reached that day.
    6. Stay budget-conscious and route-conscious; avoid obviously wasteful or contradictory moves.
    7. Return a structured itinerary only. No prose, no analysis, no markdown.

    Before finalizing each day, silently check:
    - What city am I in now?
    - Did I change cities today? If yes, is transportation non-empty?
    - Are the entities grounded in the provided reference information?
    - Am I leaving later days accidentally unplanned?

    Return a structured itinerary only.
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Structured day-by-day travel itinerary.'
    )


class GenerateTravelPlanBDIv3(dspy.Signature):
    __doc__ = """
    You are solving TravelPlanner in sole-planning mode.
    Build the plan in two internal phases:

    Phase 1: produce a structured planning checklist.
    Phase 2: produce the final itinerary from that checklist.

    The checklist must reason only from public sole-planning inputs:
    - query
    - days
    - origin
    - destination
    - dates
    - reference information

    Checklist obligations:
    - identify which days are travel days vs stay days
    - track start city and end city for each day
    - choose one transportation family plan that does not conflict across the trip
    - segment hotel stays by city
    - explicitly assess restaurant reuse risk
    - explicitly assess missing-field risk for non-travel days

    Final itinerary obligations:
    - no repeated restaurants across the trip unless clearly unavoidable
    - no travel day with `transportation = '-'`
    - no non-travel day without meals / attraction / accommodation when the public sole-planning contract requires them
    - no city-sequence break or non-closed-circle artifact
    - prefer lower-cost grounded options when multiple grounded candidates exist in the reference information
    - do not output the checklist as prose; return the checklist object and the itinerary object only
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    checklist: TravelPlanningChecklist = dspy.OutputField(
        desc='Internal structured checklist used to build the itinerary.'
    )
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Structured day-by-day travel itinerary.'
    )


class GenerateTravelPlanChecklistV4(dspy.Signature):
    __doc__ = """
    You are solving TravelPlanner in sole-planning mode.
    Build only the route-and-constraint checklist first.

    The checklist must:
    - identify travel days vs stay days
    - track start city and end city
    - choose a non-conflicting transportation family plan
    - group hotel stay segments by city
    - flag restaurant reuse risk
    - flag missing-field risk
    - explicitly note budget pressure from the public query and reference information
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    checklist: TravelPlanningChecklist = dspy.OutputField(
        desc='Structured route and constraint checklist.'
    )


class RenderTravelPlanFromChecklistV4(dspy.Signature):
    __doc__ = """
    You are rendering a final sole-planning itinerary from a route checklist.

    Use the checklist and public reference information to build a grounded shortlist
    of restaurants, accommodations, and flights, then emit the final itinerary.

    Hard requirements:
    - prefer lower-cost grounded candidates when multiple candidates satisfy the checklist
    - avoid repeated restaurants
    - keep accommodation stays coherent with minimum-night constraints
    - avoid conflicting transportation families
    - preserve closed-circle / route consistency from the checklist
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    checklist_json: str = dspy.InputField()
    shortlist: TravelGroundingShortlist = dspy.OutputField(
        desc='Grounded candidate shortlist used to render the itinerary.'
    )
    itinerary: TravelPlannerItinerary = dspy.OutputField(
        desc='Structured day-by-day travel itinerary.'
    )


class CritiqueTravelPlan(dspy.Signature):
    __doc__ = """
    Review a sole-planning itinerary and report only issues that are clearly wrong.
    Prefer high precision over high recall. If a problem is uncertain, do not report it.
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    itinerary_json: str = dspy.InputField()
    critique: TravelPlanCritique = dspy.OutputField(
        desc='High-confidence critique of the itinerary.'
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


class RepairTravelPlanPatch(dspy.Signature):
    __doc__ = """
    You are repairing a TravelPlanner itinerary in sole-planning mode.

    You will receive:
    - the original task context
    - the previous itinerary as JSON
    - a deterministic critique JSON describing only high-confidence issues
    - optional official evaluator feedback (available only on labeled splits)

    Your job is to return a SMALL patch, not a rewritten itinerary.

    Hard repair doctrine:
    1. Preserve untouched days exactly.
    2. Edit only days directly implicated by the critique or feedback.
    3. Prefer the smallest patch that resolves the known issue.
    4. Do not rewrite the entire plan.
    5. If no clearly actionable fix is needed, return an empty patch list.
    """

    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    domain_context: str = dspy.InputField(default='')
    previous_itinerary_json: str = dspy.InputField()
    critique_json: str = dspy.InputField(default='')
    oracle_feedback: str = dspy.InputField(default='')
    patch: TravelPlanPatch = dspy.OutputField(
        desc='A minimal day-level patch for the itinerary.'
    )
