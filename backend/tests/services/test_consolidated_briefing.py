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
