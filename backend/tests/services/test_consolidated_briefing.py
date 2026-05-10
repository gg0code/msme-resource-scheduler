# tests/services/test_consolidated_briefing.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Tests for app/services/consolidated_briefing — the v6.3.19 morning-
# briefing flag/next_step selector. Covers the seven cases enumerated
# in the v6.3.19 next_step prompt step 5.
#
# WHO CALLS THIS FILE
# - pytest under the unit tier (mark "not integration"); invoked by
#   the v6.3.19 verification gate.
#
# WHAT THIS FILE CALLS
# - app.services.consolidated_briefing — module under test.
# - app.services.briefing_intelligence.signals.SignalResult —
#   constructed directly to drive the selector. SignalResult is NOT
#   modified; tests use the existing dataclass shape.

import pytest

from app.services import consolidated_briefing as cb
from app.services.briefing_intelligence.signals import SignalResult


def _make_signal(
    signal_id: str,
    *,
    category: str = "job",
    tier: int = 1,
    confidence: str = "high",
    severity: float = 1.0,
    message_hi_en: str = "Hinglish observation",
    message_en: str = "English observation",
) -> SignalResult:
    """Build a SignalResult with sensible defaults.

    Called by:    every test in this file that needs a SignalResult.
    Calls into:   SignalResult dataclass constructor.
    Side effects: none.

    Defaults are tier=1/confidence=high so tests that don't care about
    sort order get plausible values; tests that care override them.
    """
    return SignalResult(
        signal_id=signal_id,
        category=category,
        tier=tier,
        confidence=confidence,
        subject_entity_type="tenant",
        subject_entity_id=None,
        severity_score=severity,
        message_hi_en=message_hi_en,
        message_en=message_en,
        cooldown_days=1,
    )


def test_select_returns_blocker_signal_when_present():
    """A single blocker-class signal yields its flag + next_step."""
    signals = [
        _make_signal(
            "delayed_jobs_count",
            message_hi_en="2 jobs delayed hai",
            message_en="2 jobs are delayed",
        ),
    ]

    flag, nxt = cb.select_flag_and_next_step(signals, locale="hi_en")

    assert flag == "2 jobs delayed hai"
    assert nxt == cb._NEXT_STEP_TEMPLATES["delayed_jobs_count"]["hi_en"]


def test_select_returns_none_when_only_informational_signals():
    """Customer/tenancy/health signals do not qualify for the flag slot.

    Uses the actual informational signal_ids confirmed by the v6.3.19
    audit: recurring_customer_callout, revenue_at_risk,
    day_2_first_observation, day_7_marker, manager_silence.
    """
    signals = [
        _make_signal("recurring_customer_callout", category="customer"),
        _make_signal("revenue_at_risk", category="customer"),
        _make_signal("day_2_first_observation", category="tenancy"),
        _make_signal("day_7_marker", category="tenancy"),
        _make_signal("manager_silence", category="health"),
    ]

    flag, nxt = cb.select_flag_and_next_step(signals, locale="hi_en")

    assert flag is None
    assert nxt is None


def test_select_returns_none_when_signals_empty():
    """Empty input yields (None, None) without raising."""
    flag, nxt = cb.select_flag_and_next_step([], locale="en")

    assert flag is None
    assert nxt is None


def test_select_skips_informational_picks_next_blocker():
    """Iteration order is preserved — the first blocker after any
    informational entries wins. Demonstrates the selector does not
    re-sort.
    """
    signals = [
        _make_signal("recurring_customer_callout", category="customer"),
        _make_signal("manager_silence", category="health"),
        _make_signal(
            "idle_machine",
            category="machine",
            message_hi_en="Machine khali hai",
            message_en="Machine has been idle",
        ),
        # The selector must stop at idle_machine and never reach this
        # later blocker — confirms order is preserved, not re-sorted.
        _make_signal(
            "delayed_jobs_count",
            category="job",
            message_hi_en="(should not be picked)",
            message_en="(should not be picked)",
        ),
    ]

    flag, nxt = cb.select_flag_and_next_step(signals, locale="en")

    assert flag == "Machine has been idle"
    assert nxt == cb._NEXT_STEP_TEMPLATES["idle_machine"]["en"]


def test_select_uses_correct_locale_strings():
    """hi_en and en produce different message + next_step pairings."""
    signals = [
        _make_signal(
            "consecutive_absence",
            category="attendance",
            message_hi_en="Rakesh 2 din se gayab",
            message_en="Rakesh has been absent 2 days",
        ),
    ]

    flag_hi, nxt_hi = cb.select_flag_and_next_step(signals, locale="hi_en")
    flag_en, nxt_en = cb.select_flag_and_next_step(signals, locale="en")

    assert flag_hi == "Rakesh 2 din se gayab"
    assert flag_en == "Rakesh has been absent 2 days"
    assert nxt_hi == cb._NEXT_STEP_TEMPLATES["consecutive_absence"]["hi_en"]
    assert nxt_en == cb._NEXT_STEP_TEMPLATES["consecutive_absence"]["en"]
    assert nxt_hi != nxt_en


