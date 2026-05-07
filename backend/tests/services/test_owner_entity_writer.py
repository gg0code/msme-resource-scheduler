# tests/services/test_owner_entity_writer.py
# Branch: v5-whatsapp
# Iteration: v6.3.17 (WhatsApp Natural-Language Entity Edits)
#
# FILE PURPOSE
# Unit tests for app/services/owner_entity_writer.py. Coverage axes
# (matching the user's stage-2 requirements + spec section E):
#
#   1. Heuristic detector — 8+ NEGATIVE tests against non-create
#      phrasings that look superficially similar but must NOT trigger
#      a write. Plus positive tests for each entity kind. The
#      detector errs toward false negatives; tests pin that bias.
#
#   2. Role gate — all four top-tier values, both mid-tier values,
#      operator, NULL, and an unknown role string. Top-tier proceeds;
#      everything else falls through with no write.
#
#   3. Idempotency — every writer fuzzy-matches against existing
#      rows. A second identical message must NOT create a duplicate
#      and must NOT emit a second audit event.
#
#   4. Audit event payload — entity.owner_added rows carry
#      parse_strategy='heuristic' so v6.4.x evolution to a hybrid
#      LLM-assisted parser is forward-compatible.
#
#   5. Cross-entity flows — employee with missing skill, link with
#      missing employee, link with missing skill. Replies prompt the
#      next correct action without writing.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.owner_entity_writer.{evaluate_and_write,
#     detect_owner_create_intent, write_employee, write_machine,
#     write_skill, link_employee_skill}.
#   tests/services/conftest.py builders (make_tenant, make_employee).
#
# DESIGN NOTES
#   - patch_now_defaults_for_sqlite (parent conftest autouse) covers
#     the tables we touch: tenants, employees, machines, events.
#     Skill table needs the same patch — wired locally below.
#   - Tests use a fresh SQLite session per test (`db` fixture from
#     parent conftest). No mocking — real ORM, real fuzzy_match.

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.sql.schema import DefaultClause
from sqlalchemy import text as sa_text

from app.models.auth import Tenant
from app.models.employee import Employee, EmployeeSkill, VALID_SOURCE_VALUES
from app.models.event import Event
from app.models.machine import Machine
from app.models.skill import Skill
from app.services.owner_entity_writer import (
    CREATION_VERB_PHRASES,
    EVENT_OWNER_ADDED,
    OwnerCreateIntent,
    PARSE_STRATEGY_HEURISTIC,
    SOURCE_VALUE,
    detect_owner_create_intent,
    evaluate_and_write,
    link_employee_skill,
    write_employee,
    write_machine,
    write_skill,
)

from tests.services.conftest import make_employee, make_tenant


# ---------------------------------------------------------------------------
# Skill server_default patch — local autouse fixture.
# The parent conftest's patch list does not include Skill (Skill only
# gained server_defaults in v6.3.17 migration 032 — for SQLite tests we
# also strip the now() defaults if any appear). Keeps Skill INSERTs
# working under in-memory SQLite without touching parent fixtures.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_skill_defaults_for_sqlite():
    patched = []
    for col in Skill.__table__.columns:
        if col.server_default is None:
            continue
        arg = getattr(col.server_default, "arg", None)
        text_value = str(arg) if arg is not None else ""
        if "now()" in text_value.lower():
            patched.append((col, col.server_default))
            col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    for col, original in patched:
        col.server_default = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill(db, *, tenant: Tenant, name: str, category: str = "Generic") -> Skill:
    s = Skill(
        tenant_id=tenant.id,
        name=name,
        category=category,
        is_active=True,
        source="manual",
    )
    db.add(s)
    db.flush()
    return s


def _last_owner_added_event(db, tenant_id: int) -> Event | None:
    return (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == EVENT_OWNER_ADDED,
        )
        .order_by(Event.id.desc())
        .first()
    )


def _count_owner_added(db, tenant_id: int) -> int:
    return (
        db.query(Event)
        .filter(
            Event.tenant_id == tenant_id,
            Event.event_type == EVENT_OWNER_ADDED,
        )
        .count()
    )


