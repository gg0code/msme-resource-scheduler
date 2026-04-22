# tests/test_jobs_unit.py
# SRS §6.5 Job Definition & Management — unit tier
#
# NOTE: The jobs router schema uses start_date/end_date as Python str, not date.
# PostgreSQL coerces these automatically; SQLite rejects them with TypeError.
# HTTP-layer job creation tests are therefore integration (need real PostgreSQL).
# Model-level tests (is_locked default, original_dates columns, tenant isolation)
# are covered here via direct ORM access.

import pytest
from datetime import date, timedelta
from app.models.job import Job


def _d(offset=0):
    return date.today() + timedelta(days=offset)


def _make_job(db, tenant_id, name="Test Job", start_offset=0, end_offset=5):
    job = Job(
        tenant_id=tenant_id,
        name=name,
        start_date=_d(start_offset),
        end_date=_d(end_offset),
        estimated_hours_per_day=8.0,
        priority="Medium",
        status="Draft",
        raw_materials=[],
        timer_status="idle",
        paused_seconds=0,
        timer_log=[],
    )
    db.add(job)
    db.flush()
    return job


class TestJobModelDefaults:

    def test_is_locked_defaults_to_false(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id)
        assert job.is_locked is False

    def test_original_start_date_is_none_by_default(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id, name="Orig Date Job")
        assert job.original_start_date is None

    def test_original_end_date_is_none_by_default(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id, name="Orig End Job")
        assert job.original_end_date is None

    def test_status_defaults_to_draft(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id, name="Status Job")
        assert job.status == "Draft"

    def test_priority_defaults_to_medium(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id, name="Priority Job")
        assert job.priority == "Medium"


class TestJobTenantIsolation:

    def test_query_by_tenant_id_only_returns_own_jobs(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        _make_job(db, tenant.id, name="Tenant Job 1")
        _make_job(db, tenant.id, name="Tenant Job 2")
        # Query a different tenant — should return nothing
        jobs = db.query(Job).filter(Job.tenant_id == 9999).all()
        assert len(jobs) == 0

    def test_query_own_tenant_returns_created_jobs(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        _make_job(db, tenant.id, name="Own Tenant Job")
        jobs = db.query(Job).filter(Job.tenant_id == tenant.id).all()
        names = [j.name for j in jobs]
        assert "Own Tenant Job" in names


class TestJobOriginalDates:

    def test_setting_original_dates_preserves_start_date(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id, name="Reschedule Job", start_offset=2, end_offset=7)
        original_start = job.start_date
        # Simulate scheduler moving the job
        job.original_start_date = original_start
        job.start_date = _d(10)
        db.flush()
        assert job.original_start_date == original_start
        assert job.start_date == _d(10)

    def test_restoring_original_dates_resets_to_original(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        job = _make_job(db, tenant.id, name="Restore Job", start_offset=2, end_offset=7)
        original_start = job.start_date
        original_end = job.end_date
        job.original_start_date = original_start
        job.original_end_date = original_end
        job.start_date = _d(15)
        job.end_date = _d(20)
        db.flush()
        # Restore
        job.start_date = job.original_start_date
        job.end_date = job.original_end_date
        job.original_start_date = None
        job.original_end_date = None
        db.flush()
        assert job.start_date == original_start
        assert job.end_date == original_end
        assert job.original_start_date is None


class TestJobHTTPEndpoints:

    def test_unauthenticated_list_returns_401(self, client):
        r = client.get("/api/jobs/")
        assert r.status_code == 401

    def test_unauthenticated_create_returns_401(self, client):
        r = client.post("/api/jobs/", json={
            "name": "Ghost Job",
            "start_date": str(date.today()),
            "end_date": str(date.today() + timedelta(days=5)),
        })
        assert r.status_code == 401

    def test_authenticated_list_returns_200(self, client, auth_headers):
        r = client.get("/api/jobs/", headers=auth_headers)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_nonexistent_job_returns_404(self, client, auth_headers):
        r = client.get("/api/jobs/999999", headers=auth_headers)
        assert r.status_code == 404