@pytest.mark.parametrize("bad_locale", ["fr", "", "HI_EN", "hi", "en_US"])
def test_select_invalid_locale_raises(bad_locale):
    """Any locale outside {'hi_en', 'en'} raises ValueError.

    Parametrised across common near-misses (case difference,
    truncation, en_US-style locale tag) to lock the contract.
    """
    signals = [_make_signal("delayed_jobs_count")]

    with pytest.raises(ValueError):
        cb.select_flag_and_next_step(signals, locale=bad_locale)


# ---------------------------------------------------------------------------
# v6.3.19 slice 2B — field computation helpers
# ---------------------------------------------------------------------------
# These tests exercise the three pure-SQL helpers added in slice 2B:
# _compute_jobs_starting, _compute_continuing, _compute_crew_expected.
# They use the in-memory SQLite `db` fixture from conftest.py and
# build minimal Tenant / Job / Employee / EmployeeLeave rows on demand.

from datetime import date, timedelta  # noqa: E402

from app.models.auth import Tenant  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.unavailability import EmployeeLeave  # noqa: E402


def _make_tenant_row(db, name: str = "Acme") -> Tenant:
    """Insert a minimal Tenant row and return it.

    Called by:    field-helper tests in this file.
    Calls into:   Tenant ORM, db.add / db.flush.
    Side effects: writes one row to the in-memory test DB.
    """
    t = Tenant(name=name, slug=name.lower().replace(" ", "-"))
    db.add(t)
    db.flush()
    return t


def _make_job(
    db, *, tenant_id: int, name: str, start: date, end: date,
    status: str = "in_progress", is_locked: bool = False,
) -> Job:
    """Insert a Job row with sensible defaults.

    Called by:    _compute_jobs_starting / _compute_continuing tests.
    Calls into:   Job ORM, db.add / db.flush.
    Side effects: writes one row.
    """
    j = Job(
        tenant_id=tenant_id,
        name=name,
        start_date=start,
        end_date=end,
        status=status,
        is_locked=is_locked,
    )
    db.add(j)
    db.flush()
    return j


def _make_employee(
    db, *, tenant_id: int, name: str,
    worker_type: str = "permanent", status: str = "active",
) -> Employee:
    """Insert an Employee row with sensible defaults.

    Called by:    _compute_crew_expected tests.
    Calls into:   Employee ORM, db.add / db.flush.
    Side effects: writes one row.
    """
    e = Employee(
        tenant_id=tenant_id,
        full_name=name,
        worker_type=worker_type,
        status=status,
    )
    db.add(e)
    db.flush()
    return e


def _make_leave(
    db, *, tenant_id: int, employee_id: int, start: date, end: date,
) -> EmployeeLeave:
    """Insert an EmployeeLeave row.

    Called by:    _compute_crew_expected tests.
    Calls into:   EmployeeLeave ORM, db.add / db.flush.
    Side effects: writes one row.
    """
    leave = EmployeeLeave(
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=start,
        end_date=end,
    )
    db.add(leave)
    db.flush()
    return leave


# ---------------------------------------------------------------------------
# _compute_jobs_starting
# ---------------------------------------------------------------------------

def test_jobs_starting_counts_only_today(db):
    """Three jobs with start_date=today, all non-terminal → returns 3.
    Jobs with other start_dates are ignored."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    for i in range(3):
        _make_job(db, tenant_id=t.id, name=f"Job {i}", start=today, end=today + timedelta(days=2))
    # Distractors: one yesterday, one tomorrow.
    _make_job(db, tenant_id=t.id, name="Yesterday", start=today - timedelta(days=1), end=today)
    _make_job(db, tenant_id=t.id, name="Tomorrow", start=today + timedelta(days=1), end=today + timedelta(days=3))

    assert cb._compute_jobs_starting(t.id, today, db) == 3


def test_jobs_starting_excludes_terminal_statuses(db):
    """completed and cancelled jobs starting today are not counted."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    _make_job(db, tenant_id=t.id, name="Live A", start=today, end=today, status="in_progress")
    _make_job(db, tenant_id=t.id, name="Live B", start=today, end=today, status="scheduled")
    _make_job(db, tenant_id=t.id, name="Done", start=today, end=today, status="completed")
    _make_job(db, tenant_id=t.id, name="Done CAPS", start=today, end=today, status="Completed")
    _make_job(db, tenant_id=t.id, name="Cancelled", start=today, end=today, status="cancelled")

    assert cb._compute_jobs_starting(t.id, today, db) == 2


def test_jobs_starting_filters_by_tenant(db):
    """Jobs in other tenants must not contribute to the count."""
    today = date(2026, 5, 9)
    t1 = _make_tenant_row(db, name="Tenant 1")
    t2 = _make_tenant_row(db, name="Tenant 2")
    _make_job(db, tenant_id=t1.id, name="T1 Job", start=today, end=today)
    _make_job(db, tenant_id=t2.id, name="T2 Job A", start=today, end=today)
    _make_job(db, tenant_id=t2.id, name="T2 Job B", start=today, end=today)

    assert cb._compute_jobs_starting(t1.id, today, db) == 1
    assert cb._compute_jobs_starting(t2.id, today, db) == 2


