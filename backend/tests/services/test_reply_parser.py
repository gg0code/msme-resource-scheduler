# tests/services/test_reply_parser.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Unit tests for app/services/promotion/reply_parser.py (v6.3.15
# revised). Covers the hybrid (heuristic + LLM) parsing strategy:
#   - all-yes / all-no / skip via heuristic (multi-vocabulary)
#   - numbered partial via heuristic
#   - named partial via heuristic
#   - LLM prong with stubbed Groq client
#   - LLM failure -> all-deferred fallback
#   - empty / missing reply
#   - reusing whatsapp_actions vocabulary (per Stage-1 A.6)

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.services.promotion.reply_parser import parse_reply


@dataclass
class _FakeCandidate:
    id: int
    raw_value: str
    entity_type: str = "employee"
    normalized_value: str = ""

    def __post_init__(self):
        if not self.normalized_value:
            self.normalized_value = self.raw_value.strip().lower()


def _make_batch(*pairs: tuple[int, str]) -> list[_FakeCandidate]:
    """Helper - one fake candidate per (id, raw_value) pair."""
    return [_FakeCandidate(id=i, raw_value=n) for i, n in pairs]


# ---------------------------------------------------------------------------
# Heuristic - all-yes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yes_word", [
    "haan", "haa", "han", "yes", "ok", "theek", "bilkul",
    "Haan", "  YES  ",  # case + whitespace tolerance
])
def test_heuristic_all_yes_words(yes_word):
    batch = _make_batch((1, "Suresh"), (2, "Mukesh"))

    out = parse_reply(yes_word, batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {1: "confirmed", 2: "confirmed"}


@pytest.mark.parametrize("no_word", [
    "nahi", "nahin", "naa", "no", "cancel", "rehne do",
    "NAHI",
])
def test_heuristic_all_no_words(no_word):
    batch = _make_batch((1, "Suresh"), (2, "Mukesh"))

    out = parse_reply(no_word, batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {1: "rejected", 2: "rejected"}


@pytest.mark.parametrize("skip_word", [
    "skip", "kuch nahi", "Skip",
])
def test_heuristic_all_skip_words(skip_word):
    batch = _make_batch((1, "Suresh"), (2, "Mukesh"))

    out = parse_reply(skip_word, batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {1: "deferred", 2: "deferred"}


# ---------------------------------------------------------------------------
# Heuristic - numbered partial
# ---------------------------------------------------------------------------

def test_numbered_partial_one_yes_two_no():
    batch = _make_batch((10, "Suresh"), (20, "Mukesh"))

    out = parse_reply("1 haan, 2 nahi", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {10: "confirmed", 20: "rejected"}


def test_numbered_partial_grouped_indices():
    batch = _make_batch((10, "A"), (20, "B"), (30, "C"))

    out = parse_reply("1, 2 haan, 3 nahi", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {10: "confirmed", 20: "confirmed", 30: "rejected"}


def test_numbered_partial_unmentioned_index_defers():
    batch = _make_batch((10, "A"), (20, "B"), (30, "C"))

    out = parse_reply("1 haan", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    # Only 1 explicit; others default to deferred (NOT confirmed).
    assert out.decisions == {10: "confirmed", 20: "deferred", 30: "deferred"}


# ---------------------------------------------------------------------------
# Heuristic - named partial
# ---------------------------------------------------------------------------

def test_named_partial_two_names_two_verdicts():
    batch = _make_batch((1, "Suresh"), (2, "Mukesh"))

    out = parse_reply("suresh haan, mukesh nahi", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {1: "confirmed", 2: "rejected"}


def test_named_partial_longest_match_wins():
    """'Suresh' should not steal the verdict for 'Suresh Kumar'."""
    batch = _make_batch((1, "Suresh"), (2, "Suresh Kumar"))

    out = parse_reply("suresh kumar haan", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    # 'Suresh Kumar' (longer match) wins.
    assert out.decisions[2] == "confirmed"
    # 'Suresh' was not explicitly mentioned -> deferred.
    assert out.decisions[1] == "deferred"


def test_named_partial_unrecognised_name_falls_to_llm(monkeypatch):
    """A name not in the batch + no number -> heuristic gives up."""
    batch = _make_batch((1, "Suresh"))

    # Stub the LLM to confirm everything so we can assert strategy=='llm'.
    fake = _make_groq_stub({"1": "confirmed"})
    out = parse_reply(
        "ravi haan",
        batch,
        tenant_id=12,
        groq_client=fake,
    )

    # The clause "ravi haan" doesn't match any candidate -> heuristic
    # returns None -> LLM stub fires.
    assert out.strategy == "llm"
    assert out.decisions == {1: "confirmed"}


# ---------------------------------------------------------------------------
# LLM prong - stubbed Groq client
# ---------------------------------------------------------------------------

def _make_groq_stub(decisions_payload: dict) -> SimpleNamespace:
    """Build a minimal stub of the Groq client.

    Mirrors the shape entity_extractor.py uses: client.chat.completions.create
    returns an object with .choices[0].message.content (a JSON string).
    """
    import json as _json
    body = _json.dumps({"decisions": decisions_payload})

    msg     = SimpleNamespace(content=body)
    choice  = SimpleNamespace(message=msg)
    response = SimpleNamespace(choices=[choice])

    create = lambda **kwargs: response  # noqa: E731 - tiny stub
    completions = SimpleNamespace(create=create)
    chat = SimpleNamespace(completions=completions)
    return SimpleNamespace(chat=chat)


def _make_groq_failing_stub() -> SimpleNamespace:
    """Stub that raises on chat.completions.create."""
    def _raise(**kwargs):
        raise RuntimeError("simulated Groq failure")
    completions = SimpleNamespace(create=_raise)
    chat = SimpleNamespace(completions=completions)
    return SimpleNamespace(chat=chat)


def test_llm_prong_handles_complex_partial(monkeypatch):
    batch = _make_batch((1, "Suresh"), (2, "Mukesh"), (3, "Heidelberg"))
    # Owner says something nuanced that mentions no candidate name and
    # no heuristic verdict token - heuristic gives up, LLM resolves.
    fake = _make_groq_stub(
        {"1": "confirmed", "2": "rejected", "3": "deferred"}
    )

    out = parse_reply(
        "samajh nahi aaya in mein se konsa wala aapka apna hai",
        batch,
        tenant_id=12,
        groq_client=fake,
    )

    assert out.strategy == "llm"
    assert out.decisions == {1: "confirmed", 2: "rejected", 3: "deferred"}


def test_llm_failure_falls_back_to_all_deferred():
    batch = _make_batch((1, "Suresh"), (2, "Mukesh"))
    fake = _make_groq_failing_stub()

    out = parse_reply(
        "kuch alag bolna chahta hoon ye option mein nahi hain",
        batch,
        tenant_id=12,
        groq_client=fake,
    )

    assert out.strategy == "fallback"
    assert out.decisions == {1: "deferred", 2: "deferred"}
    # The unparsed text is preserved for human review.
    assert "kuch alag" in out.unparsed_text


def test_llm_pads_missing_ids_with_deferred():
    """LLM that only returns 1 of 3 candidates - parser pads the rest.

    The reply intentionally avoids any heuristic token (no candidate
    names from the batch, no haan/nahi/skip etc.) so the LLM prong
    fires.
    """
    batch = _make_batch((1, "Alpha"), (2, "Bravo"), (3, "Charlie"))
    fake = _make_groq_stub({"1": "confirmed"})  # Missing 2 and 3.

    out = parse_reply(
        "pehla wala thik lag raha pakka kuch keh sakta",
        batch, tenant_id=12, groq_client=fake,
    )

    assert out.strategy == "llm"
    assert out.decisions[1] == "confirmed"
    assert out.decisions[2] == "deferred"
    assert out.decisions[3] == "deferred"


def test_llm_drops_unknown_candidate_ids():
    """LLM hallucinating candidate id 999 - parser ignores it.

    Reply written to defeat the heuristic so the LLM prong runs.
    """
    batch = _make_batch((1, "Alpha"))
    fake = _make_groq_stub({"1": "confirmed", "999": "confirmed"})

    out = parse_reply(
        "ye saari list samajh hi nahi paya",
        batch, tenant_id=12, groq_client=fake,
    )

    assert out.strategy == "llm"
    assert out.decisions == {1: "confirmed"}


def test_llm_drops_invalid_verdict_values():
    """LLM returning a non-vocab verdict - parser drops it.

    Reply written so neither named-partial nor numbered-partial
    resolves heuristically; the LLM stub returns the bad verdict
    that we want the parser to drop.
    """
    batch = _make_batch((1, "Alpha"), (2, "Bravo"))
    fake = _make_groq_stub({"1": "maybe", "2": "confirmed"})  # 'maybe' invalid.

    out = parse_reply(
        "kuch samajh paya kuch samajh nahi paya",
        batch, tenant_id=12, groq_client=fake,
    )

    assert out.strategy == "llm"
    # 'maybe' was dropped -> id 1 padded as deferred. id 2 honoured.
    assert out.decisions[1] == "deferred"
    assert out.decisions[2] == "confirmed"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_reply_defers_all():
    batch = _make_batch((1, "A"), (2, "B"))

    out = parse_reply("", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {1: "deferred", 2: "deferred"}


def test_whitespace_only_reply_defers_all():
    batch = _make_batch((1, "A"))

    out = parse_reply("   \n  ", batch, tenant_id=12)

    assert out.strategy == "heuristic"
    assert out.decisions == {1: "deferred"}


def test_no_candidates_returns_empty_fallback():
    out = parse_reply("haan", [], tenant_id=12)

    assert out.strategy == "fallback"
    assert out.decisions == {}


def test_partial_with_haan_and_digit_not_swallowed_as_all_yes():
    """'haan 1 nahi' must NOT resolve as all-yes because of leading 'haan'."""
    batch = _make_batch((1, "A"), (2, "B"))

    out = parse_reply("haan 1 nahi", batch, tenant_id=12)

    # Heuristic recognises the partial shape (digits) and routes to the
    # numbered parser. '1 nahi' -> id 1 rejected, id 2 deferred.
    assert out.strategy == "heuristic"
    assert out.decisions[1] == "rejected"
    assert out.decisions[2] == "deferred"


def test_raw_reply_is_lowercased_and_stripped():
    batch = _make_batch((1, "A"))

    out = parse_reply("  HAAN  ", batch, tenant_id=12)

    assert out.raw_reply == "haan"
    assert out.decisions == {1: "confirmed"}
