"""
tests/conftest.py
-----------------
Pytest configuration and shared fixtures for the ZetaOps Copilot test suite.
Sets up a separate test database, creates all tables before the session starts,
and wraps each test in a rolled-back transaction so tests are isolated.
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models.auth import Tenant, User

# Use env var if set, otherwise fall back to local test DB
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler_test"
)

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Session-scoped fixture that creates all tables once before any tests run,
    then drops them all after the entire test session completes.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """
    Function-scoped fixture that provides a DB session wrapped in a savepoint.
    The transaction is rolled back after each test, keeping the DB clean.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db):
    """
    Function-scoped fixture that provides a FastAPI TestClient wired to the test DB.
    Overrides the get_db dependency so all API requests use the rolled-back session.
    """
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(db):
    """
    Function-scoped fixture that creates a test tenant + proprietor user,
    generates a valid JWT access token, and returns Authorization headers.

    Use in any test that calls a protected endpoint:
        def test_something(client, auth_headers):
            resp = client.get("/api/skills/", headers=auth_headers)

    The tenant and user are rolled back with the rest of the transaction
    after the test completes — no cleanup needed.
    """
    # Create test tenant
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        plan="free",
        industry_type="printing",
    )
    db.add(tenant)
    db.flush()

    # Create proprietor user (highest role — can call all endpoints)
    user = User(
        tenant_id=tenant.id,
        email="test@zetaops.io",
        hashed_password=hash_password("testpassword"),
        role="proprietor",
        is_active=True,
    )
    db.add(user)
    db.flush()

    # Generate JWT token
    token = create_access_token(
        user_id=user.id,
        tenant_id=tenant.id,
        role=user.role,
    )

    return {"Authorization": f"Bearer {token}"}