def test_jobs_starting_returns_zero_for_empty_tenant(db):
    """Tenant with no jobs returns 0 cleanly."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    assert cb._compute_jobs_starting(t.id, today, db) == 0


# ---------------------------------------------------------------------------
# _compute_continuing
# ---------------------------------------------------------------------------

def test_continuing_returns_empty_when_no_in_progress(db):
    """Zero in-progress jobs → empty string (caller decides rendering)."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    # Yesterday-only job has ended, today-only is starting (not continuing).
    _make_job(db, tenant_id=t.id, name="Done yesterday",
              start=today - timedelta(days=2), end=today - timedelta(days=1))
    _make_job(db, tenant_id=t.id, name="Starting today",
              start=today, end=today + timedelta(days=2))

    assert cb._compute_continuing(t.id, today, db) == ""


def test_continuing_singular_format(db):
    """Exactly one in_progress continuing job → '1 ({name})'."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    _make_job(db, tenant_id=t.id, name="Patel brochures",
              start=today - timedelta(days=2), end=today + timedelta(days=1),
              status="in_progress")

    assert cb._compute_continuing(t.id, today, db) == "1 (Patel brochures)"


def test_continuing_two_or_three_format(db):
    """Two or three in_progress → '{N} (n1, n2[, n3])'."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    # Two jobs, locked first to deterministically lead the names list.
    _make_job(db, tenant_id=t.id, name="Patel brochures",
              start=today - timedelta(days=3), end=today + timedelta(days=1),
              status="in_progress", is_locked=True)
    _make_job(db, tenant_id=t.id, name="Modi pamphlets",
              start=today - timedelta(days=2), end=today + timedelta(days=2),
              status="in_progress", is_locked=False)

    assert cb._compute_continuing(t.id, today, db) == "2 (Patel brochures, Modi pamphlets)"


def test_continuing_four_plus_format(db):
    """Four+ in_progress → '{N} (first three names and {N-3} more)'."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    # Five jobs all locked so ordering is start_date ASC then id ASC.
    for i, name in enumerate(["Alpha", "Bravo", "Charlie", "Delta", "Echo"]):
        _make_job(db, tenant_id=t.id, name=name,
                  start=today - timedelta(days=5 - i),  # Alpha oldest, Echo newest
                  end=today + timedelta(days=2),
                  status="in_progress", is_locked=True)

    assert cb._compute_continuing(t.id, today, db) == "5 (Alpha, Bravo, Charlie and 2 more)"


def test_continuing_locked_leads_unlocked(db):
    """is_locked DESC ordering: a locked job leads even when its
    start_date is later than an unlocked one."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    # Unlocked, older — would lead under start_date ASC alone.
    _make_job(db, tenant_id=t.id, name="Old unlocked",
              start=today - timedelta(days=10), end=today + timedelta(days=2),
              status="in_progress", is_locked=False)
    # Locked, newer — should still lead because is_locked DESC wins first.
    _make_job(db, tenant_id=t.id, name="Recent locked",
              start=today - timedelta(days=2), end=today + timedelta(days=2),
              status="in_progress", is_locked=True)

    assert cb._compute_continuing(t.id, today, db) == "2 (Recent locked, Old unlocked)"


def test_continuing_handles_titlecase_status(db):
    """'In Progress' (titlecase) and 'in_progress' both qualify."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    _make_job(db, tenant_id=t.id, name="Snake case",
              start=today - timedelta(days=2), end=today + timedelta(days=2),
              status="in_progress")
    _make_job(db, tenant_id=t.id, name="Title Case",
              start=today - timedelta(days=2), end=today + timedelta(days=2),
              status="In Progress")

    assert cb._compute_continuing(t.id, today, db) == "2 (Snake case, Title Case)"


# ---------------------------------------------------------------------------
# _compute_crew_expected
# ---------------------------------------------------------------------------

def test_crew_expected_subtracts_on_leave(db):
    """11 permanent active, 1 on leave today → '10 of 11 permanent'."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    employees = [_make_employee(db, tenant_id=t.id, name=f"Emp {i}") for i in range(11)]
    _make_leave(db, tenant_id=t.id, employee_id=employees[0].id,
                start=today - timedelta(days=1), end=today + timedelta(days=2))

    assert cb._compute_crew_expected(t.id, today, db) == "10 of 11 permanent"


def test_crew_expected_full_attendance(db):
    """No leave rows → expected == roster."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    for i in range(11):
        _make_employee(db, tenant_id=t.id, name=f"Emp {i}")

    assert cb._compute_crew_expected(t.id, today, db) == "11 of 11 permanent"


def test_crew_expected_excludes_inactive(db):
    """status != 'active' employees are not counted in roster."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    for i in range(8):
        _make_employee(db, tenant_id=t.id, name=f"Active {i}", status="active")
    for i in range(2):
        _make_employee(db, tenant_id=t.id, name=f"Inactive {i}", status="inactive")

    assert cb._compute_crew_expected(t.id, today, db) == "8 of 8 permanent"


