"""
app/services/ai_service.py — V3.0
AI Copilot service using Groq (Llama 3.3) with tool calling.
Tools: revenue, raw_material_cost, delayed_jobs, machine_availability, employee_availability,
       job_cost_breakdown, shop_floor_summary
"""

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

from groq import Groq
from sqlalchemy.orm import Session, selectinload

from app.models.job import Job, JobAssignment
from app.models.employee import Employee
from app.models.machine import Machine

# ── Safe date parser ──────────────────────────────────────────────────────────
def safe_date_parse(check_str: Any, fallback: date) -> date:
    """Parse a date string robustly. Handles ISO format and relative terms."""
    if not check_str or isinstance(check_str, dict):
        return fallback
    s = str(check_str).strip().lower()
    today = date.today()
    if s in ("today", "now", ""):
        return today
    if s in ("tomorrow", "next day"):
        return today + timedelta(days=1)
    if s == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(check_str)
    except (ValueError, TypeError):
        return fallback

def safe_days(d1: Any, d2: Any, default: int = 0) -> int:
    """Safely compute (d1 - d2).days, returning default on any error."""
    try:
        return (d1 - d2).days
    except Exception:
        return default

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
            "description": "Get total order book value and revenue breakdown for a given month and year. Use this for questions about revenue, order value, income, earnings this month/week/year. If month/year not specified, use current month/year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12. Default: current month."},
                    "year":  {"type": "integer", "description": "4-digit year e.g. 2026. Default: current year."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_raw_material_cost",
            "description": "Get total raw material cost across all jobs for a given month. Use for questions about raw material cost, material spend, RM cost. If month/year not specified, use current month/year.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12. Default: current month."},
                    "year":  {"type": "integer", "description": "4-digit year e.g. 2026. Default: current year."},
                },
                "required": [],
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
            "name": "get_all_jobs_cost_summary",
            "description": "Get cost, profit and margin breakdown for ALL jobs, ranked by total cost or profit. Use for: 'which job has highest cost', 'most expensive job', 'highest profit job', 'profit margin summary', 'compare job costs', 'best margin', 'worst margin', 'all jobs profit', 'cost across all jobs'. Returns every job with employee + machine + material + misc costs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status_filter": {
                        "type": "string",
                        "description": "Optional status to filter by: 'active' (In Progress + Scheduled + Draft), 'completed', or 'all'. Defaults to 'all'.",
                    },
                    "sort_by": {
                        "type": "string",
                        "description": "Sort results by: 'total_cost', 'profit', 'margin_pct', or 'order_value'. Defaults to 'total_cost'.",
                    },
                },
                "required": [],
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
    {
        "type": "function",
        "function": {
            "name": "get_employee_utilisation",
            "description": "Get employee utilisation — who is most/least used, how many jobs each employee is assigned to, and which jobs would be affected if a specific employee is absent. Use for questions about top performer, most utilised, who is overloaded, impact of absence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "employee_name": {
                        "type": "string",
                        "description": "Optional: partial name of employee to check absence impact for. Leave empty for full utilisation summary.",
                    },
                },
                "required": [],
            },
        },
    },
    # ── NEW TOOLS (J1.1 gap-fill) ─────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "get_monthly_cost_summary",
            "description": "Get full cost vs revenue comparison for a given month across all jobs: total employee cost, machine cost, raw material cost, misc cost, total cost, total revenue, net profit, overall margin. Use for: 'cost vs revenue this month', 'am I profitable', 'total employee cost this month', 'total machine cost this month', 'misc costs this month', 'order book value all active jobs'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month number 1-12. Defaults to current month."},
                    "year":  {"type": "integer", "description": "4-digit year. Defaults to current year."},
                    "include_all_active": {"type": "boolean", "description": "If true, includes ALL active jobs regardless of start month (for order book queries). Default false."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_schedule_overview",
            "description": "Get scheduling intelligence: jobs that should have started but haven't, jobs due this week, jobs starting next week, busiest day this month, scheduling conflicts (resources double-booked), critical jobs not started, jobs ending in next N days. Use for: 'scheduling conflicts', 'busiest day', 'jobs not started', 'critical jobs status', 'jobs due this week', 'overdue', 'ending in 3 days', 'jobs starting next week'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "What to return: 'conflicts' (resource double-bookings), 'not_started' (should have started), 'due_this_week', 'starting_next_week', 'busiest_day', 'critical_status', 'ending_soon'. Default 'conflicts'.",
                    },
                    "days_ahead": {"type": "integer", "description": "For ending_soon mode: how many days ahead to check. Default 3."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_alerts_summary",
            "description": "Get ALL actionable alerts in one call: overdue jobs, critical not started, unassigned jobs, jobs with no raw materials, low margin jobs, ending soon, at-risk jobs. Use for: 'all alerts today', 'what needs attention', 'unassigned jobs', 'no raw materials', 'low profit jobs', 'critical not started'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "margin_threshold": {"type": "number", "description": "Profit margin % below which a job is flagged as low-margin. Default 10."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_machine_utilisation",
            "description": "Get machine utilisation: which machines are most/least used, idle days, cost generated per machine this month, impact if a machine breaks down. Use for: 'machine utilisation', 'idle machines', 'machine cost analysis', 'if machine breaks which jobs affected', 'most used machine'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month 1-12. Defaults to current month."},
                    "year":  {"type": "integer", "description": "4-digit year. Defaults to current year."},
                    "machine_name": {"type": "string", "description": "Optional: partial machine name to get breakdown impact for a specific machine."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employees_by_skill",
            "description": "Get employees grouped by skill or department, with hours assigned this month per employee. Use for: 'employees by skill', 'employees by department', 'overtime this month', 'who has most hours', 'list employees grouped by skill'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "month": {"type": "integer", "description": "Month 1-12 for hours calculation. Defaults to current month."},
                    "year":  {"type": "integer", "description": "4-digit year. Defaults to current year."},
                    "group_by": {"type": "string", "description": "'skill' or 'department'. Default 'department'."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_jobs_overview",
            "description": "Get jobs grouped by customer, jobs by priority, completed jobs this month with value, jobs starting next week. Use for: 'jobs by customer', 'completed this month', 'jobs grouped by customer', 'which customer has most jobs', 'completed jobs total value'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "description": "'by_customer', 'by_priority', 'completed_this_month', 'starting_next_week'. Default 'by_customer'."},
                    "month": {"type": "integer", "description": "Month for completed_this_month mode. Defaults to current."},
                    "year":  {"type": "integer", "description": "Year. Defaults to current."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rm_cost_impact",
            "description": "Simulate impact of raw material cost increase on job profitability. Use for: 'if RM costs increase by X%', 'which jobs become unprofitable if costs rise', 'cost increase impact', 'sensitivity analysis'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "increase_pct": {"type": "number", "description": "Percentage increase in raw material costs, e.g. 15 for 15%. Default 15."},
                },
                "required": [],
            },
        },
    },
]

