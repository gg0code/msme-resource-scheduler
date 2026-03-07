"""
app/routers/ai_chat.py — V3.2
AI Copilot chat endpoint using Groq + Llama 3.3
POST /api/ai/chat
GET  /api/ai/usage  — get current usage for tenant
Added: per-tenant daily query tracking + token counting
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

    if request.page_context and messages and messages[0]["role"] == "user":
        messages[0]["content"] = f"[User is on {request.page_context.upper()} page]\n{messages[0]['content']}"

    try:
        reply = run_ai_chat(
            messages=messages,
            db=db,
            tenant_id=current_user.tenant_id,
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")

# ── Usage endpoint ────────────────────────────────────────────────────────────
@router.get("/usage", response_model=UsageResponse)
def get_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
