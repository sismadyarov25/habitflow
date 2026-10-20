from __future__ import annotations

from datetime import date, timedelta
from fastapi.testclient import TestClient


def test_index_and_health(client: TestClient):
    """Verify HTML frontend and health endpoint respond with 200 OK."""
    res_home = client.get("/")
    assert res_home.status_code == 200
    assert "HabitFlow" in res_home.text

    res_health = client.get("/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "ok"


def test_habit_crud_and_validation(client: TestClient):
    """Test creating, updating, listing, validating, and deleting habits."""
    # 1. Invalid empty name should return 422
    bad_res = client.post("/api/habits", json={"name": "   ", "color": "#4F46E5"})
    assert bad_res.status_code == 422

    # 2. Invalid HEX color should return 422
    bad_color = client.post("/api/habits", json={"name": "Спорт", "color": "red"})
    assert bad_color.status_code == 422

    # 3. Valid habit creation
    create_res = client.post(
        "/api/habits",
        json={
            "name": "Утренняя зарядка",
            "description": "15 минут разминки",
            "color": "#10B981",
            "icon": "🏃",
            "target_days_per_week": 6,
        },
    )
    assert create_res.status_code == 201
    habit = create_res.json()
    habit_id = habit["id"]
    assert habit["name"] == "Утренняя зарядка"
    assert habit["current_streak"] == 0
    assert habit["best_streak"] == 0

    # 4. Update habit
    upd_res = client.put(
        f"/api/habits/{habit_id}",
        json={"name": "Зарядка + растяжка", "target_days_per_week": 7},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["name"] == "Зарядка + растяжка"
    assert upd_res.json()["target_days_per_week"] == 7

    # 5. Delete habit
    del_res = client.delete(f"/api/habits/{habit_id}")
    assert del_res.status_code == 204

    # 6. Verify 404 after deletion
    not_found = client.get(f"/api/habits/{habit_id}")
    assert not_found.status_code == 404


def test_prevent_duplicate_habit_checkin_on_same_date(client: TestClient):
    """Ensure a habit cannot have duplicate completion records for the same date."""
    h_res = client.post("/api/habits", json={"name": "Чтение 20 страниц"})
    habit_id = h_res.json()["id"]
    today_str = date.today().isoformat()

    # First strict check-in succeeds
    first = client.post(
        f"/api/habits/{habit_id}/checkins",
        json={"completed_date": today_str},
    )
    assert first.status_code == 201

    # Second strict check-in on the same date MUST fail with 409 Conflict
    duplicate = client.post(
        f"/api/habits/{habit_id}/checkins",
        json={"completed_date": today_str},
    )
    assert duplicate.status_code == 409

    # Verify total_completions is still 1
    habit_info = client.get(f"/api/habits/{habit_id}").json()
    assert habit_info["total_completions"] == 1


def test_future_date_checkin_rejected(client: TestClient):
    """Ensure users cannot mark habits completed in the future."""
    h_res = client.post("/api/habits", json={"name": "Медитация"})
    habit_id = h_res.json()["id"]
    future_date = (date.today() + timedelta(days=5)).isoformat()

    res = client.post(
        f"/api/habits/{habit_id}/toggle",
        json={"completed_date": future_date},
    )
    assert res.status_code == 400


def test_streak_calculation_and_toggle(client: TestClient):
    """Verify current_streak and best_streak calculation across consecutive and broken days."""
    h_res = client.post("/api/habits", json={"name": "Английский язык"})
    habit_id = h_res.json()["id"]
    today = date.today()

    # Log 3 consecutive days ending today (today, yesterday, 2 days ago)
    # Plus an older 4-day streak separated by a gap
    older_streak_dates = [today - timedelta(days=d) for d in (10, 9, 8, 7)]
    current_streak_dates = [today - timedelta(days=d) for d in (2, 1, 0)]

    for d in older_streak_dates + current_streak_dates:
        r = client.post(
            f"/api/habits/{habit_id}/toggle",
            json={"completed_date": d.isoformat()},
        )
        assert r.status_code == 200

    stats = client.get(f"/api/habits/{habit_id}").json()
    assert stats["current_streak"] == 3
    assert stats["best_streak"] == 4
    assert stats["completed_today"] is True
    assert stats["total_completions"] == 7

    # Toggle today OFF -> current streak should still be 2 (yesterday + 2 days ago)
    uncheck = client.post(
        f"/api/habits/{habit_id}/toggle",
        json={"completed_date": today.isoformat()},
    )
    assert uncheck.status_code == 200
    assert uncheck.json()["completed"] is False
    assert uncheck.json()["current_streak"] == 2


def test_task_crud_priorities_and_overdue(client: TestClient):
    """Test creating tasks, overdue detection, status transitions, and filtering."""
    today = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()

    # Create overdue high-priority task
    t1 = client.post(
        "/api/tasks",
        json={
            "title": "Сдать отчёт по практике",
            "due_date": yesterday,
            "priority": "high",
            "status": "todo",
        },
    )
    assert t1.status_code == 201
    t1_data = t1.json()
    assert t1_data["is_overdue"] is True
    assert t1_data["completed_at"] is None

    # Mark task as done -> is_overdue becomes False and completed_at is populated
    done_res = client.patch(
        f"/api/tasks/{t1_data['id']}",
        json={"status": "done"},
    )
    assert done_res.status_code == 200
    done_data = done_res.json()
    assert done_data["status"] == "done"
    assert done_data["is_overdue"] is False
    assert done_data["completed_at"] is not None

    # Filter tasks by status=done
    list_done = client.get("/api/tasks?status=done")
    assert list_done.status_code == 200
    assert len(list_done.json()) == 1


def test_monthly_calendar_and_analytics_summary(client: TestClient):
    """Verify dashboard, monthly calendar, weekly/monthly stats, and demo seed."""
    seed_res = client.post("/api/stats/seed")
    assert seed_res.status_code == 200
    assert seed_res.json()["seeded"] is True

    # Dashboard
    dash = client.get("/api/stats/dashboard")
    assert dash.status_code == 200
    dash_data = dash.json()
    assert dash_data["habits_total_today"] >= 4
    assert "productivity_score" in dash_data

    # Monthly Calendar
    today = date.today()
    cal = client.get(f"/api/stats/calendar?year={today.year}&month={today.month}")
    assert cal.status_code == 200
    cal_data = cal.json()
    assert cal_data["year"] == today.year
    assert cal_data["month"] == today.month
    assert len(cal_data["days"]) >= 28

    # Weekly & Monthly Analytics
    summary = client.get("/api/stats/summary")
    assert summary.status_code == 200
    sum_data = summary.json()
    assert sum_data["weekly"]["period_days"] == 7
    assert sum_data["monthly"]["period_days"] == 30
    assert len(sum_data["weekly"]["daily_trend"]) == 7
    assert len(sum_data["monthly"]["daily_trend"]) == 30


def test_pro_waitlist_registration(client: TestClient):
    """Verify Fake Door Pro subscription waitlist signup and idempotency."""
    res1 = client.post(
        "/api/stats/waitlist",
        json={"contact": "@student_dev", "desired_feature": "Облачная синхронизация"},
    )
    assert res1.status_code == 201
    assert res1.json()["contact"] == "@student_dev"

    # Second submission with same contact updates gracefully without 500 error
    res2 = client.post(
        "/api/stats/waitlist",
        json={"contact": "@student_dev", "desired_feature": "PDF-отчёты"},
    )
    assert res2.status_code == 201
    assert res2.json()["desired_feature"] == "PDF-отчёты"
