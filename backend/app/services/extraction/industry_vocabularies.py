# app/services/extraction/industry_vocabularies.py
# Branch: v5-whatsapp
#
# FILE PURPOSE
# Backend mirror of the per-vertical skill + machine vocabularies that
# the v6.3.10 frontend industry config files expose under
# IndustryConfig.pickers.{skills, machineTypes}. The v6.3.14 entity
# extractor injects these into its LLM prompt so the model can
# disambiguate vertical-specific terms — e.g. "Heidelberg" is a
# printing press in the printing vertical, not a German town.
#
# WHO CALLS THIS FILE
# - app/services/extraction/entity_extractor.py — get_industry_vocabulary
#   is called once per inbound message to compose the prompt.
# - backend/tests/services/test_industry_vocabularies_sync.py —
#   parses the matching frontend .ts files and asserts both sides agree.
#
# WHAT THIS FILE CALLS
# - nothing — pure data module.
#
# SYNC_WITH (manual discipline; the sync test guards us)
#   frontend/src/config/industries/printing.ts
#   frontend/src/config/industries/fabrication.ts
#   frontend/src/config/industries/manufacturing.ts
#   frontend/src/config/industries/chemical.ts
#   frontend/src/config/industries/field_service.ts
#
# IF YOU CHANGE EITHER SIDE, UPDATE THE OTHER IN THE SAME COMMIT. The
# sync test catches divergence at unit-test time so CI fails before
# the extractor sees stale vocabulary.
#
# DESIGN NOTES
# - The backend cannot consume .ts files directly without a node
#   toolchain. Two-source discipline is a known hazard; the sync test
#   in tests/services/test_industry_vocabularies_sync.py parses the
#   .ts arrays with a small regex and asserts equality with the dict
#   below. It runs in the standard pytest pass — no extra deps.
# - get_industry_vocabulary returns an empty default for unknown
#   industries so the extractor never crashes on a tenant whose
#   industry_type is set to something unexpected. The prompt
#   degrades to entity-categories-only (no vocabulary hints).
#
# FORWARD-COMPAT
# - v6.3.15+ may grow this file with more verticals (e.g. textile,
#   garments). The shape is intentionally flat so adding a key is
#   the only edit needed.

from typing import TypedDict


class IndustryVocabulary(TypedDict):
    """One vertical's skill + machine vocabulary."""
    skills:        list[str]
    machine_types: list[str]


# Mapping from industry_type (matches Tenant.industry_type) to its
# vocabulary. Keys must match the `id` field of the corresponding
# frontend industry config (e.g. printing.ts: id: 'printing').
INDUSTRY_VOCABULARIES: dict[str, IndustryVocabulary] = {
    "printing": {
        "skills": [
            "Flexo Printing",
            "Die Cutting",
            "Lamination",
            "Quality Control",
            "Helper",
        ],
        "machine_types": [
            "Flexo Printer",
            "Die Cutter",
            "Laminator",
            "Offset Press",
            "Folder/Gluer",
        ],
    },
    "fabrication": {
        "skills": [
            "Fabrication",
            "Welding",
            "Grinding",
            "Fitting",
            "Helper",
        ],
        "machine_types": [
            "Plasma Cutter",
            "MIG Welder",
            "Press Brake",
            "Bandsaw",
            "Bench Grinder",
        ],
    },
    "manufacturing": {
        "skills": [
            "CNC Operation",
            "Welding",
            "Assembly",
            "Quality Check",
            "Helper",
        ],
        "machine_types": [
            "CNC Lathe",
            "Welding Station",
            "Assembly Line",
            "Milling Machine",
            "Drilling Machine",
        ],
    },
    "chemical": {
        "skills": [
            "Process Operation",
            "Quality Control",
            "Filling Operation",
            "Safety Officer",
            "Helper",
        ],
        "machine_types": [
            "Reactor",
            "Mixer",
            "Filling Line",
            "Centrifuge",
            "Distillation Column",
        ],
    },
    "field_service": {
        "skills": [
            "HVAC",
            "Electrical",
            "Plumbing",
            "Civil Works",
            "Helper",
        ],
        "machine_types": [
            "Service Van",
            "Hydraulic Lift",
            "Diagnostic Kit",
            "Pressure Washer",
            "Pipe Threader",
        ],
    },
}


def get_industry_vocabulary(industry_type: str | None) -> IndustryVocabulary:
    """Return the skill + machine vocabulary for an industry.

    Called by:    app/services/extraction/entity_extractor.py
                  (build_prompt embeds the lists in the LLM prompt).
    Calls into:   nothing — dict lookup only.
    Returns:      IndustryVocabulary dict. For unknown / None
                  industry_type returns an empty vocabulary so the
                  extractor still runs but without vertical hints.
    Side effects: none — pure function.

    Args:
        industry_type: Tenant.industry_type — one of 'printing',
                       'fabrication', 'manufacturing', 'chemical',
                       'field_service', or anything else (treated as
                       unknown).
    """
    if not industry_type:
        return {"skills": [], "machine_types": []}
    return INDUSTRY_VOCABULARIES.get(
        industry_type,
        {"skills": [], "machine_types": []},
    )
