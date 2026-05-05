"""
v6.3.12 manual smoke test — runs all four scenarios end-to-end.

Requires the backend running on http://localhost:8000 and
WHATSAPP_MOCK_MODE=True (so /api/v1/whatsapp/simulate is enabled
for Scenario 2b's HAAN-resume path).

Usage:
    cd backend
    python tests/smoke/smoke_v6_3_12.py
    python tests/smoke/smoke_v6_3_12.py --cleanup
"""

import sys
import time
import uuid
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime
from sqlalchemy import text

sys.path.insert(0, '.')
from app.database import SessionLocal

# ============================================================
# Config
# ============================================================
BASE_URL = "http://localhost:8000"
REGISTER_PATH = "/auth/register"
LOGIN_PATH = "/auth/login"
EMPLOYEES_PATH = "/api/employees/"
MACHINES_PATH = "/api/machines/"
ONBOARDING_COMPLETE_PATH = "/api/v1/onboarding/complete"

# Use a fake phone NOT already mapped to any tenant
PHONE = "+919999912345"

RUN_ID = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
EMAIL_PREFIX = f"smoke_v6312_{RUN_ID}"

created_tenant_ids = []
created_emails = []


# ============================================================
# Helpers
# ============================================================
def http_post(url, body=None, headers=None, timeout=15):
    headers = headers or {}
    data = None
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers.setdefault('Content-Type', 'application/json')

    req = urllib.request.Request(url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode('utf-8')
        except Exception:
            err_body = str(e)
        return e.code, err_body
    except urllib.error.URLError as e:
        return None, f"Connection error: {e.reason}"
    except Exception as e:
        return None, f"Request error: {e}"


def decode_jwt_claims(token):
    """Decode JWT payload (no verification)."""
    try:
        payload_b64 = token.split('.')[1]
        padding = 4 - (len(payload_b64) % 4)
        if padding < 4:
            payload_b64 += '=' * padding
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode('utf-8'))
    except Exception:
        return {}


def make_slug(company_name):
    slug = company_name.lower().replace(' ', '-').replace('_', '-')
    slug = ''.join(c for c in slug if c.isalnum() or c == '-')
    return f"{slug}-{uuid.uuid4().hex[:6]}"


# ============================================================
# Reporter
# ============================================================
class Reporter:
    def __init__(self):
        self.steps = []
        self.failed = False

    def step(self, name, ok, detail=""):
        marker = "PASS" if ok else "FAIL"
        line = f"  [{marker}] {name}"
        if detail:
            line += f"  -- {detail}"
        print(line)
        self.steps.append((name, ok, detail))
        if not ok:
            self.failed = True

    def section(self, title):
        print(f"\n=== {title} ===")

    def summary(self):
        print("\n" + "=" * 60)
        passed = sum(1 for _, ok, _ in self.steps if ok)
        total = len(self.steps)
        if self.failed:
            print(f"FAILED -- {passed}/{total} steps passed")
            print("\nFailed steps:")
            for name, ok, detail in self.steps:
                if not ok:
                    print(f"  - {name}: {detail}")
        else:
            print(f"ALL {total} STEPS PASSED")
        print("=" * 60)


reporter = Reporter()


# ============================================================
# API helpers
# ============================================================
def register(email, company_name, industry, team_size="1-15", phone=None):
    """Register a new tenant. Returns ((tenant_id, user_id, token), None) on success."""
    body = {
        "email": email,
        "password": "TestPass123!",
        "company_name": company_name,
        "slug": make_slug(company_name),
        "industry_type": industry,
        "team_size": team_size,
    }
    if phone:
        body["phone_e164"] = phone

    status, resp_text = http_post(f"{BASE_URL}{REGISTER_PATH}", body=body)

    if status not in (200, 201):
        return None, f"HTTP {status}: {resp_text[:300]}"

    try:
        data = json.loads(resp_text)
    except Exception:
        return None, f"Non-JSON response: {resp_text[:300]}"

    token = data.get("access_token")
    if not token:
        return None, f"No access_token in response: {data}"

    claims = decode_jwt_claims(token)
    tenant_id = claims.get("tenant_id")
    user_id = claims.get("sub")

    if not tenant_id:
        return None, f"Could not extract tenant_id from JWT: {claims}"

    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        pass

    created_tenant_ids.append(tenant_id)
    created_emails.append(email)
    return (tenant_id, user_id, token), None


def add_employee(token, name, skill, worker_type="permanent"):
    body = {"full_name": name, "primary_skill": skill, "worker_type": worker_type}
    headers = {"Authorization": f"Bearer {token}"}
    status, resp_text = http_post(f"{BASE_URL}{EMPLOYEES_PATH}", body=body, headers=headers)
    if status not in (200, 201):
        return False, f"HTTP {status}: {resp_text[:300]}"
    return True, ""