def test_crew_expected_minority_contractors_silent(db):
    """contractor_count < roster → no gap-disclosure line."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    for i in range(11):
        _make_employee(db, tenant_id=t.id, name=f"Perm {i}", worker_type="permanent")
    for i in range(3):
        _make_employee(db, tenant_id=t.id, name=f"Cont {i}", worker_type="contractor")

    assert cb._compute_crew_expected(t.id, today, db) == "11 of 11 permanent"


def test_crew_expected_majority_contractors_surface_gap(db):
    """contractor_count >= roster → gap-disclosure line appended."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    for i in range(2):
        _make_employee(db, tenant_id=t.id, name=f"Perm {i}", worker_type="permanent")
    for i in range(5):
        _make_employee(db, tenant_id=t.id, name=f"Cont {i}", worker_type="contractor")

    assert cb._compute_crew_expected(t.id, today, db) == (
        "2 of 2 permanent (5 contractors not yet tracked)"
    )


def test_crew_expected_threshold_equality_surfaces_gap(db):
    """contractor_count == roster (the equality boundary) surfaces."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)
    for i in range(5):
        _make_employee(db, tenant_id=t.id, name=f"Perm {i}", worker_type="permanent")
    for i in range(5):
        _make_employee(db, tenant_id=t.id, name=f"Cont {i}", worker_type="contractor")

    assert cb._compute_crew_expected(t.id, today, db) == (
        "5 of 5 permanent (5 contractors not yet tracked)"
    )


def test_crew_expected_zero_employees_clean(db):
    """Tenant with no employees returns '0 of 0 permanent' without
    raising — caller decides whether to render anything."""
    today = date(2026, 5, 9)
    t = _make_tenant_row(db)

    assert cb._compute_crew_expected(t.id, today, db) == "0 of 0 permanent"


def test_crew_expected_filters_by_tenant(db):
    """Employees in other tenants must not contribute."""
    today = date(2026, 5, 9)
    t1 = _make_tenant_row(db, name="Tenant 1")
    t2 = _make_tenant_row(db, name="Tenant 2")
    for i in range(11):
        _make_employee(db, tenant_id=t1.id, name=f"T1 Emp {i}")
    for i in range(3):
        _make_employee(db, tenant_id=t2.id, name=f"T2 Emp {i}")

    assert cb._compute_crew_expected(t1.id, today, db) == "11 of 11 permanent"
    assert cb._compute_crew_expected(t2.id, today, db) == "3 of 3 permanent"


# ---------------------------------------------------------------------------
# v6.3.19 slice 2C — dispatch_morning / dispatch_evening
# ---------------------------------------------------------------------------
# These tests exercise the async dispatchers. They use the SQLite `db`
# fixture from conftest.py and a per-test `mock_meta_sender` fixture
# (defined in this file) that monkeypatches the imported
# _send_whatsapp_message in the consolidated_briefing module's namespace
# so calls are recorded instead of attempting a Meta API hit.

from datetime import datetime, timezone  # noqa: E402

from sqlalchemy import text as sa_text  # noqa: E402
from sqlalchemy.schema import DefaultClause  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.models.auth import RefreshToken, User  # noqa: E402
from app.models.auth import Tenant as TenantModel  # noqa: E402
from app.models.event import Event  # noqa: E402
from app.models.whatsapp import PhoneTenantMap  # noqa: E402


@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    """SQLite has no `now()` function. Several columns use
    server_default=text('now()') which fires at INSERT — patch them to
    CURRENT_TIMESTAMP for the dispatcher unit tests. Mirrors the
    autouse fixture in tests/test_signup_v6_4.py; kept local to this
    file to avoid changing the global conftest behaviour.
    """
    patched = []
    for table_attr in (
        TenantModel.__table__,
        User.__table__,
        RefreshToken.__table__,
        PhoneTenantMap.__table__,
        Event.__table__,
    ):
        for col in table_attr.columns:
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


@pytest.fixture
def mock_meta_sender(monkeypatch):
    """Replace _send_whatsapp_message in consolidated_briefing with a recorder.

    Yields a list that accumulates one dict per call:
        {"phone": phone_e164, "message": rendered_string}

    Tests assert against the recorded list. Patches the symbol in the
    consolidated_briefing namespace specifically — patching the source
    module would not affect already-imported references.
    """
    sent: list[dict] = []

    async def fake_send(phone: str, message: str) -> None:
        sent.append({"phone": phone, "message": message})

    monkeypatch.setattr(
        "app.services.consolidated_briefing._send_whatsapp_message",
        fake_send,
    )
    return sent


def _make_user_row(db, *, tenant_id: int, email: str, role: str = "proprietor") -> User:
    """Insert a User row with a hashed dummy password.

    Called by:    dispatcher tests that need a User to anchor a
                  PhoneTenantMap row (FK constraint).
    Calls into:   User ORM, hash_password.
    Side effects: writes one row.
    """
    u = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=hash_password("test-password"),
        role=role,
    )
    db.add(u)
    db.flush()
    return u


def _make_phone_map(
    db, *, tenant_id: int, user_id: int, phone: str,
    phone_role: str = "owner", is_active: bool = True,
    alert_preferences: dict | None = None,
) -> PhoneTenantMap:
    """Insert a PhoneTenantMap row with sensible defaults.

    Called by:    dispatcher tests that need recipients.
    Calls into:   PhoneTenantMap ORM.
    Side effects: writes one row.

    The alert_preferences default is a dict with both push_morning and
    push_evening set to True so a tenant in the test DB receives both
    pushes by default. Override per-test for opt-out scenarios.
    """
    if alert_preferences is None:
        alert_preferences = {"push_morning": True, "push_evening": True}
    m = PhoneTenantMap(
        tenant_id=tenant_id,
        user_id=user_id,
        phone_number=phone,
        is_active=is_active,
        phone_role=phone_role,
        alert_preferences=alert_preferences,
    )
    db.add(m)
    db.flush()
    return m


def _seed_tenant_with_owner(db, tenant_name: str = "Acme",
                             phone: str = "+919999000001",
                             *,
                             morning_enabled: bool = True,
                             evening_enabled: bool = True) -> tuple:
    """Build a tenant with one top-tier owner phone wired up.

    Called by:    most dispatcher tests as the baseline fixture.
    Calls into:   TenantModel ORM, _make_user_row, _make_phone_map.
    Side effects: writes 3 rows (Tenant, User, PhoneTenantMap).

    Returns the tuple (tenant, user, phone_map) for tests that need
    direct access to any of them.

    Sets briefing_*_enabled to True at INSERT time (not via post-flush
    UPDATE) — SQLite stores the server_default="false" string literal
    in non-Boolean storage, and SQLAlchemy's dirty-tracking sees the
    truthy-string "false" as equal to True so a post-flush assignment
    generates no UPDATE. Setting via the constructor bypasses the
    server_default entirely. Same for briefing_morning_time /
    briefing_evening_time / briefing_timezone — explicit values guard
    against any SQLite type-storage quirks affecting the dispatcher's
    timezone-aware due-tenant filter.
    """
    from datetime import time as _time
    t = TenantModel(
        name=tenant_name,
        slug=tenant_name.lower().replace(" ", "-"),
        briefing_morning_enabled=morning_enabled,
        briefing_evening_enabled=evening_enabled,
        briefing_morning_time=_time(7, 30),
        briefing_evening_time=_time(18, 30),
        briefing_timezone="Asia/Kolkata",
    )
    db.add(t)
    db.flush()
    u = _make_user_row(db, tenant_id=t.id, email=f"owner@{t.slug}.test")
    p = _make_phone_map(db, tenant_id=t.id, user_id=u.id, phone=phone)
    return t, u, p


def _now_at(hour: int = 7, minute: int = 30) -> datetime:
    """Build a fixed, naive datetime for tests that don't care about tz.

    Called by:    dispatcher tests that drive the `now` kwarg.
    Calls into:   nothing.
    Side effects: none.
    """
    return datetime(2026, 5, 9, hour, minute, 0)


# ---------------------------------------------------------------------------
# dispatch_morning
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_morning_sends_to_top_tier_recipient(db, mock_meta_sender):
    """Happy path: top-tier owner phone receives the rendered message."""
    t, _u, _p = _seed_tenant_with_owner(db)

    result = await cb.dispatch_morning(t.id, _now_at(), db)

    assert result.success is True
    assert result.skip_reason is None
    assert result.sent_count == 1
    assert len(mock_meta_sender) == 1
    assert mock_meta_sender[0]["phone"] == "+919999000001"
    # Hinglish template was used (default locale 'hi_en').
    assert "सुबह की briefing" in mock_meta_sender[0]["message"]


@pytest.mark.asyncio
async def test_dispatch_morning_skips_paused_tenant(db, mock_meta_sender):
    """Failure mode: paused tenants must not receive."""
    t, _u, _p = _seed_tenant_with_owner(db)
    # Pause through next week.
    t.push_paused_until = date(2026, 5, 16)
    db.flush()

    result = await cb.dispatch_morning(t.id, _now_at(), db)

    assert result.success is True
    assert result.skip_reason == "paused"
    assert result.sent_count == 0
    assert mock_meta_sender == []
    # Skip logged.
    assert (
        db.query(Event)
        .filter(Event.event_type == "push.morning_skipped_paused")
        .count() == 1
    )


@pytest.mark.asyncio
async def test_dispatch_morning_skips_when_morning_enabled_false(db, mock_meta_sender):
    """Tenant with briefing_morning_enabled=False is excluded from morning."""
    t, _u, _p = _seed_tenant_with_owner(db, morning_enabled=False)

    result = await cb.dispatch_morning(t.id, _now_at(), db)

    assert result.success is True
    assert result.skip_reason == "disabled"
    assert mock_meta_sender == []


@pytest.mark.asyncio
async def test_dispatch_morning_skips_when_no_top_tier_phone(db, mock_meta_sender):
    """Tenant whose only phone is a non-top-tier role: skip with reason."""
    from datetime import time as _time
    t = TenantModel(
        name="No-toptier",
        slug="no-toptier",
        briefing_morning_enabled=True,
        briefing_evening_enabled=True,
        briefing_morning_time=_time(7, 30),
        briefing_evening_time=_time(18, 30),
        briefing_timezone="Asia/Kolkata",
    )
    db.add(t)
    db.flush()
    u = _make_user_row(db, tenant_id=t.id, email="manager@test.test")
    _make_phone_map(
        db, tenant_id=t.id, user_id=u.id,
        phone="+919999000002", phone_role="viewer",
    )

    result = await cb.dispatch_morning(t.id, _now_at(), db)

    assert result.success is True
    assert result.skip_reason == "no_recipients"
    assert mock_meta_sender == []


@pytest.mark.asyncio
async def test_dispatch_morning_uses_passed_now_not_wall_clock(db, mock_meta_sender):
    """The dispatcher's idempotency key uses the passed `now`, not the
    wall clock. Calling twice with two different `now` values for the
    same calendar date should still dedup."""
    t, _u, _p = _seed_tenant_with_owner(db)

    # First call at 07:30, sends.
    r1 = await cb.dispatch_morning(t.id, _now_at(7, 30), db)
    assert r1.sent_count == 1

    # Second call same date at 07:31, idempotent skip.
    r2 = await cb.dispatch_morning(t.id, _now_at(7, 31), db)
    assert r2.skip_reason == "idempotent"
    assert r2.sent_count == 0
    # Still only one Meta send total.
    assert len(mock_meta_sender) == 1


@pytest.mark.asyncio
async def test_dispatch_morning_logs_event_on_success(db, mock_meta_sender):
    """A successful send writes one push.morning_sent event with the
    rendered_message and recipients in the payload."""
    t, _u, _p = _seed_tenant_with_owner(db)

    await cb.dispatch_morning(t.id, _now_at(), db)

    sent_events = (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .all()
    )
    assert len(sent_events) == 1
    payload = sent_events[0].payload
    assert payload["scheduled_for_date"] == "2026-05-09"
    assert payload["sent_count"] == 1
    assert payload["recipients"] == ["+919999000001"]
    assert "rendered_message" in payload
    assert payload["locale"] == "hi_en"


@pytest.mark.asyncio
async def test_dispatch_morning_meta_failure_does_not_raise(db, monkeypatch):
    """A Meta send exception is caught, logged, and the dispatcher
    returns DispatchResult with success=False — does not propagate."""
    t, _u, _p = _seed_tenant_with_owner(db)

    async def boom(phone: str, message: str) -> None:
        raise RuntimeError("Meta HTTP 500 — fake")

    monkeypatch.setattr(
        "app.services.consolidated_briefing._send_whatsapp_message",
        boom,
    )

    result = await cb.dispatch_morning(t.id, _now_at(), db)

    assert result.success is False
    assert result.sent_count == 0
    assert "Meta HTTP 500" in (result.error or "")
    # send_failed event recorded.
    assert (
        db.query(Event)
        .filter(Event.event_type == "push.morning_send_failed")
        .count() == 1
    )
    # No *_sent event — idempotency anchor does NOT fire on full failure.
    assert (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .count() == 0
    )


@pytest.mark.asyncio
async def test_dispatch_morning_defaults_to_hi_en_locale(db, mock_meta_sender):
    """Per slice 2C decision A1, all recipients receive the hi_en
    (Hinglish) variant. Per-recipient locale resolution is deferred
    until User.language_preference exists."""
    t, _u, _p = _seed_tenant_with_owner(db)

    await cb.dispatch_morning(t.id, _now_at(), db)

    msg = mock_meta_sender[0]["message"]
    # Devanagari header from MORNING_BRIEFING_HI.
    assert "सुबह की briefing" in msg
    # English header NOT used.
    assert "Morning briefing" not in msg


@pytest.mark.asyncio
async def test_dispatch_morning_renders_placeholder_when_no_blocker(db, mock_meta_sender):
    """Hybrid pattern: when no blocker-class signal fires, the rendered
    message uses the benign placeholder ('Aaj sab routine hai') for
    flag and ('Koi action nahi chahiye') for next_step."""
    t, _u, _p = _seed_tenant_with_owner(db)

    await cb.dispatch_morning(t.id, _now_at(), db)

    msg = mock_meta_sender[0]["message"]
    assert "Aaj sab routine hai" in msg
    assert "Koi action nahi chahiye" in msg


@pytest.mark.asyncio
async def test_dispatch_morning_no_jobs_renders_zero_continuing(db, mock_meta_sender):
    """Idle case: tenant with no jobs renders the template with
    jobs_starting=0 and continuing fallback '0' string."""
    t, _u, _p = _seed_tenant_with_owner(db)

    await cb.dispatch_morning(t.id, _now_at(), db)

    msg = mock_meta_sender[0]["message"]
    # MORNING_BRIEFING_HI has " - आज शुरू होने वाले काम: {jobs_starting}".
    assert "0" in msg


# ---------------------------------------------------------------------------
# dispatch_evening
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_evening_skips_when_evening_enabled_false(db, mock_meta_sender):
    """Evening dispatcher honours briefing_evening_enabled (independent
    of morning_enabled)."""
    # Morning ON, evening OFF — set at construction to avoid SQLite
    # truthy-string post-flush dirty-tracking quirk.
    t, _u, _p = _seed_tenant_with_owner(
        db, morning_enabled=True, evening_enabled=False,
    )

    result = await cb.dispatch_evening(t.id, _now_at(18, 30), db)

    assert result.success is True
    assert result.skip_reason == "disabled"
    assert mock_meta_sender == []


@pytest.mark.asyncio
async def test_dispatch_evening_idempotent_per_kind(db, mock_meta_sender):
    """Morning and evening dedup independently — sending morning does
    NOT block evening on the same calendar day."""
    t, _u, _p = _seed_tenant_with_owner(db)

    # Morning at 07:30.
    r_m = await cb.dispatch_morning(t.id, _now_at(7, 30), db)
    assert r_m.sent_count == 1

    # Evening at 18:30 on the same day must still send (different
    # event_type prefix).
    r_e = await cb.dispatch_evening(t.id, _now_at(18, 30), db)
    assert r_e.sent_count == 1

    # Two distinct sends recorded.
    assert len(mock_meta_sender) == 2


@pytest.mark.asyncio
async def test_dispatch_evening_logs_evening_specific_event(db, mock_meta_sender):
    """dispatch_evening writes push.evening_sent (not push.morning_sent)."""
    t, _u, _p = _seed_tenant_with_owner(db)

    await cb.dispatch_evening(t.id, _now_at(18, 30), db)

    morning_events = (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .count()
    )
    evening_events = (
        db.query(Event)
        .filter(Event.event_type == "push.evening_sent")
        .count()
    )
    assert morning_events == 0
    assert evening_events == 1


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dispatch_morning_filters_by_tenant(db, mock_meta_sender):
    """Recipients in other tenants must not receive a different
    tenant's morning push."""
    t1, _u1, _p1 = _seed_tenant_with_owner(db, tenant_name="Tenant 1",
                                            phone="+919999000001")
    t2, _u2, _p2 = _seed_tenant_with_owner(db, tenant_name="Tenant 2",
                                            phone="+919999000002")

    await cb.dispatch_morning(t1.id, _now_at(), db)

    assert len(mock_meta_sender) == 1
    assert mock_meta_sender[0]["phone"] == "+919999000001"


