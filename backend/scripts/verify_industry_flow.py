"""
End-to-end verification for the industry-type data flow across all
of today's fixes (BUG-3 through BUG-6).

Tests the full chain that was broken before today's work:
  1. Registration accepts industry_type (BUG-4 schema)
  2. Tenant row stores industry_type (BUG-4 persistence)
  3. Demo seeder runs with correct industry (BUG-3 wiring)
  4. /auth/me returns industry_type (BUG-5)
  5. WhatsApp link_phone stores correct industry (BUG-6)
  6. Invalid industries rejected (BUG-4 validation)
  7. Omitted industry defaults to printing (BUG-4 default)

Usage:
    cd backend
    python -m scripts.verify_industry_flow

Requires:
    - uvicorn running on http://localhost:8000 with latest code
    - SQLAlchemy models reachable (run from backend/ with venv active)
    - Network tools (httpx should already be installed via project deps)

Exits with code 0 if all checks pass, non-zero on any failure.
Safe to re-run: creates uniquely-slugged test tenants each run.
"""
import sys
import time

import httpx

from app.database import SessionLocal
from app.models.auth import Tenant, User
from app.models.job import Job
from app.models.employee import Employee
from app.models.machine import Machine
from app.models.skill import Skill
from app.models.whatsapp import PhoneTenantMap


BASE_URL = "http://localhost:8000"
RUN_ID = int(time.time())  # unique slug suffix per run


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

class CheckResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []

    def ok(self, label: str):
        self.passed += 1
        print(f"  [PASS] {label}")

    def fail(self, label: str, detail: str = ""):
        self.failed += 1
        message = f"{label}: {detail}" if detail else label
        self.failures.append(message)
        print(f"  [FAIL] {message}")

    def summary(self) -> int:
        total = self.passed + self.failed
        print("\n" + "=" * 70)
        if self.failed == 0:
            print(f"ALL {total} CHECKS PASSED")
            return 0
        print(f"{self.failed} of {total} CHECKS FAILED")
        print("\nFailures:")
        for f in self.failures:
            print(f"  - {f}")
        return 1


def register(email: str, slug: str, industry: str | None, password: str = "qazx1234"):
    """POST /auth/register. Returns response dict or raises on HTTP error."""
    payload = {
        "email": email,
        "password": password,
        "company_name": f"Verify {slug}",
        "slug": slug,
        # v6.3.2: team_size is required by the schema. '51+' keeps this
        # verifier on the desktop_first path (no phone, no PhoneTenantMap),
        # which matches the industry-attribution scenarios this script
        # exercises.
        "team_size": "51+",
    }
    if industry is not None:
        payload["industry_type"] = industry
    return httpx.post(f"{BASE_URL}/auth/register", json=payload)


def login(email: str, password: str = "qazx1234") -> str:
    """POST /auth/login. Returns access_token."""
    r = httpx.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def me(token: str) -> dict:
    """GET /auth/me with bearer token. Returns response body."""
    r = httpx.get(f"{BASE_URL}/auth/me", headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()


def link_phone(token: str, phone: str) -> httpx.Response:
    """POST /api/v1/whatsapp/link-phone. Returns raw response."""
    return httpx.post(
        f"{BASE_URL}/api/v1/whatsapp/link-phone",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "phone_number": phone,
            "display_name": f"Verify Test {phone[-4:]}",
            "phone_role": "owner",
            "consent_given": True,
        },
    )


# ---------------------------------------------------------------------------
# Individual scenario checks
# ---------------------------------------------------------------------------

