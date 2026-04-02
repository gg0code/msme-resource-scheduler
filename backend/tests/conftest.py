"""
```python
"""
FILE PURPOSE
This file is the pytest configuration and fixture definitions for the ZetaOps Copilot test suite. It exists to provide shared test setup, database isolation, and authentication helpers for all backend tests. This file was introduced in the early v4 development and sits at the foundation of our testing architecture, ensuring every test runs in a clean, isolated environment with proper tenant scoping and authentication. It configures a separate test database and provides fixtures that other test files can use to get authenticated clients and database sessions.

WHAT THIS FILE DOES — step by step
1. Sets up the TEST_DATABASE_URL environment variable with fallback to a local test database
2. Creates a SQLAlchemy engine and session maker specifically for testing
3. Defines a session-scoped fixture that creates all database tables before tests run and drops them after
4. Defines a function-scoped fixture that provides database sessions wrapped in rolled-back transactions
5. Defines a function-scoped fixture that provides a FastAPI TestClient connected to the test database
6. Defines a function-scoped fixture that creates test tenant/user data and returns JWT authentication headers
7. Imports all necessary dependencies for database setup, FastAPI testing, and authentication

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : setup_test_db
Type         : pytest fixture (session-scoped, autouse=True)
Purpose      : Creates all database tables once at the start of the test session and drops them at the end. This fixture runs automatically for every test session and ensures we have a clean database schema. The session scope means it only runs once per pytest execution, not once per test.
Parameters   : None (pytest handles fixture injection)
Returns      : None (yields control to tests, then cleans up)
Calls        : Base.metadata.create_all() and Base.metadata.drop_all() from SQLAlchemy
DB/API       : Creates and drops all tables defined in app.models via SQLAlchemy metadata
Side effects : Creates all database tables in the test database at session start, drops them at session end

Name         : db
Type         : pytest fixture (function-scoped)
Purpose      : Provides a database session for each individual test that is wrapped in a transaction savepoint. The transaction is automatically rolled back after the test completes, ensuring complete test isolation. This is critical for maintaining test independence and preventing test pollution.
Parameters   : None (pytest handles fixture injection)
Returns      : SQLAlchemy Session object connected to the test database
Calls        : TestingSessionLocal() to create session, engine.connect() for connection management
DB/API       : Opens database connection and begins transaction that gets rolled back
Side effects : Opens database connection and transaction, rolls back transaction after test, closes connection

Name         : client
Type         : pytest fixture (function-scoped)
Purpose      : Provides a FastAPI TestClient that routes all database calls through the test database session. It overrides the get_db dependency to use the rolled-back test session instead of the production database. This allows tests to make HTTP requests to the API while staying in the test environment.
Parameters   : db (the database session fixture)
Returns      : FastAPI TestClient configured for testing
Calls        : TestClient() from fastapi.testclient, app.dependency_overrides for dependency injection
DB/API       : All API calls made through this client use the test database via dependency override
Side effects : Overrides the get_db dependency globally, clears overrides after test completes

Name         : auth_headers
Type         : pytest fixture (function-scoped)
Purpose      : Creates a complete test authentication setup including a test tenant and proprietor user, then generates a valid JWT token and returns properly formatted Authorization headers. The proprietor role ensures the test can access all endpoints without role restrictions. This fixture handles all the authentication boilerplate that most API tests need.
Parameters   : db (the database session fixture)
Returns      : Dictionary with "Authorization" key containing "Bearer {token}" value
Calls        : create_access_token() from app.core.security, hash_password() from app.core.security
DB/API       : Creates Tenant and User records in the test database, commits them via db.flush()
Side effects : Creates test tenant with slug "test-tenant" and proprietor user with email "test@zetaops.io", data is rolled back after test

WHO CALLS THIS FILE
- backend/tests/test_*.py files (all test files import fixtures from this conftest.py automatically)
- pytest automatically discovers and loads this file when running tests from the tests/ directory
- Any test function that uses parameters like (client, auth_headers, db) gets these fixtures injected

IMPORTS EXPLAINED
- os: Used to read TEST_DATABASE_URL environment variable with fallback to hardcoded test database URL
- pytest: The testing framework that provides the @pytest.fixture decorator and fixture management
- fastapi.testclient.TestClient: Provides HTTP client for testing FastAPI endpoints without running a server
- sqlalchemy.create_engine: Creates database engine connection specifically for the test database
- sqlalchemy.orm.sessionmaker: Creates session factory for generating database sessions bound to test engine
- app.main.app: The main FastAPI application instance that we test against
- app.database.Base: SQLAlchemy declarative base containing all table metadata for create_all/drop_all
- app.database.get_db: Production database dependency that we override in tests
- app.core.security.create_access_token: Generates JWT tokens for authenticated test requests
- app.core.security.hash_password: Hashes passwords for creating test users
- app.models.auth.Tenant: Tenant model for creating test tenant records
- app.models.auth.User: User model for creating test user records

INTERN NOTES
- Easiest thing to break: Forgetting to use the auth_headers fixture in tests that call protected endpoints - you'll get 401 errors that are confusing to debug
- Non-obvious design decision: We use transaction rollback instead of truncating tables because it's much faster and provides better isolation between tests
- Most common mistake: Creating database records in tests without using the db fixture, or forgetting that the test database URL needs to point to a real PostgreSQL instance
- Design principle implemented: This file implements principle #2 (tenant scoping) by creating test data with proper tenant_id relationships in the auth_headers fixture
- What to check if behaving unexpectedly: Verify TEST_DATABASE_URL points to a real PostgreSQL database that the test user can create/drop tables on, and check that no tests are committing transactions instead of using flush()
- Since this is v4-dev: This file should be stable and any v5-whatsapp specific test fixtures should go in a separate conftest.py or be feature-flagged to avoid merge conflicts
"""
```
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
