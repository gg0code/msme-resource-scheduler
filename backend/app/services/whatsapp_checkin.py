# whatsapp_checkin.py - Version 1.1
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Manager morning check-in flow for v5.15.
# Owns all logic for the two-phone WhatsApp loop:
#   MANAGER (7:00am) — input channel: attendance, machine status, work summary.
#   OWNER   (7:15am) — output channel: clean briefing built from manager inputs.
#
# WHO CALLS THIS FILE
#   app/services/whatsapp_alerts.py  - send_manager_checkin() calls build_checkin_prompt()
#   app/services/whatsapp_alerts.py  - send_owner_briefing_from_checkin() calls build_owner_briefing_from_checkin()
#   app/routers/whatsapp.py          - handle_manager_checkin_reply() called on inbound manager messages
#
# WHAT THIS FILE CALLS
#   app/models/employee.py           - Employee, EmployeeSkill (full_name, skills M2M via EmployeeSkill/Skill)
#   app/models/skill.py              - Skill (name field for skill matching)
#   app/models/machine.py            - Machine (name, machine_type)
#   app/models/whatsapp.py           - PhoneTenantMap (role lookup, phone numbers)
#   app/models/job.py                - Job (active orders for owner briefing)
#   app/database.py                  - SessionLocal (sync session for scheduler jobs)
#   app/services/whatsapp_responses.py - get_response(), Language
#   app/services/whatsapp_formatter.py - format_for_whatsapp()
#
# KEY DESIGN DECISIONS
#   1. All DB access uses sync Session — never AsyncSession. This file is called
#      from APScheduler jobs which use run_in_executor. Same pattern as whatsapp_alerts.py.
#   2. Name matching is fuzzy-tolerant: lowercase + strip. No external library.
#      "suresh nahi aaya" matches Employee.full_name="Suresh Patel" via first-word match.
#   3. Absent list is stored in Redis under key whatsapp:checkin:{tenant_id}:{date}
#      so the 7:15am owner briefing can read what the manager reported at 7:00am.
#      TTL = 24 hours. No DB writes for transient checkin state.
#   4. Substitute suggestion uses skill match only — no availability % calculation.
#      At Day 1 the tenant has no shift data. Simple is correct here.
#   5. Machine downtime from manager reply writes to unavailability table via
#      whatsapp_actions.py — this file only detects and parses, never writes directly.
#   6. Owner briefing is generated FROM checkin state, not from scheduled data alone.
#      If no manager checkin exists for today, briefing falls back to scheduled data
#      (existing _build_morning_briefing logic in whatsapp_alerts.py).

import json
import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import SessionLocal
from app.models.employee import Employee, EmployeeSkill
from app.models.event import Event
from app.models.job import Job
from app.models.machine import Machine
from app.models.skill import Skill
from app.models.whatsapp import PhoneTenantMap
from app.services.whatsapp_formatter import format_for_whatsapp
from app.services.whatsapp_responses import Language, get_response
from app.services.whatsapp_session import redis_client, _mock_sessions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# REDIS KEY HELPERS
# ---------------------------------------------------------------------------

# Checkin state key: stores absent employee IDs + machine downtime flags for today.
# Format: whatsapp:checkin:{tenant_id}:{iso_date}
# TTL: 86400 seconds (24 hours). Automatically expires — no cleanup needed.
CHECKIN_KEY_PREFIX = "whatsapp:checkin"
CHECKIN_TTL_SECONDS = 86400


def _checkin_key(tenant_id: int, for_date: date) -> str:
    """
    Build the Redis key for today's manager checkin state.

    Called by:   save_checkin_state(), get_checkin_state()
    Calls:       nothing
    Args:
        tenant_id: The tenant this checkin belongs to.
        for_date:  The date of the checkin (usually today).
    Returns:
        Redis key string e.g. "whatsapp:checkin:12:2026-04-10"
    Side effects: None - pure function
    """
    return f"{CHECKIN_KEY_PREFIX}:{tenant_id}:{for_date.isoformat()}"


