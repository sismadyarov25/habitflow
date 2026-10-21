from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.orm import Session, joinedload

from app.config import get_owner_today
from app.models.habit import Habit, HabitLog
from app.models.task import Task
from app.models.waitlist import ProWaitlist
from app.schemas.stats import (
    AnalyticsSummaryResponse,
    CalendarDaySummary,
    DailyTrendPoint,
    DashboardResponse,
    MonthlyCalendarResponse,
    PeriodStats,
    ProWaitlistCreate,
    ProWaitlistResponse,
)
from app.services.habit_service import list_habits, serialize_habit_with_stats
from app.services.task_service import serialize_task

RU_MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def get_monthly_calendar(
    db: Session,
    year: int,
    month: int,
    reference_date: Optional[date] = None,
) -> MonthlyCalendarResponse:
    """Build a full monthly habit calendar with daily completion rates."""
    ref = reference_date or get_owner_today()
    first_weekday, days_in_month = calendar.monthrange(year, month)
    start_day = date(year, month, 1)
    end_day = date(year, month, days_in_month)

    active_habits_orm = (
        db.query(Habit)
        .options(joinedload(Habit.logs))
        .filter(Habit.is_active.is_(True))
        .order_by(Habit.id.asc())
        .all()
    )
    habits_serialized = [
        serialize_habit_with_stats(h, reference_date=ref) for h in active_habits_orm
    ]
    total_active = len(habits_serialized)

    logs_in_month = (
        db.query(HabitLog)
        .join(Habit, Habit.id == HabitLog.habit_id)
        .filter(
            Habit.is_active.is_(True),
            HabitLog.completed_date >= start_day,
            HabitLog.completed_date <= end_day,
        )
        .all()
    )

    by_date: Dict[date, List[int]] = {}
    for log in logs_in_month:
        by_date.setdefault(log.completed_date, []).append(log.habit_id)

    days_summary: List[CalendarDaySummary] = []
    elapsed_days_count = 0
    total_checkins = 0

    for day_num in range(1, days_in_month + 1):
        current_d = date(year, month, day_num)
        completed_ids = sorted(by_date.get(current_d, []))
        comp_count = len(completed_ids)
        total_checkins += comp_count
        rate = round((comp_count / total_active) * 100.0, 1) if total_active > 0 else 0.0

        if current_d <= ref:
            elapsed_days_count += 1

        days_summary.append(
            CalendarDaySummary(
                date=current_d,
                day_number=day_num,
                is_today=(current_d == ref),
                is_future=(current_d > ref),
                completed_habit_ids=completed_ids,
                completed_count=comp_count,
                total_active_habits=total_active,
                completion_rate=rate,
            )
        )

    possible_in_elapsed = elapsed_days_count * total_active
    month_rate = (
        round((total_checkins / possible_in_elapsed) * 100.0, 1)
        if possible_in_elapsed > 0
        else 0.0
    )

    return MonthlyCalendarResponse(
        year=year,
        month=month,
        month_name=RU_MONTH_NAMES.get(month, str(month)),
        first_weekday=first_weekday,
        days_in_month=days_in_month,
        habits=habits_serialized,
        days=days_summary,
        month_completion_rate=min(month_rate, 100.0),
        total_checkins_in_month=total_checkins,
    )


