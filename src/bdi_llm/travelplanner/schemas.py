from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TravelDayPlan(BaseModel):
    day: int = Field(..., ge=1)
    current_city: str = Field(...)
    transportation: str = Field(default="-")
    breakfast: str = Field(default="-")
    attraction: str = Field(default="-")
    lunch: str = Field(default="-")
    dinner: str = Field(default="-")
    accommodation: str = Field(default="-")

    @field_validator(
        "current_city",
        "transportation",
        "breakfast",
        "attraction",
        "lunch",
        "dinner",
        "accommodation",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        if value is None:
            return "-"
        text = str(value).strip()
        return text or "-"

    def to_submission_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "days": self.day,
            "current_city": self.current_city,
            "transportation": self.transportation,
            "breakfast": self.breakfast,
            "attraction": self.attraction,
            "lunch": self.lunch,
            "dinner": self.dinner,
            "accommodation": self.accommodation,
        }


class TravelPlannerItinerary(BaseModel):
    summary: str = Field(default="")
    plan: list[TravelDayPlan] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


class TravelPlanIssue(BaseModel):
    code: str = Field(...)
    message: str = Field(...)
    day: int | None = Field(default=None, ge=1)
    field: str | None = Field(default=None)
    blocking: bool = Field(default=True)
    confidence: str = Field(default="high")
    current_value: str | None = Field(default=None)

    @field_validator("code", "message", "field", "current_value", "confidence", mode="before")
    @classmethod
    def _coerce_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class TravelPlanCritique(BaseModel):
    summary: str = Field(default="")
    issues: list[TravelPlanIssue] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @property
    def blocking_issues(self) -> list[TravelPlanIssue]:
        return [issue for issue in self.issues if issue.blocking]

    @property
    def advisory_issues(self) -> list[TravelPlanIssue]:
        return [issue for issue in self.issues if not issue.blocking]

    @property
    def should_repair(self) -> bool:
        return bool(self.blocking_issues)

    def to_prompt_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2)


class TravelDayPatch(BaseModel):
    day: int = Field(..., ge=1)
    current_city: str | None = Field(default=None)
    transportation: str | None = Field(default=None)
    breakfast: str | None = Field(default=None)
    attraction: str | None = Field(default=None)
    lunch: str | None = Field(default=None)
    dinner: str | None = Field(default=None)
    accommodation: str | None = Field(default=None)

    @field_validator(
        "current_city",
        "transportation",
        "breakfast",
        "attraction",
        "lunch",
        "dinner",
        "accommodation",
        mode="before",
    )
    @classmethod
    def _coerce_patch_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class TravelPlanPatch(BaseModel):
    summary: str = Field(default="")
    patches: list[TravelDayPatch] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


class TravelChecklistDay(BaseModel):
    day: int = Field(..., ge=1)
    day_type: str = Field(..., description="travel or stay")
    start_city: str = Field(...)
    end_city: str = Field(...)
    transportation_family: str = Field(default="none")
    hotel_segment: str = Field(default="")
    restaurant_reuse_risk: str = Field(default="low")
    missing_field_risk: str = Field(default="low")

    @field_validator(
        "day_type",
        "start_city",
        "end_city",
        "transportation_family",
        "hotel_segment",
        "restaurant_reuse_risk",
        "missing_field_risk",
        mode="before",
    )
    @classmethod
    def _coerce_check_text(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()


class TravelPlanningChecklist(BaseModel):
    summary: str = Field(default="")
    days: list[TravelChecklistDay] = Field(default_factory=list)
    final_checks: list[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("final_checks", mode="before")
    @classmethod
    def _coerce_final_checks(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class TravelGroundingCandidate(BaseModel):
    day: int = Field(..., ge=1)
    field: str = Field(...)
    name: str = Field(...)
    city: str | None = Field(default=None)
    category: str = Field(default="")
    estimated_cost: float | None = Field(default=None)
    rationale: str = Field(default="")

    @field_validator("field", "name", "city", "category", "rationale", mode="before")
    @classmethod
    def _coerce_candidate_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class TravelGroundingShortlist(BaseModel):
    summary: str = Field(default="")
    candidates: list[TravelGroundingCandidate] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def _coerce_summary(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()
