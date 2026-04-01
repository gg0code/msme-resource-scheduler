# backend/app/features_config.py — V3.7
#
# Single source of truth for all feature visibility.
# Flip a flag to True and restart the backend — that feature is live.
# No code changes needed. No redeployment of logic.
#
# ── Version map ───────────────────────────────────────────────────────────────
# V1  — all False        (Job Board — replace paper register)
# V2  — scheduler, gantt → True    (The Planner — stop missing deadlines)
# V3  — qr_scan, step_intelligence → True  (Shop Floor — workers know what to do)
# V4  — csv_import, ai_copilot → True      (Full Platform)
# ─────────────────────────────────────────────────────────────────────────────

FEATURE_FLAGS: dict[str, bool] = {
    "scheduler":          True,
    "gantt":              True,
    "qr_scan":            True,
    "step_intelligence":  True,
    "csv_import":         True,
    "ai_copilot":         True,
    "whatsapp":           False,  # v5-dev only — keep False on v3-dev
}