# ---------------------------------------------------------------------------
# v6.3.19 slice 2D-shadow — push_v2_tick + shadow mode smoke tests
# ---------------------------------------------------------------------------
# These verify the shadow infrastructure itself. The comprehensive
# 15-case failure-mode matrix lives in tests/integration/test_2d_dispatcher.py
# (slice 2D-tests). These smoke tests are intentionally narrow.

def test_offset_seconds_hash_stagger_spread():
    """Verify _offset_seconds_for produces the expected mod-60 spread.

    Tenant 1   -> 1   (small id, near-start of minute)
    Tenant 12  -> 12  (matches the brief's worked example)
    Tenant 60  -> 0   (modular collision — first wraparound)
    Tenant 120 -> 0   (further wraparound, same offset as 60)
    Tenant 31  -> 31  (mid-minute)
    Tenant 59  -> 59  (last second of stagger window)
    """
    assert cb._offset_seconds_for(1) == 1
    assert cb._offset_seconds_for(12) == 12
    assert cb._offset_seconds_for(60) == 0
    assert cb._offset_seconds_for(120) == 0
    assert cb._offset_seconds_for(31) == 31
    assert cb._offset_seconds_for(59) == 59


@pytest.mark.asyncio
async def test_push_v2_tick_empty_when_no_tenants_due(db, mock_meta_sender):
    """Tick at a minute that no tenant is configured for: returns
    empty list, no events written."""
    # Seed a tenant whose morning_push_time is 07:30 (default).
    _t, _u, _p = _seed_tenant_with_owner(db)

    # Tick at 09:15 — neither 07:30 morning nor 18:30 evening match.
    now = datetime(2026, 5, 9, 9, 15, 0, tzinfo=timezone.utc)
    results = await cb.push_v2_tick(now, db, apply_stagger=False)

    assert results == []
    assert mock_meta_sender == []
    # No events written.
    assert db.query(Event).count() == 0