# ===========================================================================
# Suggested manual test cases (per $GGRULE step 5)
# ===========================================================================
#
# Run after `alembic upgrade head` against dev Postgres with
# WHATSAPP_MOCK_MODE=True so [MOCK ALERT]/[MOCK SEND] lines surface in
# the uvicorn log. Three runnable Python snippets covering happy path,
# failure-mode (role gate), and edge case (idempotency).
#
# 1) Happy path — owner adds an employee. Expect insert + audit.
#    python -c "
#    from app.database import SessionLocal
#    from app.services.owner_entity_writer import evaluate_and_write
#    db = SessionLocal()
#    reply = evaluate_and_write(
#        message='naya welder hai - Mukesh add kar do',
#        tenant_id=12,
#        phone_role='proprietor',
#        actor_user_id=14,
#        db=db,
#    )
#    db.commit()
#    print('reply:', reply)
#    "
#
# 2) Failure mode — manager attempting same message must NOT write.
#    python -c "
#    from app.database import SessionLocal
#    from app.services.owner_entity_writer import evaluate_and_write
#    db = SessionLocal()
#    reply = evaluate_and_write(
#        message='naya welder hai - Mukesh add kar do',
#        tenant_id=12,
#        phone_role='manager',
#        actor_user_id=14,
#        db=db,
#    )
#    db.commit()
#    print('reply (must be None):', reply)
#    "
#
# 3) Edge case — second identical owner message must hit fuzzy short
#    circuit, no duplicate row, no second audit event.
#    python -c "
#    from app.database import SessionLocal
#    from sqlalchemy import select, func
#    from app.models.employee import Employee
#    from app.models.event import Event
#    from app.services.owner_entity_writer import evaluate_and_write
#    db = SessionLocal()
#    msg = 'naya welder hai - Mukesh add kar do'
#    print('1st:', evaluate_and_write(message=msg, tenant_id=12,
#          phone_role='proprietor', actor_user_id=14, db=db))
#    db.commit()
#    print('2nd:', evaluate_and_write(message=msg, tenant_id=12,
#          phone_role='proprietor', actor_user_id=14, db=db))
#    db.commit()
#    n_emp = db.execute(select(func.count(Employee.id)).where(
#        Employee.tenant_id==12, Employee.full_name=='Mukesh')).scalar()
#    n_evt = db.execute(select(func.count(Event.id)).where(
#        Event.tenant_id==12, Event.event_type=='entity.owner_added')).scalar()
#    print(f'employees: {n_emp}, events: {n_evt}  (expect 1, 1)')
#    "

# ===========================================================================
# Heuristic detector — NEGATIVE tests (false-positive resistance)
# ===========================================================================

class TestDetectorNegatives:
    """8+ messages that look superficially like creates but must NOT trigger.

    The user's stage-2 requirement: "false negatives OK, false positives
    NOT OK". Each test below is a phrasing that an owner might plausibly
    send and that the detector must classify as None.
    """

    @pytest.mark.parametrize("message", [
        # 1. handle/take care of — verb 'sambhaalo' is not create.
        "Mukesh ko sambhaalo aaj",
        # 2. absence — past tense, no create verb.
        "Suresh aaj nahi aaya",
        # 3. need a welder — verb 'chahiye' is request, not create.
        "Naya welder chahiye",
        # 4. praise — descriptive, no create verb.
        "Mukesh achha kaam karta hai",
        # 5. salary query.
        "Mukesh ki salary kya hai",
        # 6. work-assignment query.
        "Mukesh ko aaj kya kaam mila",
        # 7. future tense announcement.
        "Ek welder kal aayega",
        # 8. urgent request.
        "Welder chahiye urgent",
        # 9. name without entity clue (false negative — acceptable).
        "Heidelberg add kar do",
        # 10. spec example #2 — past-tense 'aayi hai', no creation verb.
        "ek aur machine aayi hai, naam Cutter 4",
    ])
    def test_non_create_phrasings_return_none(self, message):
        assert detect_owner_create_intent(message) is None, (
            f"False positive on: {message!r}"
        )


# ===========================================================================
# Heuristic detector — POSITIVE tests
# ===========================================================================

