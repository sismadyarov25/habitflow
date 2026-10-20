from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

TaskPriority = Literal["low", "medium", "high"]
TaskStatus = Literal["todo", "in_progress", "done"]


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Название задачи")
    description: Optional[str] = Field(default=None, max_length=1000)
    due_date: Optional[date] = Field(default=None, description="Дедлайн задачи")
    priority: TaskPriority = Field(default="medium")
    status: TaskStatus = Field(default="todo")
    category: Optional[str] = Field(default="Общее", max_length=50)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Название задачи не может быть пустым")
        return cleaned


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    due_date: Optional[date] = Field(default=None)
    priority: Optional[TaskPriority] = Field(default=None)
    status: Optional[TaskStatus] = Field(default=None)
    category: Optional[str] = Field(default=None, max_length=50)

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError("Название задачи не может быть пустым")
            return cleaned
        return v


class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    priority: TaskPriority
    status: TaskStatus
    category: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    is_overdue: bool = False

    model_config = ConfigDict(from_attributes=True)