# ---------------------------------------------------------------------------
# CHECKIN STATE — Redis read/write
# ---------------------------------------------------------------------------

def save_checkin_state(
    tenant_id: int,
    absent_ids: list[int],
    down_machine_ids: list[int],
    for_date: date,
    db: Optional[Session] = None,
    manager_user_id: Optional[int] = None,
) -> None:
    """
    Persist today's manager checkin state to Redis.

    Called by:   handle_manager_checkin_reply() after parsing manager message.
    Calls:       redis_client (whatsapp_session.py pool) or _mock_sessions dict.
                 db.add(Event(...)) when db is provided (v6.3.11-prereq).
    Args:
        tenant_id:       Tenant this checkin belongs to.
        absent_ids:      List of Employee.id values marked absent today.
        down_machine_ids: List of Machine.id values flagged as down today.
        for_date:        Date of the checkin.
        db:              Optional sync Session. When provided, an
                         attendance.recorded Event row is appended for
                         downstream pattern-aware briefing intelligence.
                         Caller owns lifecycle. Pre-v6.3.11 callers that
                         did Redis-only writes still work unchanged.
        manager_user_id: Optional User.id of the manager who reported the
                         check-in. Stored as Event.actor_user_id. None is
                         allowed (e.g. unmapped phone) — Event.actor_user_id
                         is nullable.
    Returns:
        None
    Side effects:
        Writes JSON blob to Redis with 24-hour TTL (or _mock_sessions in
        mock mode). When db is provided, also writes one Event row with
        event_type='attendance.recorded'. Event-write failures are logged
        but never raised — Redis is the source of truth for "did the
        check-in succeed".
    """
    key = _checkin_key(tenant_id, for_date)
    payload = json.dumps({
        "absent_ids": absent_ids,
        "down_machine_ids": down_machine_ids,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    })
    try:
        if redis_client is not None:
            redis_client.setex(key, CHECKIN_TTL_SECONDS, payload)
        else:
            _mock_sessions[key] = payload
        logger.info(
            "Checkin state saved for tenant %s on %s: %d absent, %d machines down.",
            tenant_id, for_date.isoformat(), len(absent_ids), len(down_machine_ids),
        )
    except Exception as exc:
        logger.error("Failed to save checkin state for tenant %s: %s", tenant_id, exc)

    # v6.3.11-prereq: persist check-in as attendance.recorded event
    # for downstream pattern-aware briefing intelligence (Section A.7
    # of v6_3_11_signals_spec.md). Failure is logged but never raised —
    # Redis is the source of truth for the live check-in flow.
    if db is not None:
        try:
            event = Event(
                tenant_id=tenant_id,
                event_type="attendance.recorded",
                entity_type="checkin",
                entity_id=None,
                actor_user_id=manager_user_id,
                source="whatsapp",
                payload={
                    "for_date": for_date.isoformat(),
                    "absent_employee_ids": list(absent_ids),
                    "down_machine_ids": list(down_machine_ids),
                },
            )
            db.add(event)
            db.commit()
        except Exception:
            logger.error(
                "Failed to persist attendance.recorded event for tenant %s on %s.",
                tenant_id, for_date.isoformat(), exc_info=True,
            )
            try:
                db.rollback()
            except Exception:
                pass


def get_checkin_state(tenant_id: int, for_date: date) -> dict:
    """
    Retrieve today's manager checkin state from Redis.

    Called by:   build_owner_briefing_from_checkin()
    Calls:       redis_client or _mock_sessions dict.
    Args:
        tenant_id: Tenant to look up.
        for_date:  Date to retrieve state for.
    Returns:
        Dict with keys 'absent_ids', 'down_machine_ids', 'recorded_at'.
        Returns empty state dict if no checkin recorded yet today.
    Side effects: None - read only
    """
    key = _checkin_key(tenant_id, for_date)
    empty: dict = {"absent_ids": [], "down_machine_ids": [], "recorded_at": None}
    try:
        raw = (
            redis_client.get(key)
            if redis_client is not None
            else _mock_sessions.get(key)
        )
        if not raw:
            return empty
        return json.loads(raw)
    except Exception as exc:
        logger.error("Failed to read checkin state for tenant %s: %s", tenant_id, exc)
        return empty


