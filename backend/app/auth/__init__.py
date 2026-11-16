"""Auth blueprint."""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select, text

from app.auth.decorators import requires_auth
from app.auth.security import (
    PasswordPolicyError,
    burn_verify,
    hash_password,
    issue_token,
    password_version,
    utc_now,
    verify_password,
)
from app.extensions import SessionLocal
from app.models import User
from app.services import audit
from app.utils.errors import ApiError

bp = Blueprint("auth", __name__, url_prefix="/auth")

TOO_MANY_ATTEMPTS = (
    "Too many failed sign-ins. Wait {minutes} minutes and try again, or ask an "
    "administrator to reset the password."
)


def _client_ip() -> str:
    # request.remote_addr is the real client only when PROXY_HOPS matches the proxies
    # actually in front of the app; see create_app.
    return (request.remote_addr or "unknown")[:64]


def _recent_failures(session, cfg, *, name: str, ip: str) -> tuple[int, int]:
    """Failed sign-ins in the window, for this name and from this address.

    Counted from audit_log, which already records every failure. Nothing new to keep in
    memory, and the count survives a server restart.
    """
    window = {"mins": cfg.LOGIN_WINDOW_MINUTES}
    by_name = session.execute(
        text(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'login_failed' "
            "AND object_id = :n AND created_at > NOW() - INTERVAL :mins MINUTE"
        ),
        {"n": name[:80], **window},
    ).scalar_one()
    by_ip = session.execute(
        text(
            "SELECT COUNT(*) FROM audit_log WHERE action = 'login_failed' "
            "AND created_at > NOW() - INTERVAL :mins MINUTE "
            "AND JSON_UNQUOTE(JSON_EXTRACT(detail, '$.ip')) = :ip"
        ),
        {"ip": ip, **window},
    ).scalar_one()
    return int(by_name), int(by_ip)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    if not name or not password:
        raise ApiError("Name and password are required.", 400)

    cfg = current_app.config["AGRISCAN"]
    session = SessionLocal()
    ip = _client_ip()

    by_name, by_ip = _recent_failures(session, cfg, name=name, ip=ip)
    if by_name >= cfg.LOGIN_MAX_FAILURES_PER_NAME or by_ip >= cfg.LOGIN_MAX_FAILURES_PER_IP:
        audit.record(None, "login_throttled", "user", name[:80], {"ip": ip})
        raise ApiError(TOO_MANY_ATTEMPTS.format(minutes=cfg.LOGIN_WINDOW_MINUTES), 429)

    user = session.execute(select(User).where(User.name == name)).scalar_one_or_none()

    # Same message and same work either way: do not leak which names exist.
    if user is None:
        burn_verify(password)
    if user is None or not user.active or not verify_password(user.password_hash, password):
        audit.record(user.id if user else None, "login_failed", "user", name[:80], {"ip": ip})
        raise ApiError("Invalid credentials.", 401)

    token = issue_token(user.id, user.role, cfg.SECRET_KEY, cfg.TOKEN_TTL_MINUTES,
                        pwv=password_version(user.password_changed_at))
    audit.record(user.id, "login", "user", user.id, {"ip": ip})
    return jsonify({"token": token, "user": user.to_dict()})


@bp.get("/me")
@requires_auth
def me():
    return jsonify(g.current_user.to_dict())


@bp.post("/password")
@requires_auth
def change_own_password():
    """Any signed-in account may change its own password.

    Every other session for this account stops working. The caller gets a fresh token
    in the response so the device they are using stays signed in.
    """
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    user: User = g.current_user
    cfg = current_app.config["AGRISCAN"]

    # 400, not 401: a mistyped current password must not sign the person out.
    if not verify_password(user.password_hash, current):
        audit.record(user.id, "password_change_failed", "user", user.id)
        raise ApiError("Current password is not correct.", 400)
    if new == current:
        raise ApiError("The new password must be different from the current one.", 400)
    try:
        new_hash = hash_password(new, cfg.PASSWORD_MIN_LENGTH)
    except PasswordPolicyError as exc:
        raise ApiError(str(exc), 400) from None

    session = SessionLocal()
    row = session.get(User, user.id)
    row.password_hash = new_hash
    row.password_changed_at = utc_now()
    session.commit()
    audit.record(user.id, "password_changed", "user", user.id)
    token = issue_token(row.id, row.role, cfg.SECRET_KEY, cfg.TOKEN_TTL_MINUTES,
                        pwv=password_version(row.password_changed_at))
    return jsonify({"token": token, "user": row.to_dict()})