@pytest.mark.asyncio
async def test_push_v2_tick_shadow_logs_without_sending(
    db, mock_meta_sender, monkeypatch,
):
    """When PUSH_V2_ENABLED=False (default), push_v2_tick logs
    push.shadow_log and does NOT call _send_whatsapp_message."""
    # Seed a tenant with morning_push_time = 07:30 (default).
    t, _u, _p = _seed_tenant_with_owner(db)

    # Force shadow mode via the config flag — explicit set even though
    # False is the default, so the test is robust to env tweaks.
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED",
        False,
    )

    # Tick at 07:30 UTC. The tenant's timezone is Asia/Kolkata which is
    # +5:30 — so 07:30 UTC is 13:00 IST. The tenant's push_time is 07:30
    # IST. To make the tick match, drive `now` as 07:30 IST minus
    # 5:30 = 02:00 UTC. Use timezone-aware datetimes throughout.
    from zoneinfo import ZoneInfo as _Z
    ist_730 = datetime(2026, 5, 9, 7, 30, 0, tzinfo=_Z("Asia/Kolkata"))
    now = ist_730.astimezone(timezone.utc)

    results = await cb.push_v2_tick(now, db, apply_stagger=False)

    # One due tenant -> one DispatchResult.
    assert len(results) == 1
    assert results[0].tenant_id == t.id
    assert results[0].kind == "morning"
    # Shadow mode: nothing sent.
    assert mock_meta_sender == []
    # push.shadow_log row written; no push.morning_sent row.
    shadow_logs = db.query(Event).filter(
        Event.event_type == "push.shadow_log",
    ).all()
    assert len(shadow_logs) == 1
    assert shadow_logs[0].payload["kind"] == "morning"
    assert shadow_logs[0].payload["stage"] == "sent"
    assert shadow_logs[0].payload["would_send"] is False
    assert (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .count() == 0
    )


