# backend/tests/test_jobs_api.py
#
# Integration tests for the jobs API.
#
# REQUIRES: Live PostgreSQL DB (the real dev database).
# All tests are marked @pytest.mark.integration.
#
# Run with:
#   cd backend
#   pytest tests/test_jobs_api.py -v -m integration
#
# These tests are SKIPPED in the normal test run to avoid requiring
# a live DB in CI. They use the real DB with a fresh test tenant.

import pytest


pytestmark = pytest.mark.integration  # skip unless -m integration passed


@pytest.fixture(scope="module")
def live_client():
    """TestClient using the real PostgreSQL DB — no overrides."""
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def live_headers(live_client):
    """Register a unique test tenant and return JWT headers."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    resp = live_client.post("/auth/register", json={
        "company_name": f"Test Co {uid}",
        "slug": f"test-co-{uid}",
        "email": f"test-{uid}@testco.com",
        "password": "test1234",
        "industry_type": "printing",
    })
    assert resp.status_code in (200, 201), f"Register failed: {resp.text}"
    token = resp.json().get("access_token")
    assert token
    return {"Authorization": f"Bearer {token}"}


class TestCreateJob:
    def test_create_job_success(self, live_client, live_headers):
        resp = live_client.post("/api/jobs/", headers=live_headers, json={
            "name": "Print Job A",
            "start_date": "2026-04-13",
            "end_date": "2026-04-20",
            "priority": "High",
            "status": "Draft",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Print Job A"
        assert data["original_start_date"] is None
        assert data["original_end_date"] is None

    def test_create_job_missing_dates(self, live_client, live_headers):
        resp = live_client.post("/api/jobs/", headers=live_headers, json={
            "name": "No Dates"
        })
        assert resp.status_code == 422

    def test_create_job_unauthenticated(self, live_client):
        resp = live_client.post("/api/jobs/", json={
            "name": "Anon", "start_date": "2026-04-13", "end_date": "2026-04-20",
        })
        assert resp.status_code == 401


class TestListJobs:
    def test_list_jobs_returns_created(self, live_client, live_headers):
        live_client.post("/api/jobs/", headers=live_headers, json={
            "name": "List Test Job",
            "start_date": "2026-04-13",
            "end_date": "2026-04-20",
        })
        resp = live_client.get("/api/jobs/", headers=live_headers)
        assert resp.status_code == 200
        names = [j["name"] for j in resp.json()]
        assert "List Test Job" in names

    def test_list_unauthenticated(self, live_client):
        assert live_client.get("/api/jobs/").status_code == 401


class TestUpdateJob:
    def test_update_restores_original_dates(self, live_client, live_headers):
        """Editing a rescheduled job restores original dates."""
        from sqlalchemy.orm import Session
        from sqlalchemy import text
        from app.database import get_db

        create = live_client.post("/api/jobs/", headers=live_headers, json={
            "name": "Rescheduled Job",
            "start_date": "2026-04-13",
            "end_date": "2026-04-20",
        })
        assert create.status_code == 201
        job_id = create.json()["id"]

        # Simulate scheduler moving dates via DB
        db: Session = next(get_db())
        db.execute(text(
            "UPDATE jobs SET end_date='2026-04-28', "
            "original_start_date='2026-04-13', original_end_date='2026-04-20' "
            f"WHERE id={job_id}"
        ))
        db.commit()
        db.close()

        resp = live_client.patch(
            f"/api/jobs/{job_id}", headers=live_headers, json={"notes": "updated"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["end_date"] == "2026-04-20"
        assert data["original_end_date"] is None


class TestTimerTransitions:
    def test_full_timer_cycle(self, live_client, live_headers):
        create = live_client.post("/api/jobs/", headers=live_headers, json={
            "name": "Timer Job",
            "start_date": "2026-04-13",
            "end_date": "2026-04-20",
            "status": "Scheduled",
        })
        job_id = create.json()["id"]
        live_client.post(f"/api/jobs/{job_id}/timer", headers=live_headers, json={"action": "start"})
        live_client.post(f"/api/jobs/{job_id}/timer", headers=live_headers, json={"action": "pause"})
        live_client.post(f"/api/jobs/{job_id}/timer", headers=live_headers, json={"action": "resume"})
        resp = live_client.post(f"/api/jobs/{job_id}/timer", headers=live_headers, json={"action": "end"})
        assert resp.status_code == 200
        assert resp.json()["timer_status"] == "ended"
        assert resp.json()["status"] == "Completed"

    def test_invalid_transition(self, live_client, live_headers):
        create = live_client.post("/api/jobs/", headers=live_headers, json={
            "name": "Invalid Timer", "start_date": "2026-04-13", "end_date": "2026-04-20",
        })
        job_id = create.json()["id"]
        resp = live_client.post(
            f"/api/jobs/{job_id}/timer", headers=live_headers, json={"action": "pause"}
        )
        assert resp.status_code == 400
