# tests/services/test_extraction_feature_flag.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/extraction/feature_flag.py (v6.3.14).
# The flag mirrors the v6.3.11 PATTERN_BRIEFING_TENANT_IDS shape, so
# these tests mirror tests/test_briefing_intelligence_feature_flag*.py
# in spirit.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app.services.extraction.feature_flag — is_entity_extraction_enabled,
#                                          _parse_csv_ids, _reset_cache.
#   app.config.settings — monkeypatched per-test.
#
# DESIGN NOTES
#   The lru_cache wrapper means tests must call _reset_cache after
#   monkeypatching settings, otherwise the previous test's state leaks.

from app.services.extraction.feature_flag import (
    _enabled_tenant_ids,
    _parse_csv_ids,
    _reset_cache,
    is_entity_extraction_enabled,
)


def test_flag_off_when_setting_empty(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "", raising=False,
    )
    _reset_cache()
    assert is_entity_extraction_enabled(1) is False
    assert is_entity_extraction_enabled(99) is False


def test_flag_on_when_tenant_id_in_csv(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "12,17,34",
        raising=False,
    )
    _reset_cache()
    assert is_entity_extraction_enabled(12) is True
    assert is_entity_extraction_enabled(17) is True
    assert is_entity_extraction_enabled(34) is True
    assert is_entity_extraction_enabled(99) is False


def test_flag_handles_whitespace_and_bad_tokens(monkeypatch):
    # Mixed whitespace, trailing commas, an empty token, a non-integer.
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS",
        " 12 , 13,, , bogus ,14 ,",
        raising=False,
    )
    _reset_cache()
    parsed = _enabled_tenant_ids()
    assert parsed == frozenset({12, 13, 14})


def test_flag_accepts_int_or_tenant_orm(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "5",
        raising=False,
    )
    _reset_cache()

    class FakeTenant:
        id = 5

    assert is_entity_extraction_enabled(5) is True
    assert is_entity_extraction_enabled(FakeTenant()) is True

    class TenantWithoutId:
        pass

    # Object without an `id` attribute => disabled, not an error.
    assert is_entity_extraction_enabled(TenantWithoutId()) is False


def test_flag_cache_resets_on_setting_change(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "1",
        raising=False,
    )
    _reset_cache()
    assert is_entity_extraction_enabled(1) is True

    monkeypatch.setattr(
        "app.config.settings.ENTITY_EXTRACTION_TENANT_IDS", "2",
        raising=False,
    )
    # Without _reset_cache the flag would still be on for 1 because of
    # the lru_cache. After reset, only 2 should be enabled.
    _reset_cache()
    assert is_entity_extraction_enabled(1) is False
    assert is_entity_extraction_enabled(2) is True


def test_parse_csv_ids_returns_frozenset():
    result = _parse_csv_ids("1,2,3")
    assert result == frozenset({1, 2, 3})
    assert isinstance(result, frozenset)