# ---------------------------------------------------------------------------
# NAME MATCHING
# ---------------------------------------------------------------------------

# Hinglish absence markers — if any appear near a name, treat as absent.
# Kept here (not in whatsapp_intent.py) because this is checkin-specific parsing,
# not generic intent detection.
ABSENT_MARKERS: tuple[str, ...] = (
    "nahi aaya", "nahi aya", "absent", "nahi hai", "nai aaya",
    "chutti", "leave", "nahi aayega", "nahi rahega", "nhi aaya",
)


def _normalise(text: str) -> str:
    """
    Lowercase and strip a string for fuzzy matching.

    Called by:   parse_attendance()
    Calls:       nothing
    Args:
        text: Any string.
    Returns:
        Lowercased, stripped string.
    Side effects: None - pure function
    """
    return text.lower().strip()


def _name_tokens(name: str) -> list[str]:
    """
    Split an employee name into lowercase tokens for partial matching.

    Called by:   _match_employee_name()
    Calls:       nothing
    Args:
        name: Employee full name e.g. "Suresh Kumar".
    Returns:
        List of tokens e.g. ["suresh", "kumar"]
    Side effects: None - pure function
    """
    return [t for t in _normalise(name).split() if len(t) > 1]


def _match_employee_name(word: str, employees: list[Employee]) -> Optional[Employee]:
    """
    Find an employee whose name contains the given word as a token.

    Matches on any token in the full name. "suresh" matches "Suresh Kumar".
    First match wins — stops at first hit to avoid ambiguity on common first names.

    Called by:   parse_attendance()
    Calls:       _name_tokens()
    Args:
        word:      Single word extracted from manager message.
        employees: All active employees for this tenant (pre-fetched, no N+1).
    Returns:
        Matching Employee instance, or None if no match found.
    Side effects: None - pure function
    """
    needle = _normalise(word)
    for emp in employees:
        if needle in _name_tokens(emp.full_name):
            return emp
    return None


# ---------------------------------------------------------------------------
# ATTENDANCE PARSING
# ---------------------------------------------------------------------------

def parse_attendance(
    message: str,
    tenant_id: int,
    db: Session,
) -> dict:
    """
    Parse a manager's free-text attendance message and identify absent employees.

    Strategy: scan every word in the message for employee name matches.
    If an absent marker appears anywhere in the message, treat matched names
    as absent. If no absent marker, treat matched names as present confirmation.
    Unmatched words are ignored — no false positives.

    Called by:   handle_manager_checkin_reply() in whatsapp_alerts.py
    Calls:       _match_employee_name(), _name_tokens()
    Args:
        message:   Raw inbound manager message text.
        tenant_id: Tenant this message belongs to.
        db:        Sync SQLAlchemy Session — caller owns lifecycle.
    Returns:
        Dict with keys:
          'absent':   list of Employee objects identified as absent
          'present':  list of Employee objects identified as present
          'unknown':  list of name strings that could not be matched
    Side effects: None - read only DB query
    """
    # Load all active employees for this tenant once — no N+1
    # Employee model uses status='Active' not is_active boolean
    # selectinload(Employee.skills) pre-fetches M2M skills in one extra query —
    # avoids N+1 when _get_employee_skill_name() accesses emp.skills per employee.
    employees: list[Employee] = (
        db.query(Employee)
        .options(selectinload(Employee.skills).selectinload(EmployeeSkill.skill))
        .filter(
            Employee.tenant_id == tenant_id,
            Employee.status == "Active",
        )
        .all()
    )

    message_lower = _normalise(message)
    has_absent_marker = any(marker in message_lower for marker in ABSENT_MARKERS)

    absent: list[Employee] = []
    present: list[Employee] = []
    unknown: list[str] = []
    matched_ids: set[int] = set()

    for word in message.split():
        if len(word) < 3:
            continue
        emp = _match_employee_name(word, employees)
        if emp and emp.id not in matched_ids:
            matched_ids.add(emp.id)
            if has_absent_marker:
                absent.append(emp)
            else:
                present.append(emp)
        elif not emp and len(word) > 3 and word.isalpha():
            unknown.append(word)

    logger.info(
        "Attendance parsed for tenant %s: %d absent, %d present, %d unknown words.",
        tenant_id, len(absent), len(present), len(unknown),
    )
    return {"absent": absent, "present": present, "unknown": unknown}


