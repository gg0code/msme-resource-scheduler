"""
FILE:    whatsapp_bridge.py
PATH:    backend/app/services/whatsapp_bridge.py
PURPOSE: The single connection point between the WhatsApp channel and the AI backend.
         Today this calls run_ai_chat() in ai_service.py directly.
         When Factory GPT is ready, only this file changes — a new class is written
         and one line is updated at the bottom. Nothing else in the WhatsApp
         codebase needs to change.

         Think of this file as a power socket. The WhatsApp code plugs into the socket.
         What generates the power (Groq today, Factory GPT tomorrow) is behind the wall.

BRANCH:  v5-whatsapp
VERSION: v5.0
CREATED: 2026-03

DEPENDENCIES:
  app/services/ai_service.py  — run_ai_chat() is the current AI backend being wrapped.
                                NOTE: run_ai_chat() is a SYNC function that takes a
                                sync SQLAlchemy Session. We run it in a thread pool
                                executor to avoid blocking the async FastAPI event loop.
  app/agents/supervisor.py    — SupervisorAgent will be the future swap-in (Factory GPT).
                                This file does not exist yet — placeholder reference only.

IMPORTANT — SYNC vs ASYNC:
  run_ai_chat() in ai_service.py is a synchronous function (uses sync Session).
  Our WhatsApp router is async (uses AsyncSession).
  We bridge this gap using asyncio.get_event_loop().run_in_executor() which runs
  the sync function in a thread pool without blocking the async event loop.
  When Factory GPT arrives, its Supervisor Agent will be natively async —
  the executor wrapper will be removed from SupervisorAgentBridge.

SWAP POINT (Factory GPT):
  When Factory GPT Supervisor Agent is ready:
    1. Write SupervisorAgentBridge class below (template at bottom of file)
    2. Change the last line: active_bridge = SupervisorAgentBridge()
    3. Done. No other file in the WhatsApp codebase needs to change.

USAGE:
  from app.services.whatsapp_bridge import active_bridge
  response = await active_bridge.process_message(
      messages=[{"role": "user", "content": "aaj ka schedule kya hai"}],
      db=db,
      tenant_id=1,
      industry_type="printing",
      language="hinglish"
  )
"""

import asyncio
import logging
from typing import Protocol, runtime_checkable

from sqlalchemy.orm import Session

from app.services.ai_service import run_ai_chat

# ---------------------------------------------------------------------------
# Module logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LANGUAGE PROMPT BUILDER
# ---------------------------------------------------------------------------

def _build_whatsapp_system_message(language: str, industry_type: str) -> dict:
    """
    Build a WhatsApp-specific system message to prepend to the conversation.

    This message tells the AI how to behave on WhatsApp — short responses,
    no markdown, and the correct language style.

    This is where ALL WhatsApp conversation behaviour is controlled.
    To change language behaviour, edit the language_instruction dict below.

    Args:
        language:      Detected language — 'hindi', 'hinglish', or 'english'.
                       Detected by detect_language() in whatsapp_formatter.py.
        industry_type: Tenant's industry vertical — passed through for context.

    Returns:
        A dict in Groq message format: {"role": "system", "content": "..."}
        This is prepended to the messages list before calling run_ai_chat().
    """

    # Language instruction — edit this dict to change language behaviour.
    # To always respond in English: change the default to "Respond in English."
    # To always respond in Hindi: change the default to "Hamesha Hindi mein jawab do."
    language_instruction = {
        "hindi":    "Hamesha Hindi mein jawab do. Devanagari script use karo.",
        "hinglish": "User ki Hinglish style match karo. Hindi aur English naturally mix karo.",
        "english":  "Respond in clear simple English."
    }.get(language, "Match the user's language exactly.")
    # .get() with a default handles any unexpected language value safely

    whatsapp_instructions = f"""You are ZetaOps Copilot responding via WhatsApp.
{language_instruction}
Keep responses SHORT — maximum 5 lines. Factory owners read on mobile screens.
Never use markdown — no **, no ###, no -, no ``` code blocks. Plain text only.
Be direct and practical. Factory owners want quick answers, not long explanations.
If a voice note is prefixed with [Voice]: treat it as normal text after transcription."""

    # Return as a system message in Groq's expected format
    return {"role": "system", "content": whatsapp_instructions}


# ---------------------------------------------------------------------------
# PROTOCOL — the contract every AI bridge must follow
# ---------------------------------------------------------------------------