class TestDetectorPositives:

    def test_employee_with_skill_hint(self):
        intent = detect_owner_create_intent(
            "naya welder hai - Mukesh add kar do"
        )
        assert intent is not None
        assert intent.kind == "employee"
        assert intent.name == "Mukesh"
        assert intent.skill_hint == "welder"

    def test_create_skill(self):
        intent = detect_owner_create_intent(
            "naya skill banao - powder coating"
        )
        assert intent is not None
        assert intent.kind == "skill"
        assert "powder coating" in intent.name.lower()

    def test_link_employee_skill(self):
        intent = detect_owner_create_intent(
            "Ravi ko skills mein paint spray bhi add kar do"
        )
        assert intent is not None
        assert intent.kind == "link_employee_skill"
        assert intent.employee_name == "Ravi"
        assert "paint spray" in intent.name.lower()

    def test_employee_via_make_role(self):
        # Spec edge case: "Mukesh ko welder banao" — interpreted as
        # employee create with welder skill_hint. Writer decides
        # link-vs-create at insert time based on existence.
        intent = detect_owner_create_intent("Mukesh ko welder banao")
        assert intent is not None
        assert intent.kind == "employee"
        assert intent.name == "Mukesh"
        assert intent.skill_hint == "welder"


# ===========================================================================
# Role gate — covers every tier + edge cases
# ===========================================================================

class TestRoleGate:

    @pytest.fixture
    def tenant(self, db):
        t = make_tenant(db, age_days=10)
        db.commit()
        return t

    @pytest.mark.parametrize("role", [
        "owner", "proprietor", "factory_manager", "co_owner",
    ])
    def test_top_tier_proceeds(self, db, tenant, role):
        reply = evaluate_and_write(
            message="naya welder hai - Mukesh add kar do",
            tenant_id=tenant.id,
            phone_role=role,
            actor_user_id=None,
            db=db,
        )
        db.commit()
        assert reply is not None
        assert "Mukesh" in reply
        assert db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Mukesh",
        ).count() == 1

    @pytest.mark.parametrize("role", [
        "manager",      # mid-tier — must fall through
        "scheduler",    # legacy mid-tier
        "operator",     # operator
        "viewer",       # unknown / non-recognised
        None,           # NULL phone_role — defaults to deny
        "",             # empty string — denies
        "OWNER",        # case mismatch — strict comparison denies
    ])
    def test_non_top_tier_falls_through(self, db, tenant, role):
        reply = evaluate_and_write(
            message="naya welder hai - Mukesh add kar do",
            tenant_id=tenant.id,
            phone_role=role,
            actor_user_id=None,
            db=db,
        )
        db.commit()
        assert reply is None
        # No employee row should have been written.
        assert db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
        ).count() == 0
        # No audit row should have been written.
        assert _count_owner_added(db, tenant.id) == 0

    def test_role_change_between_messages(self, db, tenant):
        # First message as proprietor → write happens.
        r1 = evaluate_and_write(
            message="naya welder hai - Mukesh add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        assert r1 is not None

        # Phone is downgraded to manager — second message must NOT
        # write (role gate decides per-message; no caching on a
        # previous decision).
        r2 = evaluate_and_write(
            message="naya welder hai - Suresh add kar do",
            tenant_id=tenant.id,
            phone_role="manager",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        assert r2 is None
        # Mukesh exists, Suresh does not.
        assert db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Mukesh",
        ).count() == 1
        assert db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Suresh",
        ).count() == 0


# ===========================================================================
# Writer happy paths
# ===========================================================================