def _build_period_stats(
    db: Session,
    days_count: int,
    reference_date: date,
) -> PeriodStats:
    """Compute habit & task metrics for a trailing window of `days_count` days."""
    start_date = reference_date - timedelta(days=days_count - 1)
    active_habits = (
        db.query(Habit)
        .options(joinedload(Habit.logs))
        .filter(Habit.is_active.is_(True))
        .all()
    )
    total_active = len(active_habits)

    logs = (
        db.query(HabitLog)
        .join(Habit, Habit.id == HabitLog.habit_id)
        .filter(
            Habit.is_active.is_(True),
            HabitLog.completed_date >= start_date,
            HabitLog.completed_date <= reference_date,
        )
        .all()
    )

    logs_by_date: Dict[date, int] = {}
    for log in logs:
        logs_by_date[log.completed_date] = logs_by_date.get(log.completed_date, 0) + 1

    all_tasks = db.query(Task).all()

    tasks_completed_in_period = 0
    tasks_created_in_period = 0
    high_priority_done = 0
    tasks_pending = 0
    tasks_overdue = 0
    tasks_done_by_date: Dict[date, int] = {}

    for t in all_tasks:
        created_d = t.created_at.date() if t.created_at else reference_date
        if start_date <= created_d <= reference_date:
            tasks_created_in_period += 1

        if t.status == "done":
            comp_d = t.completed_at.date() if t.completed_at else (t.due_date or created_d)
            if start_date <= comp_d <= reference_date:
                tasks_completed_in_period += 1
                tasks_done_by_date[comp_d] = tasks_done_by_date.get(comp_d, 0) + 1
                if t.priority == "high":
                    high_priority_done += 1
        else:
            tasks_pending += 1
            if t.due_date and t.due_date < reference_date:
                tasks_overdue += 1

    total_checkins = sum(logs_by_date.values())
    possible_checkins = total_active * days_count
    habit_rate = (
        round((total_checkins / possible_checkins) * 100.0, 1)
        if possible_checkins > 0
        else 0.0
    )

    serialized_habits = [
        serialize_habit_with_stats(h, reference_date=reference_date) for h in active_habits
    ]
    best_habit_name: Optional[str] = None
    best_habit_streak = 0
    if serialized_habits:
        top_h = max(serialized_habits, key=lambda item: (item.current_streak, item.best_streak))
        best_habit_name = top_h.name
        best_habit_streak = max(top_h.current_streak, top_h.best_streak)

    daily_trend: List[DailyTrendPoint] = []
    for offset in range(days_count):
        d = start_date + timedelta(days=offset)
        h_comp = logs_by_date.get(d, 0)
        d_rate = round((h_comp / total_active) * 100.0, 1) if total_active > 0 else 0.0
        daily_trend.append(
            DailyTrendPoint(
                date=d,
                label=d.strftime("%d.%m"),
                habits_completed=h_comp,
                habits_total=total_active,
                habit_rate=d_rate,
                tasks_completed=tasks_done_by_date.get(d, 0),
            )
        )

    return PeriodStats(
        period_days=days_count,
        start_date=start_date,
        end_date=reference_date,
        habit_completion_rate=min(habit_rate, 100.0),
        total_habit_checkins=total_checkins,
        possible_habit_checkins=possible_checkins,
        tasks_completed=tasks_completed_in_period,
        tasks_created=tasks_created_in_period,
        tasks_pending=tasks_pending,
        tasks_overdue=tasks_overdue,
        high_priority_done=high_priority_done,
        best_habit_name=best_habit_name,
        best_habit_streak=best_habit_streak,
        daily_trend=daily_trend,
    )


def get_analytics_summary(
    db: Session,
    reference_date: Optional[date] = None,
) -> AnalyticsSummaryResponse:
    """Return comprehensive weekly (7d) and monthly (30d) productivity statistics."""
    ref = reference_date or get_owner_today()
    weekly = _build_period_stats(db, days_count=7, reference_date=ref)
    monthly = _build_period_stats(db, days_count=30, reference_date=ref)

    all_tasks = db.query(Task).all()
    tasks_by_priority = {"high": 0, "medium": 0, "low": 0}
    tasks_by_status = {"todo": 0, "in_progress": 0, "done": 0}
    for t in all_tasks:
        tasks_by_priority[t.priority] = tasks_by_priority.get(t.priority, 0) + 1
        tasks_by_status[t.status] = tasks_by_status.get(t.status, 0) + 1

    habits = list_habits(db, active_only=True, reference_date=ref)
    top_streaks = sorted(
        habits,
        key=lambda h: (h.current_streak, h.best_streak, h.total_completions),
        reverse=True,
    )

    total_tasks_count = len(all_tasks)
    task_done_ratio = (
        (tasks_by_status.get("done", 0) / total_tasks_count) * 100.0
        if total_tasks_count > 0
        else 50.0
    )
    score = int(round(0.6 * weekly.habit_completion_rate + 0.4 * task_done_ratio))
    score = max(0, min(100, score))

    return AnalyticsSummaryResponse(
        reference_date=ref,
        weekly=weekly,
        monthly=monthly,
        tasks_by_priority=tasks_by_priority,
        tasks_by_status=tasks_by_status,
        top_streaks=top_streaks,
        productivity_score=score,
    )


def get_dashboard_data(
    db: Session,
    reference_date: Optional[date] = None,
) -> DashboardResponse:
    """Aggregate today's habits, today's tasks, overdue tasks, and quick score for the main dashboard."""
    ref = reference_date or get_owner_today()
    habits_today = list_habits(db, active_only=True, reference_date=ref)
    habits_total = len(habits_today)
    habits_done = sum(1 for h in habits_today if h.completed_today)
    habits_pct = round((habits_done / habits_total) * 100.0, 1) if habits_total > 0 else 0.0

    all_tasks = db.query(Task).order_by(Task.due_date.asc(), Task.id.desc()).all()
    tasks_today = []
    tasks_overdue = []
    tasks_upcoming = []
    tasks_done_today_count = 0

    for t in all_tasks:
        serialized = serialize_task(t, reference_date=ref)
        if t.status == "done":
            comp_date = t.completed_at.date() if t.completed_at else t.due_date
            if comp_date == ref:
                tasks_done_today_count += 1
            if t.due_date == ref:
                tasks_today.append(serialized)
            continue

        if t.due_date == ref or t.due_date is None:
            tasks_today.append(serialized)
        elif t.due_date < ref:
            tasks_overdue.append(serialized)
        else:
            tasks_upcoming.append(serialized)

    max_streak = max((h.current_streak for h in habits_today), default=0)
    summary = get_analytics_summary(db, reference_date=ref)

    return DashboardResponse(
        today=ref,
        habits_today=habits_today,
        habits_completed_today=habits_done,
        habits_total_today=habits_total,
        habits_progress_percent=habits_pct,
        tasks_today=tasks_today,
        tasks_overdue=tasks_overdue,
        tasks_upcoming=tasks_upcoming[:6],
        tasks_done_today_count=tasks_done_today_count,
        active_streaks_max=max_streak,
        productivity_score=summary.productivity_score,
    )


