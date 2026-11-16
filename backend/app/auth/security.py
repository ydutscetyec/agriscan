"""Password hashing and signed tokens.

Argon2id via argon2-cffi. Plaintext passwords are never stored, logged or returned.
"""

from __future__ import annotations

import datetime as dt

from app.utils.clock import utc_now as _clock_utc_now

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()


class PasswordPolicyError(ValueError):
    pass


def hash_password(password: str, min_length: int = 10) -> str:
    if password is None or len(password) < min_length:
        raise PasswordPolicyError(
            f"Password must be at least {min_length} characters."
        )
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, TypeError):
        return False


# Verified against when the name does not exist, so an unknown name costs the same
# Argon2 work as a wrong password and response time does not reveal which names exist.
_DUMMY_HASH = _hasher.hash("agriscan-timing-equaliser")


def burn_verify(password: str) -> None:
    verify_password(_DUMMY_HASH, password or "")


def utc_now() -> dt.datetime:
    """Naive UTC with microseconds, the form stored in users.password_changed_at."""
    return _clock_utc_now()


def password_version(changed_at: dt.datetime | None) -> int:
    """The version a token must carry. 0 for an account whose password never changed,
    so tokens issued before p21 keep working until the first change."""
    if changed_at is None:
        return 0
    return int(changed_at.replace(tzinfo=dt.timezone.utc).timestamp() * 1_000_000)


def issue_token(user_id: int, role: str, secret: str, ttl_minutes: int,
                pwv: int = 0) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + dt.timedelta(minutes=ttl_minutes)).timestamp()),
        "pwv": pwv,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict | None:
    """Return the payload, or None if the token is invalid, expired or forged."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
