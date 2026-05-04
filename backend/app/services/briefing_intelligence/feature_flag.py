# app/services/briefing_intelligence/feature_flag.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Per-tenant gate for v6.3.11 pattern briefings. Default is OFF for
# every tenant — the new dispatcher path only runs for tenant ids
# explicitly listed in PATTERN_BRIEFING_TENANT_IDS.
#
# WHO CALLS THIS FILE
# - app/services/briefings/dispatcher.py — _build_content_for_kind
#   wraps compose_briefing in is_pattern_briefing_enabled().
#
# WHAT THIS FILE CALLS
# - app/config.py — settings.PATTERN_BRIEFING_TENANT_IDS (CSV string).
#
# DESIGN NOTES
# - Approach (b) from the v6.3.11 implementation prompt: env-driven
#   CSV list of enabled tenant IDs. Approach (a) — a JSONB feature_flags
#   column on tenants — was rejected because that column does not exist
#   on the Tenant model and adding it would require a migration the
#   user explicitly wanted to avoid for v6.3.11-alpha.
# - Empty / unset CSV = OFF for everyone. v6.3.11-alpha is therefore
#   safe to merge to main with no observable behaviour change for any
#   tenant until an operator explicitly opts a tenant in.
# - Parsing is permissive: surrounding whitespace, trailing commas, and
#   non-numeric tokens are silently skipped. A malformed env value can
#   never crash the dispatcher path.

import logging
from functools import lru_cache
from typing import Iterable, Union

from app.config import settings
from app.models.auth import Tenant

logger = logging.getLogger(__name__)


def _parse_csv_ids(raw: str) -> frozenset[int]:
    """Parse a CSV of tenant IDs into a frozenset[int]. Tolerant of
    whitespace, trailing commas, and bad tokens.
    """
    if not raw:
        return frozenset()
    out: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(int(token))
        except ValueError:
            logger.warning(
                "Ignoring non-integer tenant id in PATTERN_BRIEFING_TENANT_IDS: %r",
                token,
            )
    return frozenset(out)


@lru_cache(maxsize=1)
def _enabled_tenant_ids() -> frozenset[int]:
    """Cache the parsed CSV for the lifetime of the process. Tests that
    need to flip the flag mid-run should call _reset_cache().
    """
    raw = getattr(settings, "PATTERN_BRIEFING_TENANT_IDS", "") or ""
    parsed = _parse_csv_ids(raw)
    if parsed:
        logger.info(
            "Pattern briefing enabled for %d tenant(s): %s",
            len(parsed), sorted(parsed),
        )
    return parsed


def _reset_cache() -> None:
    """Test-only — invalidate the lru_cache after monkeypatching settings."""
    _enabled_tenant_ids.cache_clear()


def is_pattern_briefing_enabled(tenant: Union[Tenant, int]) -> bool:
    """True when this tenant should receive the v6.3.11 pattern briefing
    instead of the v6.3.4 templated path.

    Called by:    briefings/dispatcher.py:_build_content_for_kind.
    Calls into:   _enabled_tenant_ids (cached CSV parse).
    Side effects: none.

    Args:
        tenant: Tenant ORM instance or bare tenant id. The dispatcher
                holds the ORM object; tests sometimes pass an int for
                convenience.

    Returns:
        True iff `tenant.id` (or `tenant` itself when int) is listed
        in settings.PATTERN_BRIEFING_TENANT_IDS. Returns False when
        the setting is empty or the tenant id is missing.
    """
    if isinstance(tenant, int):
        tenant_id = tenant
    else:
        tenant_id = getattr(tenant, "id", None)
    if tenant_id is None:
        return False
    return tenant_id in _enabled_tenant_ids()
