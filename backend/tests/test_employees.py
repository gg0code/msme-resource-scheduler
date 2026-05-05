# tests/test_employees.py
# SRS §6.2 Employee / Operator Master Data + §6.19 Day 1 source/worker_type
# All tests use SQLite StaticPool via conftest.py fixtures.

import pytest
from app.models.employee import Employee, VALID_SOURCE_VALUES, VALID_WORKER_TYPE_VALUES


# ---------------------------------------------------------------------------
# §6.2 CRUD
# ---------------------------------------------------------------------------

class TestEmployeeCRUD:

    def test_create_employee_returns_201(self, client, auth_headers):
        payload = {
            "full_name": "Ravi Kumar",
            "employment_type": "Full-time",
            "base_availability_pct": 100.0,
            "status": "Active",
        }
        r = client.post("/api/employees/", json=payload, headers=auth_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["full_name"] == "Ravi Kumar"
        assert data["id"] is not None

    def test_create_employee_second_worker(self, client, auth_headers):
        payload = {"full_name": "Meena Sharma", "employment_type": "Full-time",
                   "base_availability_pct": 100.0, "status": "Active"}
        r = client.post("/api/employees/", json=payload, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["full_name"] == "Meena Sharma"

    def test_list_employees_returns_own_tenant(self, client, auth_headers):
        for name in ["Worker A", "Worker B"]:
            client.post("/api/employees/", json={
                "full_name": name, "employment_type": "Full-time",
                "base_availability_pct": 100.0, "status": "Active"
            }, headers=auth_headers)
        r = client.get("/api/employees/", headers=auth_headers)
        assert r.status_code == 200
        names = [e["full_name"] for e in r.json()]
        assert "Worker A" in names
        assert "Worker B" in names

    def test_get_employee_by_id(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Suresh Das", "employment_type": "Full-time",
            "base_availability_pct": 80.0, "status": "Active"
        }, headers=auth_headers)
        emp_id = r.json()["id"]
        r2 = client.get(f"/api/employees/{emp_id}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["full_name"] == "Suresh Das"

    def test_get_employee_wrong_id_returns_404(self, client, auth_headers):
        r = client.get("/api/employees/999999", headers=auth_headers)
        assert r.status_code == 404

    def test_update_employee_changes_field(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Ajay Singh", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        emp_id = r.json()["id"]
        r2 = client.patch(f"/api/employees/{emp_id}",
                          json={"base_availability_pct": 75.0},
                          headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["base_availability_pct"] == 75.0

    def test_delete_employee_returns_204(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Temp Worker", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        emp_id = r.json()["id"]
        r2 = client.delete(f"/api/employees/{emp_id}", headers=auth_headers)
        assert r2.status_code == 204

    def test_unauthenticated_list_returns_401(self, client):
        r = client.get("/api/employees/")
        assert r.status_code == 401

    def test_unauthenticated_create_returns_401(self, client):
        r = client.post("/api/employees/", json={
            "full_name": "Ghost", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        })
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# §6.19 source field (migration 023)
# ---------------------------------------------------------------------------

class TestEmployeeSourceField:

    def test_source_defaults_to_manual(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Default Source", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["source"] == "manual"

    def test_source_can_be_set_to_whatsapp(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "WA Employee", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active",
            "source": "whatsapp"
        }, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["source"] == "whatsapp"

    def test_source_can_be_set_to_erp_sync(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "ERP Employee", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active",
            "source": "erp_sync"
        }, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["source"] == "erp_sync"

    def test_source_present_in_list_response(self, client, auth_headers):
        client.post("/api/employees/", json={
            "full_name": "Source Check", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        r = client.get("/api/employees/", headers=auth_headers)
        assert r.status_code == 200
        assert "source" in r.json()[0]

    def test_valid_source_values_constant(self):
        assert "manual" in VALID_SOURCE_VALUES
        assert "whatsapp" in VALID_SOURCE_VALUES
        # v6.3.15 added 'whatsapp_inferred' for the candidate-promotion job.
        assert "whatsapp_inferred" in VALID_SOURCE_VALUES
        assert "erp_sync" in VALID_SOURCE_VALUES
        assert len(VALID_SOURCE_VALUES) == 4


# ---------------------------------------------------------------------------
# §6.19 worker_type field (migration 023)
# ---------------------------------------------------------------------------

class TestEmployeeWorkerTypeField:

    def test_worker_type_defaults_to_permanent(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Perm Worker", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["worker_type"] == "permanent"

    def test_worker_type_can_be_contractor(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Contractor X", "employment_type": "Contract",
            "base_availability_pct": 100.0, "status": "Active",
            "worker_type": "contractor"
        }, headers=auth_headers)
        assert r.status_code == 201
        assert r.json()["worker_type"] == "contractor"

    def test_worker_type_present_in_response(self, client, auth_headers):
        r = client.post("/api/employees/", json={
            "full_name": "Type Check", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        assert "worker_type" in r.json()

    def test_valid_worker_type_values_constant(self):
        assert "permanent" in VALID_WORKER_TYPE_VALUES
        assert "contractor" in VALID_WORKER_TYPE_VALUES
        assert len(VALID_WORKER_TYPE_VALUES) == 2

    def test_worker_type_present_in_list_response(self, client, auth_headers):
        client.post("/api/employees/", json={
            "full_name": "List Type", "employment_type": "Full-time",
            "base_availability_pct": 100.0, "status": "Active"
        }, headers=auth_headers)
        r = client.get("/api/employees/", headers=auth_headers)
        assert "worker_type" in r.json()[0]