# ---------------------------------------------------------------------------
# SUBSTITUTE SUGGESTION
# ---------------------------------------------------------------------------

def find_substitute(
    absent_employee: Employee,
    tenant_id: int,
    db: Session,
    already_absent_ids: list[int],
) -> Optional[Employee]:
    """
    Find the best available substitute for an absent employee by skill match.

    Skills are M2M via EmployeeSkill -> Skill. Gets absent employee's first
    skill, then finds another active employee with the same skill.
    Excludes the absent employee and anyone already marked absent today.
    Returns the first match — no ranking by availability_pct at Day 1
    because new tenants have no shift data yet.

    Called by:   handle_manager_checkin_reply(), build_owner_briefing_from_checkin()
    Calls:       EmployeeSkill, Skill (M2M join)
    Args:
        absent_employee:    The Employee who is absent.
        tenant_id:          Tenant scope — never cross-tenant.
        db:                 Sync SQLAlchemy Session — caller owns lifecycle.
        already_absent_ids: IDs already confirmed absent today — excluded.
    Returns:
        A substitute Employee, or None if no match found.
    Side effects: None - read only DB query
    """
    # Get absent employee's first skill via M2M relationship
    # skills relationship is already loaded via selectinload on Employee query
    first_skill_name: Optional[str] = None
    for emp_skill in absent_employee.skills:
        if emp_skill.skill and emp_skill.skill.name:
            first_skill_name = emp_skill.skill.name
            break

    if not first_skill_name:
        # Employee has no skills recorded — cannot suggest substitute
        return None

    exclude_ids = already_absent_ids + [absent_employee.id]

    # Find another active employee with the same skill via M2M join — no N+1
    substitute: Optional[Employee] = (
        db.query(Employee)
        .join(EmployeeSkill, EmployeeSkill.employee_id == Employee.id)
        .join(Skill, Skill.id == EmployeeSkill.skill_id)
        .filter(
            Employee.tenant_id == tenant_id,
            Employee.status == "Active",
            Skill.name == first_skill_name,
            Employee.id.notin_(exclude_ids),
        )
        .first()
    )
    return substitute


def _get_employee_skill_name(employee: Employee) -> Optional[str]:
    """
    Get the first skill name for an employee from the M2M relationship.

    Skills are stored in EmployeeSkill -> Skill, not as a column on Employee.
    Used by build_absent_reply() and build_owner_briefing_from_checkin()
    to display the skill context in messages.

    Called by:   build_absent_reply(), build_owner_briefing_from_checkin()
    Calls:       nothing (reads already-loaded relationship)
    Args:
        employee: Employee instance with skills relationship loaded.
    Returns:
        First skill name string, or None if no skills recorded.
    Side effects: None - pure function
    """
    for emp_skill in employee.skills:
        if emp_skill.skill and emp_skill.skill.name:
            return emp_skill.skill.name
    return None


# ---------------------------------------------------------------------------
# MESSAGE BUILDERS — manager phone (input channel)
# ---------------------------------------------------------------------------

