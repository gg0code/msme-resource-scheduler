"""
```python
"""
FILE PURPOSE
This is a FastAPI router that exposes a public API endpoint for retrieving feature flags 
configuration. It exists to allow the frontend to dynamically determine which UI features 
should be visible or enabled without hardcoding these decisions in the client-side code. 
This file was introduced in v3.7 and sits in the API layer of the architecture, serving 
as a bridge between the global feature configuration and the frontend's need to know 
what functionality is currently available.

WHAT THIS FILE DOES — step by step
1. Imports FastAPI's APIRouter for creating route handlers
2. Imports the FEATURE_FLAGS dictionary from the global features configuration
3. Creates a router instance tagged with "features" for OpenAPI documentation
4. Defines a single GET endpoint that returns the complete feature flags dictionary
5. Makes the feature flags available to any client without authentication requirements

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : router
Type         : FastAPI APIRouter instance
Purpose      : Groups feature-related endpoints together and provides the "features" tag 
               for API documentation. This router gets included in the main FastAPI app 
               with the "/api" prefix.
Parameters   : tags=["features"] for OpenAPI grouping
Returns      : N/A (this is an instance, not a function)
Calls        : N/A
DB/API       : None
Side effects : None

Name         : get_feature_flags
Type         : FastAPI endpoint
Purpose      : Returns the complete dictionary of feature flags to any caller without 
               requiring authentication. This allows the frontend to make UI decisions 
               based on what features are currently enabled globally. The endpoint is 
               intentionally public because feature flags are not sensitive data.
Parameters   : None
Returns      : dict[str, bool] - A dictionary where keys are feature names (like 
               "scheduler", "gantt") and values are boolean flags indicating whether 
               each feature is enabled
Calls        : Accesses FEATURE_FLAGS from app.features_config
DB/API       : No database queries or external API calls
Side effects : None - this is a pure read operation

WHO CALLS THIS FILE
- backend/app/main.py imports this router and includes it in the FastAPI application
- Frontend code (likely frontend/src/context/FeatureFlags.tsx or similar API client 
  files) makes HTTP GET requests to the /api/features endpoint
- Any HTTP client can call GET /api/features since no authentication is required

IMPORTS EXPLAINED
- fastapi.APIRouter: Provides the routing functionality to create REST endpoints that 
  can be grouped together and included in the main FastAPI application
- app.features_config.FEATURE_FLAGS: The global dictionary containing all feature flag 
  definitions that this file needs to return to clients

INTERN NOTES
- Easiest thing to break without realising: Modifying FEATURE_FLAGS directly instead of 
  understanding that this endpoint just returns whatever is in features_config.py
- Non-obvious design decision and why: This endpoint requires no authentication because 
  feature flags control UI visibility, not security - they're not secret information
- Most common mistake when editing: Adding authentication requirements when this endpoint 
  is intentionally public, or trying to filter flags per user/tenant when flags are global
- Which design principle this implements: Principle #8 - feature flags gate all optional 
  features via FEATURE_FLAGS, and this endpoint makes those flags available to the frontend
- What to check if features aren't working: Verify FEATURE_FLAGS in features_config.py 
  has the expected values, check that main.py properly includes this router with /api prefix
- N/A for v5-whatsapp merging since this is v4-dev code, but ensure any new v5 features 
  added to FEATURE_FLAGS are properly documented when merging
"""
```
"""

# backend/app/routers/features.py — V3.7
#
# Public endpoint — no auth required.
# Frontend fetches this once on load to know which features are visible.
#
# GET /api/features  →  { "scheduler": false, "gantt": false, ... }
#
# Register in main.py:
#   from app.routers import features
#   app.include_router(features.router, prefix="/api")

from fastapi import APIRouter
from app.features_config import FEATURE_FLAGS

router = APIRouter(tags=["features"])


@router.get("/features")
def get_feature_flags() -> dict[str, bool]:
    """
    Returns all feature flags.
    No auth needed — flags are not secret, they are UI visibility controls.
    """
    return FEATURE_FLAGS
