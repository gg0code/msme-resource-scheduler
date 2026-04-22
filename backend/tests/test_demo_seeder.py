# tests/test_demo_seeder.py
# SRS §6.14 Demo Data Seeder (v4.0.6)
#
# BUG FOUND BY AUDIT: demo_seeder.py passes job_type= and quantity= to Job(),
# but the Job ORM model does NOT define these columns (model-schema drift).
# Migration 015 added job_type and quantity to the DB, but the model was never
# updated. The seeder fails with: TypeError: 'job_type' is an invalid keyword
# argument for Job.
# Status: production bug. Do not fix here. Reported in test_audit_report.md.

import pytest
from app.services.demo_seeder import seed_demo_data
from app.models.skill import Skill
from app.models.employee import Employee
from app.models.machine import Machine
from app.models.job import Job


SEED_BUG = pytest.mark.xfail(
    reason="BUG: demo_seeder uses job_type kwarg but Job model lacks the column (model-schema drift, migration 015)",
    strict=True,
)


class TestDemoSeeder:

    @SEED_BUG
    def test_seeder_creates_skills(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        skills = db.query(Skill).filter(Skill.tenant_id == tenant.id).all()
        assert len(skills) > 0

    @SEED_BUG
    def test_seeder_creates_employees(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        employees = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(employees) > 0

    @SEED_BUG
    def test_seeder_creates_machines(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        machines = db.query(Machine).filter(Machine.tenant_id == tenant.id).all()
        assert len(machines) > 0

    @SEED_BUG
    def test_seeder_creates_jobs(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        jobs = db.query(Job).filter(Job.tenant_id == tenant.id).all()
        assert len(jobs) > 0

    @SEED_BUG
    def test_seeder_is_idempotent(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        count_first = db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        seed_demo_data(db, tenant.id, "printing")
        count_second = db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        assert count_first == count_second

    @SEED_BUG
    def test_seeder_data_belongs_to_tenant(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        foreign_skills = db.query(Skill).filter(Skill.tenant_id != tenant.id).all()
        assert len(foreign_skills) == 0
