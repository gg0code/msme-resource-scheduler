# tests/test_whatsapp_branded_headers.py
# Branch: v5-whatsapp
# Iteration: v6.3.23 — brand asset library.
#
# FILE PURPOSE
# Unit-tier coverage for the v6.3.23 WhatsApp brand asset library.
# Seven acceptance criteria, one test each:
#   6.3.23-AC1 — REGISTRY has exactly 8 entries with valid filenames.
#   6.3.23-AC2 — every entry resolves to an asset file on disk.
#   6.3.23-AC3 — every asset is 640x335 PNG under 5MB.
#   6.3.23-AC4 — mock mode [MOCK TEMPLATE] log carries template name +
#                header asset filename.
#   6.3.23-AC5 — null header_image_handle falls through with a logged
#                WARNING, not an exception.
#   6.3.23-AC6 — submit_whatsapp_templates.run() reports zero new
#                submissions on the second consecutive run against the
#                same Meta state.
#   6.3.23-AC7 — GET /api/v1/whatsapp/assets/{filename} returns
#                image/png for whitelisted filenames; 404 otherwise.
# AC8 (no regression in existing whatsapp tests) is verified by the
# full suite passing — not a new test in this file.

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from PIL import Image
from sqlalchemy.schema import DefaultClause
from sqlalchemy.sql import text as sa_text

from app.config import settings
from app.core.security import hash_password
from app.models.auth import Tenant, User
from app.models.event import Event
from app.models.whatsapp import PhoneTenantMap
from app.services.whatsapp_send_helper import send_with_window_decision
from app.services.whatsapp_template_assets import (
    ASSETS_DIR,
    REGISTRY,
    BrandAsset,
    get_brand_asset,
    get_header_image_handle,
    is_known_asset_filename,
)
from scripts.submit_whatsapp_templates import (
    SubmissionTarget,
    Submitter,
    run as run_submit,
)


# SQLite-now() patch — mirrors tests/services/conftest.py:patch_now_defaults_for_sqlite
# but lives here because this test file is at tests/ root (not tests/services/),
# so the services conftest's autouse fixture does not apply. Same swap:
# text("now()") -> CURRENT_TIMESTAMP for tables this file touches.
@pytest.fixture(autouse=True)
def _patch_sqlite_now_defaults():
    targets = (Tenant.__table__, User.__table__, Event.__table__, PhoneTenantMap.__table__)
    patched: list[tuple[Any, Any]] = []
    for tbl in targets:
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


# ---------------------------------------------------------------------------
# Row factories — local copies. Tiny, no need to share across files.
# ---------------------------------------------------------------------------

def _make_tenant(db) -> Tenant:
    t = Tenant(name="Brand HQ", slug=f"brand-hq-{id(db)}", plan="paid", is_active=True)
    db.add(t)
    db.flush()
    return t


def _make_user(db, *, tenant_id: int) -> User:
    u = User(
        tenant_id=tenant_id,
        email=f"owner-{tenant_id}@brand.test",
        hashed_password=hash_password("test-pwd"),
        role="proprietor",
    )
    db.add(u)
    db.flush()
    return u


def _make_phone_map(
    db,
    *,
    tenant_id: int,
    user_id: int,
    phone: str = "+919999900001",
    last_seen_at: datetime | None = None,
) -> PhoneTenantMap:
    m = PhoneTenantMap(
        tenant_id=tenant_id,
        user_id=user_id,
        phone_number=phone,
        is_active=True,
        last_seen_at=last_seen_at,
    )
    db.add(m)
    db.flush()
    return m


# morning_briefing expects 6 positional args.
MORNING_ARGS: tuple = (
    "14 May",
    "3",
    "2 (Job A, Job B)",
    "8 of 10",
    "1 worker absent",
    "Plan a one-on-one with the worker.",
)


# ---------------------------------------------------------------------------
# AC1 — registry has exactly 8 entries with valid filenames
# ---------------------------------------------------------------------------

