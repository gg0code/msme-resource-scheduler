"""
app/routers/ai_chat.py — V3.0
AI Copilot chat endpoint using Groq + Llama 3.3
POST /api/ai/chat
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.auth import User
from app.services.ai_service import run_ai_chat

router = APIRouter()


class ChatMessage(BaseModel):
    role: str       # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]         # Full conversation history
    page_context: Optional[str] = None  # e.g. "jobs", "machines", "dashboard"


class ChatResponse(BaseModel):
    reply: str
    page_context: Optional[str] = None


@router.post("/chat", response_model=ChatResponse)
def ai_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    AI Copilot chat endpoint.
    Accepts full conversation history and returns AI response.
    Scoped to current user's tenant — never leaks data across tenants.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="No messages provided")

    # Convert Pydantic models to plain dicts for Groq
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Optionally prepend page context as a system hint
    if request.page_context:
        context_hint = f"[User is currently on the {request.page_context.upper()} page]"
        # Inject as first user message prefix if it's a single message
        if messages and messages[0]["role"] == "user":
            messages[0]["content"] = f"{context_hint}\n{messages[0]['content']}"

    try:
        reply = run_ai_chat(
            messages=messages,
            db=db,
            tenant_id=current_user.tenant_id,
        )
        return ChatResponse(reply=reply, page_context=request.page_context)

    except ValueError as e:
        # GROQ_API_KEY not set
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI service error: {str(e)}")
