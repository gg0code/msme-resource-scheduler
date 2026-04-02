"""
```python
"""
FILE PURPOSE
This file implements the AI Copilot chat functionality for ZetaOps, providing manufacturing
businesses with conversational AI assistance for their scheduling and resource management
needs. Introduced in v3.7 on v4-dev branch, it serves as the FastAPI router that handles
all AI chat interactions, usage tracking, and proactive shop floor summaries. It sits
between the frontend chat interface and the core AI service, managing tenant-scoped
rate limiting and feature flag protection.

WHAT THIS FILE DOES — step by step
1. Defines FastAPI router with /api/ai/ prefix for all AI-related endpoints
2. Sets up plan-based daily query limits (free: 50, pro: 500, enterprise: 99999)
3. Creates Pydantic schemas for chat requests/responses and usage tracking
4. Implements usage reset logic that resets counters daily per tenant
5. Provides POST /api/ai/chat endpoint that processes conversational AI requests
6. Guards all endpoints with ai_copilot feature flag via require_feature()
7. Tracks and enforces daily query limits per tenant plan level
8. Injects page context into user messages for better AI responses
9. Passes structured data and industry type to AI service for enhanced responses
10. Handles Groq rate limiting errors with user-friendly messages
11. Provides GET /api/ai/usage endpoint for frontend usage indicators
12. Implements GET /api/ai/greeting for proactive shop floor summaries without LLM calls

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : ChatMessage
Type         : Pydantic BaseModel class
Purpose      : Defines the structure for individual chat messages with role (user/assistant/system) and content. Used as building blocks for conversation history in chat requests.
Parameters   : role (str) - message sender type, content (str) - message text
Returns      : N/A (data model)
Calls        : None
DB/API       : None
Side effects : None

Name         : ChatRequest
Type         : Pydantic BaseModel class
Purpose      : Defines the request payload for chat interactions, including message history, current page context, and pre-fetched structured data. Added structured_data in v3.9.9 for richer AI responses.
Parameters   : messages (list[ChatMessage]) - conversation history, page_context (Optional[str]) - current UI page, structured_data (Optional[dict]) - pre-fetched endpoint data
Returns      : N/A (data model)
Calls        : None
DB/API       : None
Side effects : None

Name         : ChatResponse
Type         : Pydantic BaseModel class
Purpose      : Defines the response payload for chat interactions, including AI reply, usage tracking, and warning messages. Provides frontend with usage metrics for display.
Parameters   : reply (str) - AI response text, page_context (Optional[str]) - echoed page context, queries_used (int) - current usage, queries_limit (int) - plan limit, queries_remaining (int) - remaining quota, warning (Optional[str]) - usage warning
Returns      : N/A (data model)
Calls        : None
DB/API       : None
Side effects : None

Name         : UsageResponse
Type         : Pydantic BaseModel class
Purpose      : Defines the response payload for usage tracking endpoint, providing detailed metrics about AI query consumption for frontend usage indicators and billing warnings.
Parameters   : queries_used (int) - today's usage, queries_limit (int) - plan limit, queries_remaining (int) - remaining quota, usage_pct (float) - percentage used, plan (str) - tenant plan name, date (str) - current date
Returns      : N/A (data model)
Calls        : None
DB/API       : None
Side effects : None

Name         : get_or_reset_usage
Type         : function
Purpose      : Manages daily usage counter resets by checking if the tenant's last query date differs from today. If different, resets ai_queries_today and ai_tokens_today to 0 and updates the date. Ensures usage tracking is scoped to calendar days.
Parameters   : tenant (Tenant) - tenant ORM object, db (Session) - SQLAlchemy session
Returns      : Tenant - updated tenant object with current usage state
Calls        : None directly
DB/API       : Updates Tenant.ai_queries_today, ai_tokens_today, ai_queries_date; commits transaction
Side effects : Modifies tenant usage counters in database

Name         : check_limit
Type         : function
Purpose      : Evaluates whether a tenant has remaining AI queries for today by comparing current usage against plan limits. Returns boolean allowed status plus usage metrics for response building.
Parameters   : tenant (Tenant) - tenant ORM object with usage data
Returns      : tuple[bool, int, int] - (allowed status, queries used, query limit)
Calls        : None
DB/API       : None
Side effects : None

Name         : ai_chat
Type         : FastAPI POST endpoint
Purpose      : Main conversational AI endpoint that processes chat requests, enforces rate limits, injects context, and returns AI responses. Handles feature flagging, usage tracking, error handling, and provides rich context to the AI service including page location and structured data.
Parameters   : request (ChatRequest) - chat payload, db (Session) - database session, current_user (User) - authenticated user
Returns      : ChatResponse - AI reply with usage metrics and warnings
Calls        : require_feature(), run_ai_chat() from app.services.ai_service
DB/API       : Queries Tenant table; calls Groq API via ai_service; updates ai_queries_today counter
Side effects : Increments tenant AI query counter; commits database transaction

