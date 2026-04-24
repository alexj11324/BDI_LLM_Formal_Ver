from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from ..planning_task import PlanningTask
from .reference_info import (
    estimate_itinerary_cost,
    find_accommodation_match,
    parse_budget_from_query,
)
from .schemas import (
    TravelDayPlan,
    TravelPlanCritique,
    TravelPlanIssue,
    TravelPlannerItinerary,
    TravelPlanPatch,
)
from .serializer import PLACEHOLDER_CITY, TravelPlannerPlanSerializer

PATCHABLE_FIELDS = (
    "current_city",
    "transportation",
    "breakfast",
    "attraction",
    "lunch",
    "dinner",
    "accommodation",
)

MEAL_FIELDS = ("breakfast", "lunch", "dinner")
_TRANSITION_RE = re.compile(r"^from\s+(.+?)\s+to\s+(.+)$", re.IGNORECASE)
_PPL_RE = re.compile(r"\b(\d+)\s+(?:people|persons|travelers|travellers|guests)\b", re.IGNORECASE)
_WORD_TO_INT = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
}


@dataclass
class PatchScopeAssessment:
    accepted: bool
    reason: str
    changed_days: int
    changed_fields: int
    touched_fields: list[str]
    issue_codes: list[str]


def expected_days(task: PlanningTask, itinerary: TravelPlannerItinerary | None = None) -> int:
    raw_days = task.metadata.get("days")
    if raw_days:
        try:
            return max(0, int(raw_days))
        except (TypeError, ValueError):
            pass
    if itinerary is not None and itinerary.plan:
        return max(day.day for day in itinerary.plan)
    return 0


def is_placeholder_city(value: str) -> bool:
    return str(value).strip() == PLACEHOLDER_CITY


def normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def parse_transition(current_city: str) -> tuple[str, str] | None:
    match = _TRANSITION_RE.match(str(current_city).strip())
    if not match:
        return None
    origin = match.group(1).strip()
    destination = match.group(2).strip()
    return origin, destination


def is_travel_day(current_city: str) -> bool:
    return parse_transition(current_city) is not None


def transportation_family(text: str) -> str:
    lower = normalize_text(text)
    if not lower or lower == "-":
        return "none"
    if "flight" in lower:
        return "flight"
    if "self-driving" in lower or "self driving" in lower:
        return "self-driving"
    if "taxi" in lower:
        return "taxi"
    if "local transit" in lower or "public transit" in lower or "walk" in lower:
        return "local-transit"
    return "other"


def split_attractions(value: str) -> list[str]:
    if not value or value == "-":
        return []
    return [part.strip() for part in value.split(";") if part.strip()]


def _extract_people_count(query: str) -> int | None:
    query = query or ""
    match = _PPL_RE.search(query)
    if match:
        return int(match.group(1))
    for word, num in _WORD_TO_INT.items():
        if re.search(rf"\b{word}\s+(?:person|people|traveler|traveller|guest)s?\b", query, re.IGNORECASE):
            return num
    return None


def _city_sequence(rows: list[dict[str, Any]]) -> list[str]:
    cities: list[str] = []
    for row in rows:
        current_city = str(row.get("current_city", "")).strip()
        transition = parse_transition(current_city)
        if transition is not None:
            origin, destination = transition
            cities.extend([origin, destination])
        elif current_city and current_city != "-":
            cities.append(current_city)
    return cities


def _is_valid_city_sequence(city_list: list[str]) -> bool:
    if len(city_list) < 2:
        return False
    visited: set[str] = set()
    i = 0
    while i < len(city_list):
        city = city_list[i]
        if city in visited and i not in (0, len(city_list) - 1):
            return False
        count = 0
        while i < len(city_list) and city_list[i] == city:
            count += 1
            i += 1
        if count == 1 and 0 < i - 1 < len(city_list) - 1:
            return False
        visited.add(city)
    return True


def _iter_row_changes(before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]):
    for left, right in zip(before_rows, after_rows, strict=False):
        day = int(left.get("day") or right.get("day"))
        changed_fields = [field for field in PATCHABLE_FIELDS if left.get(field) != right.get(field)]
        if changed_fields:
            yield day, changed_fields


