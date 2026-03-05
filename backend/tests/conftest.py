"""
tests/conftest.py
-----------------
Pytest configuration and shared fixtures for the MSME Resource Scheduler test suite.
Sets up a separate test database, creates all tables before the session starts, and
wraps each test in a rolled-back transaction so tests are isolated and leave no state.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db

# A dedicated test DB prevents test data from polluting the development database
TEST_DATABASE_URL = "postgresql://msme_user:msme_pass@localhost:5432/msme_scheduler_test"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Session-scoped fixture that creates all tables once before any tests run,
    then drops them all after the entire test session completes.

    Input  : None.
    Output : Yields control to the test session; cleans up tables on teardown.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    """
    Function-scoped fixture that provides a DB session wrapped in a savepoint.
    The transaction is rolled back after each test, keeping the DB clean.

    Input  : None.
    Output : Yields a SQLAlchemy Session; rolls back all changes after the test.
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
    Function-scoped fixture that provides a FastAPI TestClient wired to the test DB session.
    Overrides the `get_db` dependency so all API requests use the rolled-back test session.

    Input  : db fixture (the test session).
    Output : Yields a TestClient instance; clears the dependency override after the test.
    """
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
