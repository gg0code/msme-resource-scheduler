# tests/services/test_confirmation_composer.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/promotion/confirmation_composer.py
# (v6.3.15 revised). Covers:
#   - per-vertical vocabulary substitution (5 industries)
#   - generic fallback for unknown industry
#   - per-locale variants (en / hi / hi-en)
#   - cap enforcement is the caller's job — composer renders what it
#     gets (verified by giving it 3 vs 7 vs 1 vs 0 candidates)
#   - sort order is the caller's job — composer preserves input order
#   - employee vs machine line variants
#   - unexpected entity_type defensive skip
#   - empty input -> None
#   - compose_ack: all-confirmed / all-rejected / mixed / unparsed
#
# The composer is pure (no DB), so tests are simple data-in/data-out.

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.promotion.confirmation_composer import (
    ComposedMessage,
    compose_ack,
    compose_message,
)


@dataclass
class _FakeCandidate:
    """Minimal stand-in for ExtractionCandidate.

    The composer only reads .id, .raw_value, .mention_count,
    .entity_type, .tenant_id. Using a fake avoids needing a DB
    fixture for these pure-function tests.
    """
    id: int
    raw_value: str
    mention_count: int
    entity_type: str
    tenant_id: int = 1
    normalized_value: str = ""

    def __post_init__(self):
        if not self.normalized_value:
            self.normalized_value = self.raw_value.strip().lower()


# ---------------------------------------------------------------------------
# Tests - per-industry happy path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "industry,expected_employee_label,expected_machine_label,expected_workspace",
    [
        ("printing",      "employee",   "press",   "factory"),
        ("fabrication",   "operator",   "machine", "workshop"),
        ("manufacturing", "operator",   "machine", "shop floor"),
        ("chemical",      "operator",   "reactor", "plant"),
        ("field_service", "technician", "asset",   "sites"),
    ],
)
def test_compose_message_uses_industry_vocabulary(
    industry, expected_employee_label,
    expected_machine_label, expected_workspace,
):
    candidates = [
        _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
        _FakeCandidate(id=2, raw_value="Heidelberg", mention_count=3, entity_type="machine"),
    ]

    out = compose_message(candidates, industry_type=industry)

    assert out is not None
    assert expected_workspace in out.text
    assert f"({expected_employee_label}?)" in out.text
    assert f"({expected_machine_label}?)" in out.text


def test_compose_message_unknown_industry_falls_back_to_printing():
    candidates = [
        _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type="not_a_real_industry")

    assert out is not None
    # Printing vocabulary - 'employee' singular, 'factory' workspace.
    assert "factory" in out.text
    assert "(employee?)" in out.text


def test_compose_message_none_industry_falls_back_to_printing():
    candidates = [
        _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type=None)

    assert out is not None
    assert "factory" in out.text


# ---------------------------------------------------------------------------
# Tests - per-locale variants
# ---------------------------------------------------------------------------

def test_compose_message_locale_en():
    candidates = [
        _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type="printing", locale="en")

    assert out is not None
    # English uses "mentioned 5 times" rather than the Hinglish "5 baar".
    assert "mentioned 5 times" in out.text
    assert "Add them?" in out.text


def test_compose_message_locale_hi_en_default():
    candidates = [
        _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type="printing")  # locale=None -> hi-en

    assert out is not None
    assert "5 baar mention hua" in out.text
    assert "Add karna hai?" in out.text
    # Per Q6 wording change: "Pichhle kuch dino mein", not "Pichhle hafte mein".
    assert "Pichhle kuch dino mein" in out.text
    assert "Pichhle hafte mein" not in out.text


