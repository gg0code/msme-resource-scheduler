# tests/test_machines.py
# SRS §6.3 Machine / Work Center Master Data + §6.19 source field

import pytest
from app.models.employee import VALID_SOURCE_VALUES


class TestMachineCRUD:

    def _make(self, client, auth_headers, name="Press 1", **extra):
        payload = {"name": name, "machine_type": "Offset Press",
                   "base_availability_pct": 100.0, "status": "Operational", **extra}
        return client.post("/api/machines/", json=payload, headers=auth_headers)

    def test_create_machine_returns_201(self, client, auth_headers):
        r = self._make(client, auth_headers)
        assert r.status_code == 201
        assert r.json()["name"] == "Press 1"
        assert r.json()["id"] is not None

    def test_create_machine_second(self, client, auth_headers):
        r = self._make(client, auth_headers, name="Press 2")
        assert r.status_code == 201
        assert r.json()["name"] == "Press 2"

    def test_list_machines_returns_own_tenant(self, client, auth_headers):
        self._make(client, auth_headers, name="Machine A")
        self._make(client, auth_headers, name="Machine B")
        r = client.get("/api/machines/", headers=auth_headers)
        assert r.status_code == 200
        names = [m["name"] for m in r.json()]
        assert "Machine A" in names
        assert "Machine B" in names

    def test_get_machine_by_id(self, client, auth_headers):
        r = self._make(client, auth_headers, name="CNC-01")
        mid = r.json()["id"]
        r2 = client.get(f"/api/machines/{mid}", headers=auth_headers)
        assert r2.status_code == 200
        assert r2.json()["name"] == "CNC-01"

    def test_get_machine_wrong_id_returns_404(self, client, auth_headers):
        r = client.get("/api/machines/999999", headers=auth_headers)
        assert r.status_code == 404

    def test_delete_machine_returns_204(self, client, auth_headers):
        r = self._make(client, auth_headers, name="Temp Machine")
        mid = r.json()["id"]
        r2 = client.delete(f"/api/machines/{mid}", headers=auth_headers)
        assert r2.status_code == 204

    def test_unauthenticated_list_returns_401(self, client):
        r = client.get("/api/machines/")
        assert r.status_code == 401

    def test_unauthenticated_create_returns_401(self, client):
        r = client.post("/api/machines/", json={"name": "Ghost", "base_availability_pct": 100.0})
        assert r.status_code == 401


class TestMachineSourceField:

    def _make(self, client, auth_headers, name="M", **extra):
        payload = {"name": name, "machine_type": "Press",
                   "base_availability_pct": 100.0, "status": "Operational", **extra}
        return client.post("/api/machines/", json=payload, headers=auth_headers)

    def test_source_defaults_to_manual(self, client, auth_headers):
        r = self._make(client, auth_headers, name="DefaultSrc")
        assert r.status_code == 201
        assert r.json()["source"] == "manual"

    def test_source_can_be_whatsapp(self, client, auth_headers):
        r = self._make(client, auth_headers, name="WA Machine", source="whatsapp")
        assert r.status_code == 201
        assert r.json()["source"] == "whatsapp"

    def test_source_can_be_erp_sync(self, client, auth_headers):
        r = self._make(client, auth_headers, name="ERP Machine", source="erp_sync")
        assert r.status_code == 201
        assert r.json()["source"] == "erp_sync"

    def test_source_present_in_list(self, client, auth_headers):
        self._make(client, auth_headers, name="ListCheck")
        r = client.get("/api/machines/", headers=auth_headers)
        assert r.status_code == 200
        assert "source" in r.json()[0]

    def test_valid_source_values_shared_constant(self):
        assert "manual" in VALID_SOURCE_VALUES
        assert "whatsapp" in VALID_SOURCE_VALUES
        assert "erp_sync" in VALID_SOURCE_VALUES