# ── Tool executor — runs the actual DB queries ────────────────────────────────
def execute_tool(name: str, args: dict, db: Session, tenant_id: int) -> dict:
    args  = args or {}

    # Safely coerce month/year — Llama sometimes passes nested objects
    def safe_int(val, default: int) -> int:
        try:
            return int(val) if val is not None and not isinstance(val, dict) else default
        except (TypeError, ValueError):
            return default

    today = date.today()

    # ── 1. Monthly Revenue ────────────────────────────────────────────────────
    if name == "get_monthly_revenue":
        month = safe_int(args.get("month"), today.month)
        year  = safe_int(args.get("year"),  today.year)

        jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
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
        month = safe_int(args.get("month"), today.month)
        year  = safe_int(args.get("year"),  today.year)

        jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
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
        jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
            Job.tenant_id == tenant_id,
            Job.status.in_(["In Progress", "Scheduled", "Draft", "Paused"]),
        ).all()

        delayed = []
        at_risk = []
        for j in jobs:
            if not j.end_date:
                continue
            days_to_end = safe_days(j.end_date, today)
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
        check_date = safe_date_parse(check_str, today)

        all_machines = db.query(Machine).filter(
            Machine.tenant_id == tenant_id,
            Machine.status == "Operational",
        ).all()

        # Find machines assigned to jobs on check_date
        busy_machine_ids = set()
        active_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
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
        check_date = safe_date_parse(check_str, today)

        all_employees = db.query(Employee).filter(
            Employee.tenant_id == tenant_id,
            Employee.status == "Active",
        ).all()

        busy_emp_ids = set()
        active_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
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
        job = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
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

    # ── 7. All Jobs Cost Summary ──────────────────────────────────────────────
    elif name == "get_all_jobs_cost_summary":
        status_filter = args.get("status_filter", "all")
        sort_by       = args.get("sort_by", "total_cost")

        q = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id == tenant_id)
        if status_filter == "active":
            q = q.filter(Job.status.in_(["In Progress", "Scheduled", "Draft", "Paused"]))
        elif status_filter == "completed":
            q = q.filter(Job.status == "Completed")

        all_jobs = q.all()

        results = []
        for job in all_jobs:
            if not job.start_date or not job.end_date:
                continue
            duration_days = max((job.end_date - job.start_date).days + 1, 1)
            total_hours   = duration_days * (job.estimated_hours_per_day or 0)

            emp_cost = sum(
                (a.employee.hourly_rate or 0) * total_hours
                for a in job.assignments if a.employee
            )
            mac_cost = sum(
                (a.machine.hourly_rate or 0) * total_hours
                for a in job.assignments if a.machine
            )
            rm_cost = sum(
                rm.get("total_cost") or (rm.get("quantity", 0) * rm.get("unit_cost", 0))
                for rm in (job.raw_materials or [])
            )
            misc_cost   = job.misc_cost or 0
            total_cost  = emp_cost + mac_cost + rm_cost + misc_cost
            order_value = job.order_value or 0
            profit      = order_value - total_cost
            margin_pct  = round((profit / order_value * 100), 1) if order_value > 0 else None

            results.append({
                "job_id":          job.id,
                "job_name":        job.name,
                "customer":        job.customer,
                "status":          job.status,
                "priority":        job.priority,
                "employee_cost":   round(emp_cost, 2),
                "machine_cost":    round(mac_cost, 2),
                "raw_material_cost": round(rm_cost, 2),
                "misc_cost":       round(misc_cost, 2),
                "total_cost":      round(total_cost, 2),
                "order_value":     round(order_value, 2),
                "profit":          round(profit, 2),
                "margin_pct":      margin_pct,
            })

        # Sort
        reverse = sort_by in ("total_cost", "order_value", "profit")
        if sort_by == "margin_pct":
            results.sort(key=lambda x: (x["margin_pct"] is not None, x["margin_pct"] or 0), reverse=True)
        else:
            results.sort(key=lambda x: x.get(sort_by) or 0, reverse=reverse)

        total_order_value = sum(r["order_value"] for r in results)
        total_cost_all    = sum(r["total_cost"]  for r in results)
        total_profit_all  = sum(r["profit"]       for r in results)
        overall_margin    = round((total_profit_all / total_order_value * 100), 1) if total_order_value > 0 else None

        return {
            "total_jobs":        len(results),
            "status_filter":     status_filter,
            "sorted_by":         sort_by,
            "jobs":              results,
            "summary": {
                "total_order_value": round(total_order_value, 2),
                "total_cost":        round(total_cost_all, 2),
                "total_profit":      round(total_profit_all, 2),
                "overall_margin_pct": overall_margin,
                "highest_cost_job":  results[0]["job_name"] if results else None,
                "most_profitable_job": max(results, key=lambda x: x["profit"])["job_name"] if results else None,
                "best_margin_job":    max((r for r in results if r["margin_pct"] is not None), key=lambda x: x["margin_pct"])["job_name"] if any(r["margin_pct"] is not None for r in results) else None,
            },
        }

    # ── 8. Shop Floor Summary ─────────────────────────────────────────────────
    elif name == "get_shop_floor_summary":
        all_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id == tenant_id).all()

        running   = [j for j in all_jobs if j.status == "In Progress"]
        paused    = [j for j in all_jobs if j.status == "Paused"]
        scheduled = [j for j in all_jobs if j.status == "Scheduled"]
        draft     = [j for j in all_jobs if j.status == "Draft"]
        completed = [j for j in all_jobs if j.status == "Completed"]

        # Delayed
        delayed = [j for j in all_jobs if j.end_date and j.status not in ["Completed", "Cancelled"] and j.end_date < today]
        at_risk = [j for j in all_jobs if j.end_date and j.status in ["Draft","Scheduled"] and safe_days(j.end_date, today) <= 5]

        # Machine + employee availability
        busy_machine_ids = set()
        busy_emp_ids = set()
        for j in running:
            for a in j.assignments:
                if a.machine_id:  busy_machine_ids.add(a.machine_id)
                if a.employee_id: busy_emp_ids.add(a.employee_id)

        from sqlalchemy import func as _func
        total_machines  = db.query(_func.count()).select_from(Machine).filter(Machine.tenant_id == tenant_id, Machine.status == "Operational").scalar()
        total_employees = db.query(_func.count()).select_from(Employee).filter(Employee.tenant_id == tenant_id, Employee.status == "Active").scalar()

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

    # ── 8. Employee Utilisation ───────────────────────────────────────────────
    elif name == "get_employee_utilisation":
        check_str  = args.get("check_date")
        check_date = safe_date_parse(check_str, today)

        all_employees = db.query(Employee).filter(
            Employee.tenant_id == tenant_id,
            Employee.status == "Active",
        ).all()

        active_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(
            Job.tenant_id == tenant_id,
            Job.start_date <= check_date,
            Job.end_date   >= check_date,
            Job.status.in_(["In Progress", "Scheduled", "Draft"]),
        ).all()

        # Build employee -> jobs mapping
        emp_job_map: dict = {}
        for j in active_jobs:
            for a in j.assignments:
                if a.employee_id:
                    if a.employee_id not in emp_job_map:
                        emp_job_map[a.employee_id] = []
                    emp_job_map[a.employee_id].append({
                        "job_name": j.name,
                        "customer": j.customer,
                        "status":   j.status,
                        "priority": j.priority,
                        "end_date": str(j.end_date),
                    })

        utilisation = []
        for e in all_employees:
            jobs_assigned = emp_job_map.get(e.id, [])
            utilisation.append({
                "employee_name":   e.full_name,
                "department":      e.department,
                "employment_type": e.employment_type,
                "jobs_count":      len(jobs_assigned),
                "jobs":            jobs_assigned,
            })

        # Sort by jobs count descending
        utilisation.sort(key=lambda x: x["jobs_count"], reverse=True)
        most_utilised = utilisation[0] if utilisation else None

        return {
            "check_date":     str(check_date),
            "utilisation":    utilisation,
            "most_utilised":  most_utilised,
            "total_active_jobs": len(active_jobs),
        }


    # ── 10. Monthly Cost Summary ──────────────────────────────────────────────
    elif name == "get_monthly_cost_summary":
        month = safe_int(args.get("month"), today.month)
        year  = safe_int(args.get("year"),  today.year)
        include_all_active = args.get("include_all_active", False)
        import calendar
        month_start = date(year, month, 1)
        month_end   = date(year, month, calendar.monthrange(year, month)[1])
        if include_all_active:
            jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id == tenant_id,
                Job.status.in_(["In Progress","Scheduled","Draft","Paused","Completed"])).all()
        else:
            jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id == tenant_id,
                Job.start_date <= month_end, Job.end_date >= month_start).all()
        total_emp = total_mac = total_rm = total_misc = total_ov = 0.0
        job_details = []
        for j in jobs:
            if not j.start_date or not j.end_date:
                continue
            dur   = max((j.end_date - j.start_date).days + 1, 1)
            hrs   = dur * (j.estimated_hours_per_day or 0)
            ec    = sum((a.employee.hourly_rate or 0)*hrs for a in j.assignments if a.employee)
            mc    = sum((a.machine.hourly_rate  or 0)*hrs for a in j.assignments if a.machine)
            rc    = sum(rm.get("total_cost") or (rm.get("quantity",0)*rm.get("unit_cost",0)) for rm in (j.raw_materials or []))
            misc  = j.misc_cost or 0
            tc    = ec + mc + rc + misc
            ov    = j.order_value or 0
            pf    = ov - tc
            mg    = round(pf/ov*100,1) if ov > 0 else None
            total_emp += ec; total_mac += mc; total_rm += rc; total_misc += misc; total_ov += ov
            job_details.append({"job_name":j.name,"customer":j.customer,"status":j.status,
                "emp_cost":round(ec,2),"mac_cost":round(mc,2),"rm_cost":round(rc,2),
                "misc_cost":round(misc,2),"total_cost":round(tc,2),"order_value":round(ov,2),
                "profit":round(pf,2),"margin_pct":mg})
        tc_all = total_emp+total_mac+total_rm+total_misc
        net    = total_ov - tc_all
        margin = round(net/total_ov*100,1) if total_ov > 0 else None
        return {"month":f"{month}/{year}","job_count":len(jobs),
            "total_employee_cost":round(total_emp,2),"total_machine_cost":round(total_mac,2),
            "total_raw_material_cost":round(total_rm,2),"total_misc_cost":round(total_misc,2),
            "total_cost":round(tc_all,2),"total_order_value":round(total_ov,2),
            "net_profit":round(net,2),"overall_margin_pct":margin,"is_profitable":net>0,
            "jobs":sorted(job_details,key=lambda x:x["total_cost"],reverse=True)}

    # ── 11. Schedule Overview ─────────────────────────────────────────────────
    elif name == "get_schedule_overview":
        import datetime as dt, calendar as cal
        mode       = args.get("mode","conflicts")
        days_ahead = safe_int(args.get("days_ahead"),3)
        all_jobs   = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,
            Job.status.notin_(["Completed","Cancelled"])).all()

        if mode == "conflicts":
            from collections import defaultdict
            emp_jobs: dict = defaultdict(list)
            mac_jobs: dict = defaultdict(list)
            for j in all_jobs:
                for a in j.assignments:
                    if a.employee_id: emp_jobs[a.employee_id].append(j)
                    if a.machine_id:  mac_jobs[a.machine_id].append(j)
            def overlaps(j1,j2): return j1.start_date<=j2.end_date and j2.start_date<=j1.end_date
            conflicts = []
            for eid, jlist in emp_jobs.items():
                for i in range(len(jlist)):
                    for k in range(i+1,len(jlist)):
                        if overlaps(jlist[i],jlist[k]):
                            e = db.query(Employee).filter(Employee.id==eid).first()
                            conflicts.append({"type":"employee","resource":e.full_name if e else f"Emp#{eid}",
                                "job1":jlist[i].name,"job1_dates":f"{jlist[i].start_date}→{jlist[i].end_date}",
                                "job2":jlist[k].name,"job2_dates":f"{jlist[k].start_date}→{jlist[k].end_date}"})
            for mid, jlist in mac_jobs.items():
                for i in range(len(jlist)):
                    for k in range(i+1,len(jlist)):
                        if overlaps(jlist[i],jlist[k]):
                            m = db.query(Machine).filter(Machine.id==mid).first()
                            conflicts.append({"type":"machine","resource":m.name if m else f"Machine#{mid}",
                                "job1":jlist[i].name,"job1_dates":f"{jlist[i].start_date}→{jlist[i].end_date}",
                                "job2":jlist[k].name,"job2_dates":f"{jlist[k].start_date}→{jlist[k].end_date}"})
            return {"mode":"conflicts","total_conflicts":len(conflicts),"conflicts":conflicts[:20],
                "message":"No scheduling conflicts found." if not conflicts else f"{len(conflicts)} conflict(s) detected."}

        elif mode == "not_started":
            data = [{"name":j.name,"customer":j.customer,"priority":j.priority,"status":j.status,
                "should_have_started":str(j.start_date),"days_late":safe_days(today,j.start_date)}
                for j in all_jobs if j.start_date and j.start_date < today and j.status in ["Draft","Scheduled"]]
            data.sort(key=lambda x:x["days_late"],reverse=True)
            return {"mode":"not_started","count":len(data),"jobs":data}

        elif mode == "due_this_week":
            week_end = today + dt.timedelta(days=7)
            data = [{"name":j.name,"customer":j.customer,"priority":j.priority,"status":j.status,
                "end_date":str(j.end_date),"days_remaining":safe_days(j.end_date,today)}
                for j in all_jobs if j.end_date and today<=j.end_date<=week_end]
            data.sort(key=lambda x:x["days_remaining"])
            return {"mode":"due_this_week","count":len(data),"jobs":data}

        elif mode == "starting_next_week":
            nws = today + dt.timedelta(days=(7-today.weekday()))
            nwe = nws + dt.timedelta(days=6)
            data = [{"name":j.name,"customer":j.customer,"priority":j.priority,"status":j.status,
                "start_date":str(j.start_date),"end_date":str(j.end_date)}
                for j in all_jobs if j.start_date and nws<=j.start_date<=nwe]
            data.sort(key=lambda x:x["start_date"])
            return {"mode":"starting_next_week","week":f"{nws}→{nwe}","count":len(data),"jobs":data}

        elif mode == "busiest_day":
            ms = date(today.year,today.month,1)
            me = date(today.year,today.month,cal.monthrange(today.year,today.month)[1])
            day_counts = {}
            d = ms
            while d <= me:
                day_counts[str(d)] = sum(1 for j in all_jobs if j.start_date and j.end_date and j.start_date<=d<=j.end_date)
                d += dt.timedelta(days=1)
            sorted_days = sorted(day_counts.items(),key=lambda x:x[1],reverse=True)
            return {"mode":"busiest_day","busiest_day":sorted_days[0][0] if sorted_days else None,
                "jobs_running":sorted_days[0][1] if sorted_days else 0,"top_5_days":sorted_days[:5]}

        elif mode == "critical_status":
            data = [{"name":j.name,"customer":j.customer,"status":j.status,
                "start_date":str(j.start_date),"end_date":str(j.end_date),
                "not_started":j.status in ["Draft","Scheduled"] and bool(j.start_date) and j.start_date<=today,
                "overdue":bool(j.end_date) and j.end_date<today} for j in all_jobs if j.priority=="Critical"]
            return {"mode":"critical_status","total_critical":len(data),
                "not_started":[c for c in data if c["not_started"]],
                "overdue":[c for c in data if c["overdue"]],
                "on_track":[c for c in data if not c["not_started"] and not c["overdue"]],"jobs":data}

        elif mode == "ending_soon":
            cutoff = today + dt.timedelta(days=days_ahead)
            data = [{"name":j.name,"customer":j.customer,"priority":j.priority,"status":j.status,
                "end_date":str(j.end_date),"days_remaining":safe_days(j.end_date,today),
                "has_assignments":len(j.assignments)>0}
                for j in all_jobs if j.end_date and today<=j.end_date<=cutoff]
            data.sort(key=lambda x:x["days_remaining"])
            return {"mode":"ending_soon","days_ahead":days_ahead,"count":len(data),"jobs":data}

        return {"error":f"Unknown mode: {mode}"}

    # ── 12. Alerts Summary ────────────────────────────────────────────────────
    elif name == "get_alerts_summary":
        margin_threshold = float(args.get("margin_threshold") or 10)
        all_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,
            Job.status.notin_(["Completed","Cancelled"])).all()
        overdue=[];crit_ns=[];unassigned=[];no_rm=[];ending=[];low_mg=[]
        for j in all_jobs:
            if not j.end_date:
                continue
            dl = safe_days(j.end_date, today)
            if j.end_date < today:
                overdue.append({"name":j.name,"priority":j.priority,"status":j.status,
                    "overdue_days":(today-j.end_date).days,"customer":j.customer})
            if j.priority=="Critical" and j.status in ["Draft","Scheduled"] and j.start_date<=today:
                crit_ns.append({"name":j.name,"start_date":str(j.start_date),"customer":j.customer})
            if not j.assignments:
                unassigned.append({"name":j.name,"priority":j.priority,"status":j.status,
                    "start_date":str(j.start_date),"customer":j.customer})
            if not j.raw_materials or len(j.raw_materials)==0:
                no_rm.append({"name":j.name,"priority":j.priority,"status":j.status})
            if 0<=dl<=3:
                ending.append({"name":j.name,"priority":j.priority,"status":j.status,
                    "end_date":str(j.end_date),"days_remaining":dl})
            if j.order_value and j.start_date and j.end_date:
                dur = max((j.end_date-j.start_date).days+1,1)
                hrs = dur*(j.estimated_hours_per_day or 0)
                ec = sum((a.employee.hourly_rate or 0)*hrs for a in j.assignments if a.employee)
                mc = sum((a.machine.hourly_rate  or 0)*hrs for a in j.assignments if a.machine)
                rc = sum(rm.get("total_cost") or (rm.get("quantity",0)*rm.get("unit_cost",0)) for rm in (j.raw_materials or []))
                tc = ec+mc+rc+(j.misc_cost or 0)
                pf = j.order_value-tc
                mg = round(pf/j.order_value*100,1)
                if mg < margin_threshold:
                    low_mg.append({"name":j.name,"customer":j.customer,"margin_pct":mg,
                        "profit":round(pf,2),"order_value":round(j.order_value,2),
                        "status":j.status,"is_loss":pf<0})
        low_mg.sort(key=lambda x:x["margin_pct"])
        return {"total_alerts":len(overdue)+len(crit_ns)+len(unassigned)+len(ending)+len(low_mg),
            "overdue_jobs":sorted(overdue,key=lambda x:x["overdue_days"],reverse=True),
            "critical_not_started":crit_ns,"unassigned_jobs":unassigned,
            "jobs_no_raw_materials":no_rm,"ending_soon_3_days":ending,
            "low_margin_jobs":low_mg,"margin_threshold_used":margin_threshold}

    # ── 13. Machine Utilisation ───────────────────────────────────────────────
    elif name == "get_machine_utilisation":
        import datetime as dt, calendar as cal
        month = safe_int(args.get("month"),today.month)
        year  = safe_int(args.get("year"), today.year)
        mname = args.get("machine_name","")
        ms = date(year,month,1)
        me = date(year,month,cal.monthrange(year,month)[1])
        wdays = sum(1 for i in range((me-ms).days+1) if (ms+dt.timedelta(i)).weekday()<6)
        all_m = db.query(Machine).filter(Machine.tenant_id==tenant_id,Machine.status=="Operational").all()
        mjobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,Job.start_date<=me,
            Job.end_date>=ms,Job.status.notin_(["Cancelled"])).all()
        results=[]
        for m in all_m:
            ajobs=[]; tcost=0.0; bdays=set()
            for j in mjobs:
                if any(a.machine_id==m.id for a in j.assignments):
                    os=max(j.start_date,ms); oe=min(j.end_date,me)
                    od=(oe-os).days+1; hrs=od*j.estimated_hours_per_day
                    c=(m.hourly_rate or 0)*hrs; tcost+=c
                    d=os
                    while d<=oe: bdays.add(d); d+=dt.timedelta(days=1)
                    ajobs.append({"job_name":j.name,"customer":j.customer,
                        "start_date":str(j.start_date),"end_date":str(j.end_date),
                        "status":j.status,"cost":round(c,2)})
            bd=len(bdays); idle=max(wdays-bd,0)
            util=round(bd/wdays*100,1) if wdays>0 else 0
            results.append({"machine_name":m.name,"machine_type":m.machine_type,
                "location_bay":m.location_bay,"hourly_rate":m.hourly_rate,
                "utilisation_pct":util,"busy_days":bd,"idle_days":idle,
                "total_cost_generated":round(tcost,2),"assigned_jobs":ajobs})
        results.sort(key=lambda x:x["utilisation_pct"],reverse=True)
        impact=[]
        if mname:
            match=next((r for r in results if mname.lower() in r["machine_name"].lower()),None)
            if match: impact=match["assigned_jobs"]
        idle3=[r for r in results if r["idle_days"]>=3]
        top=results[0] if results else None
        hc=max(results,key=lambda x:x["total_cost_generated"]) if results else None
        return {"month":f"{month}/{year}","working_days":wdays,"machines":results,
            "idle_machines_3plus_days":idle3,
            "most_utilised_machine":top["machine_name"] if top else None,
            "highest_cost_machine":hc["machine_name"] if hc else None,
            "highest_cost_value":hc["total_cost_generated"] if hc else None,
            "absence_impact":{"machine":mname,"affected_jobs":impact,
                "total_affected":len(impact)} if mname else None}

    # ── 14. Employees by Skill ────────────────────────────────────────────────
    elif name == "get_employees_by_skill":
        import calendar as cal
        month    = safe_int(args.get("month"),today.month)
        year     = safe_int(args.get("year"), today.year)
        group_by = args.get("group_by","department")
        ms = date(year,month,1)
        me = date(year,month,cal.monthrange(year,month)[1])
        all_e = db.query(Employee).options(selectinload(Employee.skills)).filter(Employee.tenant_id==tenant_id,Employee.status=="Active").all()
        mjobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,Job.start_date<=me,Job.end_date>=ms).all()
        ehours={e.id:0.0 for e in all_e}; ejobs={e.id:[] for e in all_e}
        for j in mjobs:
            os=max(j.start_date,ms); oe=min(j.end_date,me)
            hrs=((oe-os).days+1)*j.estimated_hours_per_day
            for a in j.assignments:
                if a.employee_id and a.employee_id in ehours:
                    ehours[a.employee_id]+=hrs; ejobs[a.employee_id].append(j.name)
        emp_data=[]
        for e in all_e:
            skills=[]
            if hasattr(e,"skills") and e.skills:
                skills=[{"skill_name":s.skill.name if s.skill else "?","level":s.skill_level} for s in e.skills]
            emp_data.append({"id":e.id,"name":e.full_name,"department":e.department or "Unassigned",
                "employment_type":e.employment_type,"hourly_rate":e.hourly_rate,"skills":skills,
                "hours_this_month":round(ehours[e.id],1),"jobs_this_month":ejobs[e.id]})
        groups: dict={}
        for e in emp_data:
            keys=[s["skill_name"] for s in e["skills"]] or ["No Skills"] if group_by=="skill" else [e["department"]]
            for k in keys:
                if k not in groups: groups[k]=[]
                groups[k].append(e)
        emp_data.sort(key=lambda x:x["hours_this_month"],reverse=True)
        return {"month":f"{month}/{year}","group_by":group_by,
            "groups":{k:v for k,v in sorted(groups.items())},
            "top_by_hours":emp_data[:5],"total_employees":len(all_e)}

    # ── 15. Jobs Overview ─────────────────────────────────────────────────────
    elif name == "get_jobs_overview":
        import datetime as dt, calendar as cal
        mode  = args.get("mode","by_customer")
        month = safe_int(args.get("month"),today.month)
        year  = safe_int(args.get("year"), today.year)

        if mode == "by_customer":
            all_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,
                Job.status.notin_(["Cancelled"])).all()
            groups: dict={}
            for j in all_jobs:
                k=j.customer or "(No Customer)"
                if k not in groups: groups[k]={"customer":k,"jobs":[],"total_value":0.0,"job_count":0}
                groups[k]["jobs"].append({"name":j.name,"status":j.status,"priority":j.priority,
                    "start_date":str(j.start_date),"end_date":str(j.end_date),"order_value":j.order_value or 0})
                groups[k]["total_value"]+=j.order_value or 0; groups[k]["job_count"]+=1
            return {"mode":"by_customer","total_customers":len(groups),
                "customers":sorted(groups.values(),key=lambda x:x["total_value"],reverse=True)}

        elif mode == "by_priority":
            all_jobs = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,
                Job.status.notin_(["Completed","Cancelled"])).all()
            groups={"Critical":[],"High":[],"Medium":[],"Low":[]}
            for j in all_jobs:
                p=j.priority if j.priority in groups else "Medium"
                groups[p].append({"name":j.name,"status":j.status,"customer":j.customer,
                    "end_date":str(j.end_date),"order_value":j.order_value or 0})
            return {"mode":"by_priority","groups":groups,"counts":{k:len(v) for k,v in groups.items()}}

        elif mode == "completed_this_month":
            ms=date(year,month,1); me=date(year,month,cal.monthrange(year,month)[1])
            done=db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,Job.status=="Completed",
                Job.end_date>=ms,Job.end_date<=me).all()
            jl=[{"name":j.name,"customer":j.customer,"end_date":str(j.end_date),
                "order_value":j.order_value or 0,"priority":j.priority} for j in done]
            jl.sort(key=lambda x:x["order_value"],reverse=True)
            return {"mode":"completed_this_month","month":f"{month}/{year}","count":len(done),
                "total_value":round(sum(j["order_value"] for j in jl),2),"jobs":jl}

        elif mode == "starting_next_week":
            nws=today+dt.timedelta(days=(7-today.weekday()))
            nwe=nws+dt.timedelta(days=6)
            all_jobs=db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,
                Job.start_date>=nws,Job.start_date<=nwe,
                Job.status.notin_(["Completed","Cancelled"])).all()
            jl=[{"name":j.name,"customer":j.customer,"status":j.status,"priority":j.priority,
                "start_date":str(j.start_date),"end_date":str(j.end_date) if j.end_date else None,
                "has_assignments":len(j.assignments)>0,"order_value":j.order_value or 0} for j in all_jobs]
            jl.sort(key=lambda x:x["start_date"])
            return {"mode":"starting_next_week","week":f"{nws}→{nwe}","count":len(all_jobs),"jobs":jl}

        return {"error":f"Unknown mode: {mode}"}

    # ── 16. RM Cost Impact ────────────────────────────────────────────────────
    elif name == "get_rm_cost_impact":
        increase_pct = float(args.get("increase_pct") or 15)/100
        active = db.query(Job).options(selectinload(Job.assignments).selectinload(JobAssignment.employee), selectinload(Job.assignments).selectinload(JobAssignment.machine)).filter(Job.tenant_id==tenant_id,
            Job.status.notin_(["Completed","Cancelled"])).all()
        results=[]
        for j in active:
            if not j.order_value or not j.start_date or not j.end_date: continue
            dur=max((j.end_date-j.start_date).days+1,1); hrs=dur*(j.estimated_hours_per_day or 0)
            ec=sum((a.employee.hourly_rate or 0)*hrs for a in j.assignments if a.employee)
            mc=sum((a.machine.hourly_rate  or 0)*hrs for a in j.assignments if a.machine)
            rc=sum(rm.get("total_cost") or (rm.get("quantity",0)*rm.get("unit_cost",0)) for rm in (j.raw_materials or []))
            misc=j.misc_cost or 0; ov=j.order_value
            cur_t=ec+mc+rc+misc; new_rc=rc*(1+increase_pct); new_t=ec+mc+new_rc+misc
            cur_p=ov-cur_t; new_p=ov-new_t
            cur_m=round(cur_p/ov*100,1) if ov>0 else None
            new_m=round(new_p/ov*100,1) if ov>0 else None
            results.append({"job_name":j.name,"customer":j.customer,"status":j.status,
                "current_rm_cost":round(rc,2),"new_rm_cost":round(new_rc,2),
                "rm_increase":round(new_rc-rc,2),"current_profit":round(cur_p,2),
                "new_profit":round(new_p,2),"current_margin":cur_m,"new_margin":new_m,
                "becomes_loss":new_p<0 and cur_p>=0,"already_loss":cur_p<0})
        results.sort(key=lambda x:x["new_margin"] if x["new_margin"] is not None else -999)
        newly = [r for r in results if r["becomes_loss"]]
        already= [r for r in results if r["already_loss"]]
        return {"increase_pct":f"{increase_pct*100:.0f}%","total_jobs_analysed":len(results),
            "newly_unprofitable":newly,"already_at_loss":already,"all_jobs":results,
            "summary":f"{len(newly)} job(s) would become unprofitable at +{increase_pct*100:.0f}% RM cost increase."}


    return {"error": f"Unknown tool: {name}"}