def _check_day_structure(
    itinerary: TravelPlannerItinerary,
    total_days: int,
) -> list[TravelPlanIssue]:
    """Check for duplicate day numbers and out-of-range day values."""
    issues: list[TravelPlanIssue] = []
    day_counter = Counter(day.day for day in itinerary.plan)
    for day, count in sorted(day_counter.items()):
        if count > 1:
            issues.append(
                TravelPlanIssue(
                    code="duplicate_day",
                    day=day,
                    field="day",
                    message=f"Day {day} appears {count} times in the itinerary.",
                    confidence="high",
                    current_value=str(count),
                )
            )
    for day_plan in itinerary.plan:
        if total_days and day_plan.day > total_days:
            issues.append(
                TravelPlanIssue(
                    code="out_of_range_day",
                    day=day_plan.day,
                    field="day",
                    message=f"Day {day_plan.day} is outside the requested range 1..{total_days}.",
                    confidence="high",
                    current_value=str(day_plan.day),
                )
            )
    return issues


def _check_row_issues(row: dict[str, Any], total_days: int) -> list[TravelPlanIssue]:
    """Check a single row for structural issues (city, transition, stay-day fields)."""
    issues: list[TravelPlanIssue] = []
    day = int(row["day"])
    current_city = str(row.get("current_city", "")).strip()
    transportation = str(row.get("transportation", "")).strip()

    if is_placeholder_city(current_city):
        issues.append(
            TravelPlanIssue(
                code="placeholder_day",
                day=day,
                field="current_city",
                message=("This required day was left to the serializer placeholder instead of a real itinerary entry."),
                confidence="high",
                current_value=current_city,
            )
        )
        return issues

    if current_city == "-":
        issues.append(
            TravelPlanIssue(
                code="missing_current_city",
                day=day,
                field="current_city",
                message="current_city must not be empty on a real itinerary day.",
                confidence="high",
                current_value=current_city,
            )
        )
        return issues

    transition = parse_transition(current_city)
    if transition is not None:
        origin_city, destination = transition
        if normalize_text(origin_city) == normalize_text(destination):
            issues.append(
                TravelPlanIssue(
                    code="degenerate_transition",
                    day=day,
                    field="current_city",
                    message="A travel day cannot go from a city to the same city.",
                    confidence="high",
                    current_value=current_city,
                )
            )
        if transportation == "-":
            issues.append(
                TravelPlanIssue(
                    code="missing_transport_for_travel_day",
                    day=day,
                    field="transportation",
                    message="A travel-transition day must include a non-empty transportation entry.",
                    confidence="high",
                    current_value=transportation,
                )
            )
    else:
        if row.get("attraction", "-") in ("", "-"):
            issues.append(
                TravelPlanIssue(
                    code="missing_attraction_for_stay_day",
                    day=day,
                    field="attraction",
                    message="A stay day must include at least one attraction.",
                    confidence="high",
                    current_value=str(row.get("attraction", "-")),
                )
            )
        if day != total_days and row.get("accommodation", "-") in ("", "-"):
            issues.append(
                TravelPlanIssue(
                    code="missing_accommodation_for_stay_day",
                    day=day,
                    field="accommodation",
                    message="A non-final stay day must include accommodation.",
                    confidence="high",
                    current_value=str(row.get("accommodation", "-")),
                )
            )
        missing_meals = [field for field in MEAL_FIELDS if row.get(field, "-") in ("", "-")]
        if missing_meals:
            issues.append(
                TravelPlanIssue(
                    code="missing_meal_for_stay_day",
                    day=day,
                    field=missing_meals[0],
                    message=f"A stay day is missing required meal fields: {', '.join(missing_meals)}.",
                    confidence="high",
                    current_value=", ".join(missing_meals),
                )
            )
    return issues


def _check_duplicate_venues(
    rows: list[dict[str, Any]],
) -> list[TravelPlanIssue]:
    """Check for repeated restaurants and attractions across all rows."""
    issues: list[TravelPlanIssue] = []
    restaurant_seen: dict[str, int] = {}
    attraction_seen: dict[str, int] = {}
    for row in rows:
        day = int(row["day"])
        for field in MEAL_FIELDS:
            restaurant = str(row.get(field, "")).strip()
            if not restaurant or restaurant == "-":
                continue
            key = normalize_text(restaurant)
            if key in restaurant_seen:
                issues.append(
                    TravelPlanIssue(
                        code="duplicate_restaurant",
                        day=day,
                        field=field,
                        message=f"The restaurant in day {day} {field} is repeated.",
                        confidence="high",
                        current_value=restaurant,
                    )
                )
            else:
                restaurant_seen[key] = day
        for attraction in split_attractions(str(row.get("attraction", "-"))):
            key = normalize_text(attraction)
            if key in attraction_seen:
                issues.append(
                    TravelPlanIssue(
                        code="duplicate_attraction",
                        day=day,
                        field="attraction",
                        message=f"The attraction '{attraction}' is repeated across days.",
                        confidence="high",
                        current_value=attraction,
                    )
                )
            else:
                attraction_seen[key] = day
    return issues


