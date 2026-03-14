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
