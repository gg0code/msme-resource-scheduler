"""
```python
"""
FILE PURPOSE
This file is the single source of truth for all feature flags in the ZetaOps Copilot application.
It was introduced in v3.7 and exists on the v4-dev branch as the centralized configuration that
controls which features are visible and accessible to users. This file sits at the core of the
architecture and is imported by feature_guard.py utility functions that gate access to optional
features throughout both the backend API routes and frontend components.

WHAT THIS FILE DOES — step by step
1. Defines a comprehensive comment header explaining the versioning strategy from V1 to V4
2. Creates a dictionary constant FEATURE_FLAGS that maps feature names to boolean values
3. Sets all production features (scheduler, gantt, qr_scan, step_intelligence, csv_import, ai_copilot) to True
4. Sets the whatsapp feature to False since it's only available in the v5-whatsapp branch
5. Provides inline comments explaining which features belong to which development phase
6. Establishes the version progression from basic Job Board to Full Platform capabilities

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : FEATURE_FLAGS
Type         : dictionary constant
Purpose      : This is the master configuration dictionary that controls feature visibility across
               the entire application. Each key represents a feature name that corresponds to gating
               logic in the codebase, and each boolean value determines whether that feature is
               currently enabled. When a flag is True, the feature is accessible; when False, the
               feature is hidden and inaccessible to users.
Parameters   : N/A (this is a constant dictionary, not a function)
Returns      : N/A (this is a constant dictionary that other files import and read from)
Calls        : N/A (this file defines constants and doesn't call other functions)
DB/API       : N/A (this file contains only configuration constants)
Side effects : Controls the behavior of the entire application by enabling/disabling features

WHO CALLS THIS FILE
- backend/app/utils/feature_guard.py - imports FEATURE_FLAGS to implement require_feature() decorator
- Any backend router files that need to check feature availability before exposing endpoints
- Frontend feature detection logic that queries the backend for enabled features
- Background task processors that may need to conditionally execute based on feature flags

IMPORTS EXPLAINED
This file has no imports - it only defines constants that are imported by other files throughout
the codebase. The type hint dict[str, bool] uses Python 3.9+ built-in generic typing without
requiring imports from the typing module.

INTERN NOTES
- Easiest thing to break: Changing a flag from True to False in production without understanding
  which features depend on it - users will suddenly lose access to functionality they expect
- Non-obvious design decision: WhatsApp is kept False on v4-dev branch even though the code exists,
  because it's only meant to be enabled on the v5-whatsapp branch during development
- Most common mistake: Forgetting to restart the backend server after changing flags - changes
  only take effect when the Python process reloads this configuration file
- Design principle #8: This file implements "Feature flags gate all optional features via FEATURE_FLAGS"
  by providing the centralized boolean switches that control feature visibility
- What to check if behaving unexpectedly: Verify the backend server was restarted after changes,
  and check that feature_guard.py is properly reading these flags in require_feature() calls
- Branch-specific note: When merging v5-whatsapp features back to v4-dev, always ensure the
  whatsapp flag stays False in the target branch to prevent premature feature exposure
"""
```
"""

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