Name         : get_usage
Type         : FastAPI GET endpoint
Purpose      : Provides current AI usage statistics for the authenticated tenant, enabling frontend to display usage bars, warnings, and upgrade prompts. Resets daily counters if needed before returning metrics.
Parameters   : db (Session) - database session, current_user (User) - authenticated user
Returns      : UsageResponse - detailed usage metrics and plan information
Calls        : require_feature(), get_or_reset_usage()
DB/API       : Queries Tenant table; may update usage counters if date changed
Side effects : May reset daily usage counters and commit transaction

Name         : get_greeting
Type         : FastAPI GET endpoint
Purpose      : Generates proactive shop floor summaries without LLM calls for fast AI chat initialization. Queries actual job, employee, and machine data to provide real-time status of running jobs, overdue items, at-risk jobs, and resource counts. Pure database logic with no AI inference.
Parameters   : db (Session) - database session, current_user (User) - authenticated user
Returns      : dict - greeting message with embedded shop floor data and metrics
Calls        : require_feature()
DB/API       : Queries Job, Employee, Machine tables with tenant filtering; uses aggregate functions
Side effects : None (read-only queries)

WHO CALLS THIS FILE
- frontend/src/api/api_ai.ts - makes HTTP requests to these endpoints
- frontend/src/components/AIChatPanel.tsx - consumes chat and usage endpoints
- frontend/src/pages/Dashboard.tsx - may call greeting endpoint for AI initialization
- backend/app/main.py - registers this router with /api/ai prefix

