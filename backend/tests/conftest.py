# backend/tests/conftest.py
#
# TEST DATABASE STRATEGY
# ----------------------
# We use SQLite in-memory for all tests that don't need the full app stack.
# Tests that go through the HTTP layer (TestClient) hit register/login which
# queries the tenants table via the auth service. The auth service has its
# own internal DB connection that bypasses our get_db override.
#
# RESULT: Two tiers of tests:
#   Tier 1 - Unit tests (no DB or SQLite):
#     test_scheduler_engine.py  - pure engine logic, no DB
#     test_conflict_detection.py - pure function, no DB
#     test_alembic_migrations.py - file integrity only, no DB
#
#   Tier 2 - Integration tests (need real PostgreSQL):
#     test_jobs_api.py, test_assignment_service.py
#     These are marked with @pytest.mark.integration and SKIPPED in CI.
#     Run them manually against the real dev DB:
#       pytest tests/ -m integration -v
#
# POSTGRESQL TYPE PATCHING
# PG_ARRAY and JSONB columns are patched to JSON so SQLite can create tables
# for unit tests that use the db fixture.

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.types import JSON
from fastapi.testclient import TestClient


# --- Step 1: Import app.main to register all models with Base ----------------
import app.main as _app_main  # noqa: side effect registers all ORM models

# --- Step 2: Explicitly import models that use PG-only types -----------------
from app.routers.scheduler_router import ScheduleEntryModel  # PG_ARRAY
from app.models.auth import Tenant, User, RefreshToken       # tenants, users
from app.database import Base, get_db
from app.main import app


# --- Step 3: Patch PG-only column types → JSON for SQLite --------------------
def _patch_pg_types_to_json():
    try:
        from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
        from sqlalchemy.dialects.postgresql import JSONB
    except ImportError:
        return

    patched = []
    for tbl_name, tbl in Base.metadata.tables.items():
        for col in tbl.columns:
            if isinstance(col.type, (PG_ARRAY, JSONB)):
                col.type = JSON()
                patched.append("%s.%s" % (tbl_name, col.name))
    if patched:
        print("[conftest] Patched PG->JSON (%d): %s" % (len(patched), ", ".join(patched)))
    else:
        print("[conftest] WARNING: no PG columns found. Tables: %s" % list(Base.metadata.tables.keys()))


_patch_pg_types_to_json()


# --- SQLite engine for unit tests --------------------------------------------
SQLITE_URL = "sqlite:///:memory:"

engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    """Fresh SQLite DB per test. Only for unit tests that don't need auth."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    """
    TestClient with get_db overridden.
    NOTE: Tests that call /auth/register or /auth/login will hit the real DB
    because the auth service bypasses get_db internally. Use only for
    endpoints that don't require tenant creation.
    """
    def _override():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
