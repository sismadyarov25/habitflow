from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
import sys

# Ensure project root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import Base, SessionLocal, engine
from app.models.habit import Habit, HabitLog
from app.models.task import Task
from app.models.waitlist import ProWaitlist


def export_json(output_path: Path) -> None:
    """Export all Habits, HabitLogs, Tasks, and ProWaitlist records to a portable JSON file."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        habits = db.query(Habit).order_by(Habit.id.asc()).all()
        logs = db.query(HabitLog).order_by(HabitLog.id.asc()).all()
        tasks = db.query(Task).order_by(Task.id.asc()).all()
        waitlist = db.query(ProWaitlist).order_by(ProWaitlist.id.asc()).all()

        payload = {
            "exported_at": datetime.utcnow().isoformat(),
            "habits": [
                {
                    "id": h.id,
                    "name": h.name,
                    "description": h.description,
                    "color": h.color,
                    "icon": h.icon,
                    "target_days_per_week": h.target_days_per_week,
                    "is_active": h.is_active,
                    "created_at": h.created_at.isoformat() if h.created_at else None,
                }
                for h in habits
            ],
            "habit_logs": [
                {
                    "id": l.id,
                    "habit_id": l.habit_id,
                    "completed_date": l.completed_date.isoformat(),
                    "note": l.note,
                    "created_at": l.created_at.isoformat() if l.created_at else None,
                }
                for l in logs
            ],
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "description": t.description,
                    "due_date": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "status": t.status,
                    "category": t.category,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                }
                for t in tasks
            ],
            "pro_waitlist": [
                {
                    "id": w.id,
                    "contact": w.contact,
                    "desired_feature": w.desired_feature,
                    "comment": w.comment,
                    "created_at": w.created_at.isoformat() if w.created_at else None,
                }
                for w in waitlist
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"Экспорт завершён: {output_path} "
            f"(привычек: {len(habits)}, отметок: {len(logs)}, задач: {len(tasks)})"
        )
    finally:
        db.close()


def import_json(input_path: Path) -> None:
    """Restore records from a portable JSON backup without duplicating existing records."""
    if not input_path.exists():
        raise SystemExit(f"Файл не найден: {input_path}")

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for h_data in payload.get("habits", []):
            exists = db.query(Habit).filter(Habit.id == h_data["id"]).first()
            if not exists:
                db.add(
                    Habit(
                        id=h_data["id"],
                        name=h_data["name"],
                        description=h_data.get("description"),
                        color=h_data.get("color", "#4F46E5"),
                        icon=h_data.get("icon", "✨"),
                        target_days_per_week=h_data.get("target_days_per_week", 7),
                        is_active=h_data.get("is_active", True),
                    )
                )
        db.flush()

        for l_data in payload.get("habit_logs", []):
            comp_date = date.fromisoformat(l_data["completed_date"])
            exists = (
                db.query(HabitLog)
                .filter(
                    HabitLog.habit_id == l_data["habit_id"],
                    HabitLog.completed_date == comp_date,
                )
                .first()
            )
            if not exists:
                db.add(
                    HabitLog(
                        habit_id=l_data["habit_id"],
                        completed_date=comp_date,
                        note=l_data.get("note"),
                    )
                )

        for t_data in payload.get("tasks", []):
            exists = db.query(Task).filter(Task.id == t_data["id"]).first()
            if not exists:
                due = date.fromisoformat(t_data["due_date"]) if t_data.get("due_date") else None
                db.add(
                    Task(
                        id=t_data["id"],
                        title=t_data["title"],
                        description=t_data.get("description"),
                        due_date=due,
                        priority=t_data.get("priority", "medium"),
                        status=t_data.get("status", "todo"),
                        category=t_data.get("category", "Общее"),
                    )
                )

        db.commit()
        print(f"Импорт из {input_path} успешно завершён.")
    finally:
        db.close()


def backup_sqlite_file(source_db: Path, target_db: Path) -> None:
    """Perform a safe online SQLite backup using sqlite3 backup API."""
    if not source_db.exists():
        raise SystemExit(f"Исходная база SQLite не найдена: {source_db}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(source_db))
    dst = sqlite3.connect(str(target_db))
    with dst:
        src.backup(dst)
    dst.close()
    src.close()
    print(f"Резервная копия SQLite создана: {target_db}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HabitFlow Backup & Restore Utility")
    parser.add_argument("--export-json", type=Path, help="Экспортировать все данные БД в JSON-файл")
    parser.add_argument("--import-json", type=Path, help="Импортировать данные из JSON-файла в текущую БД")
    parser.add_argument("--sqlite-backup", type=Path, help="Создать горячую копию habitflow.db в указанный файл")
    args = parser.parse_args()

    if args.export_json:
        export_json(args.export_json)
    elif args.import_json:
        import_json(args.import_json)
    elif args.sqlite_backup:
        backup_sqlite_file(ROOT_DIR / "habitflow.db", args.sqlite_backup)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
