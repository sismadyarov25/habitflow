from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator

from app.schemas.habit import HabitWithStatsResponse
from app.schemas.task import TaskResponse


class CalendarDaySummary(BaseModel):
    date: date
    day_number: int
    is_today: bool
    is_future: bool
    completed_habit_ids: List[int]
    completed_count: int
    total_active_habits: int
    completion_rate: float


class MonthlyCalendarResponse(BaseModel):
    year: int
    month: int
    month_name: str
    first_weekday: int  # 0 = Monday, 6 = Sunday
    days_in_month: int
    habits: List[HabitWithStatsResponse]
    days: List[CalendarDaySummary]
    month_completion_rate: float
    total_checkins_in_month: int


class DailyTrendPoint(BaseModel):
    date: date
    label: str
    habits_completed: int
    habits_total: int
    habit_rate: float
    tasks_completed: int


class PeriodStats(BaseModel):
    period_days: int
    start_date: date
    end_date: date
    habit_completion_rate: float
    total_habit_checkins: int
    possible_habit_checkins: int
    tasks_completed: int
    tasks_created: int
    tasks_pending: int
    tasks_overdue: int
    high_priority_done: int
    best_habit_name: Optional[str] = None
    best_habit_streak: int = 0
    daily_trend: List[DailyTrendPoint]


class AnalyticsSummaryResponse(BaseModel):
    reference_date: date
    weekly: PeriodStats
    monthly: PeriodStats
    tasks_by_priority: Dict[str, int]
    tasks_by_status: Dict[str, int]
    top_streaks: List[HabitWithStatsResponse]
    productivity_score: int


class DashboardResponse(BaseModel):
    today: date
    habits_today: List[HabitWithStatsResponse]
    habits_completed_today: int
    habits_total_today: int
    habits_progress_percent: float
    tasks_today: List[TaskResponse]
    tasks_overdue: List[TaskResponse]
    tasks_upcoming: List[TaskResponse]
    tasks_done_today_count: int
    active_streaks_max: int
    productivity_score: int


class ProWaitlistCreate(BaseModel):
    contact: str = Field(..., min_length=3, max_length=160, description="Email или Telegram")
    desired_feature: Optional[str] = Field(default="Расширенная аналитика и отчёты", max_length=100)
    comment: Optional[str] = Field(default=None, max_length=500)

    @field_validator("contact")
    @classmethod
    def validate_contact(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Укажите корректный Email или @username в Telegram")
        return cleaned


class ProWaitlistResponse(BaseModel):
    id: int
    contact: str
    desired_feature: Optional[str] = None
    created_at: datetime
    message: str