@runtime_checkable
class AIChannelBridge(Protocol):
    """
    Contract that all AI backend bridges must satisfy.

    This Protocol is the stable interface between the WhatsApp channel
    and whatever AI system is behind it. The WhatsApp code only ever
    calls process_message() — it never knows what AI is doing the work.
    """

    async def process_message(
        self,
        messages: list[dict],
        db: Session,
        tenant_id: int,
        industry_type: str,
        language: str
    ) -> str:
        """
        Send conversation messages to the AI backend and return the response.

        Args:
            messages:      Full conversation history including the new user message.
                           Format: [{"role": "user"|"assistant", "content": "..."}]
                           The WhatsApp system message is added inside this method —
                           callers do not need to add it.
            db:            SQLAlchemy Session — sync Session from ai_service.py.
            tenant_id:     The tenant making the request — for DB row isolation.
            industry_type: Tenant's industry e.g. 'printing', 'manufacturing'.
            language:      Detected language of latest message — 'hindi',
                           'hinglish', or 'english'. Controls AI response style.

        Returns:
            AI response as plain string. May contain markdown —
            pass through whatsapp_formatter.format_for_whatsapp() before sending.

        Side effects:
            None at bridge level. DB writes only via whatsapp_actions.py.
        """
        ...


# ---------------------------------------------------------------------------
# CURRENT IMPLEMENTATION — GroqDirectBridge
# ---------------------------------------------------------------------------

class GroqDirectBridge:
    """
    MVP bridge. Calls run_ai_chat() in ai_service.py directly.

    Handles the sync/async mismatch — run_ai_chat() is synchronous but
    our FastAPI app is async. We use run_in_executor() to run the sync
    function in a thread pool without blocking the event loop.

    This class will be REPLACED (not modified) when Factory GPT is ready.
    """

    async def process_message(
        self,
        messages: list[dict],
        db: Session,
        tenant_id: int,
        industry_type: str,
        language: str
    ) -> str:
        """
        Prepend WhatsApp system message and call run_ai_chat() in a thread pool.

        Args:
            See AIChannelBridge.process_message() for full arg descriptions.

        Returns:
            Raw AI response string from Groq. May contain markdown.
            Pass through whatsapp_formatter.format_for_whatsapp() next.

        Raises:
            Exception: Any exception from run_ai_chat() bubbles up.
                       The caller (routers/whatsapp.py) catches this and
                       sends a friendly error message to the owner.
        """

        # Step 1: Build the WhatsApp-specific system message.
        # This controls language, response length, and no-markdown rules.
        whatsapp_system_msg = _build_whatsapp_system_message(
            language=language,
            industry_type=industry_type
        )

        # Step 2: Prepend the system message to the conversation history.
        # System message goes FIRST — before any user/assistant messages.
        # run_ai_chat() already adds its own industry system prompt internally,
        # so our WhatsApp message adds on top of that.
        messages_with_system = [whatsapp_system_msg] + messages

        logger.debug(
            f"Calling run_ai_chat for tenant_id={tenant_id}, "
            f"industry={industry_type}, language={language}, "
            f"messages={len(messages_with_system)}"
        )

        # Step 3: Run the synchronous run_ai_chat() in a thread pool executor.
        # Why: run_ai_chat() uses a sync SQLAlchemy Session and makes blocking
        # HTTP calls to Groq API. Running it directly in async code would block
        # the entire FastAPI event loop, freezing ALL requests.
        # run_in_executor() offloads it to a separate thread — safe for async.
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,  # None = use the default thread pool executor
            lambda: run_ai_chat(
                messages=messages_with_system,
                db=db,
                tenant_id=tenant_id,
                industry_type=industry_type
            )
        )

        logger.debug(
            f"run_ai_chat completed for tenant_id={tenant_id}, "
            f"response length={len(response)} chars"
        )

        return response


# ---------------------------------------------------------------------------
# ACTIVE BRIDGE — the singleton used by the entire WhatsApp codebase
# ---------------------------------------------------------------------------
# Every file that needs to call the AI imports this one object.
# To swap the AI backend, change ONLY this one line.
#
# Current:  active_bridge = GroqDirectBridge()
# Future:   active_bridge = SupervisorAgentBridge()   ← one line change

active_bridge: AIChannelBridge = GroqDirectBridge()


# ---------------------------------------------------------------------------
# FUTURE SWAP TEMPLATE — SupervisorAgentBridge
# ---------------------------------------------------------------------------
# Uncomment and complete this when Factory GPT Supervisor Agent is ready.
# Do not uncomment until app/agents/supervisor.py exists.
#
# from app.agents.supervisor import SupervisorAgent
#
# class SupervisorAgentBridge:
#     """
#     Factory GPT bridge. Routes messages through the 7-agent Supervisor.
#     Natively async — no run_in_executor() needed unlike GroqDirectBridge.
#     """
#
#     async def process_message(
#         self,
#         messages: list[dict],
#         db: Session,
#         tenant_id: int,
#         industry_type: str,
#         language: str
#     ) -> str:
#         """Route message through Factory GPT Supervisor Agent."""
#         return await SupervisorAgent.handle(
#             tenant_id=tenant_id,
#             messages=messages,
#             industry_type=industry_type
#         )
#
# active_bridge: AIChannelBridge = SupervisorAgentBridge()  # ← one line change