def add_machine(token, name, machine_type):
    body = {"name": name, "machine_type": machine_type}
    headers = {"Authorization": f"Bearer {token}"}
    status, resp_text = http_post(f"{BASE_URL}{MACHINES_PATH}", body=body, headers=headers)
    if status not in (200, 201):
        return False, f"HTTP {status}: {resp_text[:300]}"
    return True, ""


def fire_onboarding_complete(token):
    headers = {"Authorization": f"Bearer {token}"}
    status, resp_text = http_post(f"{BASE_URL}{ONBOARDING_COMPLETE_PATH}", headers=headers)
    return status, resp_text[:300] if status and status >= 400 else ""


def simulate_inbound(phone, message, msg_type="text"):
    """
    Drive an inbound WhatsApp reply via /api/v1/whatsapp/simulate.
    Mock-mode-only endpoint (returns 403 if WHATSAPP_MOCK_MODE is False).
    Returns (status, response_text).
    """
    body = {"phone": phone, "message": message, "type": msg_type}
    return http_post(f"{BASE_URL}/api/v1/whatsapp/simulate", body=body)


# ============================================================
# DB helpers
# ============================================================
def flip_consent_directly(tenant_id):
    db = SessionLocal()
    try:
        db.execute(text(
            "UPDATE phone_tenant_map SET consent_given = TRUE WHERE tenant_id = :tid"
        ), {"tid": tenant_id})
        db.commit()
        return True, ""
    except Exception as e:
        return False, str(e)
    finally:
        db.close()


def get_events_for_tenant(tenant_id, event_type_pattern="onboarding.%"):
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT event_type, created_at FROM events "
            "WHERE tenant_id = :tid AND event_type LIKE :pat "
            "ORDER BY created_at DESC"
        ), {"tid": tenant_id, "pat": event_type_pattern}).all()
        return [(r[0], r[1]) for r in rows]
    finally:
        db.close()


def has_event(tenant_id, event_type):
    return any(e[0] == event_type for e in get_events_for_tenant(tenant_id))


def has_phone_mapping(tenant_id):
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT phone_number FROM phone_tenant_map WHERE tenant_id = :tid"
        ), {"tid": tenant_id}).first()
        return row is not None
    finally:
        db.close()


def consent_status(phone_number):
    """Return consent_given for a phone, or None if no row exists."""
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT consent_given FROM phone_tenant_map "
            "WHERE phone_number = :pn"
        ), {"pn": phone_number}).first()
        return None if row is None else bool(row[0])
    finally:
        db.close()


def count_events(tenant_id, event_type):
    """Count events of a specific type for a tenant."""
    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT COUNT(*) FROM events "
            "WHERE tenant_id = :tid AND event_type = :et"
        ), {"tid": tenant_id, "et": event_type}).first()
        return int(row[0]) if row else 0
    finally:
        db.close()


# ============================================================
# Scenarios
# ============================================================
def scenario_1_consented_immediate():
    reporter.section("SCENARIO 1: Phone consented -> immediate send")

    email = f"{EMAIL_PREFIX}_a@example.com"
    result, err = register(email, "V6312 Test A", "printing", "1-15", PHONE)
    if err:
        reporter.step("Register tenant", False, err)
        return
    tenant_id, _, token = result
    reporter.step("Register tenant", True, f"tenant_id={tenant_id}")

    if not has_phone_mapping(tenant_id):
        reporter.step("Phone mapping created at signup", False)
        return
    reporter.step("Phone mapping created at signup", True)

    ok, msg = flip_consent_directly(tenant_id)
    reporter.step("Flip consent_given=True", ok, msg)
    if not ok:
        return

    ok, msg = add_employee(token, "Ramesh Kumar", "Press operator")
    reporter.step("Add employee 1", ok, msg)
    if not ok:
        return
    ok, msg = add_employee(token, "Suresh Patel", "Binder", "contractor")
    reporter.step("Add employee 2", ok, msg)
    if not ok:
        return
    ok, msg = add_machine(token, "Heidelberg SM 52", "Offset Press")
    reporter.step("Add machine 1", ok, msg)
    if not ok:
        return

    status, err = fire_onboarding_complete(token)
    reporter.step("POST /onboarding/complete returns 204",
                  status == 204,
                  f"got {status}: {err}" if status != 204 else "")
    if status != 204:
        return

    time.sleep(1)

    if has_event(tenant_id, "onboarding.message_sent"):
        reporter.step("Event onboarding.message_sent written", True)
    else:
        events = get_events_for_tenant(tenant_id)
        reporter.step("Event onboarding.message_sent written", False,
                      f"events found: {events}")
        return

    status, err = fire_onboarding_complete(token)
    reporter.step("Re-fire returns 204 (idempotent)",
                  status == 204,
                  f"got {status}: {err}" if status != 204 else "")

    events = get_events_for_tenant(tenant_id, "onboarding.message_sent")
    reporter.step("Idempotency: only 1 message_sent event after re-fire",
                  len(events) == 1,
                  f"found {len(events)} events")