def _check_transportation_conflicts(
    transportation_families: set[str],
) -> list[TravelPlanIssue]:
    """Check for incompatible transportation families within the same itinerary."""
    issues: list[TravelPlanIssue] = []
    if "flight" in transportation_families and "self-driving" in transportation_families:
        issues.append(
            TravelPlanIssue(
                code="conflicting_transportation_family",
                message="Flight and self-driving are both used in the same itinerary.",
                field="transportation",
                confidence="high",
                current_value=", ".join(sorted(transportation_families)),
            )
        )
    if "taxi" in transportation_families and "self-driving" in transportation_families:
        issues.append(
            TravelPlanIssue(
                code="conflicting_transportation_family",
                message="Taxi and self-driving are both used in the same itinerary.",
                field="transportation",
                confidence="high",
                current_value=", ".join(sorted(transportation_families)),
            )
        )
    return issues


def _check_city_route(
    city_sequence: list[str],
    origin: str,
) -> list[TravelPlanIssue]:
    """Check route validity: correct origin, closed circle, and no revisits."""
    issues: list[TravelPlanIssue] = []
    if not city_sequence:
        return issues
    if origin and normalize_text(city_sequence[0]) != normalize_text(origin):
        issues.append(
            TravelPlanIssue(
                code="invalid_route_origin",
                day=1,
                field="current_city",
                message=f"The first city should start from {origin}.",
                confidence="high",
                current_value=city_sequence[0],
            )
        )
    if normalize_text(city_sequence[0]) != normalize_text(city_sequence[-1]):
        issues.append(
            TravelPlanIssue(
                code="invalid_closed_circle",
                field="current_city",
                message="The trip should form a closed circle.",
                confidence="high",
                current_value=" -> ".join(city_sequence),
            )
        )
    elif not _is_valid_city_sequence(city_sequence):
        issues.append(
            TravelPlanIssue(
                code="invalid_city_sequence",
                field="current_city",
                message="The city sequence is inconsistent or revisits a city after leaving it.",
                confidence="high",
                current_value=" -> ".join(city_sequence),
            )
        )
    return issues


def _check_accommodation_nights(
    rows_by_day: dict[int, dict[str, Any]],
    total_days: int,
    raw_reference_information: Any,
) -> list[TravelPlanIssue]:
    """Check accommodation minimum-night plausibility."""
    issues: list[TravelPlanIssue] = []
    current_name = None
    current_count = 0
    current_start_day = 1
    for day in range(1, total_days + 1):
        stay = str(rows_by_day.get(day, {}).get("accommodation", "-")).strip()
        if stay == current_name:
            current_count += 1
            continue
        if current_name not in (None, "", "-"):
            match = find_accommodation_match(raw_reference_information, current_name)
            if match and match.minimum_nights and current_count < match.minimum_nights:
                issues.append(
                    TravelPlanIssue(
                        code="accommodation_minimum_nights_violation",
                        day=current_start_day,
                        field="accommodation",
                        message=(
                            f"Accommodation {current_name} appears for {current_count} night(s),"
                            f" below its minimum of {match.minimum_nights}."
                        ),
                        blocking=(match.confidence == "high"),
                        confidence=match.confidence,
                        current_value=current_name,
                    )
                )
        current_name = stay
        current_count = 1
        current_start_day = day
    if current_name not in (None, "", "-"):
        match = find_accommodation_match(raw_reference_information, current_name)
        if match and match.minimum_nights and current_count < match.minimum_nights:
            issues.append(
                TravelPlanIssue(
                    code="accommodation_minimum_nights_violation",
                    day=current_start_day,
                    field="accommodation",
                    message=(
                        f"Accommodation {current_name} appears for {current_count} night(s),"
                        f" below its minimum of {match.minimum_nights}."
                    ),
                    blocking=(match.confidence == "high"),
                    confidence=match.confidence,
                    current_value=current_name,
                )
            )
    return issues


