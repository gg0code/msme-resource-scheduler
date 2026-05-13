# app/services/whatsapp_templates.py
# Branch: v5-whatsapp
# Iteration: v6.3.21 follow-up (Runtime template lookup helper + Day-7 / give-up-nudge wiring)
#
# FILE PURPOSE
# Runtime counterpart to whatsapp_meta_templates.py. Given an internal
# event name, a language, and an ordered tuple of positional args, return
# a ResolvedTemplate containing everything both mock-mode and production-
# mode WhatsApp dispatchers need: the Meta template name + language for
# the Interakt POST, the rendered Python string for [MOCK ALERT] logging
# and for the audit trail, and the ordered params list as plain strings
# ready for Meta's positional template-component API.
#
# This is the SINGLE place where "internal event name" -> "Meta template
# name" routing happens. Dispatchers should never reach into
# META_TEMPLATES directly.
#
# WHO CALLS THIS FILE (current + planned)
# - app/services/whatsapp_alerts.py        (v5.10 proactive alerts)
# - app/services/owner_briefing.py         (v5.15 7:15am briefing)
# - app/services/manager_checkin.py        (v5.15 7:00am check-in)
# - app/services/consolidated_briefing.py  (v6.3.4+ push briefing scheduler)
# - app/services/team_invite_whatsapp.py   (v6.3.5 invite welcome)
# - app/services/kpi_capture.py            (v6.24 monthly summary, planned)
# - tests/test_whatsapp_templates.py       (this iteration's tests)
# Dispatchers added in later iterations should import resolve_template
# from here. Do not duplicate the routing logic.
#
# WHAT THIS FILE CALLS
# - app.services.whatsapp_meta_templates   (META_TEMPLATES, MetaTemplate,
#                                           count_meta_placeholders)
# - app.services.message_formatters        (the per-template constants,
#                                           accessed by getattr on the
#                                           module — never imported
#                                           individually, because the
#                                           binding name comes from
#                                           PYTHON_CONSTANT_BINDINGS at
#                                           runtime, not at import time)
# - logging                                (warning on language fallback)
# - dataclasses, typing                    (ResolvedTemplate shape)
#
# KEY DESIGN DECISIONS
# - Positional args, not named kwargs. After v6.3.22a normalisation,
#   every Python constant in message_formatters uses positional {N}
#   placeholders; the Meta wire format is positional; the helper does
#   `template_string.format(*args)`. A single rendering strategy
#   covers all 40 constants.
# - Language fallback is hi -> en_US, never the other way. en_US is the
#   defined canonical language; every event has an en_US variant in the
#   registry by convention. If en_US is also missing, raise — silent
#   fallback to "whatever's there" hides bugs in the registry.
# - Mock-vs-production is the dispatcher's concern, not this helper's.
#   The helper returns BOTH the rendered Python string AND the Meta
#   params list. The caller picks which to use based on the env var.
# - Pending-status entries (draft_pending_meta_submission /
#   pending_meta_approval) do not change helper behaviour. The helper
#   resolves them identically to a live template; gating on status is a
#   production-mode dispatcher concern (it should refuse to send to Meta
#   until status flips). Mock mode doesn't care because mock mode never
#   talks to Meta.
# - Unknown event name and arg-count mismatch are distinct exceptions
#   (UnknownEventError, ArgCountMismatchError) so callsite tests can
#   distinguish "I typo'd the event name" from "I passed the wrong
#   number of args".

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

