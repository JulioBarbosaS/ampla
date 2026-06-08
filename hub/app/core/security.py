"""Security primitives: passwords, agent keys, invites and JWT.

Decisions (docs/ARCHITECTURE.md · Security section):
- passwords: bcrypt cost 12
- agent keys: 256 bits ("amp_" + 64 hex), stored as sha256,
  compared via hash lookup (deterministic) — never plaintext in the database
- invites: "AMP-" + 4 groups of 4 chars without visual ambiguity
- JWT: HS256 with expiration, algorithm pinned on decode
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

BCRYPT_ROUNDS = 12
AGENT_KEY_PREFIX = "amp_"
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # without 0/O/1/I


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# Constant bcrypt hash (default cost) for the login path with a nonexistent
# email: a check with the same cost as the real path, without generating a hash
# on every call. Computed once at import time. No real password matches it.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def generate_agent_key() -> str:
    return AGENT_KEY_PREFIX + secrets.token_hex(32)


def hash_agent_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_invite_code() -> str:
    groups = ["".join(secrets.choice(_INVITE_ALPHABET) for _ in range(4)) for _ in range(4)]
    return "AMP-" + "-".join(groups)


def create_jwt(user_id: int, secret: str, expires_days: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=expires_days)}
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> int | None:
    """Returns the user_id or None for an invalid/expired token."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
