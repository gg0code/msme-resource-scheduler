# app/services/role_helpers.py - Version 1.0
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Service-layer validators for User.role and PhoneTenantMap.phone_role.
# Introduced in v6.3.1 alongside migration 027 to back SRS v6.4 §6.28.6's
# expanded role taxonomy (owner, factory_manager, co_owner, manager, viewer).
# Validation lives at the service layer, not in the database — this matches
# the convention from migrations 017, 018, 023.
#
# WHO CALLS THIS FILE
# - app/services/auth_service.py - to validate role on register / role change
#   (wired up in v6.3.5; not yet called as of v6.3.1)
# - app/routers/whatsapp.py - to validate phone_role in link_phone() (v6.3.5)
# - tests/test_v6_4_entry_gate.py - to assert allowed/disallowed values
#
# WHAT THIS FILE CALLS
# - app.models.auth.TOP_TIER_ROLES - shared canonical top-tier role set
# Nothing else. Pure functions, no DB calls, no side effects.
#
# DESIGN NOTES
# - VALID_USER_ROLES intentionally includes 'proprietor' as a synonym for
#   'owner' — see app/models/auth.py header notes and
#   memory/feedback_role_synonyms.md. Both spellings coexist until the
#   v6.3.2 role-rename migration runs.
# - VALID_PHONE_ROLES uses the same set per the v6.3.1 prompt: 'Same for
#   phone_tenant_map.phone_role'.
# - is_top_tier-style checks should NOT be reimplemented here — use
#   User.is_top_tier / PhoneTenantMap.is_top_tier instead.

from app.models.auth import TOP_TIER_ROLES


# Allowed values for User.role. Includes 'proprietor' as a synonym for 'owner'
# (see TOP_TIER_ROLES in app/models/auth.py). Change this set in lockstep with
# the auth_service registration logic.
VALID_USER_ROLES = (
    "owner", "proprietor",          # top-tier (synonyms in current data)
    "factory_manager", "co_owner",  # top-tier (new in v6.4)
    "scheduler",                    # operational, mid-tier (existing in data)
    "manager",                      # operational, mid-tier (per SRS §6.17)
    "viewer",                       # read-only
)

TOP_TIER_ROLES = ("owner", "proprietor", "factory_manager", "co_owner")

# Allowed values for PhoneTenantMap.phone_role. Same set as VALID_USER_ROLES
# per the v6.3.1 spec — phone-level role validation mirrors user-level.
VALID_PHONE_ROLES: frozenset = VALID_USER_ROLES


def is_valid_user_role(role: object) -> bool:
    """
    Return True iff `role` is an allowed User.role value.

    Called by:    app/services/auth_service.py (v6.3.5+) on register and
                  role-change endpoints; tests/test_v6_4_entry_gate.py.
    Calls into:   nothing — pure membership test on VALID_USER_ROLES.
    Side effects: none.

    None and non-string inputs return False. The check is case-sensitive —
    'Owner' is rejected; only lowercase 'owner' is accepted, matching
    auth_service.register_tenant_and_user()'s storage convention.
    """
    if not isinstance(role, str):
        return False
    return role in VALID_USER_ROLES


def is_valid_phone_role(role: object) -> bool:
    """
    Return True iff `role` is an allowed PhoneTenantMap.phone_role value.

    Called by:    app/routers/whatsapp.py:link_phone() in v6.3.5+;
                  tests/test_v6_4_entry_gate.py.
    Calls into:   nothing — pure membership test on VALID_PHONE_ROLES.
    Side effects: none.

    Mirrors is_valid_user_role exactly per the v6.3.1 spec; kept as a
    separate function so future iterations can diverge the two sets
    without churning every call site.
    """
    if not isinstance(role, str):
        return False
    return role in VALID_PHONE_ROLES
