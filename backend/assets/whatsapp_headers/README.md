# WhatsApp Brand Asset Library — v6.3.23

Eight 640×335 PNG headers used as IMAGE-header components on outbound
WhatsApp HSM templates, plus the matching SVG sources under `_source/`.
Spec'd in SRS §6.29; wired through `whatsapp_send_helper` →
`whatsapp_template_assets.REGISTRY` at runtime.

## Files

| Brand key            | PNG                          | SVG source                              | BG       | Label             |
|----------------------|------------------------------|------------------------------------------|----------|-------------------|
| morning_briefing     | morning_briefing.png         | _source/morning_briefing.svg             | #185FA5  | MORNING BRIEFING  |
| evening_summary      | evening_summary.png          | _source/evening_summary.svg              | #3C3489  | EVENING SUMMARY   |
| compliance_reminder  | compliance_reminder.png      | _source/compliance_reminder.svg          | #BA7517  | COMPLIANCE        |
| savings_summary      | savings_summary.png          | _source/savings_summary.svg              | #0F6E56  | SAVINGS           |
| conflict_alert       | conflict_alert.png           | _source/conflict_alert.svg               | #A32D2D  | ALERT             |
| team_invite          | team_invite.png              | _source/team_invite.svg                  | #534AB7  | INVITE            |
| material_estimate    | material_estimate.png        | _source/material_estimate.svg            | #D85A30  | ESTIMATE          |
| day7_first_insight   | day7_first_insight.png       | _source/day7_first_insight.svg           | #1D9E75  | DAY 7             |

## Design tokens

- Canvas: **640 × 335 px** (Meta IMAGE-header spec).
- Background: solid brand-category fill (hex above).
- Accent bar: bottom 14 px in the same hue darkened 30%.
- Icon: white, ~160 px tall, centred at (170, 167).
- Label: bold uppercase white, Arial / DejaVuSans / Helvetica fallback.
- Wordmark: `ZetaOps` in white-80% opacity at the foot.
- File format: PNG, RGB, 8-bit, lossless. Typical size ~6–9 KB
  (5 MB ceiling per Meta).

## Regenerating

```
python backend/scripts/generate_brand_headers.py
```

Edits a single `SPEC` row + the matching icon helper in the script, then
re-runs to produce both the PNG and SVG. The SVG sources are
hand-authored to mirror the PIL output shape-for-shape — when you tweak
geometry in PIL, the SVG helper for the same icon needs the same edit
to stay in sync.

## Handle disposition

`backend/app/services/whatsapp_template_handles.json` stores the
`header_image_handle` returned by Meta after each template approval.
These IDs are **not secrets** — they are template-component references,
public in the sense that any approved template can be sent to any opted-in
recipient. The file is committed so the rest of the team sees handle
provisioning without needing access to the Meta Business account.

Until Meta approves a re-submission with IMAGE header, every entry
stays `null`. In real mode, the helper logs a `WARNING` and sends the
body-only fallback (covered by AC `6.3.23-AC5`). In mock mode, the
`[MOCK TEMPLATE]` breadcrumb shows the resolved brand key + asset
filename so dispatcher tests can assert on the wiring without depending
on Meta state.

## Out of scope for v6.3.23

- Per-tenant custom logos (brand consistency wins for now).
- Per-industry-vertical variants (single brand, not per-vertical).
- Localised headers (Hindi/Hinglish text baked into the image — body
  carries the language, headers are visual brand only).
- S3 / CDN hosting (defer; bandwidth at this scale is trivial).

## Deferred wiring (when the 4 currently-unrouted dispatchers land)

`compliance_reminder`, `savings_summary`, `material_estimate`, and
`day7_first_insight` have registry entries but no dispatcher routes
through `send_with_window_decision` for them yet. When the dispatchers
land:

1. The dispatcher commit adds its own AC test
   (`test_6_X_Y_acN_…_brand_header_routes`) verifying the IMAGE
   header is included in the Meta POST body.
2. The commit also re-runs the AC5 fallthrough test for that
   template name, confirming `header_image_handle = None` produces
   the body-only WARNING path (not an exception).
3. The DELIVERY_LEDGER row for the new dispatcher cross-references the
   `6.3.23-AC2` entry so the chain stays grep-able.

This is documented in CHANGELOG `[v6.3.23]` "Deferred" and SRS §6.29.
