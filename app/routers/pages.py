from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth import get_session_from_request
from app.config import get_owner_today, get_settings

router = APIRouter(tags=["Pages"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    session = get_session_from_request(request)
    if not session:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": settings.app_name,
            "free_plan_max_habits": settings.free_plan_max_habits,
            "owner_username": session.get("sub", settings.owner_username),
            "csrf_token": session.get("csrf", ""),
            "owner_timezone": settings.owner_timezone,
            "owner_today": get_owner_today().isoformat(),
        },
    )


@router.get("/health")
def health_check() -> dict:
    """Lightweight health check for cloud load balancers (exposes no private data)."""
    return {"status": "ok", "service": "HabitFlow"}
