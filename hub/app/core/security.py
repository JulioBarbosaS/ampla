"""Primitivas de segurança: senhas, chaves de agente, convites e JWT.

Decisões (docs/ARCHITECTURE.md · seção Segurança):
- senhas: bcrypt custo 12
- chaves de agente: 256 bits ("amp_" + 64 hex), armazenadas como sha256,
  comparação via lookup de hash (determinístico) — nunca plaintext no banco
- convites: "AMP-" + 4 grupos de 4 chars sem ambiguidade visual
- JWT: HS256 com expiração, alg fixo na decodificação
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

BCRYPT_ROUNDS = 12
AGENT_KEY_PREFIX = "amp_"
_INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sem 0/O/1/I


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


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
    """Retorna o user_id ou None para token inválido/expirado."""
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