def build_checkin_prompt(lang: Language) -> str:
    """
    Build the 7:00am manager check-in prompt message.

    Sent by APScheduler at 7:00am IST to all manager phones.
    Three questions in sequence — attendance, machines, work today.
    Single message, plain text, no markdown.

    Called by:   send_manager_checkin() in whatsapp_alerts.py
    Calls:       format_for_whatsapp() in whatsapp_formatter.py
    Args:
        lang: Detected or default language for this manager's phone.
              Uses 'en' as safe default if unknown.
    Returns:
        Formatted plain-text string ready to send via WhatsApp.
    Side effects: None - pure function
    """
    messages: dict[Language, str] = {
        "hindi": (
            "सुप्रभात! ZetaOps चेक-इन\n\n"
            "1. आज कौन-कौन आया? (गैरहाजिर लोगों के नाम बताएं)\n"
            "2. सभी मशीनें ठीक हैं? (खराब हो तो नाम बताएं)\n"
            "3. आज के मुख्य काम क्या हैं?"
        ),
        "hinglish": (
            "Good morning! ZetaOps check-in\n\n"
            "1. Aaj kaun kaun aaya? (jo nahi aaye unke naam batao)\n"
            "2. Machines theek hain? (koi band ho toh naam batao)\n"
            "3. Aaj ke main kaam kya hain?"
        ),
        "en": (
            "Good morning! ZetaOps daily check-in\n\n"
            "1. Who is present today? (mention anyone absent)\n"
            "2. Are all machines running? (name any that are down)\n"
            "3. What are the main tasks for today?"
        ),
    }
    text = messages.get(lang, messages["en"])
    return format_for_whatsapp(text)


def build_absent_reply(
    absent_employee: Employee,
    substitute: Optional[Employee],
    lang: Language,
) -> str:
    """
    Build the immediate reply to manager after an absent employee is detected.

    Sent immediately after parse_attendance() identifies an absent worker.
    One reply per absent employee — caller loops if multiple are absent.

    Called by:   handle_manager_checkin_reply() in whatsapp_alerts.py
    Calls:       format_for_whatsapp() in whatsapp_formatter.py
    Args:
        absent_employee: The Employee confirmed absent.
        substitute:      Best available substitute, or None if none found.
        lang:            Language for this manager's phone.
    Returns:
        Formatted plain-text WhatsApp reply string.
    Side effects: None - pure function
    """
    name = absent_employee.full_name
    skill = _get_employee_skill_name(absent_employee) or "general"

    if substitute:
        sub_name = substitute.full_name
        sub_type = substitute.worker_type or "permanent"
        messages: dict[Language, str] = {
            "hindi": (
                f"{name} अनुपस्थित है ({skill}).\n"
                f"सुझाव: {sub_name} ({sub_type}) उपलब्ध है और यही काम कर सकते हैं."
            ),
            "hinglish": (
                f"{name} absent hai ({skill}).\n"
                f"Substitute: {sub_name} ({sub_type}) available hai, same skill hai."
            ),
            "en": (
                f"{name} is absent ({skill}).\n"
                f"Suggested substitute: {sub_name} ({sub_type}) — same skill available."
            ),
        }
    else:
        messages = {
            "hindi": (
                f"{name} अनुपस्थित है ({skill}).\n"
                f"चेतावनी: इस काम के लिए कोई विकल्प नहीं मिला."
            ),
            "hinglish": (
                f"{name} absent hai ({skill}).\n"
                f"Warning: Koi substitute nahi mila is skill ke liye."
            ),
            "en": (
                f"{name} is absent ({skill}).\n"
                f"Warning: No substitute found with matching skill."
            ),
        }

    text = messages.get(lang, messages["en"])
    return format_for_whatsapp(text)


def build_checkin_complete_reply(lang: Language) -> str:
    """
    Build the closing message sent to manager after check-in is recorded.

    Sent once all inputs are processed. Tells manager the owner will be briefed.

    Called by:   handle_manager_checkin_reply() in whatsapp_alerts.py
    Calls:       format_for_whatsapp() in whatsapp_formatter.py
    Args:
        lang: Language for this manager's phone.
    Returns:
        Formatted plain-text WhatsApp reply string.
    Side effects: None - pure function
    """
    messages: dict[Language, str] = {
        "hindi": "समझ गया. मालिक को 7:15 बजे सारांश भेज रहा हूं.",
        "hinglish": "Got it. Sahab ko 7:15 pe summary bhej raha hoon.",
        "en": "Got it. Sending the owner a briefing at 7:15am.",
    }
    text = messages.get(lang, messages["en"])
    return format_for_whatsapp(text)


# ---------------------------------------------------------------------------
# MESSAGE BUILDERS — owner phone (output channel)
# ---------------------------------------------------------------------------

def build_owner_briefing_from_checkin(
    tenant_id: int,
    db: Session,
    lang: Language,
) -> Optional[str]:
    """
    Build the 7:15am owner briefing from today's manager check-in state.

    Reads checkin state from Redis. If no checkin recorded today, returns None
    so the caller (whatsapp_alerts.py) can fall back to the existing scheduled
    data briefing (_build_morning_briefing).

    Format:
      - Who is present / absent
      - Skill gap warning if no substitute exists
      - Machine downtime if any reported
      - Active job count
      - One suggested action (most urgent absent skill gap)

    Called by:   send_owner_briefing_from_checkin() in whatsapp_alerts.py
    Calls:       get_checkin_state(), format_for_whatsapp()
    Args:
        tenant_id: Tenant to build briefing for.
        db:        Sync SQLAlchemy Session — caller owns lifecycle.
        lang:      Language for this owner's phone.
    Returns:
        Formatted briefing string, or None if no checkin data exists today.
    Side effects: None - read only (Redis + DB reads)
    """
    today = date.today()
    state = get_checkin_state(tenant_id, for_date=today)

    # No manager checkin yet — caller falls back to scheduled data briefing
    if not state["absent_ids"] and not state["down_machine_ids"] and not state["recorded_at"]:
        logger.info(
            "No checkin state found for tenant %s on %s — owner briefing skipped.",
            tenant_id, today.isoformat(),
        )
        return None

    today_str = today.strftime("%d %b %Y")

    # Fetch absent employees in one query — no N+1
    # selectinload pre-fetches skills so _get_employee_skill_name() has no lazy loads
    absent_employees: list[Employee] = []
    if state["absent_ids"]:
        absent_employees = (
            db.query(Employee)
            .options(selectinload(Employee.skills).selectinload(EmployeeSkill.skill))
            .filter(
                Employee.tenant_id == tenant_id,
                Employee.id.in_(state["absent_ids"]),
            )
            .all()
        )

    # Fetch down machines in one query — no N+1
    down_machines: list[Machine] = []
    if state["down_machine_ids"]:
        down_machines = (
            db.query(Machine)
            .filter(
                Machine.tenant_id == tenant_id,
                Machine.id.in_(state["down_machine_ids"]),
            )
            .all()
        )

    # Active job count for context
    active_job_count: int = (
        db.query(func.count(Job.id))
        .filter(
            Job.tenant_id == tenant_id,
            Job.status.in_(["pending", "in_progress"]),
        )
        .scalar()
        or 0
    )

    # Find skill gaps — absent employees with no substitute
    skill_gaps: list[str] = []
    for emp in absent_employees:
        sub = find_substitute(emp, tenant_id, db, state["absent_ids"])
        skill_name = _get_employee_skill_name(emp)
        if not sub and skill_name:
            skill_gaps.append(skill_name)

    # Build briefing lines
    lines: list[str] = [f"ZetaOps briefing — {today_str}"]

    if absent_employees:
        names = ", ".join(e.full_name for e in absent_employees)
        lines.append(f"Absent: {names}")
    else:
        lines.append("Attendance: All present")

    if skill_gaps:
        gaps = ", ".join(set(skill_gaps))
        lines.append(f"Skill gap: No cover for {gaps} — action needed")

    if down_machines:
        machine_names = ", ".join(m.name for m in down_machines)
        lines.append(f"Machines down: {machine_names}")

    lines.append(f"Active orders: {active_job_count}")

    # Single suggested action — most critical gap
    if skill_gaps:
        lines.append(f"Suggested action: Arrange cover for {skill_gaps[0]} today")
    elif down_machines:
        lines.append(f"Suggested action: Check repair status of {down_machines[0].name}")
    else:
        lines.append("No critical gaps today")

    briefing = "\n".join(lines)
    return format_for_whatsapp(briefing)


