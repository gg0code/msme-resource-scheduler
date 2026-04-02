"""
app/services/token_service.py — Secure QR Code Token Management

FILE PURPOSE
This service creates and verifies signed JWT tokens for QR code-based job step execution.
It was introduced in v4-dev as part of the QR scanning workflow that allows factory workers
to scan printed QR codes to start or complete job steps without logging into the web interface.
The service sits in the services layer and handles all cryptographic operations for QR scan
authentication, implementing smart expiry logic to prevent indefinite token validity while
ensuring tokens remain usable for reasonable timeframes based on job schedules.

WHAT THIS FILE DOES — step by step
1. Imports datetime utilities for timezone-aware expiry calculations
2. Imports jose library for JWT token creation and verification operations
3. Defines constants for token signing algorithm and maximum token lifetime
4. Implements _compute_expiry() helper to calculate token expiration using Option C logic
5. Provides create_scan_token() to generate signed JWT tokens with job/step context
6. Provides verify_scan_token() to decode and validate tokens with user-friendly error messages

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : _compute_expiry
Type         : function (private helper)
Purpose      : Calculates token expiry date using "Option C" business logic which sets expiry
               to the minimum of either job end date plus 1 grace day, or current time plus 7 days.
               This prevents tokens from lasting indefinitely while ensuring they work for reasonable
               job durations and account for jobs that might run slightly past their scheduled end.
Parameters   : job_end_date (Optional[object]) - job's scheduled end date, can be date/datetime/None
Returns      : datetime object in UTC timezone representing when the token should expire
Calls        : datetime utilities for timezone conversion and date arithmetic
DB/API       : None - pure computation function
Side effects : None - pure function with no external modifications

Name         : create_scan_token
Type         : function (public)
Purpose      : Generates a signed JWT token containing all necessary context for QR scan execution.
               The token embeds the action type, job/step identifiers, tenant scoping, and human-readable
               names for display purposes. Uses smart expiry logic to balance security with usability.
Parameters   : action (str) - either "start_step" or "complete_step" defining what the QR scan will do
               job_id (int) - database ID of the job containing the step
               step_id (int) - database ID of the specific job step
               tenant_id (int) - tenant scope for security isolation
               step_name (str) - human-readable step name for UI display
               job_name (str) - human-readable job name for UI display
               job_end_date (optional) - job's scheduled end date for expiry calculation
Returns      : dict with "token" (signed JWT string) and "expires_at" (ISO format expiry timestamp)
Calls        : _compute_expiry() for expiry calculation, jose.jwt.encode() for signing
DB/API       : None - pure token generation
Side effects : None - creates token but doesn't store or transmit it

Name         : verify_scan_token
Type         : function (public)
Purpose      : Decodes and validates a QR scan token, checking signature and expiry. Converts
               technical JWT errors into user-friendly messages that can be displayed to factory
               workers. Essential for the QR scan security model as it ensures only valid tokens
               can execute job operations.
Parameters   : token (str) - the JWT token string from QR code scan
Returns      : dict containing the decoded payload with action, job_id, step_id, tenant_id, names
Calls        : jose.jwt.decode() for token verification and decoding
DB/API       : None - pure cryptographic verification
Side effects : Raises ValueError with "expired" or "invalid" message for display to end users

WHO CALLS THIS FILE
- backend/app/routers/qr_router.py imports this for QR code generation and scan verification endpoints
- backend/app/routers/scheduler_router.py calls create_scan_token when generating QR codes for job steps
- Any route handler that processes QR scan requests uses verify_scan_token for authentication

IMPORTS EXPLAINED
- datetime, timedelta, timezone: Required for timezone-aware expiry calculations and token validity periods
- typing.Optional: Type hints for the optional job_end_date parameter in expiry calculations
- jose.JWTError, jose.jwt: JWT library for cryptographic token signing and verification operations
- app.config.settings: Access to application configuration including the SECRET_KEY for token signing

INTERN NOTES
- Easiest thing to break: Changing the SECRET_KEY in settings will invalidate all existing QR codes instantly, causing widespread scan failures until new codes are printed
- Non-obvious design decision: Uses "Option C" expiry logic (min of job end + 1 day vs now + 7 days) to balance security against the reality that manufacturing jobs often run slightly over schedule
- Most common mistake: Forgetting that tokens contain tenant_id and must be validated against the current user's tenant to prevent cross-tenant QR code usage
- Design principle #2: Implements tenant scoping by embedding tenant_id in every token payload for security isolation
- What to check if misbehaving: Verify system clock is correct (affects JWT expiry), check that SECRET_KEY hasn't changed (breaks existing tokens), and ensure timezone handling is consistent between token creation and verification
- Not v5-whatsapp specific: This is core v4-dev functionality, but any QR-related features in v5 will build on this foundation
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.config import settings

# Secret key — in production move to settings/env var
SCAN_TOKEN_SECRET = settings.SECRET_KEY  # uses main app secret key
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