def scenario_2_pending_consent():
    reporter.section("SCENARIO 2: Phone unconsented -> pending event")

    # Use a different fake phone since Scenario 1's phone is now linked
    phone_b = "+919999912346"

    email = f"{EMAIL_PREFIX}_b@example.com"
    result, err = register(email, "V6312 Test B", "fabrication", "1-15", phone_b)
    if err:
        reporter.step("Register tenant", False, err)
        return
    tenant_id, _, token = result
    reporter.step("Register tenant", True, f"tenant_id={tenant_id}")

    if not has_phone_mapping(tenant_id):
        reporter.step("Phone mapping created at signup", False)
        return
    reporter.step("Phone mapping created at signup", True)

    # Do NOT flip consent

    ok, msg = add_employee(token, "Welder One", "Welder")
    reporter.step("Add employee", ok, msg)
    ok, msg = add_machine(token, "Lathe 1", "Lathe")
    reporter.step("Add machine", ok, msg)

    status, err = fire_onboarding_complete(token)
    reporter.step("POST /onboarding/complete returns 204",
                  status == 204,
                  f"got {status}: {err}" if status != 204 else "")
    if status != 204:
        return

    time.sleep(1)

    if has_event(tenant_id, "onboarding.pending_consent"):
        reporter.step("Event onboarding.pending_consent written", True)
    else:
        events = get_events_for_tenant(tenant_id)
        reporter.step("Event onboarding.pending_consent written", False,
                      f"events found: {events}")

    if not has_event(tenant_id, "onboarding.message_sent"):
        reporter.step("No message_sent event yet (correct)", True)
    else:
        reporter.step("No message_sent event yet (correct)", False,
                      "message_sent fired prematurely!")

    print("  NOTE: full Scenario 2 (HAAN -> auto-resume) requires manual")
    print("        HAAN reply from your phone and re-running events query.")


def scenario_2b_haan_resume():
    """
    Drives the HAAN-flip-resume path entirely in mock mode via the
    /api/v1/whatsapp/simulate endpoint. Verifies that:
      - A pending_consent stage converts to message_sent on HAAN reply.
      - phone_tenant_map.consent_given flips to True.
      - The original pending_consent event is preserved (audit-only,
        not cleared).
      - Re-firing /onboarding/complete after consent does NOT add a
        second message_sent (idempotency holds across the resume path).

    Uses a third fake phone (+919999912347) so it doesn't collide with
    Scenarios 1 or 2.
    """
    reporter.section("SCENARIO 2b: HAAN reply resumes pending message")

    phone_d = "+919999912347"

    email = f"{EMAIL_PREFIX}_d@example.com"
    # 'chemical' is excluded from the signup enum (Plan B only per CLAUDE.md).
    # Use field_service - the only accepted vertical not used by S1/S2/S3 -
    # which also exercises the workspace_label='sites' path.
    result, err = register(email, "V6312 Test D", "field_service", "1-15", phone_d)
    if err:
        reporter.step("Register tenant", False, err)
        return
    tenant_id, _, token = result
    reporter.step("Register tenant", True, f"tenant_id={tenant_id}")

    if not has_phone_mapping(tenant_id):
        reporter.step("Phone mapping created at signup", False)
        return
    reporter.step("Phone mapping created at signup", True)

    if consent_status(phone_d) is not False:
        reporter.step("Initial consent_given is False",
                      False,
                      f"got consent_status={consent_status(phone_d)}")
        return
    reporter.step("Initial consent_given is False", True)

    ok, msg = add_employee(token, "Field Tech One", "Field Technician")
    reporter.step("Add employee", ok, msg)
    ok, msg = add_machine(token, "Service Van 1", "Vehicle")
    reporter.step("Add machine", ok, msg)

    status, err = fire_onboarding_complete(token)
    reporter.step("POST /onboarding/complete returns 204",
                  status == 204,
                  f"got {status}: {err}" if status != 204 else "")
    if status != 204:
        return

    time.sleep(1)

    if not has_event(tenant_id, "onboarding.pending_consent"):
        events = get_events_for_tenant(tenant_id)
        reporter.step("Event onboarding.pending_consent staged",
                      False, f"events found: {events}")
        return
    reporter.step("Event onboarding.pending_consent staged", True)

    # Now the meaningful new assertion: drive HAAN inbound and watch the
    # resume hook flip consent + dispatch + record message_sent.
    sim_status, sim_resp = simulate_inbound(phone_d, "HAAN")
    reporter.step("POST /simulate (HAAN) returns 200",
                  sim_status == 200,
                  f"got {sim_status}: {sim_resp[:200]}" if sim_status != 200 else "")
    if sim_status != 200:
        return

    time.sleep(1)

    reporter.step("phone_tenant_map.consent_given flipped to True",
                  consent_status(phone_d) is True,
                  f"got consent_status={consent_status(phone_d)}")

    sent_count = count_events(tenant_id, "onboarding.message_sent")
    reporter.step("Resume hook fired -> 1 message_sent event",
                  sent_count == 1,
                  f"found {sent_count}")

    reporter.step("Original pending_consent event preserved",
                  has_event(tenant_id, "onboarding.pending_consent"))

    # Idempotency across the resume path: re-firing /onboarding/complete
    # after consent must be a no-op. send_if_unsent's _is_already_handled
    # check returns True once message_sent exists.
    status, err = fire_onboarding_complete(token)
    reporter.step("Re-fire /onboarding/complete after consent returns 204",
                  status == 204,
                  f"got {status}: {err}" if status != 204 else "")

    sent_count = count_events(tenant_id, "onboarding.message_sent")
    reporter.step("Idempotency: still 1 message_sent after re-fire",
                  sent_count == 1,
                  f"found {sent_count}")


