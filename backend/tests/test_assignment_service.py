# backend/tests/test_assignment_service.py
#
# Integration tests for the assignments API.
#
# REQUIRES: Live PostgreSQL DB.
# All tests are marked @pytest.mark.integration.
#
# Run with:
#   cd backend
#   pytest tests/test_assignment_service.py -v -m integration
#
# Assignments endpoint: POST /api/assignments/
# Payload: { job_id, employee_ids, machine_ids }
# HTTP method is POST (not PATCH) — returns 201 on success, 409 on conflict.

import pytest
import uuid

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def live_headers(live_client):
    uid = uuid.uuid4().hex[:8]
    resp = live_client.post("/auth/register", json={
        "company_name": f"Assign Test Co {uid}",
        "slug": f"assign-co-{uid}",
        "email": f"assign-{uid}@test.com",
        "password": "test1234",
        "industry_type": "general",
    })
    assert resp.status_code in (200, 201), f"Register failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_job(live_client, live_headers) -> int:
    resp = live_client.post("/api/jobs/", headers=live_headers, json={
        "name": "Assign Test Job",
        "start_date": "2026-04-13",
        "end_date": "2026-04-20",
    })
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_employee(live_client, live_headers, status="Active") -> int:
    resp = live_client.post("/api/employees/", headers=live_headers, json={
        "full_name": f"Worker {uuid.uuid4().hex[:4]}",
        "department": "Production",
        "status": status,
        "base_availability_pct": 100,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_machine(live_client, live_headers, status="Operational") -> int:
    resp = live_client.post("/api/machines/", headers=live_headers, json={
        "name": f"Press {uuid.uuid4().hex[:4]}",
        "machine_type": "Press",
        "status": status,
        "base_availability_pct": 100,
    })
    assert resp.status_code == 201
    return resp.json()["id"]


class TestAssignHappyPath:
    def test_assign_employee_and_machine(self, live_client, live_headers):
        job_id = _make_job(live_client, live_headers)
        emp_id = _make_employee(live_client, live_headers)
        mac_id = _make_machine(live_client, live_headers)
        resp = live_client.post("/api/assignments/", headers=live_headers, json={
            "job_id": job_id,
            "employee_ids": [emp_id],
            "machine_ids": [mac_id],
        })
        assert resp.status_code == 201, f"Assignment failed: {resp.text}"
        assignments = resp.json()["assignments"]
        types = {a["type"] for a in assignments}
        assert "employee" in types
        assert "machine" in types

    def test_unauthenticated_rejected(self, live_client):
        resp = live_client.post("/api/assignments/", json={
            "job_id": 1, "employee_ids": [], "machine_ids": [],
        })
        assert resp.status_code == 401


class TestAssignHardConstraints:
    def test_inactive_employee_rejected(self, live_client, live_headers):
        job_id = _make_job(live_client, live_headers)
        emp_id = _make_employee(live_client, live_headers, status="Inactive")
        resp = live_client.post("/api/assignments/", headers=live_headers, json={
            "job_id": job_id, "employee_ids": [emp_id], "machine_ids": [],
        })
        assert resp.status_code in (400, 409), \
            f"Expected 400/409 for inactive employee, got {resp.status_code}: {resp.text}"

    def test_non_operational_machine_rejected(self, live_client, live_headers):
        job_id = _make_job(live_client, live_headers)
        mac_id = _make_machine(live_client, live_headers, status="Under Maintenance")
        resp = live_client.post("/api/assignments/", headers=live_headers, json={
            "job_id": job_id, "employee_ids": [], "machine_ids": [mac_id],
        })
        assert resp.status_code in (400, 409), \
            f"Expected 400/409 for non-operational machine, got {resp.status_code}: {resp.text}"
