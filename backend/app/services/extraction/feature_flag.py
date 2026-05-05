# app/services/extraction/feature_flag.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Per-tenant gate for the v6.3.14 entity extractor. Default is OFF for
# every tenant — the extractor service only runs for tenant ids
# explicitly listed in ENTITY_EXTRACTION_TENANT_IDS.
#
# WHO CALLS THIS FILE
# - app/services/extraction/entity_extractor.py — schedule_extraction
#   short-circuits when the flag is off for the message's tenant.
# - app/services/extraction/__init__.py — re-exports
#   is_entity_extraction_enabled.
# - backend/tests/services/test_extraction_feature_flag.py
#
# WHAT THIS FILE CALLS
# - app/config.py — settings.ENTITY_EXTRACTION_TENANT_IDS (CSV string).
#
# DESIGN NOTES
# - Pattern lifted verbatim from
#   app/services/briefing_intelligence/feature_flag.py (v6.3.11).
#   That precedent rejected the JSONB feature_flags column on tenants
#   because the column does not exist and adding it would force a
#   migration; v6.3.14 follows the same reasoning.
# - Empty / unset CSV = OFF for everyone. v6.3.14 is therefore safe
#   to merge to main with no observable behaviour change for any
#   tenant until an operator explicitly opts a tenant in.
# - Parsing is permissive: surrounding whitespace, trailing commas,
#   and non-numeric tokens are silently skipped. A malformed env
#   value can never crash the WhatsApp pipeline.
#
# FORWARD-COMPAT
# - v6.3.15 will add a similar flag for the promotion job. Same
#   pattern, different setting key.

import logging
from functools import lru_cache
from typing import Union

from app.config import settings
from app.models.auth import Tenant

logger = logging.getLogger(__name__)


def _parse_csv_ids(raw: str) -> frozenset[int]:
    """Parse a CSV of tenant IDs into a frozenset[int].

    Tolerant of whitespace, trailing commas, and bad tokens.

    Called by:    _enabled_tenant_ids (this file).
    Calls into:   nothing (stdlib only).
    Returns:      frozenset[int] of valid tenant ids; empty if `raw`
                  is empty or contains no parseable integers.
    Side effects: logs a WARNING for each non-integer token skipped.
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
                "Ignoring non-integer tenant id in "
                "ENTITY_EXTRACTION_TENANT_IDS: %r",
                token,
            )
    return frozenset(out)


@lru_cache(maxsize=1)
def _enabled_tenant_ids() -> frozenset[int]:
    """Cache the parsed CSV for the lifetime of the process.

    Called by:    is_entity_extraction_enabled (this file).
    Calls into:   _parse_csv_ids (this file), settings (app.config).
    Returns:      frozenset[int] of opted-in tenant ids.
    Side effects: logs an INFO line on first load when the set is
                  non-empty, so an operator can confirm at boot which
                  tenants are receiving the new behaviour.

    Tests that need to flip the flag mid-run should call _reset_cache
    after monkeypatching settings.ENTITY_EXTRACTION_TENANT_IDS.
    """
    raw = getattr(settings, "ENTITY_EXTRACTION_TENANT_IDS", "") or ""
    parsed = _parse_csv_ids(raw)
    if parsed:
        logger.info(
            "Entity extraction enabled for %d tenant(s): %s",
            len(parsed), sorted(parsed),
        )
    return parsed


def _reset_cache() -> None:
    """Test-only helper — invalidate the lru_cache after monkeypatching.

    Called by:    test_extraction_feature_flag.py.
    Calls into:   _enabled_tenant_ids.cache_clear (functools).
    Side effects: clears the lru_cache; next call re-reads settings.
    """
    _enabled_tenant_ids.cache_clear()


def is_entity_extraction_enabled(tenant: Union[Tenant, int]) -> bool:
    """True when this tenant should run the v6.3.14 entity extractor.

    Called by:    app/services/extraction/entity_extractor.py
                  (schedule_extraction short-circuits when False).
    Calls into:   _enabled_tenant_ids (cached CSV parse).
    Side effects: none.

    Args:
        tenant: Tenant ORM instance or bare tenant id. The caller in
                the WhatsApp pipeline holds the tenant id directly via
                identity.tenant_id; tests may pass an ORM object.

    Returns:
        True iff `tenant.id` (or `tenant` itself when int) is listed
        in settings.ENTITY_EXTRACTION_TENANT_IDS. Returns False when
        the setting is empty or the tenant id is missing.
    """
    if isinstance(tenant, int):
        tenant_id = tenant
    else:
        tenant_id = getattr(tenant, "id", None)
    if tenant_id is None:
        return False
    return tenant_id in _enabled_tenant_ids()
