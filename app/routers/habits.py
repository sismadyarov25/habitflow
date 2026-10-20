from __future__ import annotations

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.habit import (
    HabitCheckInRequest,
    HabitCreate,
    HabitLogResponse,
    HabitToggleResponse,
    HabitUpdate,
    HabitWithStatsResponse,
)
from app.services import habit_service

router = APIRouter(prefix="/api/habits", tags=["Habits"])


@router.get("", response_model=List[HabitWithStatsResponse])
def get_habits(
    active_only: bool = Query(default=False, description="Только активные привычки"),
    reference_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[HabitWithStatsResponse]:
    return habit_service.list_habits(db, active_only=active_only, reference_date=reference_date)


@router.post("", response_model=HabitWithStatsResponse, status_code=status.HTTP_201_CREATED)
def create_habit(
    payload: HabitCreate,
    db: Session = Depends(get_db),
) -> HabitWithStatsResponse:
    return habit_service.create_habit(db, payload)


@router.get("/{habit_id}", response_model=HabitWithStatsResponse)
def get_habit(
    habit_id: int,
    reference_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> HabitWithStatsResponse:
    habit = habit_service.get_habit_or_404(db, habit_id)
    return habit_service.serialize_habit_with_stats(habit, reference_date=reference_date)


@router.put("/{habit_id}", response_model=HabitWithStatsResponse)
def update_habit(
    habit_id: int,
    payload: HabitUpdate,
    db: Session = Depends(get_db),
) -> HabitWithStatsResponse:
    return habit_service.update_habit(db, habit_id, payload)


@router.delete("/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(
    habit_id: int,
    db: Session = Depends(get_db),
) -> Response:
    habit_service.delete_habit(db, habit_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{habit_id}/checkins",
    response_model=HabitLogResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_checkin(
    habit_id: int,
    payload: HabitCheckInRequest,
    db: Session = Depends(get_db),
) -> HabitLogResponse:
    """Strictly create a check-in for a date; returns 409 if already checked in on that date."""
    log_entry = habit_service.create_habit_checkin_strict(
        db,
        habit_id=habit_id,
        completed_date=payload.completed_date,
        note=payload.note,
    )
    return HabitLogResponse.model_validate(log_entry)


@router.post("/{habit_id}/toggle", response_model=HabitToggleResponse)
def toggle_checkin(
    habit_id: int,
    payload: HabitCheckInRequest,
    db: Session = Depends(get_db),
) -> HabitToggleResponse:
    """Toggle habit completion for a given date (check / uncheck) and return updated streaks."""
    return habit_service.toggle_habit_checkin(
        db,
        habit_id=habit_id,
        completed_date=payload.completed_date,
        note=payload.note,
    )
