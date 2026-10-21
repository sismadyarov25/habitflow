from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.auth import (
    SESSION_COOKIE_NAME,
    check_rate_limit,
    clear_failed_logins,
    create_session_token,
    get_session_from_request,
    record_failed_login,
    require_owner_api,
    verify_owner_credentials,
)
from app.config import get_owner_today, get_settings

router = APIRouter(tags=["Authentication"])

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class OwnerLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=256)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    session = get_session_from_request(request)
    if session:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    settings = get_settings()
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "app_name": settings.app_name,
            "default_username": settings.owner_username,
        },
    )


@router.post("/api/auth/login")
def login_owner(
    payload: OwnerLoginRequest,
    request: Request,
    response: Response,
) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(client_ip)

    if not verify_owner_credentials(payload.username, payload.password):
        record_failed_login(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль владельца",
        )

    clear_failed_logins(client_ip)
    settings = get_settings()
    token = create_session_token(username=settings.owner_username)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.use_secure_cookies,
        path="/",
    )

    from app.auth import verify_session_token

    parsed = verify_session_token(token) or {}
    return {
        "authenticated": True,
        "owner": settings.owner_username,
        "csrf_token": parsed.get("csrf", ""),
        "timezone": settings.owner_timezone,
        "today": get_owner_today().isoformat(),
    }


@router.post("/api/auth/logout")
def logout_owner(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.use_secure_cookies,
    )
    return {"authenticated": False, "message": "Вы вышли из системы"}


@router.get("/api/auth/me")
def get_current_owner_info(request: Request) -> dict:
    session = require_owner_api(request)
    settings = get_settings()
    return {
        "authenticated": True,
        "owner": session.get("sub"),
        "csrf_token": session.get("csrf"),
        "timezone": settings.owner_timezone,
        "today": get_owner_today().isoformat(),
    }
