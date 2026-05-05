# app/services/push_schedule.py - Version 1.0
# Branch: v5-whatsapp
# Iteration: v6.3.12 (Day-1 onboarding sequence)
#
# FILE PURPOSE
# Single lookup point for the morning + evening briefing times that any
# tenant-facing message needs to quote. Today this is a thin wrapper over
# Tenant.briefing_morning_time / briefing_evening_time (defaults 07:30 /
# 18:30 IST, see migration 027). v6.3.19 will swap the bodies for the
# industry_push_config + tenant override cascade WITHOUT changing this
# module's signatures, so call sites stay stable.
#
# WHO CALLS THIS FILE
# - app/services/onboarding_message.py - quotes the morning time in the
#                                         Day-1 confirmation WhatsApp.
# - Future v6.3.x messages that need to reference the schedule should
#   call here too rather than reading the column directly. That is the
#   whole point of the indirection.
#
# WHAT THIS FILE CALLS
# - Nothing today - pure attribute reads on Tenant. v6.3.19 will introduce
#   a query into the (still-to-be-built) industry_push_config table.
#
# DESIGN NOTES
# - Returns datetime.time, not str. Callers format via strftime so locale
#   formatting stays at the call site. This avoids pre-committing the
#   v6.3.18 styling pass to a particular display format here.
# - There is intentionally no get_morning_checkin_time() helper. The
#   v6.3.4 dispatcher fires a SINGLE morning trigger that produces both
#   the attendance check-in and the briefing summary - they share one
#   time. Splitting them is a v6.3.x decision; do not anticipate it here
#   by inventing a second symbol that returns the same value today.
# - Fallback to 07:30 / 18:30 only fires if the column is unexpectedly
#   None - the migration sets a server_default and the column is
#   non-nullable, so this path is reached only by hand-built test
#   fixtures that bypass the model defaults.

from datetime import time

from app.models.auth import Tenant


def get_morning_briefing_time(tenant: Tenant) -> time:
    """
    Return the morning briefing + attendance time for this tenant.

    Called by:    app/services/onboarding_message.send_if_unsent (quotes
                  the time in the Day-1 confirmation message body).
    Calls into:   nothing today - reads Tenant.briefing_morning_time.
                  v6.3.19 will introduce industry_push_config lookup with
                  tenant override fallback inside this body.
    Side effects: none.

    Args:
        tenant: SQLAlchemy Tenant ORM row. Caller is responsible for
                ensuring the row was loaded inside a session.

    Returns:
        datetime.time. The migration 027 server_default is 07:30:00
        Asia/Kolkata; this function returns whatever the column holds.
        Callers format the value via strftime("%H:%M") at the call site.
    """
    return tenant.briefing_morning_time or time(7, 30)


def get_evening_briefing_time(tenant: Tenant) -> time:
    """
    Return the evening briefing time for this tenant.

    Called by:    reserved for future v6.3.x messages that need to
                  reference the evening recap. Not used by v6.3.12.
    Calls into:   nothing today - reads Tenant.briefing_evening_time.
                  v6.3.19 will introduce industry_push_config lookup here.
    Side effects: none.

    Args:
        tenant: SQLAlchemy Tenant ORM row.

    Returns:
        datetime.time. Migration 027 server_default is 18:30:00 IST.
    """
    return tenant.briefing_evening_time or time(18, 30)
