"""
app/services/ai_service.py — V3.0
AI Copilot service using Groq (Llama 3.3) with tool calling.
Tools: revenue, raw_material_cost, delayed_jobs, machine_availability, employee_availability,
       job_cost_breakdown, shop_floor_summary
"""

import json
import os
from datetime import date, datetime
from typing import Any

from groq import Groq
from sqlalchemy.orm import Session

from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine

# ── Groq client ───────────────────────────────────────────────────────────────
def get_groq_client() -> Groq:
    from app.config import settings
    api_key = settings.GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY not set in environment")
    return Groq(api_key=api_key)

MODEL = "llama-3.3-70b-versatile"

# ── Tool definitions (sent to Llama) ─────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_monthly_revenue",
            "description": "Get total order book value and revenue breakdown for a given month and year. Use this for questions about revenue, order value, income, earnings this month/week/year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12"},
                    "year":  {"type": "integer", "description": "4-digit year e.g. 2026"},
                },
                "required": ["month", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_raw_material_cost",
            "description": "Get total raw material cost across all jobs for a given month. Use for questions about raw material cost, material spend, RM cost.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12"},
                    "year":  {"type": "integer", "description": "4-digit year e.g. 2026"},
                },
                "required": ["month", "year"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_delayed_jobs",
            "description": "Get all jobs that are delayed, behind schedule, not started, or at risk. Use for questions about delays, late jobs, overdue jobs, jobs at risk.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_machine_availability",
            "description": "Get which machines are free, busy, or idle today or on a specific date. Use for questions about machine availability, free machines, idle machines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_date": {
                        "type": "string",
                        "description": "Date to check in YYYY-MM-DD format. Defaults to today if not provided.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employee_availability",
            "description": "Get which employees are available, free, or busy today or on a specific date. Use for questions about who is free, available staff, employee availability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "check_date": {
                        "type": "string",
                        "description": "Date to check in YYYY-MM-DD format. Defaults to today if not provided.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_cost_breakdown",
            "description": "Get detailed cost and profit breakdown for a specific job by name or partial name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_name": {
                        "type": "string",
                        "description": "Full or partial job name to search for",
                    },
                },
                "required": ["job_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_shop_floor_summary",
            "description": "Get a full summary of today's shop floor: running jobs, idle machines, available employees, revenue, alerts. Use for 'today summary', 'what is happening', 'shop floor status'.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# ── Tool executor — runs the actual DB queries ────────────────────────────────
def execute_tool(name: str, args: dict, db: Session, tenant_id: int) -> dict:

    today = date.today()

    # ── 1. Monthly Revenue ────────────────────────────────────────────────────
    if name == "get_monthly_revenue":
        month = args.get("month", today.month)
        year  = args.get("year",  today.year)

        jobs = db.query(Job).filter(
            Job.tenant_id == tenant_id,
            Job.start_date >= date(year, month, 1),
            Job.start_date <= date(year, month, 28 if month == 2 else 30 if month in [4,6,9,11] else 31),
        ).all()

        completed = [j for j in jobs if j.status == "Completed"]
        running   = [j for j in jobs if j.status == "In Progress"]
        scheduled = [j for j in jobs if j.status in ["Scheduled", "Draft"]]

        return {
            "month": f"{month}/{year}",
            "completed_revenue": sum(j.order_value or 0 for j in completed),
            "in_progress_value": sum(j.order_value or 0 for j in running),
            "scheduled_value":   sum(j.order_value or 0 for j in scheduled),
            "total_order_book":  sum(j.order_value or 0 for j in jobs),
            "job_count": len(jobs),
        }

    # ── 2. Raw Material Cost ──────────────────────────────────────────────────
    elif name == "get_raw_material_cost":
        month = args.get("month", today.month)
        year  = args.get("year",  today.year)

        jobs = db.query(Job).filter(
            Job.tenant_id == tenant_id,
            Job.start_date >= date(year, month, 1),
        ).all()

        breakdown = []
        total = 0.0
        for j in jobs:
            if j.raw_materials:
                job_rm_total = sum(
                    (rm.get("total_cost") or (rm.get("quantity", 0) * rm.get("unit_cost", 0)))
                    for rm in j.raw_materials
                )
                total += job_rm_total
                breakdown.append({"job": j.name, "cost": round(job_rm_total, 2)})

        return {
            "month": f"{month}/{year}",
            "total_raw_material_cost": round(total, 2),
            "breakdown": sorted(breakdown, key=lambda x: x["cost"], reverse=True)[:8],
        }

    # ── 3. Delayed Jobs ───────────────────────────────────────────────────────
    elif name == "get_delayed_jobs":
        jobs = db.query(Job).filter(
            Job.tenant_id == tenant_id,
            Job.status.in_(["In Progress", "Scheduled", "Draft", "Paused"]),
        ).all()

        delayed = []
        at_risk = []
        for j in jobs:
            days_to_end = (j.end_date - today).days
            if days_to_end < 0:
                delayed.append({
                    "name": j.name, "customer": j.customer,
                    "status": j.status, "overdue_days": abs(days_to_end),
                    "priority": j.priority,
                })
            elif days_to_end <= 5 and j.status in ["Draft", "Scheduled"]:
                at_risk.append({
                    "name": j.name, "customer": j.customer,
                    "status": j.status, "days_remaining": days_to_end,
                    "priority": j.priority,
                })

        return {
            "delayed_jobs": delayed,
            "at_risk_jobs": at_risk,
            "total_issues": len(delayed) + len(at_risk),
        }

    # ── 4. Machine Availability ───────────────────────────────────────────────
    elif name == "get_machine_availability":
        check_str  = args.get("check_date")
        check_date = date.fromisoformat(check_str) if check_str else today

        all_machines = db.query(Machine).filter(
            Machine.tenant_id == tenant_id,
            Machine.status == "Operational",
        ).all()

        # Find machines assigned to jobs on check_date
        busy_machine_ids = set()
        active_jobs = db.query(Job).filter(
            Job.tenant_id == tenant_id,
            Job.start_date <= check_date,
            Job.end_date   >= check_date,
            Job.status.in_(["In Progress", "Scheduled"]),
        ).all()
        for j in active_jobs:
            for a in j.assignments:
                if a.machine_id:
                    busy_machine_ids.add(a.machine_id)

        free = []
        busy = []
        for m in all_machines:
            if m.id in busy_machine_ids:
                # Find which job
                job_name = next(
                    (j.name for j in active_jobs if any(a.machine_id == m.id for a in j.assignments)),
                    "Unknown"
                )
                busy.append({"name": m.name, "type": m.machine_type, "busy_on": job_name})
            else:
                free.append({"name": m.name, "type": m.machine_type, "bay": m.location_bay})

        return {
            "check_date": str(check_date),
            "free_machines": free,
            "busy_machines": busy,
            "total_free": len(free),
            "total_busy": len(busy),
        }

    # ── 5. Employee Availability ──────────────────────────────────────────────
    elif name == "get_employee_availability":
        check_str  = args.get("check_date")
        check_date = date.fromisoformat(check_str) if check_str else today

        all_employees = db.query(Employee).filter(
            Employee.tenant_id == tenant_id,
            Employee.status == "Active",
        ).all()

        busy_emp_ids = set()
        active_jobs = db.query(Job).filter(
            Job.tenant_id == tenant_id,
            Job.start_date <= check_date,
            Job.end_date   >= check_date,
            Job.status.in_(["In Progress", "Scheduled"]),
        ).all()
        for j in active_jobs:
            for a in j.assignments:
                if a.employee_id:
                    busy_emp_ids.add(a.employee_id)

        free = []
        busy = []
        for e in all_employees:
            if e.id in busy_emp_ids:
                job_name = next(
                    (j.name for j in active_jobs if any(a.employee_id == e.id for a in j.assignments)),
                    "Unknown"
                )
                busy.append({
                    "name": e.full_name, "department": e.department,
                    "busy_on": job_name, "availability_pct": e.base_availability_pct,
                })
            else:
                free.append({
                    "name": e.full_name, "department": e.department,
                    "employment_type": e.employment_type,
                    "availability_pct": e.base_availability_pct,
                })

        return {
            "check_date": str(check_date),
            "free_employees": free,
            "busy_employees": busy,
            "total_free": len(free),
            "total_busy": len(busy),
        }

    # ── 6. Job Cost Breakdown ─────────────────────────────────────────────────
    elif name == "get_job_cost_breakdown":
        job_name = args.get("job_name", "")
        job = db.query(Job).filter(
            Job.tenant_id == tenant_id,
            Job.name.ilike(f"%{job_name}%"),
        ).first()

        if not job:
            return {"error": f"No job found matching '{job_name}'"}

        duration_days = (job.end_date - job.start_date).days + 1
        total_hours   = duration_days * job.estimated_hours_per_day

        # Employee cost
        emp_cost = 0.0
        assigned_employees = []
        for a in job.assignments:
            if a.employee and a.employee.hourly_rate:
                cost = a.employee.hourly_rate * total_hours
                emp_cost += cost
                assigned_employees.append({
                    "name": a.employee.full_name,
                    "rate": a.employee.hourly_rate,
                    "cost": round(cost, 2),
                })

        # Machine cost
        mac_cost = 0.0
        assigned_machines = []
        for a in job.assignments:
            if a.machine and a.machine.hourly_rate:
                cost = a.machine.hourly_rate * total_hours
                mac_cost += cost
                assigned_machines.append({
                    "name": a.machine.name,
                    "rate": a.machine.hourly_rate,
                    "cost": round(cost, 2),
                })

        # Raw material cost
        rm_cost = 0.0
        if job.raw_materials:
            rm_cost = sum(
                rm.get("total_cost") or (rm.get("quantity", 0) * rm.get("unit_cost", 0))
                for rm in job.raw_materials
            )

        misc_cost   = job.misc_cost or 0
        total_cost  = emp_cost + mac_cost + rm_cost + misc_cost
        order_value = job.order_value or 0
        profit      = order_value - total_cost
        margin_pct  = round((profit / order_value * 100), 1) if order_value > 0 else 0

        return {
            "job_name":          job.name,
            "customer":          job.customer,
            "status":            job.status,
            "duration_days":     duration_days,
            "total_hours":       total_hours,
            "employee_cost":     round(emp_cost, 2),
            "machine_cost":      round(mac_cost, 2),
            "raw_material_cost": round(rm_cost, 2),
            "misc_cost":         round(misc_cost, 2),
            "total_cost":        round(total_cost, 2),
            "order_value":       round(order_value, 2),
            "estimated_profit":  round(profit, 2),
            "margin_pct":        margin_pct,
            "assigned_employees": assigned_employees,
            "assigned_machines":  assigned_machines,
        }

    # ── 7. Shop Floor Summary ─────────────────────────────────────────────────
    elif name == "get_shop_floor_summary":
        all_jobs = db.query(Job).filter(Job.tenant_id == tenant_id).all()

        running   = [j for j in all_jobs if j.status == "In Progress"]
        paused    = [j for j in all_jobs if j.status == "Paused"]
        scheduled = [j for j in all_jobs if j.status == "Scheduled"]
        draft     = [j for j in all_jobs if j.status == "Draft"]
        completed = [j for j in all_jobs if j.status == "Completed"]

        # Delayed
        delayed = [j for j in all_jobs if j.status not in ["Completed", "Cancelled"] and j.end_date < today]
        at_risk = [j for j in all_jobs if j.status in ["Draft","Scheduled"] and (j.end_date - today).days <= 5]

        # Machine + employee availability
        busy_machine_ids = set()
        busy_emp_ids = set()
        for j in running:
            for a in j.assignments:
                if a.machine_id:  busy_machine_ids.add(a.machine_id)
                if a.employee_id: busy_emp_ids.add(a.employee_id)

        total_machines  = db.query(Machine).filter(Machine.tenant_id == tenant_id, Machine.status == "Operational").count()
        total_employees = db.query(Employee).filter(Employee.tenant_id == tenant_id, Employee.status == "Active").count()

        mtd_revenue = sum(j.order_value or 0 for j in completed if j.end_date.month == today.month)

        return {
            "date": str(today),
            "jobs": {
                "running":   len(running),
                "paused":    len(paused),
                "scheduled": len(scheduled),
                "draft":     len(draft),
                "completed": len(completed),
                "total":     len(all_jobs),
            },
            "alerts": {
                "delayed": len(delayed),
                "at_risk": len(at_risk),
                "delayed_names": [j.name for j in delayed[:3]],
                "at_risk_names": [j.name for j in at_risk[:3]],
            },
            "resources": {
                "machines_busy": len(busy_machine_ids),
                "machines_free": total_machines - len(busy_machine_ids),
                "employees_busy": len(busy_emp_ids),
                "employees_free": total_employees - len(busy_emp_ids),
            },
            "mtd_revenue": round(mtd_revenue, 2),
        }

    return {"error": f"Unknown tool: {name}"}


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an AI Copilot for MSME Resource Scheduler — a production management app used by Indian manufacturing shops.

You help the owner/scheduler by:
1. Answering questions about jobs, employees, machines, costs, revenue
2. Fetching real data using the tools available to you
3. Giving clear, concise answers with ₹ (Indian Rupees) for money

Rules:
- Always use tools to fetch real data — never guess numbers
- Format money as ₹X,XX,XXX (Indian number format)
- Be conversational and friendly — like a smart assistant
- Keep responses short and to the point
- Today's date is available in the shop_floor_summary tool
- If asked about something you can't answer with available tools, say so honestly

You understand Hinglish — if the user writes in Hindi or Hinglish, respond in English but be warm and friendly."""


# ── Main chat function ────────────────────────────────────────────────────────
def run_ai_chat(
    messages: list[dict],
    db: Session,
    tenant_id: int,
) -> str:
    """
    Run a full Groq tool-calling conversation cycle.
    messages: list of {role, content} — full conversation history
    Returns: final text response string
    """
    client = get_groq_client()

    # Add system prompt
    full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    # First call — let Llama decide which tool to call
    response = client.chat.completions.create(
        model=MODEL,
        messages=full_messages,
        tools=TOOLS,
        tool_choice="auto",
        max_tokens=1024,
        temperature=0.3,
    )

    msg = response.choices[0].message

    # If no tool call — return direct response
    if not msg.tool_calls:
        return msg.content or "I couldn't find an answer to that. Try asking about jobs, costs, machines, or employees."

    # Execute all tool calls
    tool_results = []
    for tc in msg.tool_calls:
        args   = json.loads(tc.function.arguments) or {}
        result = execute_tool(tc.function.name, args, db, tenant_id)
        tool_results.append({
            "tool_call_id": tc.id,
            "role":         "tool",
            "name":         tc.function.name,
            "content":      json.dumps(result),
        })

    # Second call — Llama formats the tool results into a human response
    full_messages.append({"role": "assistant", "content": msg.content, "tool_calls": msg.tool_calls})
    full_messages.extend(tool_results)

    final_response = client.chat.completions.create(
        model=MODEL,
        messages=full_messages,
        max_tokens=1024,
        temperature=0.4,
    )

    return final_response.choices[0].message.content or "Done."
