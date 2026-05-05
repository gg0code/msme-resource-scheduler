# tests/services/test_industry_vocabularies_sync.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Lint test for the v6.3.14 backend industry vocabulary mirror. Parses
# the matching frontend industry config .ts files and asserts that
# pickers.skills + pickers.machineTypes match the values in
# app/services/extraction/industry_vocabularies.py exactly.
#
# Without this test, drift between frontend and backend can go
# undetected — the extractor would silently fall back to an empty
# vocabulary for verticals where the names had been renamed on one
# side. The test runs in the standard "not integration" suite.
#
# WHO CALLS THIS FILE
#   pytest tests/ -m "not integration" -v
#
# WHAT THIS FILE CALLS
#   app/services/extraction/industry_vocabularies — INDUSTRY_VOCABULARIES.
#   frontend/src/config/industries/{printing,fabrication,manufacturing,
#                                   chemical,field_service}.ts — read as text.
#
# DESIGN NOTES
#   - The .ts files are intentionally simple JSON-shaped objects. We
#     extract the skills and machineTypes arrays with two regexes.
#     If the frontend file's shape ever changes meaningfully (e.g. the
#     arrays are pulled from a function), this test will fail loudly,
#     which is the right outcome — someone should think about the
#     backend impact rather than the test silently passing.

import re
from pathlib import Path

import pytest

from app.services.extraction.industry_vocabularies import (
    INDUSTRY_VOCABULARIES,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_INDUSTRIES = REPO_ROOT / "frontend" / "src" / "config" / "industries"


def _parse_string_array(source: str, key: str) -> list[str]:
    """Pull a string-array literal out of a TypeScript object source.

    Looks for a `<key>: [ "a", "b", ... ]` block and returns the
    string contents. Tolerant of single or double quotes and trailing
    commas. Returns [] if the key is not found.

    This is intentionally tiny — the .ts files we read are static
    object literals, not real TS expressions, so a regex parse is
    sufficient. If the frontend ever swaps to a builder function
    this regex will return [] and the assertion downstream will
    fail with a clear message.
    """
    block_re = re.compile(rf"{key}\s*:\s*\[(.*?)\]", re.DOTALL)
    block_match = block_re.search(source)
    if not block_match:
        return []
    body = block_match.group(1)
    # Match single- or double-quoted strings.
    items = re.findall(r"['\"]([^'\"]+)['\"]", body)
    return items


@pytest.mark.parametrize("industry_id", [
    "printing",
    "fabrication",
    "manufacturing",
    "chemical",
    "field_service",
])
def test_backend_vocab_matches_frontend(industry_id):
    ts_path = FRONTEND_INDUSTRIES / f"{industry_id}.ts"
    assert ts_path.exists(), f"Missing frontend config: {ts_path}"

    source = ts_path.read_text(encoding="utf-8")
    fe_skills   = _parse_string_array(source, "skills")
    fe_machines = _parse_string_array(source, "machineTypes")

    assert fe_skills,   f"Could not parse skills from {ts_path}"
    assert fe_machines, f"Could not parse machineTypes from {ts_path}"

    backend = INDUSTRY_VOCABULARIES[industry_id]

    assert backend["skills"] == fe_skills, (
        f"Backend skills for {industry_id} drifted from frontend.\n"
        f"  frontend ({ts_path.name}): {fe_skills}\n"
        f"  backend  (industry_vocabularies.py): {backend['skills']}\n"
        f"Update one or both — see SYNC_WITH block at top of "
        f"industry_vocabularies.py."
    )
    assert backend["machine_types"] == fe_machines, (
        f"Backend machine_types for {industry_id} drifted from frontend.\n"
        f"  frontend ({ts_path.name}): {fe_machines}\n"
        f"  backend  (industry_vocabularies.py): {backend['machine_types']}\n"
        f"Update one or both — see SYNC_WITH block at top of "
        f"industry_vocabularies.py."
    )


def test_backend_covers_all_five_verticals():
    expected = {"printing", "fabrication", "manufacturing", "chemical", "field_service"}
    assert set(INDUSTRY_VOCABULARIES.keys()) == expected
