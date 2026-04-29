# tests/test_permission_helpers.py
#
# FILE PURPOSE
# v6.3.3 unit tests for the four FastAPI permission factories defined in
# app/core/dependencies.py:
#   - require_role(*roles)   - exact-string match (legacy, still in use)
#   - require_top_tier()     - any role in TOP_TIER_ROLES
#   - require_operational()  - top-tier plus scheduler/manager
#   - require_billing_view() - owner / proprietor / co_owner only
#
# The helpers are pure FastAPI dependencies wrapping a single role check.
# We test them by manually invoking the inner _check function with stub
# User objects, side-stepping FastAPI's dependency-resolution wiring.
# This keeps tests sub-second and orthogonal to TestClient setup.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.core.dependencies: require_role, require_top_tier,
#                          require_operational, require_billing_view,
#                          OPERATIONAL_ROLES, BILLING_VIEW_ROLES
#   app.models.auth: User (instantiated with role only - no DB)
#
# DESIGN NOTES
# - Each dependency factory returns a function that takes `user` from
#   FastAPI's dependency tree. We bypass FastAPI by calling the returned
#   inner function directly with a hand-built User. The raise-vs-return
#   semantics are the contract under test - no need to plumb it through
#   TestClient.

import pytest
from fastapi import HTTPException

from app.core.dependencies import (
    BILLING_VIEW_ROLES, OPERATIONAL_ROLES,
    require_billing_view, require_operational, require_role, require_top_tier,
)
from app.models.auth import TOP_TIER_ROLES, User


def _user_with_role(role: str) -> User:
    """Build a transient User instance with a role; no DB attachment."""
    return User(
        id=1, tenant_id=1, email="x@y.z",
        hashed_password="x", role=role, is_active=True,
    )


# ---------------------------------------------------------------------------
# require_top_tier
# ---------------------------------------------------------------------------

class TestRequireTopTier:

    @pytest.mark.parametrize("role", list(TOP_TIER_ROLES))
    def test_passes_every_top_tier_role(self, role: str):
        check = require_top_tier()
        # Direct call, bypass FastAPI Depends wiring.
        result = check.__wrapped__(_user_with_role(role)) \
            if hasattr(check, "__wrapped__") else check(_user_with_role(role))
        assert result.role == role

    @pytest.mark.parametrize("role", ["scheduler", "manager", "viewer", "operator"])
    def test_blocks_non_top_tier(self, role: str):
        check = require_top_tier()
        with pytest.raises(HTTPException) as excinfo:
            check(_user_with_role(role))
        assert excinfo.value.status_code == 403
        assert role in excinfo.value.detail


# ---------------------------------------------------------------------------
# require_operational
# ---------------------------------------------------------------------------

class TestRequireOperational:

    @pytest.mark.parametrize("role", list(OPERATIONAL_ROLES))
    def test_passes_every_operational_role(self, role: str):
        check = require_operational()
        result = check(_user_with_role(role))
        assert result.role == role

    def test_passes_legacy_scheduler_for_v5_12_compat(self):
        # The scheduler regression: v5.12 had ~26 endpoints on
        # require_role('proprietor', 'scheduler'). Those moved to
        # require_operational(). scheduler MUST still pass or every
        # current scheduler user 403s on every operational endpoint.
        check = require_operational()
        result = check(_user_with_role("scheduler"))
        assert result.role == "scheduler"

    @pytest.mark.parametrize("role", ["viewer", "operator", "guest"])
    def test_blocks_below_operational(self, role: str):
        check = require_operational()
        with pytest.raises(HTTPException) as excinfo:
            check(_user_with_role(role))
        assert excinfo.value.status_code == 403


# ---------------------------------------------------------------------------
# require_billing_view
# ---------------------------------------------------------------------------

class TestRequireBillingView:

    @pytest.mark.parametrize("role", list(BILLING_VIEW_ROLES))
    def test_passes_billing_view_roles(self, role: str):
        check = require_billing_view()
        result = check(_user_with_role(role))
        assert result.role == role

    def test_blocks_factory_manager(self):
        # SRS Section 6.28.6: factory_manager has operational rights but
        # NO commercial visibility. require_billing_view explicitly excludes
        # them while require_top_tier and require_operational both let them in.
        check = require_billing_view()
        with pytest.raises(HTTPException) as excinfo:
            check(_user_with_role("factory_manager"))
        assert excinfo.value.status_code == 403

    @pytest.mark.parametrize("role", ["scheduler", "manager", "viewer"])
    def test_blocks_below_billing(self, role: str):
        check = require_billing_view()
        with pytest.raises(HTTPException):
            check(_user_with_role(role))


# ---------------------------------------------------------------------------
# require_role (legacy) - regression
# ---------------------------------------------------------------------------

class TestRequireRoleLegacy:

    def test_legacy_proprietor_owner_pair_passes_both(self):
        # Pattern recommended by v6.3.3 prompt for commercial-edit endpoints:
        # require_role('proprietor', 'owner') accepts both legacy and v6.4
        # spellings until the v6.5+ data consolidation runs.
        check = require_role("proprietor", "owner")
        assert check(_user_with_role("proprietor")).role == "proprietor"
        assert check(_user_with_role("owner")).role == "owner"

    def test_legacy_proprietor_owner_pair_blocks_factory_manager(self):
        check = require_role("proprietor", "owner")
        with pytest.raises(HTTPException) as excinfo:
            check(_user_with_role("factory_manager"))
        assert excinfo.value.status_code == 403
