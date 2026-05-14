# app/services/whatsapp_template_assets.py
# Branch: v5-whatsapp
# Iteration: v6.3.23 — brand asset library.
#
# FILE PURPOSE
# Single source of truth for the eight WhatsApp HSM template IMAGE
# headers shipped in v6.3.23. Maps each brand category to its asset
# filename, label, and the Meta template names that share that brand.
# Looks up Meta-returned header_image_handles via a sibling JSON
# sidecar (whatsapp_template_handles.json) so the Python source stays
# free of per-environment Meta state. Imported by:
#
#   1. whatsapp_send_helper._post_template_to_meta — picks the IMAGE
#      handle for a (meta_template_name, language) pair at send time
#      and injects a HEADER component into the Meta POST body.
#   2. routers/whatsapp.py — asset-serving endpoint validates incoming
#      filenames against the registry whitelist before serving bytes.
#   3. scripts/submit_whatsapp_templates.py — reads the registry to
#      decide which assets to upload to Meta and which (name, language)
#      slots to fill in the handle JSON after approval.
#   4. tests/test_whatsapp_branded_headers.py — drives all eight ACs
#      from this registry.
#
# WHAT THIS FILE CALLS
#   - json (stdlib) — reads the handle sidecar at import.
#   - pathlib.Path — locates assets dir and the sidecar JSON.
#   - dataclasses, typing — BrandAsset shape.
#
# KEY DESIGN DECISIONS
#   - Eight brand-category entries, not one entry per (Meta template,
#     language) pair, because the brief's AC1 says "exactly 8 entries"
#     and several Meta templates share one brand (e.g. the three
#     compliance_reminder_t30/t7/t1 variants share one asset).
#   - meta_template_names is a tuple — empty for material_estimate
#     (no Meta template exists for it yet). Entries with empty tuples
#     still ship the asset + registry row so the dispatcher that lands
#     later can wire through without a registry edit.
#   - Handles live in a sibling JSON file rather than as constants here
#     so the submit script can rewrite them idempotently without
#     touching Python source. Handles are NOT secrets — they're
#     template-component IDs returned by Meta after approval — so the
#     JSON is committed.
#   - The asset-serving endpoint accepts only filenames present in
#     REGISTRY. Any "../" or "/" in the requested filename is rejected
#     by FastAPI's path conversion before this module sees it, but the
#     whitelist is the load-bearing defence regardless.

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ASSETS_DIR: Path = Path(__file__).resolve().parents[2] / "assets" / "whatsapp_headers"
_HANDLES_PATH: Path = Path(__file__).with_name("whatsapp_template_handles.json")


@dataclass(frozen=True)
class BrandAsset:
    """One brand-category entry in the v6.3.23 asset library.

    key:                  short snake_case category name; matches the
                          PNG filename stem.
    filename:             PNG basename under backend/assets/whatsapp_headers/.
    label:                uppercase brand label baked into the image.
    bg_hex:               brand background colour (informational; not
                          re-read at runtime).
    meta_template_names:  zero or more Meta HSM template names that
                          use this brand. Empty tuple means the brand
                          ships now but no dispatcher routes through
                          it yet (material_estimate falls in this
                          group for v6.3.23).
    """
    key: str
    filename: str
    label: str
    bg_hex: str
    meta_template_names: tuple[str, ...]

    @property
    def path(self) -> Path:
        return ASSETS_DIR / self.filename


