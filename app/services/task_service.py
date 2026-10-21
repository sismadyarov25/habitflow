from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional
from fastapi import HTTPException, status
from sqlalchemy import case
from sqlalchemy.orm import Session

from app.config import get_owner_today
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate


def serialize_task(task: Task, reference_date: Optional[date] = None) -> TaskResponse:
    """Serialize Task ORM object to TaskResponse with computed overdue flag."""
    ref = reference_date or get_owner_today()
    is_overdue = bool(
        task.due_date is not None
        and task.due_date < ref
        and task.status != "done"
    )
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        due_date=task.due_date,
        priority=task.priority,  # type: ignore[arg-type]
        status=task.status,  # type: ignore[arg-type]
        category=task.category,
        created_at=task.created_at,
        completed_at=task.completed_at,
        is_overdue=is_overdue,
    )


def list_tasks(
    db: Session,
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    due_date_filter: Optional[date] = None,
    reference_date: Optional[date] = None,
) -> List[TaskResponse]:
    """Return tasks ordered by completion state, priority weight, and due date."""
    query = db.query(Task)

    if status_filter:
        query = query.filter(Task.status == status_filter)
    if priority_filter:
        query = query.filter(Task.priority == priority_filter)
    if due_date_filter:
        query = query.filter(Task.due_date == due_date_filter)

    priority_order = case(
        (Task.priority == "high", 1),
        (Task.priority == "medium", 2),
        (Task.priority == "low", 3),
        else_=4,
    )
    status_order = case(
        (Task.status == "in_progress", 1),
        (Task.status == "todo", 2),
        (Task.status == "done", 3),
        else_=4,
    )
    due_nulls_last = case((Task.due_date.is_(None), 1), else_=0)

    tasks = (
        query.order_by(
            status_order.asc(),
            due_nulls_last.asc(),
            Task.due_date.asc(),
            priority_order.asc(),
            Task.id.desc(),
        )
        .all()
    )
    return [serialize_task(t, reference_date=reference_date) for t in tasks]


def get_task_or_404(db: Session, task_id: int) -> Task:
    """Fetch a single task by ID or raise 404."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Задача с ID {task_id} не найдена",
        )
    return task


def create_task(db: Session, payload: TaskCreate) -> TaskResponse:
    """Create a new task."""
    completed_at = datetime.utcnow() if payload.status == "done" else None
    task = Task(
        title=payload.title,
        description=payload.description,
        due_date=payload.due_date,
        priority=payload.priority,
        status=payload.status,
        category=payload.category or "Общее",
        completed_at=completed_at,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def update_task(db: Session, task_id: int, payload: TaskUpdate) -> TaskResponse:
    """Update an existing task and manage its completed_at timestamp."""
    task = get_task_or_404(db, task_id)
    update_data = payload.model_dump(exclude_unset=True)

    if "status" in update_data:
        new_status = update_data["status"]
        if new_status == "done" and task.status != "done":
            task.completed_at = datetime.utcnow()
        elif new_status != "done":
            task.completed_at = None

    for field, value in update_data.items():
        setattr(task, field, value)

    db.commit()
    db.refresh(task)
    return serialize_task(task)


def delete_task(db: Session, task_id: int) -> None:
    """Delete a task by ID."""
    task = get_task_or_404(db, task_id)
    db.delete(task)
    db.commit()
