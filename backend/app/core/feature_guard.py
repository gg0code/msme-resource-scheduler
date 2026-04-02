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