REGISTRY: dict[str, BrandAsset] = {
    "morning_briefing": BrandAsset(
        key="morning_briefing",
        filename="morning_briefing.png",
        label="MORNING BRIEFING",
        bg_hex="#185FA5",
        meta_template_names=("zetaops_morning_briefing",),
    ),
    "evening_summary": BrandAsset(
        key="evening_summary",
        filename="evening_summary.png",
        label="EVENING SUMMARY",
        bg_hex="#3C3489",
        meta_template_names=("zetaops_evening_briefing",),
    ),
    "compliance_reminder": BrandAsset(
        key="compliance_reminder",
        filename="compliance_reminder.png",
        label="COMPLIANCE",
        bg_hex="#BA7517",
        meta_template_names=(
            "zetaops_compliance_reminder_t30",
            "zetaops_compliance_reminder_t7",
            "zetaops_compliance_reminder_t1",
        ),
    ),
    "savings_summary": BrandAsset(
        key="savings_summary",
        filename="savings_summary.png",
        label="SAVINGS",
        bg_hex="#0F6E56",
        meta_template_names=("zetaops_performance_summary_monthly",),
    ),
    "conflict_alert": BrandAsset(
        key="conflict_alert",
        filename="conflict_alert.png",
        label="ALERT",
        bg_hex="#A32D2D",
        meta_template_names=("zetaops_job_conflict_alert",),
    ),
    "team_invite": BrandAsset(
        key="team_invite",
        filename="team_invite.png",
        label="INVITE",
        bg_hex="#534AB7",
        meta_template_names=("zetaops_invite_team_member",),
    ),
    "material_estimate": BrandAsset(
        key="material_estimate",
        filename="material_estimate.png",
        label="ESTIMATE",
        bg_hex="#D85A30",
        meta_template_names=(),
    ),
    "day7_first_insight": BrandAsset(
        key="day7_first_insight",
        filename="day7_first_insight.png",
        label="DAY 7",
        bg_hex="#1D9E75",
        meta_template_names=("zetaops_owner_day7_insight",),
    ),
}


_META_NAME_TO_BRAND_KEY: dict[str, str] = {
    meta_name: brand.key
    for brand in REGISTRY.values()
    for meta_name in brand.meta_template_names
}


def get_brand_asset(meta_template_name: str) -> Optional[BrandAsset]:
    """Return the BrandAsset whose meta_template_names includes the arg.

    Called by:    whatsapp_send_helper._post_template_to_meta (for log
                  lines + handle lookup); the asset-serving endpoint
                  does NOT call this — it walks REGISTRY directly to
                  validate inbound filenames.
    Calls into:   _META_NAME_TO_BRAND_KEY (built at import).
    Side effects: none.

    Returns None if the Meta template name is not in the registry.
    Callers should fall through to "no brand header" behaviour
    (free-form-style send) when None is returned.
    """
    key = _META_NAME_TO_BRAND_KEY.get(meta_template_name)
    return REGISTRY.get(key) if key else None


def _load_handles() -> dict[str, Optional[str]]:
    """Read whatsapp_template_handles.json. Skips the `_comment` key.

    Called by:    module body once at import; result cached in _HANDLES.
    Calls into:   json.load on _HANDLES_PATH.
    Side effects: single disk read at import time.

    Returns dict keyed by "<meta_template_name>::<language>". Values are
    handle strings or None. Missing keys read as None in
    get_header_image_handle (no KeyError).
    """
    with _HANDLES_PATH.open(encoding="utf-8") as f:
        raw = json.load(f)
    return {k: v for k, v in raw.items() if not k.startswith("_")}


_HANDLES: dict[str, Optional[str]] = _load_handles()


def get_header_image_handle(
    meta_template_name: str, language: str,
) -> Optional[str]:
    """Look up Meta's HEADER IMAGE handle for (meta_template_name, language).

    Called by:    whatsapp_send_helper._post_template_to_meta when
                  picking whether to inject a HEADER IMAGE component
                  into the Meta POST body.
    Calls into:   _HANDLES (loaded at import).
    Side effects: none.

    Returns the handle string when Meta has approved a submission for
    this (template, language) pair; None otherwise. None is the
    expected state through Meta portfolio review; the runtime path
    logs a WARNING in real mode and falls through to body-only.
    """
    return _HANDLES.get(f"{meta_template_name}::{language}")


def is_known_asset_filename(filename: str) -> bool:
    """Whitelist check for the asset-serving endpoint.

    Called by:    routers/whatsapp.py asset endpoint as a defence
                  alongside FastAPI's path validation.
    Calls into:   REGISTRY (set comprehension).
    Side effects: none.

    Treats the filename as opaque — any caller that passed "../" or "/"
    would already have failed the FastAPI path conversion. The
    whitelist defends against an unlisted PNG appearing in the assets
    directory.
    """
    return filename in {asset.filename for asset in REGISTRY.values()}
