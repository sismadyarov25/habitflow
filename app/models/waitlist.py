from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class ProWaitlist(Base):
    """Stores early-access signups for the HabitFlow Pro subscription (Fake Door validation)."""

    __tablename__ = "pro_waitlist"

    id = Column(Integer, primary_key=True, index=True)
    contact = Column(String(160), nullable=False, unique=True, index=True)
    desired_feature = Column(String(100), nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
