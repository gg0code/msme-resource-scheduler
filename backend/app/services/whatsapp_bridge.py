"""
```python
"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE PURPOSE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This file is the single abstraction layer between the WhatsApp messaging channel and 
the AI backend systems. It acts as a "power socket" - the WhatsApp code plugs into 
this socket, but what generates the AI responses behind the wall can change without 
affecting any WhatsApp code. Introduced in v5-whatsapp branch as part of the Factory 
GPT preparation. Currently wraps Groq/LLaMA calls but designed for seamless swap to 
Factory GPT Supervisor Agent by changing one line.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT THIS FILE DOES — step by step
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Defines AIChannelBridge Protocol - the contract every AI backend must implement
2. Provides _build_whatsapp_context() to create language-specific instruction blocks
3. Provides _inject_whatsapp_context() to prepend instructions to first user message
4. Implements GroqDirectBridge class that wraps ai_service.run_ai_chat()
5. Handles sync/async mismatch using asyncio.run_in_executor() thread pool
6. Exports active_bridge singleton - the one object all WhatsApp code uses
7. Includes template comments for future SupervisorAgentBridge implementation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KEY FUNCTIONS / CLASSES / COMPONENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_build_whatsapp_context()
    Name         : _build_whatsapp_context
    Type         : Private utility function
    Purpose      : Creates a context instruction block to control AI behaviour for 
                   WhatsApp responses. Selects appropriate language instructions 
                   (Hindi/Hinglish/English) and adds mobile-friendly formatting rules.
    Parameters   : language (str) - detected language ('hindi', 'hinglish', 'english')
    Returns      : String block with [WHATSAPP CONTEXT] wrapper containing behavioral 
                   instructions to prepend to user messages
    Calls        : Nothing - pure string building function
    DB/API       : None
    Side effects : None - pure function

_inject_whatsapp_context()
    Name         : _inject_whatsapp_context  
    Type         : Private utility function
    Purpose      : Injects WhatsApp behavioral instructions into the first user message
                   in a conversation. Avoids adding second system message which breaks
                   Groq tool calling validation. Makes shallow copy to avoid mutations.
    Parameters   : messages (list[dict]) - conversation history with role/content dicts
                   language (str) - detected language for instruction selection
    Returns      : New list with context block prepended to first user message content
    Calls        : _build_whatsapp_context() to get the instruction block
    DB/API       : None  
    Side effects : None - creates new list, doesn't mutate input

AIChannelBridge
    Name         : AIChannelBridge
    Type         : Protocol (typing contract)
    Purpose      : Defines the interface contract that every AI backend bridge must 
                   implement. Ensures WhatsApp code can call any AI system uniformly
                   through process_message() method. Uses @runtime_checkable for 
                   isinstance() validation.
    Parameters   : N/A - Protocol definition only
    Returns      : N/A - defines interface, doesn't implement
    Calls        : Nothing - interface definition only
    DB/API       : Specifies that implementations receive Session and tenant_id
    Side effects : None - contract definition only

GroqDirectBridge
    Name         : GroqDirectBridge  
    Type         : Class implementing AIChannelBridge
    Purpose      : Current MVP implementation that wraps ai_service.run_ai_chat() calls.
                   Handles sync/async mismatch by running sync AI calls in thread pool
                   executor. Injects WhatsApp context before calling AI. Will be replaced
                   (not modified) when Factory GPT is ready.
    Parameters   : None for class init
    Returns      : Instance that implements process_message() async method
    Calls        : _inject_whatsapp_context(), ai_service.run_ai_chat()
    DB/API       : Passes Session to run_ai_chat() which makes Groq API calls
    Side effects : None at bridge level - DB writes happen in whatsapp_actions.py

GroqDirectBridge.process_message()
    Name         : process_message
    Type         : Async method of GroqDirectBridge class
    Purpose      : Main entry point for AI processing. Injects WhatsApp context into
                   messages, then calls sync run_ai_chat() via thread pool executor
                   to avoid blocking FastAPI event loop. Returns raw AI response.
    Parameters   : messages (list[dict]) - conversation history with role/content
                   db (Session) - sync SQLAlchemy session for AI service
                   tenant_id (int) - tenant making request for DB isolation
                   industry_type (str) - tenant industry for AI context
                   language (str) - detected language for response formatting
    Returns      : String containing raw AI response (may have markdown formatting)
    Calls        : _inject_whatsapp_context(), asyncio.get_running_loop(), 
                   loop.run_in_executor(), ai_service.run_ai_chat()
    DB/API       : Indirectly makes Groq API calls via run_ai_chat() in thread pool
    Side effects : None - response processing happens in caller (whatsapp router)

active_bridge
    Name         : active_bridge
    Type         : Global singleton variable
    Purpose      : The single instance that all WhatsApp code imports and uses for AI
                   calls. Currently set to GroqDirectBridge(). To swap AI backends,
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

    # No user message found — return unchanged
    # This should never happen in normal flow but handles edge cases safely
    logger.warning(
        "WhatsApp context injection: no user message found in messages list. "
        "Context not injected. Check message flow in routers/whatsapp.py."
    )
    return result


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
# CURRENT IMPLEMENTATION — GroqDirectBridge
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
        language: str
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
        # run_in_executor() offloads it to a separate thread — safe for async.
        loop = asyncio.get_running_loop()

        response = await loop.run_in_executor(
            None,  # None = use the default thread pool executor
            lambda: run_ai_chat(
                messages=messages_with_context,
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