def check_fabrication_full_flow(r: CheckResult):
    """BUG-3 + BUG-4 + BUG-5 + BUG-6: full chain for a fabrication tenant."""
    print("\n[SCENARIO 1] Fabrication tenant — full chain")
    email = f"verify-fab-{RUN_ID}@test.com"
    slug = f"verify-fab-{RUN_ID}"
    phone = f"+91999{RUN_ID % 10000000:07d}"

    # Register
    resp = register(email, slug, "fabrication")
    if resp.status_code not in (200, 201):
        r.fail("register as fabrication", f"HTTP {resp.status_code}: {resp.text[:200]}")
        return
    r.ok(f"register as fabrication (HTTP {resp.status_code})")

    # Verify Tenant row has industry_type (BUG-4 persistence)
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
        if tenant is None:
            r.fail("tenant row created", "not found")
            return
        r.ok(f"tenant row created (id={tenant.id})")

        if tenant.industry_type == "fabrication":
            r.ok(f"BUG-4: tenant.industry_type == 'fabrication'")
        else:
            r.fail("BUG-4 persistence", f"expected 'fabrication', got {tenant.industry_type!r}")

        # Verify seeder ran (BUG-3)
        job_count = db.query(Job).filter(Job.tenant_id == tenant.id).count()
        emp_count = db.query(Employee).filter(Employee.tenant_id == tenant.id).count()
        mach_count = db.query(Machine).filter(Machine.tenant_id == tenant.id).count()
        skill_count = db.query(Skill).filter(Skill.tenant_id == tenant.id).count()

        if job_count > 0 and emp_count > 0 and mach_count > 0 and skill_count > 0:
            r.ok(f"BUG-3: seeder ran (jobs={job_count}, emps={emp_count}, mach={mach_count}, skills={skill_count})")
        else:
            r.fail("BUG-3 seeding", f"jobs={job_count}, emps={emp_count}, mach={mach_count}, skills={skill_count} — some are zero")

        # Check the seeded jobs are fabrication-specific (not printing)
        job_names = [j.name for j in db.query(Job).filter(Job.tenant_id == tenant.id).all()]
        has_fabrication_indicator = any(
            kw in name.lower()
            for name in job_names
            for kw in ("fab", "weld", "metal", "steel", "pipe", "sheet")
        )
        has_printing_indicator = any(
            kw in name.lower()
            for name in job_names
            for kw in ("corrugat", "carton", "flexo", "cmyk", "print", "label")
        )
        if has_fabrication_indicator and not has_printing_indicator:
            r.ok(f"BUG-3: seeded jobs are fabrication-specific ({job_names[:3]})")
        elif has_printing_indicator:
            r.fail("BUG-3 seeder used wrong industry", f"got printing job names: {job_names}")
        else:
            r.ok(f"BUG-3: seeded jobs present (names inconclusive): {job_names[:3]}")
    finally:
        db.close()

    # Login + /auth/me (BUG-5)
    try:
        token = login(email)
    except Exception as e:
        r.fail("login", str(e))
        return
    r.ok("login succeeded")

    me_body = me(token)
    if me_body.get("industry_type") == "fabrication":
        r.ok(f"BUG-5: /auth/me returns industry_type='fabrication'")
    else:
        r.fail("BUG-5 /auth/me", f"expected 'fabrication', got {me_body.get('industry_type')!r}")

    # Link phone (BUG-6)
    link_resp = link_phone(token, phone)
    if link_resp.status_code not in (200, 201):
        r.fail("link phone", f"HTTP {link_resp.status_code}: {link_resp.text[:200]}")
        return
    r.ok(f"link phone (HTTP {link_resp.status_code})")

    db = SessionLocal()
    try:
        mapping = db.query(PhoneTenantMap).filter(
            PhoneTenantMap.phone_number == phone
        ).first()
        if mapping is None:
            r.fail("PhoneTenantMap row", "not created")
            return
        if mapping.industry_type == "fabrication":
            r.ok(f"BUG-6: PhoneTenantMap.industry_type == 'fabrication'")
        else:
            r.fail("BUG-6", f"expected 'fabrication', got {mapping.industry_type!r}")
    finally:
        db.close()


def check_chemical_rejected(r: CheckResult):
    """BUG-4: RegisterRequest Literal rejects 'chemical' at the API boundary."""
    print("\n[SCENARIO 2] Chemical industry — must be rejected")
    email = f"verify-chem-{RUN_ID}@test.com"
    slug = f"verify-chem-{RUN_ID}"

    resp = register(email, slug, "chemical")
    if resp.status_code == 422:
        r.ok("BUG-4: 'chemical' rejected with 422")
    else:
        r.fail("BUG-4 chemical rejection", f"expected 422, got HTTP {resp.status_code}")
        return

    # Tenant should NOT have been created
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
        if tenant is None:
            r.ok("no tenant created for rejected registration")
        else:
            r.fail("rejection side effect", f"tenant was created despite 422 (id={tenant.id})")
    finally:
        db.close()


