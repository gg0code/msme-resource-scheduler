# app/services/briefings/send_with_retry.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Async retry wrapper for briefing sends. Up to MAX_RETRIES retries with
# exponential backoff (1s, 2s, 4s by default). On final failure logs a
# briefing.send_failed event and returns False - never raises. Briefing
# dispatch must not crash the scheduler when one tenant's send misfires.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py - dispatch_briefing wraps every
#   per-recipient WhatsApp send through send_briefing_with_retry.
# - tests/test_briefings.py              - injects a fake send_fn to
#                                           assert retry counts and the
#                                           briefing.send_failed event row.
#
# WHAT THIS FILE CALLS
# - asyncio.sleep   - the backoff timer; injected via sleep_fn param so
#                     tests can replace it with an instant no-op.
# - app/models/event.Event - the failure-event row writer.
# - sqlalchemy Session.add - the failure event is staged on the caller-
#                            owned session; caller commits.

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from sqlalchemy.orm import Session

from app.models.event import Event

logger = logging.getLogger(__name__)


MAX_RETRIES: int = 3       # number of retries AFTER the first attempt
INITIAL_DELAY_SECONDS: float = 1.0
BACKOFF_FACTOR: float = 2.0


SendFn = Callable[[], Awaitable[None]]
SleepFn = Callable[[float], Awaitable[None]]


async def send_briefing_with_retry(
    send_fn: SendFn,
    *,
    tenant_id: int,
    kind: str,
    recipient_user_id: Optional[int],
    db: Session,
    max_retries: int = MAX_RETRIES,
    initial_delay: float = INITIAL_DELAY_SECONDS,
    sleep_fn: SleepFn = asyncio.sleep,
) -> bool:
    """
    Run `send_fn` with up to `max_retries` retries on exception.

    Called by:    dispatcher.dispatch_briefing,
                  dispatcher.manual_trigger_briefing.
    Calls into:   send_fn (caller-supplied async send),
                  sleep_fn (asyncio.sleep by default; injected for tests),
                  _emit_send_failed_event on terminal failure.
    Side effects:
        - At most (max_retries + 1) invocations of send_fn.
        - At most max_retries calls to sleep_fn between attempts.
        - On terminal failure: stages one Event row of type
          'briefing.send_failed' on the caller's `db` session. Caller
          commits; the writer never commits or rolls back its own work.

    Args:
        send_fn:           Zero-arg async callable that performs the
                           WhatsApp send. Raises on failure.
        tenant_id:         For event scoping.
        kind:              'morning' | 'evening' - flows into the failure
                           event payload so audit can group failures.
        recipient_user_id: User ID the send was destined for. Stored in
                           the failure event payload for triage. May be
                           None for cron sends keyed by phone number only.
        db:                Sync SQLAlchemy session. Caller commits.
        max_retries:       Defaults to MAX_RETRIES (3). 0 disables retry
                           - one attempt, no sleeps, no fallback event
                           emission.
        initial_delay:     Seconds to wait before the first retry. Each
                           subsequent retry doubles via BACKOFF_FACTOR.
        sleep_fn:          Injected sleep so tests can avoid real waits.

    Returns:
        True on success at any attempt. False after exhausting all
        retries. NEVER raises - the caller can rely on the boolean
        return without a try/except.
    """
    delay = initial_delay
    last_exc: Optional[BaseException] = None

    for attempt in range(max_retries + 1):
        try:
            await send_fn()
            return True
        except Exception as exc:  # noqa: BLE001 - we want to retry on anything
            last_exc = exc
            if attempt < max_retries:
                logger.warning(
                    "Briefing send failed (attempt %d/%d) tenant=%s kind=%s: %s",
                    attempt + 1, max_retries + 1, tenant_id, kind, exc,
                )
                await sleep_fn(delay)
                delay *= BACKOFF_FACTOR
            else:
                logger.error(
                    "Briefing send failed permanently after %d attempts "
                    "tenant=%s kind=%s recipient_user_id=%s: %s",
                    max_retries + 1, tenant_id, kind, recipient_user_id, exc,
                )

    _emit_send_failed_event(
        db,
        tenant_id=tenant_id,
        kind=kind,
        recipient_user_id=recipient_user_id,
        error=str(last_exc) if last_exc is not None else "unknown",
        attempts=max_retries + 1,
    )
    return False


def _emit_send_failed_event(
    db: Session,
    *,
    tenant_id: int,
    kind: str,
    recipient_user_id: Optional[int],
    error: str,
    attempts: int,
) -> None:
    """
    Stage a single 'briefing.send_failed' Event row on the caller's
    session. Caller commits.

    Called by:    send_briefing_with_retry on terminal failure only.
    Calls into:   db.add (no flush, no commit).
    Side effects: stages an INSERT on events. Visible after the
                  caller's next flush; durable after commit.

    Why no commit here: the dispatcher batches multiple briefings per
    transaction so it can roll back cleanly on a wider failure. Owning
    the commit here would tear that boundary.
    """
    db.add(Event(
        tenant_id=tenant_id,
        event_type="briefing.send_failed",
        entity_type="briefing",
        entity_id=None,
        actor_user_id=None,
        source="system",
        payload={
            "kind":              kind,
            "recipient_user_id": recipient_user_id,
            "attempts":          attempts,
            "error":             error[:500],  # cap to keep payload bounded
        },
    ))