def _check_budget(
    query: str,
    raw_reference_information: Any,
    rows: list[dict[str, Any]],
) -> list[TravelPlanIssue]:
    """Soft price sanity: only fire when estimate is high-confidence and clearly over budget."""
    budget = parse_budget_from_query(query)
    if budget is None:
        return []
    people = _extract_people_count(query) or 1
    estimate = estimate_itinerary_cost(raw_reference_information, rows, people_count=people)
    estimated_total = estimate.total_cost
    if estimate.confidence == "high" and estimated_total > max(budget * 1.15, budget + 100):
        return [
            TravelPlanIssue(
                code="high_confidence_budget_overrun",
                field="transportation",
                message=(
                    f"High-confidence public price estimate ${estimated_total:.0f} exceeds query budget ${budget}."
                ),
                blocking=False,
                confidence="high",
                current_value=f"{estimated_total:.0f}>{budget}",
            )
        ]
    return []


def critique_itinerary(
    itinerary: TravelPlannerItinerary,
    task: PlanningTask,
) -> TravelPlanCritique:
    """Run a high-precision, low-recall non-oracle critique over a sole-planning itinerary."""
    total_days = expected_days(task, itinerary)
    serializer = TravelPlannerPlanSerializer()
    rows = serializer.from_bdi_plan(itinerary, task)
    raw_reference_information = task.metadata.get("reference_information")
    query = str(task.metadata.get("query") or "")
    origin = str(task.metadata.get("org") or "").strip()
    city_sequence = _city_sequence(rows)

    issues: list[TravelPlanIssue] = _check_day_structure(itinerary, total_days)

    transportation_families: set[str] = set()
    for row in rows:
        issues.extend(_check_row_issues(row, total_days))
        family = transportation_family(str(row.get("transportation", "")).strip())
        if family not in ("none", "other", "local-transit"):
            transportation_families.add(family)

    issues.extend(_check_duplicate_venues(rows))
    issues.extend(_check_transportation_conflicts(transportation_families))
    issues.extend(_check_city_route(city_sequence, origin))
    rows_by_day = {int(row["day"]): row for row in rows}
    issues.extend(_check_accommodation_nights(rows_by_day, total_days, raw_reference_information))
    issues.extend(_check_budget(query, raw_reference_information, rows))

    if not issues:
        return TravelPlanCritique(summary="No high-confidence sole-planning issues detected.", issues=[])

    summary = "; ".join(issue.message for issue in issues[:4])
    return TravelPlanCritique(summary=summary, issues=issues)


def allowed_patch_fields_for_issue_codes(issue_codes: set[str]) -> set[str]:
    if not issue_codes:
        return set()
    allowed: set[str] = set()
    for code in issue_codes:
        if code in {"duplicate_restaurant", "missing_meal_for_stay_day"}:
            allowed.update(MEAL_FIELDS)
        elif code in {"duplicate_attraction", "missing_attraction_for_stay_day"}:
            allowed.add("attraction")
        elif code in {
            "missing_transport_for_travel_day",
            "conflicting_transportation_family",
        }:
            allowed.update({"current_city", "transportation"})
        elif code in {
            "invalid_closed_circle",
            "invalid_city_sequence",
            "invalid_route_origin",
            "degenerate_transition",
        }:
            allowed.update({"current_city", "transportation", "accommodation"})
        elif code in {
            "missing_accommodation_for_stay_day",
            "accommodation_minimum_nights_violation",
        }:
            allowed.add("accommodation")
        elif code in {"placeholder_day", "missing_current_city"}:
            allowed.update({"current_city", "transportation", "accommodation"})
        else:
            allowed.update(PATCHABLE_FIELDS)
    return allowed


def apply_patch(
    itinerary: TravelPlannerItinerary,
    patch: TravelPlanPatch,
    task: PlanningTask,
) -> TravelPlannerItinerary:
    """Apply day-level patches while preserving untouched days exactly."""
    total_days = expected_days(task, itinerary)
    day_map: dict[int, TravelDayPlan] = {day.day: day.model_copy(deep=True) for day in itinerary.plan}

    for day_patch in patch.patches:
        if total_days and day_patch.day > total_days:
            continue

        current = day_map.get(day_patch.day)
        if current is None:
            current = TravelDayPlan(day=day_patch.day, current_city=PLACEHOLDER_CITY)

        updates: dict[str, Any] = {}
        for field in PATCHABLE_FIELDS:
            value = getattr(day_patch, field)
            if value is not None:
                updates[field] = value

        if not updates:
            continue

        if current.current_city == PLACEHOLDER_CITY and "current_city" not in updates:
            continue

        day_map[day_patch.day] = current.model_copy(update=updates)

    return TravelPlannerItinerary(
        summary=patch.summary or itinerary.summary,
        plan=sorted(day_map.values(), key=lambda day: day.day),
    )