def scenario_3_no_phone():
    reporter.section("SCENARIO 3: No phone (team_size=51+) -> skipped event")

    email = f"{EMAIL_PREFIX}_c@example.com"
    result, err = register(email, "V6312 Test C", "manufacturing", "51+", phone=None)
    if err:
        reporter.step("Register tenant (no phone)", False, err)
        return
    tenant_id, _, token = result
    reporter.step("Register tenant (no phone)", True, f"tenant_id={tenant_id}")

    if has_phone_mapping(tenant_id):
        reporter.step("Phone mapping NOT created at signup", False,
                      "unexpected phone_tenant_map row exists")
    else:
        reporter.step("Phone mapping NOT created at signup", True)

    ok, msg = add_employee(token, "Operator A", "Press operator")
    reporter.step("Add employee", ok, msg)
    ok, msg = add_machine(token, "Machine M1", "Offset Press")
    reporter.step("Add machine", ok, msg)

    status, err = fire_onboarding_complete(token)
    reporter.step("POST /onboarding/complete returns 204",
                  status == 204,
                  f"got {status}: {err}" if status != 204 else "")
    if status != 204:
        return

    time.sleep(1)

    if has_event(tenant_id, "onboarding.skipped_no_phone"):
        reporter.step("Event onboarding.skipped_no_phone written", True)
    else:
        events = get_events_for_tenant(tenant_id)
        reporter.step("Event onboarding.skipped_no_phone written", False,
                      f"events found: {events}")

    if not has_event(tenant_id, "onboarding.message_sent"):
        reporter.step("No message_sent event (correct for desktop-first)", True)
    else:
        reporter.step("No message_sent event (correct for desktop-first)", False)


# ============================================================
# Cleanup
# ============================================================
def cleanup():
    print("\n=== Cleanup ===")
    db = SessionLocal()
    try:
        rows = db.execute(text(
            "SELECT id, name FROM tenants WHERE name LIKE 'V6312 Test %'"
        )).all()
        if not rows:
            print("  No test tenants found.")
            return
        ids = [r[0] for r in rows]
        print(f"  Cleaning up {len(ids)} test tenants: {ids}")

        for tbl in ("events", "phone_tenant_map", "employees", "machines",
                    "whatsapp_conversations", "users", "tenants"):
            try:
                if tbl == "tenants":
                    where = "id IN :ids"
                else:
                    where = "tenant_id IN :ids"
                db.execute(
                    text(f"DELETE FROM {tbl} WHERE {where}"),
                    {"ids": tuple(ids)}
                )
            except Exception as e:
                print(f"  Skip table {tbl}: {e}")

        db.commit()
        print("  Cleanup complete.")
    finally:
        db.close()


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        cleanup()
        sys.exit(0)

    print(f"v6.3.12 smoke test — run id: {RUN_ID}")
    print(f"Backend: {BASE_URL}")
    print(f"Test phone (Scenario 1): {PHONE}")
    print()

    scenario_1_consented_immediate()
    scenario_2_pending_consent()
    scenario_2b_haan_resume()
    scenario_3_no_phone()

    reporter.summary()

    print("\nTo clean up test data, run:")
    print("  python smoke_v6_3_12.py --cleanup")

    sys.exit(1 if reporter.failed else 0)