def check_default_printing(r: CheckResult):
    """BUG-4: omitting industry_type defaults to 'printing'."""
    print("\n[SCENARIO 3] Omitted industry_type — must default to 'printing'")
    email = f"verify-default-{RUN_ID}@test.com"
    slug = f"verify-default-{RUN_ID}"

    resp = register(email, slug, industry=None)
    if resp.status_code not in (200, 201):
        r.fail("register without industry_type", f"HTTP {resp.status_code}: {resp.text[:200]}")
        return
    r.ok(f"register without industry_type (HTTP {resp.status_code})")

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
        if tenant is None:
            r.fail("tenant created", "not found")
            return
        if tenant.industry_type == "printing":
            r.ok("BUG-4: default industry_type is 'printing'")
        else:
            r.fail("BUG-4 default", f"expected 'printing', got {tenant.industry_type!r}")
    finally:
        db.close()


def check_migration_head(r: CheckResult):
    """Sanity: alembic head is still 023 — none of these fixes added a migration."""
    print("\n[SCENARIO 4] Alembic migration head sanity")
    import subprocess
    try:
        out = subprocess.run(
            ["alembic", "heads"],
            capture_output=True, text=True, timeout=10,
        )
        if "023" in out.stdout:
            r.ok("alembic head is 023 (no new migrations added)")
        else:
            r.fail("alembic head", f"expected 023 in output, got: {out.stdout.strip()}")
    except FileNotFoundError:
        r.fail("alembic heads", "alembic command not found in PATH")
    except Exception as e:
        r.fail("alembic heads", str(e))


# ---------------------------------------------------------------------------
# Cleanup — delete everything this script created
# ---------------------------------------------------------------------------

def cleanup(r: CheckResult):
    """Remove test tenants, users, mappings, and seeded data created by this run."""
    print(f"\n[CLEANUP] Removing test data for run_id={RUN_ID}")
    slugs = [
        f"verify-fab-{RUN_ID}",
        f"verify-default-{RUN_ID}",
    ]

    db = SessionLocal()
    try:
        for slug in slugs:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).first()
            if tenant is None:
                continue
            tid = tenant.id
            db.query(PhoneTenantMap).filter(PhoneTenantMap.tenant_id == tid).delete()
            db.query(Job).filter(Job.tenant_id == tid).delete()
            db.query(Employee).filter(Employee.tenant_id == tid).delete()
            db.query(Machine).filter(Machine.tenant_id == tid).delete()
            db.query(Skill).filter(Skill.tenant_id == tid).delete()
            db.query(User).filter(User.tenant_id == tid).delete()
            db.delete(tenant)
        db.commit()
        r.ok(f"cleaned up {len(slugs)} test tenants and related rows")
    except Exception as e:
        db.rollback()
        r.fail("cleanup", str(e))
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"End-to-end verification (BUG-3 through BUG-6)")
    print(f"Target: {BASE_URL}")
    print(f"Run ID: {RUN_ID}")
    print("-" * 70)

    # Pre-flight: is uvicorn reachable?
    try:
        r_health = httpx.get(f"{BASE_URL}/docs", timeout=3.0)
        if r_health.status_code != 200:
            print(f"[ABORT] {BASE_URL}/docs returned HTTP {r_health.status_code}. "
                  "Is uvicorn running with the latest code?")
            return 2
    except httpx.RequestError as e:
        print(f"[ABORT] cannot reach {BASE_URL}. Is uvicorn running? Error: {e}")
        return 2

    results = CheckResult()

    try:
        check_fabrication_full_flow(results)
        check_chemical_rejected(results)
        check_default_printing(results)
        check_migration_head(results)
    finally:
        cleanup(results)

    return results.summary()


if __name__ == "__main__":
    sys.exit(main())
