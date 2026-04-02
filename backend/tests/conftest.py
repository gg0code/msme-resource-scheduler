"""
tests/conftest.py
-----------------
Pytest configuration and shared fixtures for the ZetaOps Copilot test suite.
Sets up a separate test database, creates all tables before the session starts,
and wraps each test in a rolled-back transaction so tests are isolated.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

TEST_DATABASE_URL = "postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler_test"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Creates all tables once before tests, drops them after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """Provides a DB session wrapped in a savepoint, rolled back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """FastAPI TestClient wired to the test DB session."""
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """
    Creates a test tenant + user, logs in, and returns Authorization headers.
    Used by any test that calls an authenticated endpoint.
    """
    # Register a test tenant
    reg_resp = client.post("/auth/register", json={
        "company_name": "Test Co",
        "slug": "test-co-pytest",
        "industry_type": "printing",
        "email": "pytest@testco.com",
        "password": "testpass123",
        "role": "proprietor",
    })
    # Login (works whether register succeeded or user already exists)
    login_resp = client.post("/auth/login", json={
        "email": "pytest@testco.com",
        "password": "testpass123",
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
