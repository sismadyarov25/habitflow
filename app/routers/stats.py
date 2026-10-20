from __future__ import annotations

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.stats import (
    AnalyticsSummaryResponse,
    DashboardResponse,
    MonthlyCalendarResponse,
    ProWaitlistCreate,
    ProWaitlistResponse,
)
from app.services import stats_service

router = APIRouter(prefix="/api/stats", tags=["Statistics & Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    reference_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> DashboardResponse:
    return stats_service.get_dashboard_data(db, reference_date=reference_date)


@router.get("/calendar", response_model=MonthlyCalendarResponse)
def get_calendar(
    year: Optional[int] = Query(default=None, ge=2000, le=2100),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    reference_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> MonthlyCalendarResponse:
    today = reference_date or date.today()
    target_year = year or today.year
    target_month = month or today.month
    return stats_service.get_monthly_calendar(
        db,
        year=target_year,
        month=target_month,
        reference_date=today,
    )


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_summary(
    reference_date: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
) -> AnalyticsSummaryResponse:
    return stats_service.get_analytics_summary(db, reference_date=reference_date)


@router.post("/seed")
def seed_demo(
    db: Session = Depends(get_db),
) -> dict:
    return stats_service.seed_demo_data(db)


@router.post(
    "/waitlist",
    response_model=ProWaitlistResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_pro_waitlist(
    payload: ProWaitlistCreate,
    db: Session = Depends(get_db),
) -> ProWaitlistResponse:
    return stats_service.register_pro_waitlist(db, payload)