def register_pro_waitlist(
    db: Session,
    payload: ProWaitlistCreate,
) -> ProWaitlistResponse:
    """Save a user's contact for HabitFlow Pro early access (idempotent if already registered)."""
    existing = (
        db.query(ProWaitlist)
        .filter(ProWaitlist.contact == payload.contact)
        .first()
    )
    if existing:
        existing.desired_feature = payload.desired_feature or existing.desired_feature
        existing.comment = payload.comment or existing.comment
        db.commit()
        db.refresh(existing)
        return ProWaitlistResponse(
            id=existing.id,
            contact=existing.contact,
            desired_feature=existing.desired_feature,
            created_at=existing.created_at,
            message="Вы уже в списке раннего доступа! Мы обновили ваши пожелания.",
        )

    entry = ProWaitlist(
        contact=payload.contact,
        desired_feature=payload.desired_feature,
        comment=payload.comment,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return ProWaitlistResponse(
        id=entry.id,
        contact=entry.contact,
        desired_feature=entry.desired_feature,
        created_at=entry.created_at,
        message="Спасибо! Вы добавлены в список раннего доступа HabitFlow Pro со скидкой 50%.",
    )


def seed_demo_data(db: Session, reference_date: Optional[date] = None) -> dict:
    """Populate realistic demo habits, logs, and tasks if requested by the user."""
    ref = reference_date or get_owner_today()

    if db.query(Habit).count() > 0 or db.query(Task).count() > 0:
        return {"seeded": False, "message": "Данные уже существуют в базе"}

    demo_habits = [
        Habit(
            name="Чтение профильной литературы (25 мин)",
            description="Книги по разработке, продукту или статьи на английском",
            color="#4F46E5",
            icon="📚",
            target_days_per_week=7,
        ),
        Habit(
            name="Тренировка / 8 000 шагов",
            description="Разминка утром или вечерняя прогулка без телефона",
            color="#10B981",
            icon="🏃",
            target_days_per_week=5,
        ),
        Habit(
            name="Фокус-сессия Deep Work (90 мин)",
            description="Работа над главной задачей дня без мессенджеров",
            color="#F59E0B",
            icon="🎯",
            target_days_per_week=6,
        ),
        Habit(
            name="Английский язык (Anki + аудирование)",
            description="Повторение 20 карточек и 1 подкаст",
            color="#EC4899",
            icon="🌍",
            target_days_per_week=7,
        ),
    ]
    db.add_all(demo_habits)
    db.flush()

    # Create streak history over the past 12 days
    patterns = {
        0: [0, 1, 2, 3, 4, 5, 7, 8, 9, 10],  # 6-day current streak (today + last 5 days)
        1: [1, 2, 3, 5, 6, 8, 10],           # 3-day streak ending yesterday
        2: [0, 1, 2, 4, 5, 6, 7],            # 3-day current streak
        3: [0, 2, 3, 4, 6, 7, 9],            # 1-day current streak
    }
    for idx, habit in enumerate(demo_habits):
        for offset in patterns.get(idx, []):
            db.add(
                HabitLog(
                    habit_id=habit.id,
                    completed_date=ref - timedelta(days=offset),
                )
            )

    demo_tasks = [
        Task(
            title="Подготовить презентацию MVP проекта",
            description="Собрать ключевые метрики, скриншоты и план на неделю",
            due_date=ref,
            priority="high",
            status="in_progress",
            category="Стартап",
        ),
        Task(
            title="Разобрать конспект по алгоритмам и структурам данных",
            description="Повторить графы и динамическое программирование",
            due_date=ref,
            priority="medium",
            status="todo",
            category="Учёба",
        ),
        Task(
            title="Отправить резюме и портфолио на 3 стажировки",
            description="Адаптировать сопроводительное письмо под каждую компанию",
            due_date=ref - timedelta(days=1),
            priority="high",
            status="todo",
            category="Карьера",
        ),
        Task(
            title="Настроить рабочее окружение и Git-репозиторий",
            description="Проверить тесты и структуру папок",
            due_date=ref,
            priority="medium",
            status="done",
            category="Разработка",
            completed_at=datetime.utcnow(),
        ),
        Task(
            title="Провести 5 коротких интервью с первыми пользователями",
            description="Узнать, что мешает вести привычки каждый день",
            due_date=ref + timedelta(days=2),
            priority="high",
            status="todo",
            category="Стартап",
        ),
    ]
    db.add_all(demo_tasks)
    db.commit()
    return {"seeded": True, "message": "Демо-данные успешно загружены"}
