from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Habit(Base):
    """Represents a recurring user habit."""

    __tablename__ = "habits"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(20), nullable=False, default="#4F46E5")
    icon = Column(String(32), nullable=False, default="✨")
    target_days_per_week = Column(Integer, nullable=False, default=7)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    logs = relationship(
        "HabitLog",
        back_populates="habit",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class HabitLog(Base):
    """Represents a single completion check-in for a habit on a specific date.

    Enforces a strict database-level unique constraint on (habit_id, completed_date)
    so a habit can never be logged twice on the same calendar day.
    """

    __tablename__ = "habit_logs"
    __table_args__ = (
        UniqueConstraint("habit_id", "completed_date", name="uq_habit_completed_date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    habit_id = Column(
        Integer,
        ForeignKey("habits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    completed_date = Column(Date, nullable=False, index=True)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    habit = relationship("Habit", back_populates="logs")
