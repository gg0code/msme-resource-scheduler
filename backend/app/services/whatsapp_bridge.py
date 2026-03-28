"""
FILE:    whatsapp_bridge.py
PATH:    backend/app/services/whatsapp_bridge.py
PURPOSE: The single connection point between the WhatsApp channel and the AI backend.
         Today this calls run_ai_chat() with Groq + 16 DB tools directly.
         When Factory GPT is ready, only this file changes — a new class is written
         and one line is updated. Nothing in the webhook, session, formatter, or
         Interakt integration needs to change.

         Think of this file as a power socket. The WhatsApp code plugs into the socket.
         What generates the power (Groq today, Factory GPT tomorrow) is behind the wall.

BRANCH:  v5-whatsapp
VERSION: v5.0
CREATED: 2026-03

DEPENDENCIES:
  app/services/ai_chat.py   — run_ai_chat() is the current AI backend being wrapped
  app/agents/supervisor.py  — SupervisorAgent will be the future swap-in (Factory GPT)
                              This file does not exist yet — it is a placeholder reference.

SWAP POINT (Factory GPT):
  When Factory GPT Supervisor Agent is ready:
    1. Write SupervisorAgentBridge class below (template provided at bottom of file)
    2. Change the last line: active_bridge = SupervisorAgentBridge()
    3. Done. No other file in the WhatsApp codebase needs to change.

USAGE:
  from app.services.whatsapp_bridge import active_bridge
  response = await active_bridge.process_message(
      tenant_id=1,
      user_id=42,
      message="aaj ka schedule kya hai",
      industry_type="printing",
      conversation_history=[{"role": "user", "content": "hello"}]
  )
"""

from typing import Protocol, runtime_checkable
from app.services.ai_chat import run_ai_chat


# ---------------------------------------------------------------------------
# PROTOCOL — the contract that every AI bridge must follow
# ---------------------------------------------------------------------------
# A Protocol in Python is like an interface in Java or C#.
# It defines what methods a class MUST have, without forcing inheritance.
# Any class that has a process_message() method with this exact signature
# automatically qualifies as an AIChannelBridge — no need to inherit from it.

@runtime_checkable
class AIChannelBridge(Protocol):
    """
    Contract that all AI backend bridges must satisfy.

    This Protocol is the stable interface between the WhatsApp channel
    and whatever AI system is behind it. The WhatsApp code only ever
    calls process_message() — it never knows or cares whether Groq,
    Factory GPT, or any other system is doing the actual work.
    """

    async def process_message(
        self,
        tenant_id: int,
        user_id: int,
        message: str,
        industry_type: str,
        conversation_history: list[dict]
    ) -> str:
        """
        Send a user message to the AI backend and return the response.

        This is the single method the WhatsApp channel calls. All AI
        backends must implement this exact signature.

        Args:
            tenant_id:            The tenant making the request.
                                  Used for row-level DB isolation — every
                                  DB query in the AI tools filters by this.
            user_id:              The specific user within that tenant.
            message:              Plain text message from the factory owner.
                                  If this was a voice note, it has already
                                  been transcribed by whatsapp_session.py
                                  before reaching here.
            industry_type:        The tenant's industry vertical, e.g.
                                  'printing', 'manufacturing', 'fabrication',
                                  'chemical', 'field_service'.
                                  Controls which AI tools are shown to the LLM.
            conversation_history: The last N messages from Redis session.
                                  Format: [{"role": "user"|"assistant",
                                            "content": "..."}]
                                  Gives the AI memory of the conversation.

        Returns:
            AI response as a plain string. This is NOT yet formatted for
            WhatsApp — markdown may still be present. The caller
            (routers/whatsapp.py) passes this to whatsapp_formatter.py next.

        Side effects:
            None. This method is read-only at the bridge level.
            Any DB writes happen only inside whatsapp_actions.py,
            never inside the AI bridge.
        """
        ...  # Protocol methods have no body — the implementing class provides it


# ---------------------------------------------------------------------------
# CURRENT IMPLEMENTATION — GroqDirectBridge
# ---------------------------------------------------------------------------
# This is the MVP bridge. It calls run_ai_chat() which uses:
#   - Groq API (Llama model)
#   - 16 DB tool functions defined in ai_chat.py
#   - Industry-aware system prompt
#
# This class will be REPLACED (not modified) when Factory GPT is ready.
# The replacement class is templated at the bottom of this file.

class GroqDirectBridge:
    """
    MVP AI bridge. Calls the existing run_ai_chat() function directly.

    This is the simplest possible implementation — it just passes the
    message straight through to the existing AI Copilot that already
    powers the ZetaOps web UI. The WhatsApp channel gets the same AI
    intelligence as the web dashboard, with no extra setup.

    When Factory GPT agents are ready, this entire class is replaced
    by SupervisorAgentBridge. Nothing else in the codebase changes.
    """

    async def process_message(
        self,
        tenant_id: int,
        user_id: int,
        message: str,
        industry_type: str,
        conversation_history: list[dict]
    ) -> str:
        """
        Pass the message to run_ai_chat() and return its response.

        Translates the bridge interface into the exact parameter format
        that run_ai_chat() expects. If run_ai_chat()'s signature ever
        changes, this is the only place that needs updating.

        Args:
            See AIChannelBridge.process_message() for full arg descriptions.

        Returns:
            Raw AI response string from Groq. May contain markdown.
            Will be cleaned up by whatsapp_formatter.py after this call.

        Raises:
            Exception: Any exception from run_ai_chat() is allowed to
                       bubble up. The caller (routers/whatsapp.py) handles
                       it and sends a friendly error message to the owner.
        """
        # Delegate directly to the existing AI function.
        # run_ai_chat() is defined in app/services/ai_chat.py and is
        # the same function that powers the ZetaOps web UI copilot.
        return await run_ai_chat(
            tenant_id=tenant_id,
            user_id=user_id,
            message=message,
            industry_type=industry_type,
            conversation_history=conversation_history
        )


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
# This template shows exactly what to write when Factory GPT is ready.
# Do not uncomment this until app/agents/supervisor.py exists.
#
# from app.agents.supervisor import SupervisorAgent
#
# class SupervisorAgentBridge:
#     """
#     Factory GPT bridge. Routes messages through the 7-agent Supervisor.
#     Replaces GroqDirectBridge when Factory GPT agents are ready.
#     Change the active_bridge line below to use this class.
#     """
#
#     async def process_message(
#         self,
#         tenant_id: int,
#         user_id: int,
#         message: str,
#         industry_type: str,
#         conversation_history: list[dict]
#     ) -> str:
#         """Route message through Factory GPT Supervisor Agent."""
#         return await SupervisorAgent.handle(
#             tenant_id=tenant_id,
#             message=message,
#             history=conversation_history
#         )
#
# active_bridge: AIChannelBridge = SupervisorAgentBridge()