from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Date, DateTime, Integer, String, Text

from app.database import Base


class Task(Base):
    """Represents a daily or deadline-driven task with priority and status."""

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True, index=True)
    priority = Column(String(16), nullable=False, default="medium", index=True)  # low | medium | high
    status = Column(String(20), nullable=False, default="todo", index=True)  # todo | in_progress | done
    category = Column(String(50), nullable=True, default="Общее")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
