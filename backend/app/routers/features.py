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