IMPORTS EXPLAINED
- traceback - captures full stack traces for debugging AI service errors in production
- date from datetime - manages daily usage reset logic and date comparisons
- APIRouter, Depends, HTTPException from fastapi - core FastAPI routing and dependency injection
- BaseModel from pydantic - creates request/response schemas with validation
- Session from sqlalchemy.orm - provides database session for tenant and usage queries
"""

import traceback
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.auth import User, Tenant
from app.services.ai_service import run_ai_chat
from app.utils.feature_guard import require_feature

try:
    from groq import RateLimitError as GroqRateLimitError
except ImportError:
    GroqRateLimitError = None  # type: ignore

router = APIRouter()

# ── Plan limits ───────────────────────────────────────────────────────────────
PLAN_LIMITS = {
    "free":       50,
    "pro":        500,
    "enterprise": 99999,
}

# ── Schemas ───────────────────────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    page_context: Optional[str] = None
    structured_data: Optional[dict] = None   # v3.9.9 — pre-fetched endpoint data passed by frontend

class ChatResponse(BaseModel):
    reply: str
    page_context: Optional[str] = None
    queries_used: int
    queries_limit: int
    queries_remaining: int
    warning: Optional[str] = None

class UsageResponse(BaseModel):
    queries_used: int
    queries_limit: int
    queries_remaining: int
    usage_pct: float
    plan: str
    date: str

# ── Usage helpers ─────────────────────────────────────────────────────────────
def get_or_reset_usage(tenant: Tenant, db: Session) -> Tenant:
    today = date.today()
    if tenant.ai_queries_date != today:
        tenant.ai_queries_today = 0
        tenant.ai_tokens_today  = 0
        tenant.ai_queries_date  = today
        db.commit()
    return tenant

def check_limit(tenant: Tenant) -> tuple[bool, int, int]:
    limit = PLAN_LIMITS.get(tenant.plan, 50)
    used  = tenant.ai_queries_today or 0
    return used < limit, used, limit

# ── Chat endpoint ─────────────────────────────────────────────────────────────
@router.post("/chat", response_model=ChatResponse)
def ai_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("ai_copilot")
    if guard:
        return guard

    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant = get_or_reset_usage(tenant, db)
    allowed, used, limit = check_limit(tenant)

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily AI query limit reached ({limit}/day on {tenant.plan} plan). Upgrade to continue."
        )

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Inject page context into the last user message (the current question)
    if request.page_context and messages:
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages[i]["content"] = f"[User is on {request.page_context.upper()} page]\n{messages[i]['content']}"
                break

    try:
        # v3.9.9 — pass structured_data to run_ai_chat so it injects into system prompt
        # v4.0.8 — pass industry_type so AI uses correct terminology
        tenant_obj = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        industry_type = (tenant_obj.industry_type or "printing") if tenant_obj else "printing"
        reply = run_ai_chat(
            messages=messages,
            db=db,
            tenant_id=current_user.tenant_id,
            structured_data=request.structured_data,
            industry_type=industry_type,
        )

        tenant.ai_queries_today = (tenant.ai_queries_today or 0) + 1
        db.commit()

        used_now  = tenant.ai_queries_today
        remaining = max(0, limit - used_now)
        usage_pct = (used_now / limit) * 100

        warning = None
        if usage_pct >= 90:
            warning = f"You've used {used_now}/{limit} AI queries today. Upgrade your plan for more."

        return ChatResponse(
            reply=reply,
            page_context=request.page_context,
            queries_used=used_now,
            queries_limit=limit,
            queries_remaining=remaining,
            warning=warning,
        )

    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        # Groq rate-limit (token quota exhausted) — show friendly message
        err_str = str(e)
        if GroqRateLimitError and isinstance(e, GroqRateLimitError):
            raise HTTPException(
                status_code=429,
                detail="AI service is temporarily at capacity (Groq token limit reached). Please try again in ~30 minutes, or upgrade the Groq plan at console.groq.com."
            )
        if "rate_limit_exceeded" in err_str or "tokens per day" in err_str.lower():
            raise HTTPException(
                status_code=429,
                detail="AI service is temporarily at capacity (daily token limit reached). Please try again in ~30 minutes."
            )
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

# ── Usage endpoint ────────────────────────────────────────────────────────────
@router.get("/usage", response_model=UsageResponse)
def get_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # V3.7 — feature flag guard
    guard = require_feature("ai_copilot")
    if guard:
        return guard

    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant = get_or_reset_usage(tenant, db)
    limit  = PLAN_LIMITS.get(tenant.plan, 50)
    used   = tenant.ai_queries_today or 0

    return UsageResponse(
        queries_used=used,
        queries_limit=limit,
        queries_remaining=max(0, limit - used),
        usage_pct=round((used / limit) * 100, 1),
        plan=tenant.plan,
        date=str(date.today()),
    )


# ── Proactive greeting endpoint — V3.9 ────────────────────────────────────────
@router.get("/greeting")
def get_greeting(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns a proactive shop floor summary for the AI opening message.
    Pure DB query — no LLM call. Fast and always grounded in real data.
    """
    guard = require_feature("ai_copilot")
    if guard:
        return guard

    from app.models.job import Job, JobAssignment
    from app.models.employee import Employee
    from app.models.machine import Machine
    from datetime import datetime
    from sqlalchemy import func

    tenant_id = current_user.tenant_id
    today = date.today()

    # All active jobs
    active_jobs = db.query(Job).filter(
        Job.tenant_id == tenant_id,
        Job.status.notin_(["Completed", "Cancelled"]),
    ).all()

    # Running jobs
    running = [j for j in active_jobs if j.timer_status == "running"]

    # At risk — due within 3 days and not started
    at_risk = [
        j for j in active_jobs
        if j.end_date and j.status in ["Draft", "Scheduled"]
        and 0 <= ((j.end_date.date() if hasattr(j.end_date, 'date') else j.end_date) - today).days <= 3
    ]

    # Overdue
    overdue = [
        j for j in active_jobs
        if j.end_date and (j.end_date.date() if hasattr(j.end_date, 'date') else j.end_date) < today
    ]

    # Unassigned
    unassigned = [j for j in active_jobs if not j.assignments]

    # Resource counts
    total_employees = db.query(func.count()).select_from(Employee).filter(
        Employee.tenant_id == tenant_id, Employee.status == "Active"
    ).scalar() or 0

    total_machines = db.query(func.count()).select_from(Machine).filter(
        Machine.tenant_id == tenant_id, Machine.status == "Operational"
    ).scalar() or 0

    # Build greeting message
    total_active = len(active_jobs)

    if total_active == 0:
        message = (
            "Namaste! 👋 Your shop floor is quiet — no active jobs right now.\n\n"
            "Use the **Getting Started** checklist on your Dashboard to set up your first job, "
            "or ask me anything about your resources."
        )
    else:
        lines = [f"Namaste! 👋 Here's your shop floor right now:\n"]

        lines.append(f"📋 **{total_active} active job{'s' if total_active > 1 else ''}**")

        if running:
            names = ", ".join(j.name for j in running[:2])
            suffix = f" +{len(running)-2} more" if len(running) > 2 else ""
            lines.append(f"▶️  Running: {names}{suffix}")

        if overdue:
            names = ", ".join(j.name for j in overdue[:2])
            suffix = f" +{len(overdue)-2} more" if len(overdue) > 2 else ""
            lines.append(f"🔴 Overdue: {names}{suffix}")

        if at_risk:
            names = ", ".join(j.name for j in at_risk[:2])
            suffix = f" +{len(at_risk)-2} more" if len(at_risk) > 2 else ""
            lines.append(f"⚠️  At risk (due soon): {names}{suffix}")

        if unassigned:
            lines.append(f"📌 {len(unassigned)} job{'s' if len(unassigned) > 1 else ''} with no resources assigned")

        lines.append(f"\n👥 {total_employees} employees · 🏭 {total_machines} machines")
        lines.append("\nWhat would you like to know?")

        message = "\n".join(lines)

    return {
        "message": message,
        "data": {
            "total_active": total_active,
            "running": len(running),
            "overdue": len(overdue),
            "at_risk": len(at_risk),
            "unassigned": len(unassigned),
            "total_employees": total_employees,
            "total_machines": total_machines,
        }
    }
