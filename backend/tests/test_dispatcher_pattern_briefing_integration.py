# tests/test_dispatcher_pattern_briefing_integration.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Verifies that briefings/dispatcher.py:_build_content_for_kind respects
# the v6.3.11-alpha feature flag and that pattern-briefing failures
# fall through silently to the v6.3.4 templated path.

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.sql.schema import DefaultClause

from app.models.auth import RefreshToken, Tenant, User
from app.models.employee import Employee
from app.models.event import Event
from app.models.job import Job
from app.models.whatsapp import PhoneTenantMap
from app.services.briefing_intelligence import feature_flag as ff_module
from app.services.briefings import dispatcher as dispatcher_module
from app.services.briefings.dispatcher import _build_content_for_kind


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def patch_now_defaults_for_sqlite():
    patched = []
    for tbl in (
        Tenant.__table__, User.__table__, RefreshToken.__table__,
        PhoneTenantMap.__table__, Event.__table__,
        Job.__table__, Employee.__table__,
    ):
        for col in tbl.columns:
            if col.server_default is None:
                continue
            arg = getattr(col.server_default, "arg", None)
            text_value = str(arg) if arg is not None else ""
            if "now()" in text_value.lower():
                patched.append((col, col.server_default))
                col.server_default = DefaultClause(sa_text("CURRENT_TIMESTAMP"))
    yield
    for col, original in patched:
        col.server_default = original


@pytest.fixture(autouse=True)
def reset_feature_flag_cache():
    """The lru_cache in feature_flag holds a frozenset across tests; clear
    it before AND after each test so monkeypatched settings actually apply.
    """
    ff_module._reset_cache()
    yield
    ff_module._reset_cache()


_COUNTER = {"n": 0}


def _next() -> int:
    _COUNTER["n"] += 1
    return _COUNTER["n"]


def _make_tenant(db) -> Tenant:
    n = _next()
    now = datetime.now(timezone.utc)
    t = Tenant(
        name=f"Disp {n}", slug=f"disp-{n}", plan="free",
        is_active=True, industry_type="printing",
        # Created 30 days ago — past quiet period, past day-7 threshold.
        created_at=now - timedelta(days=30),
        updated_at=now,
    )
    db.add(t)
    db.flush()
    return t


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

class TestDispatcherPatternBriefingIntegration:

    def test_flag_off_uses_existing_templated_path(self, db, monkeypatch):
        """With no tenants opted in, the dispatcher must call the v6.3.4
        templated builder and never the pattern composer."""
        tenant = _make_tenant(db)
        db.commit()

        # Ensure flag is OFF (default) and compose_briefing must NOT be called.
        from app.services.briefing_intelligence import feature_flag as ff
        monkeypatch.setattr(
            ff.settings, "PATTERN_BRIEFING_TENANT_IDS", "",
        )
        ff._reset_cache()

        sentinel = "TEMPLATED_PATH_OUTPUT"

        def fake_morning(*args, **kwargs):
            return sentinel

        def fake_compose(*args, **kwargs):
            raise AssertionError(
                "compose_briefing must not be called when flag is OFF"
            )

        monkeypatch.setattr(
            dispatcher_module, "build_morning_briefing", fake_morning
        )
        # Patch the lazily-imported compose_briefing too, via module
        # injection on the briefing_intelligence package.
        from app.services import briefing_intelligence
        monkeypatch.setattr(
            briefing_intelligence, "compose_briefing", fake_compose
        )

        out = _build_content_for_kind(
            tenant=tenant, kind="morning",
            today_in_tz=date(2026, 5, 4), db=db,
        )
        assert out == sentinel

    def test_flag_on_uses_compose_briefing(self, db, monkeypatch):
        tenant = _make_tenant(db)
        db.commit()

        # Opt this tenant in.
        from app.services.briefing_intelligence import feature_flag as ff
        monkeypatch.setattr(
            ff.settings, "PATTERN_BRIEFING_TENANT_IDS", str(tenant.id),
        )
        ff._reset_cache()

        sentinel = "PATTERN_PATH_OUTPUT"

        def fake_compose(*args, **kwargs):
            return sentinel

        from app.services import briefing_intelligence
        monkeypatch.setattr(
            briefing_intelligence, "compose_briefing", fake_compose
        )

        out = _build_content_for_kind(
            tenant=tenant, kind="morning",
            today_in_tz=date(2026, 5, 4), db=db,
        )
        assert out == sentinel

    def test_compose_briefing_failure_falls_back_silently(
        self, db, monkeypatch, caplog,
    ):
        """A raised exception inside compose_briefing must not propagate;
        the dispatcher must fall through to the templated builder."""
        tenant = _make_tenant(db)
        db.commit()

        from app.services.briefing_intelligence import feature_flag as ff
        monkeypatch.setattr(
            ff.settings, "PATTERN_BRIEFING_TENANT_IDS", str(tenant.id),
        )
        ff._reset_cache()

        def boom(*args, **kwargs):
            raise RuntimeError("simulated pattern path failure")

        templated_sentinel = "TEMPLATED_FALLBACK_AFTER_FAILURE"

        def fake_morning(*args, **kwargs):
            return templated_sentinel

        from app.services import briefing_intelligence
        monkeypatch.setattr(
            briefing_intelligence, "compose_briefing", boom
        )
        monkeypatch.setattr(
            dispatcher_module, "build_morning_briefing", fake_morning
        )

        import logging
        with caplog.at_level(logging.ERROR):
            out = _build_content_for_kind(
                tenant=tenant, kind="morning",
                today_in_tz=date(2026, 5, 4), db=db,
            )

        assert out == templated_sentinel
        assert "Pattern briefing failed" in caplog.text
