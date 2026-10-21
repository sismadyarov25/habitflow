from __future__ import annotations

from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.auth import require_owner_api
from app.database import get_db
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services import task_service

router = APIRouter(
    prefix="/api/tasks",
    tags=["Tasks"],
    dependencies=[Depends(require_owner_api)],
)


@router.get("", response_model=List[TaskResponse])
def get_tasks(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    priority_filter: Optional[str] = Query(default=None, alias="priority"),
    due_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> List[TaskResponse]:
    return task_service.list_tasks(
        db,
        status_filter=status_filter,
        priority_filter=priority_filter,
        due_date_filter=due_date,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
) -> TaskResponse:
    return task_service.create_task(db, payload)


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    db: Session = Depends(get_db),
) -> TaskResponse:
    task = task_service.get_task_or_404(db, task_id)
    return task_service.serialize_task(task)


@router.put("/{task_id}", response_model=TaskResponse)
@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> TaskResponse:
    return task_service.update_task(db, task_id, payload)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
) -> Response:
    task_service.delete_task(db, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