# ── System prompt ─────────────────────────────────────────────────────────────
_SYSTEM_PROMPT_BASE = """You are an AI Copilot for MSME Resource Scheduler — a production management app used by Indian manufacturing shops.

You help the owner/scheduler by:
1. Answering questions about jobs, employees, machines, costs, revenue
2. Fetching real data using the tools available to you
3. Giving clear, concise answers with ₹ (Indian Rupees) for money

DATE CONTEXT (IMPORTANT — always use these exact dates):
- Today:     {today}  (YYYY-MM-DD)
- Tomorrow:  {tomorrow}  (YYYY-MM-DD)
- Yesterday: {yesterday}  (YYYY-MM-DD)
- When user says "today" → check_date={today}
- When user says "tomorrow" → check_date={tomorrow}
- When user says "yesterday" → check_date={yesterday}
- Always pass check_date as a YYYY-MM-DD string, never as a word like "tomorrow"

Rules:
- Always use tools to fetch real data — never guess numbers
- When referring to jobs, always mention the job NAME (e.g. 'Crankshaft Machining') not just the ID
- When calling tools with month/year parameters, always pass plain integers (e.g. month=3, year=2026). Never pass objects.
- If month/year not specified, do NOT pass those parameters — let the tool use current defaults
- Format money as ₹X,XX,XXX (Indian number format)
- Be conversational and friendly — like a smart assistant
- Keep responses short and to the point
- Never call the same tool twice in one response
- If asked about something you can't answer with available tools, say so honestly
- NEVER refer to jobs by their database ID numbers. Always use job names from tool results

TOOL ROUTING — always pick the most specific tool:
- "most utilised / busiest employee", "if employee absent"         → get_employee_utilisation
- "employees by skill / department", "overtime", "most hours"      → get_employees_by_skill
- "which job highest cost", "most expensive job", "all jobs profit/margin", "best/worst margin" → get_all_jobs_cost_summary
- "cost of ONE specific job"                                        → get_job_cost_breakdown
- "total employee cost this month", "total machine cost", "cost vs revenue", "am I profitable", "misc costs", "order book all active jobs" → get_monthly_cost_summary
- "scheduling conflicts", "double booked", "resource clash"         → get_schedule_overview mode=conflicts
- "jobs not started / should have started"                         → get_schedule_overview mode=not_started
- "jobs due this week"                                             → get_schedule_overview mode=due_this_week
- "busiest day this month"                                         → get_schedule_overview mode=busiest_day
- "critical jobs status", "critical not started"                   → get_schedule_overview mode=critical_status
- "ending in 3 days", "ending soon"                                → get_schedule_overview mode=ending_soon
- "all alerts", "unassigned jobs", "no raw materials", "low profit jobs" → get_alerts_summary
- "machine utilisation", "idle machines", "machine cost", "if machine breaks" → get_machine_utilisation
- "jobs by customer", "customer groups"                            → get_jobs_overview mode=by_customer
- "jobs by priority"                                               → get_jobs_overview mode=by_priority
- "completed this month"                                           → get_jobs_overview mode=completed_this_month
- "jobs starting next week"                                        → get_jobs_overview mode=starting_next_week
- "if RM costs increase", "raw material cost impact"               → get_rm_cost_impact
- "revenue this month", "order book value this month"              → get_monthly_revenue
- "raw material cost breakdown by job"                             → get_raw_material_cost
- "delayed jobs", "overdue", "at risk"                             → get_delayed_jobs
- "who is free today/tomorrow", "who is available"                 → get_employee_availability
- "free / busy machines today"                                     → get_machine_availability
- "shop floor summary", "today summary"                            → get_shop_floor_summary

You understand Hinglish — if the user writes in Hindi or Hinglish, respond in English but be warm and friendly."""


def _build_system_prompt() -> str:
    today = date.today()
    return _SYSTEM_PROMPT_BASE.format(
        today=str(today),
        tomorrow=str(today + timedelta(days=1)),
        yesterday=str(today - timedelta(days=1)),
    )


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

    # Add dynamic system prompt (includes today's date)
    full_messages = [{"role": "system", "content": _build_system_prompt()}] + messages

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
        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
        result = execute_tool(tc.function.name, args, db, tenant_id)
        tool_results.append({
            "tool_call_id": tc.id,
            "role":         "tool",
            "name":         tc.function.name,
            "content":      json.dumps(result),
        })

    # Second call — Llama formats the tool results into a human response
    # msg.content may be None when tool_calls are present — use "" to avoid Groq validation error
    full_messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": msg.tool_calls})
    full_messages.extend(tool_results)

    final_response = client.chat.completions.create(
        model=MODEL,
        messages=full_messages,
        max_tokens=1024,
        temperature=0.4,
    )

    return final_response.choices[0].message.content or "Done."
