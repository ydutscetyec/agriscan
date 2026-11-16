"""Authentication and role enforcement. Server-side only.

The frontend never supplies a role: the role is read from the signed token and
re-checked against the database row on every request.
"""

from __future__ import annotations

import functools

from flask import current_app, g, request

from app.auth.security import decode_token, password_version
from app.extensions import SessionLocal
from app.models import User
from app.utils.errors import ApiError


def _load_user_from_request() -> User | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    payload = decode_token(header[7:], current_app.config["AGRISCAN"].SECRET_KEY)
    if not payload:
        return None
    session = SessionLocal()
    user = session.get(User, int(payload["sub"]))
    if user is None or not user.active:
        return None
    # The token's role claim is advisory; the database row is authoritative.
    if user.role != payload.get("role"):
        return None
    # A password change or reset ends every session issued under the old password.
    if int(payload.get("pwv", 0)) != password_version(user.password_changed_at):
        return None
    return user


def current_user_or_none() -> User | None:
    """The signed-in user, or None. For endpoints that answer either way and only
    change how much they say — /health, which has to stay reachable without a token."""
    try:
        return _load_user_from_request()
    except Exception:  # noqa: BLE001 - a malformed token is simply "not signed in"
        return None


def requires_auth(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        user = _load_user_from_request()
        if user is None:
            raise ApiError("Authentication required.", 401)
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def requires_role(*roles: str):
    """Allow only the named roles. Always stacked on top of requires_auth."""

    def decorator(fn):
        @functools.wraps(fn)
        @requires_auth
        def wrapper(*args, **kwargs):
            if g.current_user.role not in roles:
                raise ApiError(
                    f"Role '{g.current_user.role}' is not permitted here.", 403
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator
