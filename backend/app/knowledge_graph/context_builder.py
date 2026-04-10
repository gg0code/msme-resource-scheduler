# context_builder.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Assembles the full context block that is appended to every AI system prompt.
# This is the bridge between the static schema description (schema_context.py),
# the live tenant state (DB snapshot), and the industry knowledge (RAG files).
#
# The context block answers three questions for the AI before it processes
# any user message:
#   1. WHAT IS THE DB STRUCTURE? (from schema_context.py — static)
#   2. WHAT DOES THIS TENANT LOOK LIKE RIGHT NOW? (live DB snapshot)
#   3. WHAT ARE THE INDUSTRY NORMS FOR THIS VERTICAL? (from rag_service.py)
#
# WHO CALLS THIS FILE
#   app/services/ai_service.py — _build_system_prompt() appends the result
#                                of build_context_block() to the system prompt
#
# WHAT THIS FILE CALLS
#   app/knowledge_graph/schema_context.py - SCHEMA_CONTEXT constant
#   app/services/rag_service.py           - load_rag_context()
#   app/models/employee.py               - Employee (live headcount query)
#   app/models/machine.py                - Machine (live machine count query)
#   app/models/job.py                    - Job (active job count query)
#   app/models/employee.py              - EmployeeSkill (skill list query)
#   app/models/skill.py                 - Skill (skill names)
#
# KEY DESIGN DECISIONS
#   1. LIVE SNAPSHOT IS SMALL — we fetch counts and skill names only, not
#      full records. The AI tools (get_employee_availability etc.) handle
#      detailed data retrieval. The snapshot gives the AI orientation:
#      "this tenant has 12 employees, 3 machines, 6 active jobs".
#   2. GRACEFUL DEGRADATION — if any DB query fails, we log the error and
#      return whatever we have. A partial context is better than no context.
#      The system prompt always works even if the snapshot is empty.
#   3. SYNC SESSION ONLY — this is called from run_ai_chat() which already
#      runs in a thread pool executor (via run_in_executor in whatsapp_bridge).
#      We use the sync Session passed in — never create a new one here.
#   4. TOKEN BUDGET — context block must stay under ~1500 tokens to leave
#      room for conversation history and tool results within Groq's limits.
#      Schema: ~600 tokens. Snapshot: ~100 tokens. RAG: ~600 tokens. Total: ~1300.
#   5. INDUSTRY-AGNOSTIC SCHEMA — SCHEMA_CONTEXT describes the DB, not the
#      industry. Industry knowledge comes from RAG files only. This separation
#      means schema_context.py never needs to know about printing vs fabrication.

import logging
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

logger = logging.getLogger(__name__)


def build_context_block(
    tenant_id: int,
    db: Session,
    industry_type: str = "printing",
) -> str:
    """
    Assemble the full context block for injection into the AI system prompt.

    Combines three sources:
      1. DB schema description (static, from schema_context.py)
      2. Live tenant snapshot (dynamic, queried from DB)
      3. Industry RAG knowledge (from rag_data/{tenant_id}/*.txt files)

    Called by:   app/services/ai_service.py — _build_system_prompt()
    Calls:       SCHEMA_CONTEXT (schema_context.py),
                 _build_tenant_snapshot() (this file),
                 load_rag_context() (rag_service.py)
    Args:
        tenant_id:     Integer ID of the tenant making the request.
                       Used for DB queries and RAG file loading.
                       NEVER cross-tenant — always filter all queries by this.
        db:            Sync SQLAlchemy Session — caller owns the lifecycle.
                       Do not create or close sessions inside this function.
        industry_type: Industry slug from tenant record. Used to label the
                       RAG context section header. Valid: 'printing',
                       'manufacturing', 'fabrication', 'field_service'.
    Returns:
        Single string ready to append to the system prompt.
        Contains three clearly delimited sections.
        Returns a minimal string (schema only) if DB or RAG queries fail.
    Side effects:
        Read-only DB queries — no writes, no commits, no session lifecycle.
        Read-only filesystem access via load_rag_context().
    """
    # Import here to avoid circular imports at module load time.
    # schema_context.py has no imports so this is safe.
    from app.knowledge_graph.schema_context import SCHEMA_CONTEXT
    from app.services.rag_service import load_rag_context

    sections: list[str] = []

    # -----------------------------------------------------------------------
    # SECTION 1 — DB Schema (static, always included)
    # -----------------------------------------------------------------------
    # This tells the AI the exact table and field names so it never invents
    # field names like "employee.name" when the real field is "employee.full_name".
    sections.append(SCHEMA_CONTEXT.strip())

    # -----------------------------------------------------------------------
    # SECTION 2 — Live tenant snapshot (dynamic, queried from DB)
    # -----------------------------------------------------------------------
    # This gives the AI a quick orientation about this specific tenant's data
    # volume and skill set before it calls any detailed tools.
    snapshot = _build_tenant_snapshot(tenant_id=tenant_id, db=db)
    if snapshot:
        sections.append(snapshot)

    # -----------------------------------------------------------------------
    # SECTION 3 — Industry RAG knowledge (from flat files)
    # -----------------------------------------------------------------------
    # This gives the AI industry-specific knowledge: paper rates, machine specs,
    # weld times, SLA standards etc. Different content per industry vertical.
    rag_context = load_rag_context(tenant_id=tenant_id)
    if rag_context:
        sections.append(
            f"--- INDUSTRY CONTEXT ({industry_type.upper()}) ---\n"
            f"The following is industry-specific knowledge for this tenant's "
            f"vertical ({industry_type}). Use it to answer quantity, time, "
            f"cost, and specification questions without hallucinating values.\n\n"
            f"{rag_context}"
        )
    else:
        # No RAG files — log so developer knows to investigate
        logger.warning(
            "build_context_block: no RAG context loaded for tenant %s "
            "(industry=%s). AI will answer without industry norms. "
            "Run seed_rag_from_template(%s, '%s') to fix.",
            tenant_id, industry_type, tenant_id, industry_type,
        )

    # Join all sections — double newline between them for readability
    return "\n\n" + "\n\n".join(sections)


def _build_tenant_snapshot(tenant_id: int, db: Session) -> str:
    """
    Build a brief live snapshot of this tenant's current data state.

    Fetches counts and the skill list — not full records. The AI tools
    handle detailed queries. This snapshot gives orientation: "12 employees,
    3 machines, 6 active jobs, skills: Flexo Printing, Die Cutting, ...".

    Called by:   build_context_block()
    Calls:       Employee, Machine, Job, EmployeeSkill, Skill models (read-only)
    Args:
        tenant_id: Tenant to query — all queries filter by this.
        db:        Sync SQLAlchemy Session — caller owns lifecycle.
    Returns:
        Formatted snapshot string, or empty string if all queries fail.
    Side effects:
        Read-only DB queries. No writes, no commits.
    """
    # Import models locally to keep module-level imports clean and avoid
    # any circular import issues at package load time.
    from app.models.employee import Employee, EmployeeSkill
    from app.models.machine import Machine
    from app.models.job import Job
    from app.models.skill import Skill

    lines: list[str] = [
        "--- THIS TENANT'S CURRENT DATA SUMMARY ---",
        f"(tenant_id={tenant_id} — all queries must filter by this ID)",
    ]

    # Employee count — filter by Active status only
    try:
        employee_count: int = (
            db.query(func.count(Employee.id))
            .filter(
                Employee.tenant_id == tenant_id,
                Employee.status == "Active",
            )
            .scalar()
            or 0
        )
        lines.append(f"Active employees: {employee_count}")
    except Exception as exc:
        logger.error(
            "_build_tenant_snapshot: employee count failed for tenant %s: %s",
            tenant_id, exc,
        )
        lines.append("Active employees: (query failed)")

    # Machine count — filter by Operational status only
    try:
        machine_count: int = (
            db.query(func.count(Machine.id))
            .filter(
                Machine.tenant_id == tenant_id,
                Machine.status == "Operational",
            )
            .scalar()
            or 0
        )
        lines.append(f"Operational machines: {machine_count}")
    except Exception as exc:
        logger.error(
            "_build_tenant_snapshot: machine count failed for tenant %s: %s",
            tenant_id, exc,
        )
        lines.append("Operational machines: (query failed)")

    # Active job count — pending + in_progress only
    try:
        active_job_count: int = (
            db.query(func.count(Job.id))
            .filter(
                Job.tenant_id == tenant_id,
                Job.status.in_(["pending", "in_progress"]),
            )
            .scalar()
            or 0
        )
        lines.append(f"Active jobs (pending + in_progress): {active_job_count}")
    except Exception as exc:
        logger.error(
            "_build_tenant_snapshot: job count failed for tenant %s: %s",
            tenant_id, exc,
        )
        lines.append("Active jobs: (query failed)")

    # Skill list — all unique active skills this tenant has configured.
    # Gives the AI the actual skill names so it uses them exactly.
    # e.g. "Flexo Printing" not "flexo" or "printing".
    try:
        skill_names: list[str] = [
            row[0] for row in (
                db.query(Skill.name)
                .filter(
                    Skill.tenant_id == tenant_id,
                    Skill.is_active == True,  # noqa: E712
                )
                .order_by(Skill.name)
                .all()
            )
        ]
        if skill_names:
            lines.append(f"Available skills: {', '.join(skill_names)}")
        else:
            lines.append("Available skills: none configured yet")
    except Exception as exc:
        logger.error(
            "_build_tenant_snapshot: skill list failed for tenant %s: %s",
            tenant_id, exc,
        )
        lines.append("Available skills: (query failed)")

    lines.append("--- END OF SUMMARY ---")
    return "\n".join(lines)
