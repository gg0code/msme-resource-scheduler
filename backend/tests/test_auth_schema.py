# tests/test_auth_schema.py
# BUG-4: Verify RegisterRequest accepts valid industries, defaults to printing,
# and rejects invalid values with ValidationError.

import pytest
from pydantic import ValidationError
from app.schemas.auth import RegisterRequest

REQUIRED = {
    "email": "test@example.com",
    "password": "password123",
    "company_name": "Test Co",
    "slug": "test-co",
    # v6.3.2: team_size is now required by RegisterRequest. '51+' is the
    # desktop_first path that mirrors the schema's pre-v6.3.2 behaviour
    # (email + password required, phone optional).
    "team_size": "51+",
}


@pytest.mark.parametrize("industry", ["printing", "manufacturing", "fabrication", "field_service"])
def test_accepts_valid_industry(industry):
    req = RegisterRequest(**REQUIRED, industry_type=industry)
    assert req.industry_type == industry


def test_defaults_to_printing_when_omitted():
    req = RegisterRequest(**REQUIRED)
    assert req.industry_type == "printing"


@pytest.mark.parametrize("bad_value", ["chemical", "textile", "PRINTING", "", "general"])
def test_rejects_invalid_industry(bad_value):
    with pytest.raises(ValidationError):
        RegisterRequest(**REQUIRED, industry_type=bad_value)


def test_rejects_wrong_type():
    with pytest.raises(ValidationError):
        RegisterRequest(**REQUIRED, industry_type=42)