from app.services import message_formatters
from app.services.whatsapp_meta_templates import (
    META_TEMPLATES,
    MetaTemplate,
    count_meta_placeholders,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class UnknownEventError(KeyError):
    """Raised when resolve_template is called with an event name that
    EVENT_ROUTING doesn't know. The exception message lists every known
    event for grep-friendly debugging."""


class ArgCountMismatchError(ValueError):
    """Raised when the number of args passed to resolve_template does
    not match the Meta template's HEADER+BODY {{n}} placeholder count.
    The exception message names the event, language, expected count, and
    received count."""


@dataclass(frozen=True)
class ResolvedTemplate:
    """The single output of resolve_template.

    meta_name:      Meta template name, e.g. 'zetaops_morning_briefing'.
                    Production-mode dispatchers pass this to Interakt.
    meta_language:  The language code actually used after fallback, one
                    of 'en_US' or 'hi'. May differ from the language the
                    caller requested if fallback fired.
    rendered_text:  The Python format-string from message_formatters,
                    rendered with the caller's args. Mock-mode dispatchers
                    print this as [MOCK ALERT]; audit logs use it too.
    meta_params:    The args list, with every element coerced to str,
                    ready to be sent as Interakt template components.
                    Order matches the meta-side HEADER+BODY {{n}}
                    numbering convention from whatsapp_meta_templates.py
                    (HEADER first, then BODY).
    used_fallback:  True iff the caller requested 'hi' but only 'en_US'
                    was available. Dispatchers may surface this for
                    observability. Always False when caller requested
                    'en_US' directly.
    """
    meta_name: str
    meta_language: str
    rendered_text: str
    meta_params: list[str]
    used_fallback: bool


# ---------------------------------------------------------------------------
# Internal: event -> meta_name routing
# ---------------------------------------------------------------------------
# This map is the only place where "internal event name" meets "Meta
# template name". Adding a new template means adding a row here AND
# wiring its Python constant in message_formatters.py AND binding it in
# whatsapp_meta_templates.py PYTHON_CONSTANT_BINDINGS. The alignment
# audit (AC 23-AC7) enforces the latter two; this dict is enforced by
# tests in test_whatsapp_templates.py which assert every event maps to
# at least one (name, language) present in META_TEMPLATES.

EVENT_ROUTING: Final[dict[str, str]] = {
    # Onboarding & consent
    "welcome_consent":              "zetaops_welcome_consent",
    "workspace_ready":              "zetaops_workspace_ready",
    # Briefings
    "morning_briefing":             "zetaops_morning_briefing",
    "evening_briefing":             "zetaops_evening_briefing",
    # Manager check-in
    "manager_checkin":              "zetaops_manager_checkin",
    # Operational alerts
    "machine_breakdown_alert":      "zetaops_machine_breakdown_alert",
    "job_conflict_alert":           "zetaops_job_conflict_alert",
    "job_ending_soon":              "zetaops_job_ending_soon",
    "attendance_flag":              "zetaops_attendance_flag",
    # Order intake
    "order_confirmation_request":   "zetaops_order_confirmation_request",
    # Compliance
    "compliance_reminder_t30":      "zetaops_compliance_reminder_t30",
    "compliance_reminder_t7":       "zetaops_compliance_reminder_t7",
    "compliance_reminder_t1":       "zetaops_compliance_reminder_t1",
    # Team invite
    "invite_team_member":           "zetaops_invite_team_member",
    "manager_activated":            "zetaops_manager_activated",
    "manager_joined_owner_notice":  "zetaops_manager_joined_owner_notice",
    "invite_pending_owner_nudge":   "zetaops_invite_pending_owner_nudge",
    # Manager engagement ladder
    "manager_input_acknowledged":   "zetaops_manager_input_acknowledged",
    "manager_reply_nudge":          "zetaops_manager_reply_nudge",
    "manager_day3_rhythm":          "zetaops_manager_day3_rhythm",
    "manager_day7_mirror":          "zetaops_manager_day7_mirror",
    # Performance & finance
    "performance_summary_monthly":  "zetaops_performance_summary_monthly",
    "gst_einvoice_ready":           "zetaops_gst_einvoice_ready",
    # Day-7 insight + engagement ladder fallback (Meta submission PENDING)
    "owner_day7_insight":           "zetaops_owner_day7_insight",
    "engagement_give_up_nudge":     "zetaops_engagement_give_up_nudge",
}


# Languages allowed as caller input. Hinglish is detected upstream and
# routed to 'en_US' or 'hi' by the caller (detect_language() in
# whatsapp_responses.py per SRS Section 6.18) before reaching this
# helper. The helper does not classify language itself.
_ALLOWED_LANGUAGES: Final[frozenset[str]] = frozenset({"en_US", "hi"})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_template(
    event: str,
    language: str,
    args: tuple[object, ...] | list[object],
) -> ResolvedTemplate:
    """Resolve an internal event + language + args to a ResolvedTemplate.

    Called by:    every WhatsApp dispatcher in app/services/*.py and
                  app/routers/whatsapp_router.py. See WHO CALLS THIS FILE
                  in the module header for the current list.
    Calls into:   META_TEMPLATES (whatsapp_meta_templates), getattr on
                  the message_formatters module, count_meta_placeholders,
                  logger.warning on fallback.
    Side effects: one logger.warning if language fallback fires.
                  Otherwise pure — no I/O, no DB, no Meta API.

    Args:
        event:    Internal event name; must be a key of EVENT_ROUTING.
        language: 'en_US' or 'hi'. Caller is responsible for
                  classifying Hinglish to one of these before calling.
        args:     Ordered positional args matching the template's
                  HEADER+BODY placeholder count (e.g. EVENING_BRIEFING_EN
                  expects 6 args because HEADER has 1 and BODY has 5).
                  Tuple or list; elements may be any type — they are
                  str()-converted for meta_params and passed unchanged
                  to .format() for rendered_text.

    Returns:
        ResolvedTemplate. See the dataclass docstring for field semantics.

    Raises:
        UnknownEventError:     event not in EVENT_ROUTING.
        ValueError:            language not in {'en_US', 'hi'}.
        ArgCountMismatchError: len(args) != Meta placeholder count for
                               the resolved (name, language) pair.
        AttributeError:        if PYTHON_CONSTANT_BINDINGS names a
                               constant that doesn't exist in
                               message_formatters. This is a registry
                               drift bug, not a caller bug — let it
                               propagate so the missing constant is
                               obvious from the stack trace.
    """
    if event not in EVENT_ROUTING:
        known = ", ".join(sorted(EVENT_ROUTING.keys()))
        raise UnknownEventError(
            f"Unknown event {event!r}. Known events: {known}"
        )

    if language not in _ALLOWED_LANGUAGES:
        raise ValueError(
            f"language must be one of {sorted(_ALLOWED_LANGUAGES)}; "
            f"got {language!r}. Hinglish should be classified to "
            f"'en_US' or 'hi' upstream (see SRS Section 6.18)."
        )

    meta_name = EVENT_ROUTING[event]

    used_fallback = False
    key = (meta_name, language)
    if key not in META_TEMPLATES:
        if language == "hi":
            fallback_key = (meta_name, "en_US")
            if fallback_key not in META_TEMPLATES:
                raise KeyError(
                    f"Registry drift: META_TEMPLATES has neither "
                    f"({meta_name!r}, 'hi') nor ({meta_name!r}, 'en_US'). "
                    f"Every event in EVENT_ROUTING must have at least an "
                    f"en_US entry."
                )
            logger.warning(
                "whatsapp_templates: language fallback fired for "
                "event=%s requested=hi served=en_US meta_name=%s",
                event, meta_name,
            )
            key = fallback_key
            used_fallback = True
        else:
            raise KeyError(
                f"Registry drift: META_TEMPLATES has no "
                f"({meta_name!r}, 'en_US') entry. Check wiring for "
                f"event={event!r}."
            )

    entry: MetaTemplate = META_TEMPLATES[key]

    expected = count_meta_placeholders(entry)
    given = len(args)
    if given != expected:
        raise ArgCountMismatchError(
            f"event={event!r} language={key[1]!r} (meta_name={meta_name!r}) "
            f"expects {expected} args (HEADER+BODY placeholder count); "
            f"got {given}."
        )

    constant_name = entry["python_constant"]
    if constant_name is None:
        raise KeyError(
            f"event={event!r} language={key[1]!r}: META_TEMPLATES entry "
            f"has no python_constant binding. Add it in "
            f"PYTHON_CONSTANT_BINDINGS (whatsapp_meta_templates.py)."
        )
    template_string: str = getattr(message_formatters, constant_name)
    rendered_text = template_string.format(*args)

    meta_params = [str(a) for a in args]

    return ResolvedTemplate(
        meta_name=meta_name,
        meta_language=key[1],
        rendered_text=rendered_text,
        meta_params=meta_params,
        used_fallback=used_fallback,
    )


# ---------------------------------------------------------------------------
# Convenience accessor
# ---------------------------------------------------------------------------

def known_events() -> list[str]:
    """Sorted list of every event name in EVENT_ROUTING.

    Called by:    debug routes, ops scripts, and the registry-coverage
                  test in tests/test_whatsapp_templates.py.
    Calls into:   nothing.
    Side effects: none.
    """
    return sorted(EVENT_ROUTING.keys())
