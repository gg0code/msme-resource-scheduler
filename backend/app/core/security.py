"""
```python
"""
FILE PURPOSE
This file provides all JWT token management and password security utilities for the ZetaOps
Copilot authentication system. Introduced in early v4 development, it centralizes all
cryptographic operations including password hashing with bcrypt, JWT access token creation/validation,
and refresh token generation/hashing. It sits at the core security layer, used by authentication
routers and dependency injection to verify user identity and maintain secure sessions.

WHAT THIS FILE DOES — step by step
1. Imports bcrypt for secure password hashing, jose for JWT operations, and core datetime/crypto utilities
2. Defines hash_password() to convert plain text passwords into bcrypt hashes for database storage
3. Defines verify_password() to check plain text passwords against stored bcrypt hashes during login
4. Defines create_access_token() to generate short-lived JWT tokens containing user_id, tenant_id, and role
5. Defines decode_access_token() to parse and validate JWT tokens, ensuring they are access tokens
6. Defines generate_refresh_token() to create cryptographically secure random refresh tokens
7. Defines hash_refresh_token() to convert raw refresh tokens into SHA256 hashes for database storage
8. Defines refresh_token_expiry() to calculate expiration timestamps for refresh tokens

KEY FUNCTIONS / CLASSES / COMPONENTS

Name         : hash_password
Type         : function
Purpose      : Converts plain text passwords into secure bcrypt hashes for storage in the database.
               Uses bcrypt's built-in salt generation to ensure each hash is unique even for identical passwords.
               This is called during user registration and password changes to never store plain text passwords.
Parameters   : plain (str) - the raw password string entered by the user
Returns      : str - bcrypt hash as UTF-8 string, safe to store in database User.hashed_password field
Calls        : bcrypt.hashpw(), bcrypt.gensalt() from bcrypt library
DB/API       : None - pure cryptographic function
Side effects : None - returns hash without modifying anything

Name         : verify_password
Type         : function
Purpose      : Validates a plain text password against a stored bcrypt hash during login attempts.
               Uses bcrypt's constant-time comparison to prevent timing attacks. Returns boolean
               indicating whether the password matches, used by authentication endpoints to grant/deny access.
Parameters   : plain (str) - password entered by user during login
               hashed (str) - bcrypt hash retrieved from User.hashed_password database field
Returns      : bool - True if password matches hash, False otherwise
Calls        : bcrypt.checkpw() from bcrypt library
DB/API       : None - pure cryptographic function
Side effects : None - readonly validation function

Name         : create_access_token
Type         : function
Purpose      : Generates JWT access tokens containing user identity and permissions for API authentication.
               Embeds user_id, tenant_id, and role in the payload for tenant scoping and role-based access.
               Sets expiration timestamp and token type to prevent misuse of refresh tokens as access tokens.
Parameters   : user_id (int) - primary key from User table
               tenant_id (int) - foreign key for tenant scoping (design principle #2)
               role (str) - user role for permission checks (admin/manager/operator)
               expires_delta (Optional[timedelta]) - custom expiration, defaults to ACCESS_TOKEN_EXPIRE_MINUTES
Returns      : str - encoded JWT token for Authorization header, stored in frontend tokenStore
Calls        : jwt.encode() from jose library, datetime operations
DB/API       : None - pure token generation
Side effects : None - returns token without modifying anything

Name         : decode_access_token
Type         : function
Purpose      : Parses and validates JWT access tokens to extract user identity and permissions.
               Verifies signature, expiration, and token type to ensure token authenticity.
               Used by get_current_user dependency to authenticate API requests and enforce tenant scoping.
Parameters   : token (str) - JWT token from Authorization header
Returns      : dict - decoded payload containing sub (user_id), tenant_id, role, exp, type fields
Calls        : jwt.decode() from jose library
DB/API       : None - pure token validation
Side effects : Raises JWTError if token is invalid, expired, or wrong type

Name         : generate_refresh_token
Type         : function
Purpose      : Creates cryptographically secure random tokens for long-term authentication persistence.
               Uses 48-byte URL-safe tokens for high entropy. Raw token is sent to client as httpOnly cookie,
               while hashed version is stored in database to prevent token theft from database breaches.
Parameters   : None
Returns      : str - 48-byte URL-safe random token string for client storage
Calls        : secrets.token_urlsafe() from Python standard library
DB/API       : None - pure token generation
Side effects : None - generates random data without modifying anything

Name         : hash_refresh_token
Type         : function
Purpose      : Converts raw refresh tokens into SHA256 hashes for secure database storage.
               Raw tokens are never stored in database to prevent credential theft if database is compromised.
               Hash is stored in User.refresh_token_hash field and compared during token refresh operations.
Parameters   : raw (str) - raw refresh token from generate_refresh_token()
Returns      : str - SHA256 hexadecimal hash for database storage
Calls        : hashlib.sha256() from Python standard library
DB/API       : None - pure cryptographic function
Side effects : None - returns hash without modifying anything

Name         : refresh_token_expiry
Type         : function
Purpose      : Calculates expiration timestamp for refresh tokens using configured expiration period.
               Returns UTC datetime for database storage in User.refresh_token_expires field.
               Used during login and token refresh to set proper expiration dates for security.
Parameters   : None
Returns      : datetime - UTC timestamp when refresh token should expire
Calls        : datetime operations from Python standard library
DB/API       : None - pure calculation
Side effects : None - returns timestamp without modifying anything

WHO CALLS THIS FILE
- backend/app/routers/auth.py - login, register, and token refresh endpoints
- backend/app/core/dependencies.py - get_current_user dependency for request authentication
- backend/app/routers/users.py - password change functionality
- backend/app/crud/users.py - user creation and authentication database operations

IMPORTS EXPLAINED
- hashlib: Python standard library for SHA256 hashing of refresh tokens before database storage
- secrets: Python standard library for cryptographically secure random token generation
- datetime, timedelta, timezone: Standard library for JWT expiration timestamps and token validity periods
- typing.Optional: Type hints for optional expires_delta parameter in create_access_token
- bcrypt: Third-party library for secure password hashing with built-in salting and computational cost
- jose.JWTError, jose.jwt: Third-party library for JSON Web Token creation, parsing, and validation
- app.config.settings: Application configuration containing SECRET_KEY, ALGORITHM, and token expiration settings

INTERN NOTES
- Easiest thing to break: Changing SECRET_KEY in settings will invalidate ALL existing JWT tokens, logging out every user
- Non-obvious design decision: Refresh tokens are hashed before database storage to prevent credential theft even if database is compromised, while access tokens are stateless JWTs
- Most common mistake: Forgetting to include tenant_id in JWT payload breaks tenant scoping (design principle #2) and creates security vulnerabilities
- Design principle implemented: Principle #2 (tenant scoping) by embedding tenant_id in every access token payload
- Check if behaving unexpectedly: Verify settings.SECRET_KEY is consistent, check token expiration times, and
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from app.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(user_id: int, tenant_id: int, role: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(user_id), "tenant_id": tenant_id, "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    return payload

def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)

def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