# ---------------------------------------------------------------------------
# INBOUND MESSAGE HANDLER — called from whatsapp router
# ---------------------------------------------------------------------------

def handle_manager_checkin_reply(
    message: str,
    tenant_id: int,
    phone_number: str,
    lang: Language,
    db: Session,
) -> list[str]:
    """
    Process a manager's inbound reply during the morning check-in window.

    Called from whatsapp.py router when the sender has phone_role='manager'
    and the time is between 7:00am and 9:00am IST (check-in window).
    Outside that window, messages route to the normal AI pipeline.

    Flow:
      1. Parse attendance from message text
      2. For each absent employee: find substitute, build reply
      3. Save checkin state to Redis (absent IDs + machine IDs)
      4. Return closing confirmation reply

    Machine downtime detection is handled upstream in whatsapp_intent.py
    (detect_write_intent). If a machine downtime action is detected, it is
    executed via whatsapp_actions.py before this function is called.
    This function only handles attendance — not machine state.

    Called by:   app/routers/whatsapp.py — on inbound message from manager role
    Calls:       parse_attendance(), find_substitute(), build_absent_reply(),
                 build_checkin_complete_reply(), save_checkin_state()
    Args:
        message:      Raw inbound message text from manager.
        tenant_id:    Tenant scope.
        phone_number: Manager's phone in E.164 format.
        lang:         Detected language of message.
        db:           Sync SQLAlchemy Session — caller owns lifecycle.
    Returns:
        List of reply strings to send in sequence.
        May be multiple messages (one per absent employee + closing message).
    Side effects:
        Writes checkin state to Redis via save_checkin_state().
    """
    replies: list[str] = []
    today = date.today()

    # Parse attendance from message
    result = parse_attendance(message, tenant_id, db)
    absent_list: list[Employee] = result["absent"]
    absent_ids: list[int] = [e.id for e in absent_list]

    # One reply per absent employee with substitute suggestion
    for emp in absent_list:
        sub = find_substitute(emp, tenant_id, db, absent_ids)
        reply = build_absent_reply(emp, sub, lang)
        replies.append(reply)

    # Resolve the manager's User.id from their WhatsApp number so the
    # attendance.recorded event written by save_checkin_state can attribute
    # who reported the check-in. Lookup is best-effort — if no mapping
    # exists (rare; possible in dev/test), the event is still written with
    # actor_user_id=None (Event.actor_user_id is nullable by design).
    mapping = (
        db.query(PhoneTenantMap)
        .filter(
            PhoneTenantMap.phone_number == phone_number,
            PhoneTenantMap.tenant_id == tenant_id,
        )
        .first()
    )
    manager_user_id = mapping.user_id if mapping else None

    # Persist checkin state — machine IDs come from pending action context
    # Machine downtime is written by whatsapp_actions.py before we reach here.
    # We store empty machine list here; whatsapp_alerts.py enriches from
    # unavailability table when building the owner briefing.
    save_checkin_state(
        tenant_id=tenant_id,
        absent_ids=absent_ids,
        down_machine_ids=[],
        for_date=today,
        db=db,
        manager_user_id=manager_user_id,
    )

    # Closing confirmation
    replies.append(build_checkin_complete_reply(lang))

    logger.info(
        "Manager checkin handled for tenant %s, phone %s: %d absent employees.",
        tenant_id, phone_number[-4:], len(absent_list),
    )
    return replies