@pytest.mark.asyncio
async def test_push_v2_tick_real_mode_sends_when_flag_enabled(
    db, mock_meta_sender, monkeypatch,
):
    """When PUSH_V2_ENABLED=True, push_v2_tick calls the real
    _send_whatsapp_message and writes push.morning_sent (NOT
    push.shadow_log)."""
    t, _u, _p = _seed_tenant_with_owner(db)

    # Flip flag.
    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED",
        True,
    )

    from zoneinfo import ZoneInfo as _Z
    ist_730 = datetime(2026, 5, 9, 7, 30, 0, tzinfo=_Z("Asia/Kolkata"))
    now = ist_730.astimezone(timezone.utc)

    results = await cb.push_v2_tick(now, db, apply_stagger=False)

    assert len(results) == 1
    assert results[0].sent_count == 1
    assert len(mock_meta_sender) == 1
    # push.morning_sent (real anchor) written; no shadow_log row.
    assert (
        db.query(Event)
        .filter(Event.event_type == "push.morning_sent")
        .count() == 1
    )
    assert (
        db.query(Event)
        .filter(Event.event_type == "push.shadow_log")
        .count() == 0
    )


@pytest.mark.asyncio
async def test_push_v2_tick_skips_disabled_direction(
    db, mock_meta_sender, monkeypatch,
):
    """Tenant with briefing_morning_enabled=False is excluded from
    _tenants_due_for, so push_v2_tick does not even consider it."""
    t, _u, _p = _seed_tenant_with_owner(db, morning_enabled=False)

    monkeypatch.setattr(
        "app.services.consolidated_briefing._settings.PUSH_V2_ENABLED",
        False,
    )

    from zoneinfo import ZoneInfo as _Z
    ist_730 = datetime(2026, 5, 9, 7, 30, 0, tzinfo=_Z("Asia/Kolkata"))
    now = ist_730.astimezone(timezone.utc)

    results = await cb.push_v2_tick(now, db, apply_stagger=False)

    # Tenant filtered out at the DB level — no result.
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_morning_shadow_kwarg_writes_shadow_log(
    db, mock_meta_sender,
):
    """Direct dispatch_morning(..., shadow=True) writes push.shadow_log
    and does NOT send. Mirrors the push_v2_tick behaviour without the
    tick wrapper."""
    t, _u, _p = _seed_tenant_with_owner(db)

    result = await cb.dispatch_morning(
        t.id, _now_at(), db, shadow=True,
    )

    assert result.success is True
    # event_id surfaces back so the debug endpoint can return it.
    assert result.event_id is not None
    # recipients populated even in shadow mode.
    assert result.recipients == ("+919999000001",)
    assert mock_meta_sender == []
    # Single shadow_log row.
    shadow_logs = db.query(Event).filter(
        Event.event_type == "push.shadow_log",
    ).all()
    assert len(shadow_logs) == 1
    assert shadow_logs[0].payload["stage"] == "sent"


