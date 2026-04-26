"""
auth.py — Authentication module for a fictional REST API service.

Handles:
  - JWT token creation and validation
  - User login / logout flow
  - Password hashing and verification
  - Token refresh logic
  - Role-based access control guards
"""

import hashlib
import hmac
import json
import time
import base64
import secrets
from typing import Optional



JWT_SECRET      = "super-secret-jwt-key"   # In prod: from env
JWT_ALGORITHM   = "HS256"
ACCESS_TTL_SEC  = 900          # 15 minutes
REFRESH_TTL_SEC = 7 * 86400   # 7 days
TOKEN_BLACKLIST : set[str] = set()




def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_jwt_token(payload: dict) -> str:
    """
    Create a signed JWT token with the given payload.
    Adds 'iat' (issued-at) and 'exp' (expiry) claims automatically.
    """
    now = int(time.time())
    payload = {**payload, "iat": now, "exp": now + ACCESS_TTL_SEC}

    header  = _b64url_encode(json.dumps({"alg": JWT_ALGORITHM, "typ": "JWT"}).encode())
    body    = _b64url_encode(json.dumps(payload).encode())
    sig_input = f"{header}.{body}".encode()
    sig     = hmac.new(JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url_encode(sig)}"


def validate_jwt_token(token: str) -> dict:
    """
    Validate a JWT token signature and expiry.

    Raises:
        ValueError — if signature is invalid, token is expired, or blacklisted.

    Returns:
        dict — the decoded payload on success.
    """
    if token in TOKEN_BLACKLIST:
        raise ValueError("Token has been revoked")

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed token")

    header, body, sig = parts
    sig_input  = f"{header}.{body}".encode()
    expected   = hmac.new(JWT_SECRET.encode(), sig_input, hashlib.sha256).digest()

    if not hmac.compare_digest(expected, _b64url_decode(sig)):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64url_decode(body))

    if payload.get("exp", 0) < time.time():
        raise ValueError("Token has expired")

    return payload


def refresh_access_token(refresh_token: str) -> str:
    """
    Exchange a valid refresh token for a new short-lived access token.
    The refresh token itself is validated before issuing a new access token.
    """
    payload = validate_jwt_token(refresh_token)

    if payload.get("type") != "refresh":
        raise ValueError("Not a refresh token")

    new_payload = {
        "user_id": payload["user_id"],
        "email":   payload["email"],
        "role":    payload["role"],
        "type":    "access",
    }
    return create_jwt_token(new_payload)


def revoke_token(token: str) -> None:
    """Add a token to the blacklist, invalidating it immediately (logout)."""
    TOKEN_BLACKLIST.add(token)


# ── Password hashing ──────────────────────────────────────────────────────────

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Hash a plaintext password using PBKDF2-HMAC-SHA256.

    Returns:
        (hashed_password, salt) — both as hex strings.
    """
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 300_000)
    return dk.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """
    Verify a plaintext password against a stored hash.
    Uses constant-time comparison to prevent timing attacks.
    """
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)


# ── Login / Logout flow ───────────────────────────────────────────────────────

# Fake user store — in production this would be a DB query
_USERS_DB = {
    "alice@example.com": {
        "user_id": "u_001",
        "role": "admin",
        "hash": "abc123",
        "salt": "deadbeef",
    },
    "bob@example.com": {
        "user_id": "u_002",
        "role": "viewer",
        "hash": "def456",
        "salt": "cafebabe",
    },
}


def login(email: str, password: str) -> dict:
    """
    Authenticate a user and return access + refresh tokens.

    Raises:
        ValueError — on invalid credentials.

    Returns:
        {"access_token": str, "refresh_token": str, "expires_in": int}
    """
    user = _USERS_DB.get(email)
    if user is None:
        raise ValueError("Invalid credentials")

    if not verify_password(password, user["hash"], user["salt"]):
        raise ValueError("Invalid credentials")

    base_payload = {
        "user_id": user["user_id"],
        "email":   email,
        "role":    user["role"],
    }
    access_token  = create_jwt_token({**base_payload, "type": "access"})
    refresh_token = create_jwt_token({
        **base_payload,
        "type": "refresh",
        "exp":  int(time.time()) + REFRESH_TTL_SEC,
    })

    return {
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "expires_in":    ACCESS_TTL_SEC,
    }


def logout(access_token: str, refresh_token: str) -> None:
    """Revoke both tokens, ending the user session."""
    revoke_token(access_token)
    revoke_token(refresh_token)


# ── Role-based access guard ───────────────────────────────────────────────────

def require_role(token: str, required_role: str) -> dict:
    """
    Validate a token and assert the user has the required role.

    Raises:
        PermissionError — if role does not match.

    Returns:
        The decoded token payload.
    """
    payload = validate_jwt_token(token)
    if payload.get("role") != required_role:
        raise PermissionError(
            f"Access denied: requires '{required_role}', "
            f"got '{payload.get('role')}'"
        )
    return payload
