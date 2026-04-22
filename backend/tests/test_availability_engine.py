# tests/test_availability_engine.py
# SRS §6.8 Resource Availability Engine — pure function / unit tests (no DB needed)

from datetime import date, timedelta
from app.services.availability_engine import (
    _date_range,
    _level_meets,
    _effective_availability,
    SKILL_LEVEL_RANK,
)


def d(offset=0):
    return date.today() + timedelta(days=offset)


class TestDateRange:

    def test_single_day_range(self):
        result = _date_range(d(0), d(0))
        assert result == [d(0)]

    def test_multi_day_range(self):
        result = _date_range(d(0), d(4))
        assert len(result) == 5
        assert result[0] == d(0)
        assert result[-1] == d(4)

    def test_range_is_inclusive(self):
        start = date(2026, 4, 1)
        end = date(2026, 4, 3)
        result = _date_range(start, end)
        assert date(2026, 4, 1) in result
        assert date(2026, 4, 2) in result
        assert date(2026, 4, 3) in result
        assert len(result) == 3

    def test_empty_range_when_end_before_start(self):
        result = _date_range(d(5), d(3))
        assert result == []


class TestSkillLevelRank:

    def test_premium_is_highest(self):
        assert SKILL_LEVEL_RANK["Premium"] > SKILL_LEVEL_RANK["Intermediate"]
        assert SKILL_LEVEL_RANK["Premium"] > SKILL_LEVEL_RANK["Generic"]

    def test_intermediate_beats_generic(self):
        assert SKILL_LEVEL_RANK["Intermediate"] > SKILL_LEVEL_RANK["Generic"]

    def test_level_meets_same(self):
        assert _level_meets("Generic", "Generic") is True
        assert _level_meets("Intermediate", "Intermediate") is True
        assert _level_meets("Premium", "Premium") is True

    def test_premium_meets_lower_requirements(self):
        assert _level_meets("Premium", "Intermediate") is True
        assert _level_meets("Premium", "Generic") is True

    def test_intermediate_meets_generic(self):
        assert _level_meets("Intermediate", "Generic") is True

    def test_generic_does_not_meet_higher(self):
        assert _level_meets("Generic", "Intermediate") is False
        assert _level_meets("Generic", "Premium") is False

    def test_intermediate_does_not_meet_premium(self):
        assert _level_meets("Intermediate", "Premium") is False

    def test_unknown_level_treated_as_zero(self):
        assert _level_meets("Unknown", "Generic") is False


class TestEffectiveAvailability:

    def test_no_overrides_returns_base(self):
        result = _effective_availability(100.0, [], d(0))
        assert result == 100.0

    def test_override_reduces_availability(self):
        class FakeOverride:
            date_from = d(-1)
            date_to = d(1)
            availability_pct = 50.0

        result = _effective_availability(100.0, [FakeOverride()], d(0))
        assert result == 50.0

    def test_override_outside_date_range_ignored(self):
        class FakeOverride:
            date_from = d(5)
            date_to = d(10)
            availability_pct = 0.0

        result = _effective_availability(100.0, [FakeOverride()], d(0))
        assert result == 100.0

    def test_multiple_overrides_takes_minimum(self):
        class Ov1:
            date_from = d(-1)
            date_to = d(1)
            availability_pct = 70.0

        class Ov2:
            date_from = d(-1)
            date_to = d(1)
            availability_pct = 30.0

        result = _effective_availability(100.0, [Ov1(), Ov2()], d(0))
        assert result == 30.0

    def test_override_cannot_increase_availability(self):
        class Ov:
            date_from = d(-1)
            date_to = d(1)
            availability_pct = 150.0

        result = _effective_availability(80.0, [Ov()], d(0))
        assert result == 80.0