def test_6_3_23_ac1_registry_has_eight_template_entries():
    """6.3.23-AC1: Registry contains exactly 8 template entries with valid filenames."""
    assert len(REGISTRY) == 8

    expected_keys = {
        "morning_briefing",
        "evening_summary",
        "compliance_reminder",
        "savings_summary",
        "conflict_alert",
        "team_invite",
        "material_estimate",
        "day7_first_insight",
    }
    assert set(REGISTRY.keys()) == expected_keys

    for key, asset in REGISTRY.items():
        assert isinstance(asset, BrandAsset)
        assert asset.key == key
        assert asset.filename == f"{key}.png"
        assert asset.filename.endswith(".png")
        # Defence-in-depth: filenames must be pure basenames (no '/' or '..').
        assert "/" not in asset.filename
        assert "\\" not in asset.filename
        assert ".." not in asset.filename
        assert asset.label  # non-empty


# ---------------------------------------------------------------------------
# AC2 — every entry resolves to an asset file on disk
# ---------------------------------------------------------------------------

def test_6_3_23_ac2_each_template_resolves_to_existing_asset_file():
    """6.3.23-AC2: Every registry entry points to an asset file that exists on disk."""
    for key, asset in REGISTRY.items():
        assert asset.path.is_file(), (
            f"asset {key} -> {asset.path} missing on disk; "
            f"re-run backend/scripts/generate_brand_headers.py"
        )
        # Cross-check the helper used by the asset-serving endpoint.
        assert is_known_asset_filename(asset.filename) is True


# ---------------------------------------------------------------------------
# AC3 — every asset is 640x335 PNG under 5 MB
# ---------------------------------------------------------------------------

MAX_PNG_BYTES = 5 * 1024 * 1024


@pytest.mark.parametrize("brand_key", sorted(REGISTRY.keys()))
def test_6_3_23_ac3_each_asset_meets_meta_size_spec(brand_key: str):
    """6.3.23-AC3: Every asset is 640x335 px PNG under 5 MB.

    Parametrised across all 8 brand keys so a failure for one asset
    points at exactly which PNG drifted.
    """
    asset = REGISTRY[brand_key]
    assert asset.path.is_file()

    file_size = asset.path.stat().st_size
    assert file_size < MAX_PNG_BYTES, (
        f"{asset.filename} is {file_size} bytes — exceeds Meta's 5MB cap."
    )

    with Image.open(asset.path) as img:
        assert img.format == "PNG", f"{asset.filename} is not PNG ({img.format})"
        assert img.size == (640, 335), (
            f"{asset.filename} is {img.size}; spec requires (640, 335)"
        )


# ---------------------------------------------------------------------------
# AC4 — mock mode log line carries template name + asset filename
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_3_23_ac4_mock_mode_logs_template_and_asset_name(
    db, monkeypatch, caplog,
):
    """6.3.23-AC4: In mock mode, [MOCK TEMPLATE] log carries template name + asset filename."""
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    caplog.set_level(logging.INFO, logger="app.services.whatsapp_send_helper")

    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    now = datetime.now(timezone.utc)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=now - timedelta(hours=30),  # outside 24h, forces template path
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=MORNING_ARGS,
        free_form_text="ignored when template path fires",
        alert_type="push_morning",
        now=now,
    )
    assert outcome.path == "template"

    matching = [
        r for r in caplog.records
        if "[MOCK TEMPLATE]" in r.message
        and "zetaops_morning_briefing" in r.message
        and "morning_briefing.png" in r.message
    ]
    assert matching, (
        "expected [MOCK TEMPLATE] line carrying template name and asset "
        f"filename; got: {[r.message for r in caplog.records]}"
    )

    # Sanity: the same line shows the handle slot (null today).
    assert "header_handle=None" in matching[0].message


# ---------------------------------------------------------------------------
# AC5 — null handle falls through to body-only with a logged WARNING
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_6_3_23_ac5_missing_header_handle_falls_through_with_warning(
    db, monkeypatch, caplog,
):
    """6.3.23-AC5: null header_image_handle sends body-only with a logged WARNING, not an exception."""
    monkeypatch.setattr(settings, "WHATSAPP_MOCK_MODE", True)
    caplog.set_level(logging.WARNING, logger="app.services.whatsapp_send_helper")

    # Confirm the v6.3.23 ship-state: every handle slot still null.
    assert get_header_image_handle("zetaops_morning_briefing", "en_US") is None
    assert get_header_image_handle("zetaops_invite_team_member", "en_US") is None

    tenant = _make_tenant(db)
    user = _make_user(db, tenant_id=tenant.id)
    now = datetime.now(timezone.utc)
    _make_phone_map(
        db, tenant_id=tenant.id, user_id=user.id,
        last_seen_at=now - timedelta(hours=30),
    )

    outcome = await send_with_window_decision(
        db=db,
        tenant_id=tenant.id,
        phone_e164="+919999900001",
        event="morning_briefing",
        language="en_US",
        args=MORNING_ARGS,
        free_form_text="ignored",
        alert_type="push_morning",
        now=now,
    )

    # No exception, template path completes successfully.
    assert outcome.success is True
    assert outcome.path == "template"

    # The WARNING line names both the template and the asset filename so
    # an operator grepping for "morning_briefing.png" in production logs
    # gets the actionable context for each missing approval.
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING
        and "morning_briefing.png" in r.message
        and "header_image_handle" in r.message
    ]
    assert warnings, (
        "expected WARNING line naming the asset filename + handle gap; "
        f"got: {[(r.levelname, r.message) for r in caplog.records]}"
    )


