# tests/test_demo_seeder.py
# SRS §6.14 Demo Data Seeder (v4.0.6)
#
# Originally xfail'd for BUG-1 (Job model missing job_type/quantity).
# Fixed by adding job_type and quantity columns to app/models/job.py.
# Tests now pass.

import pytest
from app.services.demo_seeder import seed_demo_data
from app.models.skill import Skill
from app.models.employee import Employee
from app.models.machine import Machine
from app.models.job import Job


class TestDemoSeeder:

    def test_seeder_creates_skills(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        skills = db.query(Skill).filter(Skill.tenant_id == tenant.id).all()
        assert len(skills) > 0

    def test_seeder_creates_employees(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        employees = db.query(Employee).filter(Employee.tenant_id == tenant.id).all()
        assert len(employees) > 0

    def test_seeder_creates_machines(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        machines = db.query(Machine).filter(Machine.tenant_id == tenant.id).all()
        assert len(machines) > 0

    def test_seeder_creates_jobs(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        jobs = db.query(Job).filter(Job.tenant_id == tenant.id).all()
        assert len(jobs) > 0

    def test_seeder_is_idempotent(self, db, auth_headers):
        from app.models.auth import Tenant
        tenant = db.query(Tenant).first()
        seed_demo_data(db, tenant.id, "printing")
        count_first = db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        seed_demo_data(db, tenant.id, "printing")
        count_second = db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        assert count_first == count_second

    def test_seeder_does_not_leak_to_other_tenant(self, db):
        from datetime import datetime, timezone
        from app.models.auth import Tenant
        now = datetime.now(timezone.utc)
        tenant_a = Tenant(name="Tenant A", slug="tenant-a-seeder-test", created_at=now, updated_at=now)
        tenant_b = Tenant(name="Tenant B", slug="tenant-b-seeder-test", created_at=now, updated_at=now)
        db.add_all([tenant_a, tenant_b])
        db.commit()

        seed_demo_data(db, tenant_a.id, "printing")

        a_skills = db.query(Skill).filter(Skill.tenant_id == tenant_a.id).all()
        b_skills = db.query(Skill).filter(Skill.tenant_id == tenant_b.id).all()
        assert len(a_skills) > 0
        assert len(b_skills) == 0
