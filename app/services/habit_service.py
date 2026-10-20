from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Optional, Set, Tuple
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.habit import Habit, HabitLog
from app.schemas.habit import (
    HabitCreate,
    HabitToggleResponse,
    HabitUpdate,
    HabitWithStatsResponse,
)


def calculate_streaks(
    completed_dates: Iterable[date],
    reference_date: Optional[date] = None,
) -> Tuple[int, int]:
    """Calculate (current_streak, best_streak) from a collection of completed dates.

    Rules:
    - Duplicate dates are ignored.
    - Dates strictly in the future relative to `reference_date` do not inflate current_streak.
    - `current_streak` remains active if the habit was completed on `reference_date` (today)
      OR on `reference_date - 1 day` (yesterday). Otherwise it is 0.
    - `best_streak` is the longest consecutive daily sequence across all recorded dates.
    """
    ref = reference_date or date.today()
    unique_dates: Set[date] = {d for d in completed_dates if d <= ref}
    if not unique_dates:
        return 0, 0

    sorted_dates = sorted(unique_dates)

    # Calculate best streak
    best_streak = 1
    running = 1
    for idx in range(1, len(sorted_dates)):
        if (sorted_dates[idx] - sorted_dates[idx - 1]).days == 1:
            running += 1
            if running > best_streak:
                best_streak = running
        else:
            running = 1

    # Calculate current streak ending at today or yesterday
    yesterday = ref - timedelta(days=1)
    if ref in unique_dates:
        cursor = ref
    elif yesterday in unique_dates:
        cursor = yesterday
    else:
        return 0, best_streak

    current_streak = 0
    while cursor in unique_dates:
        current_streak += 1
        cursor -= timedelta(days=1)

    return current_streak, best_streak


def serialize_habit_with_stats(
    habit: Habit,
    reference_date: Optional[date] = None,
) -> HabitWithStatsResponse:
    """Convert a Habit ORM instance into HabitWithStatsResponse with calculated streaks."""
    ref = reference_date or date.today()
    all_dates = [log.completed_date for log in habit.logs]
    current_streak, best_streak = calculate_streaks(all_dates, reference_date=ref)
    recent_cutoff = ref - timedelta(days=30)
    recent_dates = sorted([d for d in all_dates if recent_cutoff <= d <= ref])

    return HabitWithStatsResponse(
        id=habit.id,
        name=habit.name,
        description=habit.description,
        color=habit.color,
        icon=habit.icon,
        target_days_per_week=habit.target_days_per_week,
        is_active=habit.is_active,
        created_at=habit.created_at,
        completed_today=(ref in all_dates),
        current_streak=current_streak,
        best_streak=best_streak,
        total_completions=len(all_dates),
        completed_dates_recent=recent_dates,
    )


def list_habits(
    db: Session,
    active_only: bool = False,
    reference_date: Optional[date] = None,
) -> List[HabitWithStatsResponse]:
    """List habits ordered by creation time with their streak statistics."""
    query = db.query(Habit).options(joinedload(Habit.logs))
    if active_only:
        query = query.filter(Habit.is_active.is_(True))
    habits = query.order_by(Habit.is_active.desc(), Habit.id.asc()).all()
    return [serialize_habit_with_stats(h, reference_date=reference_date) for h in habits]


def get_habit_or_404(db: Session, habit_id: int) -> Habit:
    """Fetch a single habit with its logs or raise 404."""
    habit = (
        db.query(Habit)
        .options(joinedload(Habit.logs))
        .filter(Habit.id == habit_id)
        .first()
    )
    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Привычка с ID {habit_id} не найдена",
        )
    return habit


def create_habit(db: Session, payload: HabitCreate) -> HabitWithStatsResponse:
    """Create a new habit."""
    habit = Habit(
        name=payload.name,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
        target_days_per_week=payload.target_days_per_week,
        is_active=payload.is_active,
    )
    db.add(habit)
    db.commit()
    db.refresh(habit)
    return serialize_habit_with_stats(habit)


def update_habit(
    db: Session,
    habit_id: int,
    payload: HabitUpdate,
) -> HabitWithStatsResponse:
    """Update an existing habit."""
    habit = get_habit_or_404(db, habit_id)
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(habit, field, value)
    db.commit()
    db.refresh(habit)
    return serialize_habit_with_stats(habit)


def delete_habit(db: Session, habit_id: int) -> None:
    """Delete a habit and all its logs."""
    habit = get_habit_or_404(db, habit_id)
    db.delete(habit)
    db.commit()


def create_habit_checkin_strict(
    db: Session,
    habit_id: int,
    completed_date: date,
    note: Optional[str] = None,
) -> HabitLog:
    """Strictly record a habit completion for a specific date.

    Raises 409 Conflict if the habit is already marked as completed on that date.
    """
    habit = get_habit_or_404(db, habit_id)
    if completed_date > date.today() + timedelta(days=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отмечать выполнение привычки на будущие даты",
        )

    existing = (
        db.query(HabitLog)
        .filter(
            HabitLog.habit_id == habit.id,
            HabitLog.completed_date == completed_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Привычка уже отмечена выполненной за дату {completed_date.isoformat()}",
        )

    log_entry = HabitLog(
        habit_id=habit.id,
        completed_date=completed_date,
        note=note,
    )
    db.add(log_entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Привычка уже отмечена выполненной за дату {completed_date.isoformat()}",
        )
    db.refresh(log_entry)
    return log_entry


def toggle_habit_checkin(
    db: Session,
    habit_id: int,
    completed_date: date,
    note: Optional[str] = None,
    reference_date: Optional[date] = None,
) -> HabitToggleResponse:
    """Idempotent toggle for a habit completion on a given date (check / uncheck)."""
    habit = get_habit_or_404(db, habit_id)
    ref = reference_date or date.today()
    if completed_date > ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя отмечать выполнение привычки на будущие даты",
        )

    existing = (
        db.query(HabitLog)
        .filter(
            HabitLog.habit_id == habit.id,
            HabitLog.completed_date == completed_date,
        )
        .first()
    )

    if existing:
        db.delete(existing)
        db.commit()
        completed = False
    else:
        new_log = HabitLog(
            habit_id=habit.id,
            completed_date=completed_date,
            note=note,
        )
        db.add(new_log)
        try:
            db.commit()
            completed = True
        except IntegrityError:
            db.rollback()
            completed = True

    db.expire(habit)
    refreshed = get_habit_or_404(db, habit_id)
    stats = serialize_habit_with_stats(refreshed, reference_date=ref)

    return HabitToggleResponse(
        habit_id=habit.id,
        completed_date=completed_date,
        completed=completed,
        current_streak=stats.current_streak,
        best_streak=stats.best_streak,
        total_completions=stats.total_completions,
    )
