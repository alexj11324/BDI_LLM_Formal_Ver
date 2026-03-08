from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class TravelDayPlan(BaseModel):
    day: int = Field(..., ge=1)
    current_city: str = Field(...)
    transportation: str = Field(default='-')
    breakfast: str = Field(default='-')
    attraction: str = Field(default='-')
    lunch: str = Field(default='-')
    dinner: str = Field(default='-')
    accommodation: str = Field(default='-')

    @field_validator(
        'current_city', 'transportation', 'breakfast', 'attraction',
        'lunch', 'dinner', 'accommodation',
        mode='before'
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        if value is None:
            return '-'
        text = str(value).strip()
        return text or '-'

    def to_submission_dict(self) -> dict[str, Any]:
        return {
            'day': self.day,
            'days': self.day,
            'current_city': self.current_city,
            'transportation': self.transportation,
            'breakfast': self.breakfast,
            'attraction': self.attraction,
            'lunch': self.lunch,
            'dinner': self.dinner,
            'accommodation': self.accommodation,
        }


class TravelPlannerItinerary(BaseModel):
    summary: str = Field(default='')
    plan: list[TravelDayPlan] = Field(default_factory=list)

    @field_validator('summary', mode='before')
    @classmethod
    def _coerce_summary(cls, value: Any) -> str:
        return '' if value is None else str(value).strip()
