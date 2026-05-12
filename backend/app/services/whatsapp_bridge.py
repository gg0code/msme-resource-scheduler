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
# WHATSAPP CONTEXT INJECTOR
# ---------------------------------------------------------------------------

def _build_whatsapp_context(language: str) -> str:
    """
    Build a WhatsApp behavioural context block to prepend to the first user message.

    WHY THIS APPROACH:
    Groq requires exactly one system message. Adding a second system message
    causes tool call validation to fail. Instead, we inject WhatsApp instructions
    as a [WHATSAPP CONTEXT] block at the start of the first user message.
    The model reads it as instructions before seeing the user's actual question.

    Args:
        language: Detected language — 'hindi', 'hinglish', or 'english'.

    Returns:
        A string block to prepend to the first user message content.
        Example output:
          [WHATSAPP CONTEXT]
          User ki Hinglish style match karo...
          Keep responses SHORT...
          [END CONTEXT]
          <actual user message>
    """

    # Language instruction per detected language
    language_instruction = {
        "hindi":    "Hamesha Hindi mein jawab do. Devanagari script use karo.",
        "hinglish": "User ki Hinglish style match karo. Hindi aur English naturally mix karo.",
        "english":  "Respond in clear simple English.",
    }.get(language, "Match the user's language exactly.")

    return (
        f"[WHATSAPP CONTEXT]\n"
        f"{language_instruction}\n"
        f"Keep responses SHORT — maximum 5 lines. Factory owners read on mobile screens.\n"
        f"Never use markdown — no **, no ###, no -, no ``` blocks. Plain text only.\n"
        f"Be direct and practical. Quick answers only.\n"
        f"[END CONTEXT]\n\n"
    )


def _inject_whatsapp_context(messages: list[dict], language: str) -> list[dict]:
    """
    Inject WhatsApp behavioural instructions into the messages list.

    Finds the first user message and prepends the context block to its content.
    If no user message exists, returns messages unchanged.

    This avoids adding a second system message which breaks Groq tool calling.

    Args:
        messages: Conversation history — list of {role, content} dicts.
        language: Detected language for instruction selection.

    Returns:
        New messages list with context injected into first user message.
        Original list is not mutated — a shallow copy is made.

    Side effects:
        None — pure function.
    """

    context_block = _build_whatsapp_context(language)

    # Make a shallow copy so we don't mutate the caller's list
    result = list(messages)

    # Find the first user message and prepend context to it
    for i, msg in enumerate(result):
        if msg.get("role") == "user":
            result[i] = {
                **msg,
                "content": context_block + msg["content"]
            }
            return result

    # No user message found - return unchanged
    # This should never happen in normal flow but handles edge cases safely
    logger.warning(
        "WhatsApp context injection: no user message found in messages list. "
        "Context not injected. Check message flow in routers/whatsapp.py."
    )
    return result


# ---------------------------------------------------------------------------
# PROTOCOL - the contract every AI bridge must follow
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
        language: str,
        *,
        actor_user_id: int | None = None,
        phone_number: str | None = None,
    ) -> str:
        """
        Send conversation messages to the AI backend and return the response.

        Args:
            messages:      Full conversation history including the new user message.
                           Format: [{"role": "user"|"assistant", "content": "..."}]
                           WhatsApp context is injected inside this method —
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
# CURRENT IMPLEMENTATION - GroqDirectBridge
# ---------------------------------------------------------------------------

class GroqDirectBridge:
    """
    MVP bridge. Calls run_ai_chat() in ai_service.py directly.

    Handles the sync/async mismatch — run_ai_chat() is synchronous but
    our FastAPI app is async. We use run_in_executor() to run the sync
    function in a thread pool without blocking the event loop.

    v5.1 fix: WhatsApp instructions injected into first user message instead
    of as a second system message, which broke Groq tool call validation.

    This class will be REPLACED (not modified) when Factory GPT is ready.
    """

    async def process_message(
        self,
        messages: list[dict],
        db: Session,
        tenant_id: int,
        industry_type: str,
        language: str,
        *,
        actor_user_id: int | None = None,
        phone_number: str | None = None,
    ) -> str:
        """
        Inject WhatsApp context and call run_ai_chat() in a thread pool.

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

        # Step 1: Inject WhatsApp behavioural instructions into the first
        # user message. This avoids a second system message which breaks
        # Groq's tool call validation. See _inject_whatsapp_context() docs.
        messages_with_context = _inject_whatsapp_context(messages, language)

        logger.debug(
            f"Calling run_ai_chat for tenant_id={tenant_id}, "
            f"industry={industry_type}, language={language}, "
            f"messages={len(messages_with_context)}"
        )

        # Step 2: Run the synchronous run_ai_chat() in a thread pool executor.
        # Why: run_ai_chat() uses a sync SQLAlchemy Session and makes blocking
        # HTTP calls to Groq API. Running it directly in async code would block
        # the entire FastAPI event loop, freezing ALL requests.
        # run_in_executor() offloads it to a separate thread - safe for async.
        loop = asyncio.get_event_loop()

        response = await loop.run_in_executor(
            None,  # None = use the default thread pool executor
            lambda: run_ai_chat(
                messages=messages_with_context,
                db=db,
                tenant_id=tenant_id,
                industry_type=industry_type,
                actor_user_id=actor_user_id,
                phone_number=phone_number,
            )
        )

        logger.debug(
            f"run_ai_chat completed for tenant_id={tenant_id}, "
            f"response length={len(response)} chars"
        )

        return response


# ---------------------------------------------------------------------------
# ACTIVE BRIDGE - the singleton used by the entire WhatsApp codebase
# ---------------------------------------------------------------------------
# Every file that needs to call the AI imports this one object.
# To swap the AI backend, change ONLY this one line.
#
# Current:  active_bridge = GroqDirectBridge()
# Future:   active_bridge = SupervisorAgentBridge()   <- one line change

active_bridge: AIChannelBridge = GroqDirectBridge()


# ---------------------------------------------------------------------------
# FUTURE SWAP TEMPLATE - SupervisorAgentBridge
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
# active_bridge: AIChannelBridge = SupervisorAgentBridge()  # <- one line change
