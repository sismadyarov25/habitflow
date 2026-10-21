from __future__ import annotations

import re
from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_owner_today

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class HabitBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, description="Название привычки")
    description: Optional[str] = Field(default=None, max_length=500)
    color: str = Field(default="#4F46E5", description="HEX-цвет привычки")
    icon: str = Field(default="✨", min_length=1, max_length=32)
    target_days_per_week: int = Field(default=7, ge=1, le=7)
    is_active: bool = Field(default=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Название привычки не может быть пустым")
        return cleaned

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: str) -> str:
        cleaned = v.strip()
        if not HEX_COLOR_RE.match(cleaned):
            raise ValueError("Цвет должен быть в формате HEX, например #4F46E5")
        return cleaned.upper()


class HabitCreate(HabitBase):
    pass


class HabitUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=500)
    color: Optional[str] = Field(default=None)
    icon: Optional[str] = Field(default=None, min_length=1, max_length=32)
    target_days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    is_active: Optional[bool] = Field(default=None)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Название привычки не может быть пустым")
            return cleaned
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not HEX_COLOR_RE.match(cleaned):
                raise ValueError("Цвет должен быть в формате HEX, например #4F46E5")
            return cleaned.upper()
        return v


class HabitCheckInRequest(BaseModel):
    completed_date: date = Field(default_factory=get_owner_today)
    note: Optional[str] = Field(default=None, max_length=255)


class HabitLogResponse(BaseModel):
    id: int
    habit_id: int
    completed_date: date
    note: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HabitWithStatsResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    color: str
    icon: str
    target_days_per_week: int
    is_active: bool
    created_at: datetime
    completed_today: bool = False
    current_streak: int = 0
    best_streak: int = 0
    total_completions: int = 0
    completed_dates_recent: List[date] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class HabitToggleResponse(BaseModel):
    habit_id: int
    completed_date: date
    completed: bool
    current_streak: int
    best_streak: int
    total_completions: int
