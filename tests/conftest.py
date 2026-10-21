from __future__ import annotations

from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import clear_failed_logins
from app.config import get_settings
from app.database import Base, get_db
from app.main import app


TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
    future=True,
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_fk(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    future=True,
)


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    """Create fresh tables before each test and drop them afterwards."""
    clear_failed_logins("testclient")
    clear_failed_logins("unknown")
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def anon_client(db_session: Session) -> Generator[TestClient, None, None]:
    """Unauthenticated TestClient to verify access control on private routes."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Authenticated owner TestClient with automatic CSRF header injection."""
    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    settings = get_settings()
    with TestClient(app) as test_client:
        login_res = test_client.post(
            "/api/auth/login",
            json={
                "username": settings.owner_username,
                "password": settings.owner_password or "habitflow-dev-pass",
            },
        )
        assert login_res.status_code == 200, login_res.text
        csrf_token = login_res.json()["csrf_token"]
        test_client.headers.update({"X-CSRF-Token": csrf_token})
        yield test_client
    app.dependency_overrides.clear()