class TestWriteEmployee:

    def test_creates_with_source_whatsapp_owner(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        reply = evaluate_and_write(
            message="naya welder hai - Mukesh add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        emp = db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Mukesh",
        ).one()
        assert emp.source == "whatsapp_owner"
        assert "whatsapp_owner" in VALID_SOURCE_VALUES
        ev = _last_owner_added_event(db, tenant.id)
        assert ev is not None
        assert ev.payload["entity_type"] == "employee"
        assert ev.payload["source"] == "whatsapp_owner"
        assert ev.payload["parse_strategy"] == PARSE_STRATEGY_HEURISTIC
        assert ev.payload["fuzzy_skipped"] is False
        assert "Mukesh" in reply

    def test_employee_with_existing_skill_links(self, db):
        tenant = make_tenant(db, age_days=10)
        skill = _make_skill(db, tenant=tenant, name="Welder")
        db.commit()
        reply = evaluate_and_write(
            message="naya welder hai - Suresh add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        emp = db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Suresh",
        ).one()
        link = db.query(EmployeeSkill).filter(
            EmployeeSkill.tenant_id == tenant.id,
            EmployeeSkill.employee_id == emp.id,
            EmployeeSkill.skill_id == skill.id,
        ).first()
        assert link is not None
        assert "Welder" in reply

    def test_employee_with_missing_skill_prompts(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        reply = evaluate_and_write(
            message="naya welder hai - Ravi add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        # Employee created, skill not linked (none exists), reply
        # prompts to create the skill.
        assert "Ravi added" in reply
        assert "skill nahi mila" in reply
        assert db.query(EmployeeSkill).filter(
            EmployeeSkill.tenant_id == tenant.id,
        ).count() == 0


class TestWriteMachine:

    def test_creates_machine_with_source_whatsapp_owner(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        intent = OwnerCreateIntent(
            kind="machine",
            name="Cutter 4",
            raw_message="naya machine - Cutter 4 add kar do",
        )
        outcome = write_machine(intent, tenant.id, None, db)
        db.commit()
        assert outcome.kind == "created"
        m = db.query(Machine).filter(
            Machine.tenant_id == tenant.id,
            Machine.name == "Cutter 4",
        ).one()
        assert m.source == "whatsapp_owner"
        ev = _last_owner_added_event(db, tenant.id)
        assert ev is not None
        assert ev.payload["entity_type"] == "machine"


class TestWriteSkill:

    def test_creates_skill_with_source_whatsapp_owner(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        reply = evaluate_and_write(
            message="naya skill banao - powder coating",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        skills = db.query(Skill).filter(
            Skill.tenant_id == tenant.id,
        ).all()
        # Powder coating now exists.
        target = next(s for s in skills if "powder" in s.name.lower())
        assert target.source == "whatsapp_owner"
        ev = _last_owner_added_event(db, tenant.id)
        assert ev is not None
        assert ev.payload["entity_type"] == "skill"
        assert "Powder Coating" in reply or "powder coating" in reply.lower()


class TestLinkEmployeeSkill:

    def test_links_existing_employee_to_existing_skill(self, db):
        tenant = make_tenant(db, age_days=10)
        ravi = make_employee(db, tenant=tenant, full_name="Ravi")
        skill = _make_skill(db, tenant=tenant, name="Paint Spray")
        db.commit()
        reply = evaluate_and_write(
            message="Ravi ko skills mein paint spray bhi add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        link = db.query(EmployeeSkill).filter(
            EmployeeSkill.tenant_id == tenant.id,
            EmployeeSkill.employee_id == ravi.id,
            EmployeeSkill.skill_id == skill.id,
        ).first()
        assert link is not None
        assert "Ravi" in reply
        assert "Paint Spray" in reply
        ev = _last_owner_added_event(db, tenant.id)
        assert ev is not None
        assert ev.payload["entity_type"] == "employee_skill"

    def test_link_with_missing_employee(self, db):
        tenant = make_tenant(db, age_days=10)
        _make_skill(db, tenant=tenant, name="Paint Spray")
        db.commit()
        reply = evaluate_and_write(
            message="Ghost ko skills mein paint spray bhi add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        # Reply prompts to add the employee. No link, no audit row.
        assert "Ghost" in reply
        assert "team mein nahi hai" in reply
        assert db.query(EmployeeSkill).filter(
            EmployeeSkill.tenant_id == tenant.id,
        ).count() == 0
        assert _count_owner_added(db, tenant.id) == 0

    def test_link_with_missing_skill(self, db):
        tenant = make_tenant(db, age_days=10)
        make_employee(db, tenant=tenant, full_name="Ravi")
        db.commit()
        reply = evaluate_and_write(
            message="Ravi ko skills mein quantum mechanics bhi add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=None,
            db=db,
        )
        db.commit()
        # Reply prompts to create the skill first. No link, no audit.
        assert "skill nahi hai" in reply
        assert db.query(EmployeeSkill).filter(
            EmployeeSkill.tenant_id == tenant.id,
        ).count() == 0
        assert _count_owner_added(db, tenant.id) == 0


# ===========================================================================
# Idempotency — fuzzy match short circuits duplicate writes
# ===========================================================================

class TestIdempotency:

    def test_employee_second_call_is_noop(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()

        msg = "naya welder hai - Mukesh add kar do"
        first = evaluate_and_write(
            message=msg, tenant_id=tenant.id,
            phone_role="proprietor", actor_user_id=None, db=db,
        )
        db.commit()
        assert "Mukesh" in first

        second = evaluate_and_write(
            message=msg, tenant_id=tenant.id,
            phone_role="proprietor", actor_user_id=None, db=db,
        )
        db.commit()
        assert "pehle se" in second  # "already exists" reply
        # Exactly one Employee row, exactly one audit event.
        assert db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
            Employee.full_name == "Mukesh",
        ).count() == 1
        assert _count_owner_added(db, tenant.id) == 1

    def test_machine_second_call_is_noop(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        intent = OwnerCreateIntent(
            kind="machine", name="Press SM52",
            raw_message="machine add kar do - Press SM52",
        )
        write_machine(intent, tenant.id, None, db)
        db.commit()
        out2 = write_machine(intent, tenant.id, None, db)
        db.commit()
        assert out2.kind == "already_exists"
        assert out2.fuzzy_skipped is True
        assert db.query(Machine).filter(
            Machine.tenant_id == tenant.id,
        ).count() == 1
        assert _count_owner_added(db, tenant.id) == 1

    def test_skill_second_call_is_noop(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        intent = OwnerCreateIntent(
            kind="skill", name="Powder Coating",
            raw_message="naya skill banao - powder coating",
        )
        write_skill(intent, tenant.id, None, db)
        db.commit()
        out2 = write_skill(intent, tenant.id, None, db)
        db.commit()
        assert out2.kind == "already_exists"
        assert db.query(Skill).filter(
            Skill.tenant_id == tenant.id,
        ).count() == 1
        assert _count_owner_added(db, tenant.id) == 1

    def test_employee_skill_link_second_call_is_noop(self, db):
        tenant = make_tenant(db, age_days=10)
        ravi = make_employee(db, tenant=tenant, full_name="Ravi")
        skill = _make_skill(db, tenant=tenant, name="Paint Spray")
        db.commit()
        intent = OwnerCreateIntent(
            kind="link_employee_skill",
            name="Paint Spray",
            employee_name="Ravi",
            raw_message="Ravi ko skills mein paint spray bhi add kar do",
        )
        link_employee_skill(intent, tenant.id, None, db)
        db.commit()
        out2 = link_employee_skill(intent, tenant.id, None, db)
        db.commit()
        assert out2.kind == "already_exists"
        assert db.query(EmployeeSkill).filter(
            EmployeeSkill.tenant_id == tenant.id,
            EmployeeSkill.employee_id == ravi.id,
            EmployeeSkill.skill_id == skill.id,
        ).count() == 1
        assert _count_owner_added(db, tenant.id) == 1

    def test_fuzzy_match_catches_multi_token_close_spelling(self, db):
        # Multi-token candidate "Mukesh Kumar" against existing
        # "Mukesh Singh Kumar" uses token_set_ratio with the 85
        # threshold (per v6.3.15 fuzzy_match design). Single-token
        # candidates use the stricter ratio (90); that path is the
        # v6.3.15 promoter's "acceptable known edge case" where a
        # short rename can cause a duplicate insert. Documenting that
        # behaviour by NOT asserting on it here.
        tenant = make_tenant(db, age_days=10)
        make_employee(db, tenant=tenant, full_name="Mukesh Singh Kumar")
        db.commit()
        intent = OwnerCreateIntent(
            kind="employee",
            name="Mukesh Kumar",
            raw_message="naya welder hai - Mukesh Kumar add kar do",
        )
        outcome = write_employee(intent, tenant.id, None, db)
        db.commit()
        # Multi-token fuzzy short circuit fires.
        assert outcome.kind == "already_exists"
        assert outcome.fuzzy_skipped is True
        assert db.query(Employee).filter(
            Employee.tenant_id == tenant.id,
        ).count() == 1


# ===========================================================================
# Audit-event payload contract (Q5)
# ===========================================================================

class TestAuditPayload:

    def test_payload_shape(self, db):
        tenant = make_tenant(db, age_days=10)
        db.commit()
        evaluate_and_write(
            message="naya welder hai - Mukesh add kar do",
            tenant_id=tenant.id,
            phone_role="proprietor",
            actor_user_id=42,
            db=db,
        )
        db.commit()
        ev = _last_owner_added_event(db, tenant.id)
        assert ev is not None
        # All required keys per Q5.
        for key in (
            "entity_type", "entity_id", "raw_message", "source",
            "actor_user_id", "parse_strategy", "fuzzy_skipped",
        ):
            assert key in ev.payload, f"missing payload key: {key}"
        assert ev.payload["source"] == "whatsapp_owner"
        assert ev.payload["parse_strategy"] == "heuristic"
        assert ev.payload["actor_user_id"] == 42
        assert ev.payload["raw_message"].startswith("naya welder hai")
