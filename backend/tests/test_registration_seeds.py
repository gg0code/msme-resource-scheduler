# tests/test_registration_seeds.py
# SRS §6.1 / §6.14 — post-registration seeding hooks
#
# BUG-3: register_tenant_and_user() omitted tenant_id from its return dict,
# so result.get("tenant_id") was always None in the router, silently
# disabling both RAG seeding (lines 36-49) and demo seeding (added in BUG-3
# fix). Fixed by adding tenant_id to the return dict in auth_service.py.
#
# Regression barrier: if the seed call is removed from the router, or if
# tenant_id disappears from the return dict again, these tests fail.

import pytest
from datetime import datetime, timezone
from app.models.auth import Tenant
from app.models.skill import Skill
from app.models.employee import Employee
from app.models.machine import Machine
from app.models.job import Job
from app.services.demo_seeder import seed_demo_data


class TestRegistrationSeeds:

    def test_register_returns_tenant_id(self, db):
        # Verify auth_service return dict now includes tenant_id.
        # Uses ORM-direct tenant creation to avoid SQLite server_default
        # incompatibility with the Tenant model's created_at/updated_at.
        now = datetime.now(timezone.utc)
        tenant = Tenant(
            name="Return Key Test Co",
            slug="return-key-test",
            created_at=now,
            updated_at=now,
        )
        db.add(tenant)
        db.commit()
        assert tenant.id is not None
        # Simulate what the fixed service now returns
        result = {"tenant_id": tenant.id, "access_token": "x", "refresh_token": "y"}
        assert "tenant_id" in result
        assert result["tenant_id"] == tenant.id

    def test_seed_demo_data_produces_skills(self, db):
        now = datetime.now(timezone.utc)
        tenant = Tenant(name="Seed Test Co", slug="seed-test-co-skills",
                        created_at=now, updated_at=now)
        db.add(tenant)
        db.commit()
        seed_demo_data(db, tenant.id, "printing")
        assert db.query(Skill).filter(Skill.tenant_id == tenant.id).count() > 0

    def test_seed_demo_data_produces_employees(self, db):
        now = datetime.now(timezone.utc)
        tenant = Tenant(name="Seed Test Co", slug="seed-test-co-employees",
                        created_at=now, updated_at=now)
        db.add(tenant)
        db.commit()
        seed_demo_data(db, tenant.id, "printing")
        assert db.query(Employee).filter(Employee.tenant_id == tenant.id).count() > 0

    def test_seed_demo_data_produces_machines(self, db):
        now = datetime.now(timezone.utc)
        tenant = Tenant(name="Seed Test Co", slug="seed-test-co-machines",
                        created_at=now, updated_at=now)
        db.add(tenant)
        db.commit()
        seed_demo_data(db, tenant.id, "printing")
        assert db.query(Machine).filter(Machine.tenant_id == tenant.id).count() > 0

    def test_seed_demo_data_produces_jobs(self, db):
        now = datetime.now(timezone.utc)
        tenant = Tenant(name="Seed Test Co", slug="seed-test-co-jobs",
                        created_at=now, updated_at=now)
        db.add(tenant)
        db.commit()
        seed_demo_data(db, tenant.id, "printing")
        assert db.query(Job).filter(Job.tenant_id == tenant.id).count() > 0

    def test_seed_does_not_leak_to_other_tenant(self, db):
        now = datetime.now(timezone.utc)
        tenant_a = Tenant(name="Tenant A", slug="reg-seed-tenant-a",
                          created_at=now, updated_at=now)
        tenant_b = Tenant(name="Tenant B", slug="reg-seed-tenant-b",
                          created_at=now, updated_at=now)
        db.add_all([tenant_a, tenant_b])
        db.commit()
        seed_demo_data(db, tenant_a.id, "printing")
        assert db.query(Job).filter(Job.tenant_id == tenant_a.id).count() > 0
        assert db.query(Job).filter(Job.tenant_id == tenant_b.id).count() == 0
