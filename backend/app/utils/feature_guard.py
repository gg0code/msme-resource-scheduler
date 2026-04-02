"""
```python
"""
FILE PURPOSE
This file provides feature flag gating for API endpoints in the ZetaOps Copilot
scheduling application. It was introduced in v3.7 to allow graceful disabling
of features based on tenant plans or feature rollouts. Instead of throwing HTTP
errors when features are disabled, it returns warm user-friendly messages that
guide users to contact support. This sits in the utils layer and is called by
FastAPI route handlers before executing feature-specific business logic.

WHAT THIS FILE DOES — step by step
1. Imports the FEATURE_FLAGS dictionary from features_config.py which contains
   the master list of all feature toggles in the application
2. Defines a single function require_feature() that checks if a given feature
   flag is enabled or disabled
3. If the feature is enabled (flag is True), returns None to signal the caller
   should proceed with normal endpoint execution
4. If the feature is disabled (flag is False or missing), returns a structured
   dictionary with a user-friendly message explaining the feature is not active
5. Never raises HTTP exceptions or error responses - always provides warm,
   helpful messaging to guide users toward enabling the feature

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : require_feature
Type         : function
Purpose      : Checks whether a specific feature flag is enabled and returns
               either None (proceed) or a warm response dict (feature disabled).
               This is the single entry point for all feature gating in the
               application and ensures consistent messaging when features are off.
Parameters   : flag (str) - the exact feature flag name as defined in
               FEATURE_FLAGS dictionary (e.g. "scheduler", "ai_copilot", "whatsapp")
Returns      : dict | None - returns None if feature is enabled (caller proceeds
               normally), or returns a dict with "available": False, "feature": flag
               name, and "message" with instructions to contact support
Calls        : FEATURE_FLAGS.get() to lookup the flag value with False as default
DB/API       : None - this is a pure function with no external dependencies
Side effects : None - only reads configuration, does not modify any state

WHO CALLS THIS FILE
- backend/app/routers/scheduler_router.py (gates scheduling endpoints)
- backend/app/routers/ai_router.py (gates AI copilot features)
- backend/app/routers/whatsapp_router.py (gates WhatsApp features in v5 branch)
- backend/app/routers/analytics_router.py (gates advanced analytics features)
- Any FastAPI endpoint that needs to check feature availability before execution

IMPORTS EXPLAINED
- app.features_config.FEATURE_FLAGS: The master dictionary containing all feature
  toggles for the application, imported to check if specific features are enabled

INTERN NOTES
- Easiest thing to break: Typos in feature flag names - if you pass "schedular"
  instead of "scheduler", it will always return disabled since .get() defaults to False
- Non-obvious design decision: Returns warm 200 responses instead of 403 errors
  because disabled features aren't permission errors - they're plan limitations
- Most common mistake: Forgetting to check the return value in endpoints - you
  must write "guard = require_feature('flag'); if guard: return guard" pattern
- Implements design principle #8: Feature flags gate all optional features via
  FEATURE_FLAGS dictionary for clean enable/disable without code changes
- What to check if behaving unexpectedly: Verify the exact flag name exists in
  features_config.py and matches the string you're passing to require_feature()
- v4-dev file: This is production-stable code that v5-whatsapp inherits - new
  WhatsApp features should add their flags to FEATURE_FLAGS, not modify this logic
"""
```
"""

# backend/app/utils/feature_guard.py — V3.7
#
# Call require_feature(flag) at the top of any gated endpoint.
# Returns a warm 200 dict if the feature is off — never raises a 403.
# Returns None if the feature is on — caller proceeds normally.
#
# Usage:
#   guard = require_feature("scheduler")
#   if guard: return guard          # feature is off — return warm message
#   ... rest of endpoint logic ...

from app.features_config import FEATURE_FLAGS


def require_feature(flag: str) -> dict | None:
    """
    Returns None if the feature is enabled (caller should proceed).
    Returns a warm response dict if the feature is disabled (caller should return it).
    Never raises an HTTPException — no 403, no error connotation.
    """
    if FEATURE_FLAGS.get(flag, False):
        return None  # feature is on — proceed

    return {
        "available": False,
        "feature": flag,
        "message": (
            "This feature is not active on your account yet. "
            "Contact us to enable it for your plan."
        ),
    }