def test_module_assertion_catches_missing_template():
    """The module-level guard fires when blocker-class set and template
    keys diverge. Asserts the equality expression directly rather than
    forcing a module reimport — same logic as the production guard,
    no import gymnastics.
    """
    # Production state must hold: every blocker has a template, no
    # extras.
    assert cb._BLOCKER_CLASS_SIGNALS == cb._NEXT_STEP_TEMPLATES.keys(), (
        "Production module-level guard must hold with no patches "
        "applied — adding a blocker_class id without a template "
        "should have failed at import."
    )

    # Simulate a developer adding a new blocker without a template.
    # The diff must surface exactly that id, proving the guard logic
    # would catch the omission at import time.
    fake_blocker_set = cb._BLOCKER_CLASS_SIGNALS | {"phantom_signal"}
    missing = fake_blocker_set - cb._NEXT_STEP_TEMPLATES.keys()
    assert missing == {"phantom_signal"}

    # Mirror direction: an extra template without a blocker entry must
    # also be detectable. The production assertion checks both
    # directions via .keys() equality.
    fake_template_keys = cb._NEXT_STEP_TEMPLATES.keys() | {"orphan_template"}
    extras = fake_template_keys - cb._BLOCKER_CLASS_SIGNALS
    assert extras == {"orphan_template"}