# ---------------------------------------------------------------------------
# AC6 — submit_whatsapp_templates.run() idempotent on the second pass
# ---------------------------------------------------------------------------

class _StubSubmitter:
    """Test double for Submitter. Returns a synthetic handle on every call."""

    def __init__(self):
        self.calls: list[SubmissionTarget] = []

    def submit(self, target: SubmissionTarget) -> str:
        self.calls.append(target)
        return f"stub_handle_{target.handle_key.replace('::', '_')}"


def _fresh_handles_dict() -> dict:
    """Build an in-memory handles dict matching the on-disk JSON shape."""
    handles: dict = {"_comment": "test fixture"}
    for brand in REGISTRY.values():
        for meta_name in brand.meta_template_names:
            for lang in ("en_US", "hi"):
                # Only seed slots that the real JSON would carry — see
                # whatsapp_template_handles.json. For determinism, add
                # both en_US and hi for every Meta-template-name; the
                # real JSON omits some hi entries, but the test only
                # cares about the idempotency invariant, not the slot
                # population pattern.
                handles[f"{meta_name}::{lang}"] = None
    return handles


def test_6_3_23_ac6_submit_script_is_idempotent():
    """6.3.23-AC6: second consecutive run reports zero new submissions."""
    handles = _fresh_handles_dict()
    initial_slots = sum(1 for k in handles if not k.startswith("_"))

    # First run — every populated brand asset should submit.
    submitter = _StubSubmitter()
    report1 = run_submit(
        dry_run=False, submitter=submitter, handles_override=handles,
    )
    assert report1.targets_submitted > 0
    assert report1.targets_submitted == len(submitter.calls)

    # The handles dict was updated in place — every slot for a brand-
    # asset-backed template now has a stub handle.
    populated_after_first = sum(
        1 for k, v in handles.items()
        if not k.startswith("_") and v is not None
    )
    assert populated_after_first == report1.targets_submitted

    # Second consecutive run — submitter must not be invoked again.
    submitter2 = _StubSubmitter()
    report2 = run_submit(
        dry_run=False, submitter=submitter2, handles_override=handles,
    )
    assert report2.targets_submitted == 0
    assert submitter2.calls == []
    assert report2.targets_already_submitted == report1.targets_submitted

    # Total target count is stable across runs.
    assert report2.targets_total == report1.targets_total


# ---------------------------------------------------------------------------
# AC7 — asset endpoint serves PNG with image/png; rejects unknown filenames
# ---------------------------------------------------------------------------

def test_6_3_23_ac7_asset_endpoint_serves_png_with_correct_content_type(client):
    """6.3.23-AC7: GET /api/v1/whatsapp/assets/{filename} returns image/png; 404 otherwise."""
    # Whitelisted filename returns the bytes on disk.
    response = client.get("/api/v1/whatsapp/assets/morning_briefing.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    on_disk = (ASSETS_DIR / "morning_briefing.png").read_bytes()
    assert response.content == on_disk

    # An unlisted PNG name returns 404 even when no traversal is attempted.
    response = client.get("/api/v1/whatsapp/assets/not_a_real_brand.png")
    assert response.status_code == 404

    # Path traversal attempts: FastAPI's path conversion strips the
    # traversal segment so the request reaches the endpoint with a
    # different filename or fails to route at all. Either way, the
    # endpoint never serves a non-registry file.
    response = client.get("/api/v1/whatsapp/assets/../../requirements.txt")
    # Possible outcomes: 404 (route doesn't match) or 404 (whitelist
    # rejection). Both satisfy AC7's "404 otherwise."
    assert response.status_code == 404
