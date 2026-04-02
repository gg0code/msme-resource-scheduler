from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt

# Secret key - in production move to settings/env var
SCAN_TOKEN_SECRET = "msme-scan-secret-change-in-production"
SCAN_TOKEN_ALGORITHM = "HS256"
MAX_TOKEN_DAYS = 7


def _compute_expiry(job_end_date: Optional[object]) -> datetime:
    """Option C: min(end_date + 1 day, now + 7 days)"""
    now = datetime.now(timezone.utc)
    cap = now + timedelta(days=MAX_TOKEN_DAYS)

    if job_end_date is None:
        return cap

    # Normalise to datetime
    if hasattr(job_end_date, "date"):
        end_dt = datetime(job_end_date.year, job_end_date.month,
                          job_end_date.day, 23, 59, 59, tzinfo=timezone.utc)
    else:
        end_dt = datetime.combine(job_end_date, datetime.max.time()).replace(tzinfo=timezone.utc)

    grace = end_dt + timedelta(days=1)
    return min(grace, cap)


def create_scan_token(
    action: str,          # "start_step" | "complete_step"
    job_id: int,
    step_id: int,
    tenant_id: int,
    step_name: str,
    job_name: str,
    job_end_date=None,
) -> dict:
    """Create a signed JWT scan token. Returns {token, expires_at}."""
    expires_at = _compute_expiry(job_end_date)
    payload = {
        "action":    action,
        "job_id":    job_id,
        "step_id":   step_id,
        "tenant_id": tenant_id,
        "step_name": step_name,
        "job_name":  job_name,
        "exp":       expires_at,
    }
    token = jwt.encode(payload, SCAN_TOKEN_SECRET, algorithm=SCAN_TOKEN_ALGORITHM)
    return {
        "token":      token,
        "expires_at": expires_at.isoformat(),
    }


def verify_scan_token(token: str) -> dict:
    """
    Decode and verify a scan token.
    Raises ValueError with user-friendly message on any failure.
    Returns the payload dict on success.
    """
    try:
        payload = jwt.decode(token, SCAN_TOKEN_SECRET, algorithms=[SCAN_TOKEN_ALGORITHM])
        return payload
    except JWTError as e:
        msg = str(e).lower()
        if "expired" in msg:
            raise ValueError("expired")
        raise ValueError("invalid")