def test_compose_message_locale_hi():
    candidates = [
        _FakeCandidate(id=1, raw_value="Mukesh", mention_count=4, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type="printing", locale="hi")

    assert out is not None
    assert "Pichhle kuch dino mein" in out.text


# ---------------------------------------------------------------------------
# Tests - rendering shape
# ---------------------------------------------------------------------------

def test_compose_message_numbers_lines_one_indexed():
    candidates = [
        _FakeCandidate(id=11, raw_value="A", mention_count=5, entity_type="employee"),
        _FakeCandidate(id=22, raw_value="B", mention_count=4, entity_type="machine"),
        _FakeCandidate(id=33, raw_value="C", mention_count=3, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type="printing")

    assert out is not None
    # 1-based numbering for owner readability.
    assert "1. A" in out.text
    assert "2. B" in out.text
    assert "3. C" in out.text
    assert out.candidate_ids == [11, 22, 33]
    assert out.candidate_index_map == {1: 11, 2: 22, 3: 33}


def test_compose_message_employee_vs_machine_line_variants():
    candidates = [
        _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
        _FakeCandidate(id=2, raw_value="Heidelberg", mention_count=3, entity_type="machine"),
    ]

    out = compose_message(candidates, industry_type="printing")

    assert out is not None
    # Employee line carries "(employee?)"; machine line carries "(press?)".
    assert "1. Suresh - 5 baar mention hua (employee?)" in out.text
    assert "2. Heidelberg - 3 baar mention hua (press?)" in out.text


def test_compose_message_single_candidate_renders():
    candidates = [
        _FakeCandidate(id=1, raw_value="Solo", mention_count=10, entity_type="employee"),
    ]

    out = compose_message(candidates, industry_type="printing")

    assert out is not None
    assert "1. Solo" in out.text
    assert out.candidate_ids == [1]


def test_compose_message_zero_candidates_returns_none():
    out = compose_message([], industry_type="printing")
    assert out is None


def test_compose_message_unexpected_entity_type_skipped(caplog):
    """Defensive: composer should skip unknown entity_types and log."""
    import logging
    caplog.set_level(logging.WARNING, logger="app.services.promotion.confirmation_composer")
    candidates = [
        _FakeCandidate(id=1, raw_value="A", mention_count=5, entity_type="employee"),
        _FakeCandidate(id=2, raw_value="Bad", mention_count=4, entity_type="customer"),
        _FakeCandidate(id=3, raw_value="C", mention_count=3, entity_type="machine"),
    ]

    out = compose_message(candidates, industry_type="printing")

    assert out is not None
    # Bad candidate skipped; renumbered as 1, 2.
    assert "1. A" in out.text
    assert "2. C" in out.text
    assert "Bad" not in out.text
    assert out.candidate_ids == [1, 3]
    assert any("unexpected_type" in r.message for r in caplog.records)


def test_compose_message_all_unexpected_returns_none():
    candidates = [
        _FakeCandidate(id=1, raw_value="A", mention_count=5, entity_type="customer"),
        _FakeCandidate(id=2, raw_value="B", mention_count=4, entity_type="skill"),
    ]
    out = compose_message(candidates, industry_type="printing")
    assert out is None


def test_compose_message_preserves_input_order():
    """Composer does NOT re-sort; the caller is responsible for ordering."""
    # Caller passes in (id=3 first, id=1 second) intentionally; composer
    # must render in that order.
    candidates = [
        _FakeCandidate(id=3, raw_value="Z", mention_count=99, entity_type="employee"),
        _FakeCandidate(id=1, raw_value="A", mention_count=1,  entity_type="employee"),
    ]
    out = compose_message(candidates, industry_type="printing")
    assert out is not None
    assert out.candidate_ids == [3, 1]
    # Z renders before A despite alphabetical order.
    z_pos = out.text.index("1. Z")
    a_pos = out.text.index("2. A")
    assert z_pos < a_pos


# ---------------------------------------------------------------------------
# Tests - compose_ack
# ---------------------------------------------------------------------------

def test_compose_ack_all_confirmed():
    cand_by_id = {
        1: _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
        2: _FakeCandidate(id=2, raw_value="Mukesh", mention_count=4, entity_type="employee"),
    }
    decisions = {1: "confirmed", 2: "confirmed"}

    ack = compose_ack(
        decisions=decisions,
        candidates_by_id=cand_by_id,
        industry_type="printing",
    )

    assert "Suresh" in ack
    assert "Mukesh" in ack
    # All-confirmed template doesn't include skip language.
    assert "skip" not in ack.lower() and "skipped" not in ack.lower()


def test_compose_ack_all_rejected():
    cand_by_id = {
        1: _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
    }
    decisions = {1: "rejected"}

    ack = compose_ack(
        decisions=decisions,
        candidates_by_id=cand_by_id,
        industry_type="printing",
    )

    # All-rejected uses the "kuch add nahi kiya" template.
    assert "kuch add nahi" in ack.lower() or "nothing added" in ack.lower()


def test_compose_ack_mixed_confirmed_rejected():
    cand_by_id = {
        1: _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
        2: _FakeCandidate(id=2, raw_value="Mukesh", mention_count=4, entity_type="employee"),
    }
    decisions = {1: "confirmed", 2: "rejected"}

    ack = compose_ack(
        decisions=decisions,
        candidates_by_id=cand_by_id,
        industry_type="printing",
    )

    assert "Suresh" in ack
    assert "Mukesh" in ack


def test_compose_ack_all_deferred_uses_unparsed_template():
    cand_by_id = {
        1: _FakeCandidate(id=1, raw_value="Suresh", mention_count=5, entity_type="employee"),
    }
    decisions = {1: "deferred"}

    ack = compose_ack(
        decisions=decisions,
        candidates_by_id=cand_by_id,
        industry_type="printing",
    )

    # All-deferred is the parser-fallback case - ack tells the owner
    # to be more specific.
    assert "haan" in ack.lower() or "nahi" in ack.lower() or "yes" in ack.lower()