def count_itinerary_changes(
    before: TravelPlannerItinerary,
    after: TravelPlannerItinerary,
    task: PlanningTask,
) -> tuple[int, int]:
    serializer = TravelPlannerPlanSerializer()
    before_rows = serializer.from_bdi_plan(before, task)
    after_rows = serializer.from_bdi_plan(after, task)

    changed_days = 0
    changed_fields = 0
    for _, changed in _iter_row_changes(before_rows, after_rows):
        changed_fields += len(changed)
        changed_days += 1
    return changed_days, changed_fields


def assess_patch_scope(
    before: TravelPlannerItinerary,
    after: TravelPlannerItinerary,
    task: PlanningTask,
    critique: TravelPlanCritique,
    *,
    previous_stats: PatchScopeAssessment | None = None,
) -> PatchScopeAssessment:
    serializer = TravelPlannerPlanSerializer()
    before_rows = serializer.from_bdi_plan(before, task)
    after_rows = serializer.from_bdi_plan(after, task)

    issue_codes = {issue.code for issue in critique.blocking_issues}
    issue_days = {issue.day for issue in critique.blocking_issues if issue.day is not None}
    touched_fields: list[str] = []
    touched_days: list[int] = []
    for day, fields in _iter_row_changes(before_rows, after_rows):
        touched_days.append(day)
        touched_fields.extend(fields)

    changed_days = len(set(touched_days))
    changed_fields = len(touched_fields)
    touched_field_set = set(touched_fields)
    allowed_fields = allowed_patch_fields_for_issue_codes(issue_codes)

    if changed_days == 0 and changed_fields == 0:
        return PatchScopeAssessment(True, "no_change", 0, 0, [], sorted(issue_codes))

    if allowed_fields and touched_field_set - allowed_fields:
        return PatchScopeAssessment(
            False,
            f"patch touched disallowed fields: {sorted(touched_field_set - allowed_fields)}",
            changed_days,
            changed_fields,
            sorted(touched_field_set),
            sorted(issue_codes),
        )

    max_days = min(max(len(issue_days) + 1, 1), 4)
    max_fields = max(len(issue_codes) * 3, 3)

    if changed_days > max_days:
        return PatchScopeAssessment(
            False,
            f"patch changed too many days ({changed_days} > {max_days})",
            changed_days,
            changed_fields,
            sorted(touched_field_set),
            sorted(issue_codes),
        )

    if changed_fields > max_fields:
        return PatchScopeAssessment(
            False,
            f"patch changed too many fields ({changed_fields} > {max_fields})",
            changed_days,
            changed_fields,
            sorted(touched_field_set),
            sorted(issue_codes),
        )

    if previous_stats is not None:
        if changed_fields > previous_stats.changed_fields:
            return PatchScopeAssessment(
                False,
                "patch expanded field-change scope on a later pass",
                changed_days,
                changed_fields,
                sorted(touched_field_set),
                sorted(issue_codes),
            )
        if changed_days > previous_stats.changed_days:
            return PatchScopeAssessment(
                False,
                "patch expanded day-change scope on a later pass",
                changed_days,
                changed_fields,
                sorted(touched_field_set),
                sorted(issue_codes),
            )

    # A patch that expands beyond the implicated days is always suspicious.
    if issue_days:
        max_issue_day = max(issue_days)
        min_issue_day = min(issue_days)
        widened_days = [day for day in touched_days if day < min_issue_day - 1 or day > max_issue_day + 1]
        if widened_days:
            return PatchScopeAssessment(
                False,
                f"patch touched unrelated days: {sorted(set(widened_days))}",
                changed_days,
                changed_fields,
                sorted(touched_field_set),
                sorted(issue_codes),
            )

    return PatchScopeAssessment(
        True,
        "accepted",
        changed_days,
        changed_fields,
        sorted(touched_field_set),
        sorted(issue_codes),
    )


def summarize_issue_categories(critiques: list[TravelPlanCritique]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for critique in critiques:
        for issue in critique.issues:
            counts[issue.code] += 1
    return dict(sorted(counts.items()))


def build_non_oracle_diagnostics(
    before: TravelPlannerItinerary,
    after: TravelPlannerItinerary,
    task: PlanningTask,
    critiques: list[TravelPlanCritique],
    passes_used: int,
    *,
    guardrails: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    changed_days, changed_fields = count_itinerary_changes(before, after, task)
    return {
        "triggered": bool(critiques),
        "passes_used": passes_used,
        "changed_days": changed_days,
        "changed_fields": changed_fields,
        "issue_categories": summarize_issue_categories(critiques),
        "issues": [critique.model_dump() for critique in critiques],
        "guardrails": guardrails or [],
    }
