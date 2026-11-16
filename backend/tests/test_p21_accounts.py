"""p21: account management, session invalidation and the sign-in limit.

Every test makes its own accounts. The shared fixture accounts (t_admin and friends) are
used by the rest of the suite, so changing their passwords here would break other files.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app import create_app
from app.auth.security import hash_password
from app.config import get_config
from app.extensions import SessionLocal
from app.models import User
from tests.conftest import auth_headers, login

PW = "correct-horse-battery"


def _make(role: str, password: str = PW, active: bool = True) -> User:
    session = SessionLocal()
    user = User(
        name=f"p21-{role}-{uuid.uuid4().hex[:8]}", role=role, barangay="Test",
        password_hash=hash_password(password, 10), active=active, is_demo=True,
    )
    session.add(user)
    session.commit()
    return user


# ------------------------------------------------------------ own password


def test_change_own_password_issues_new_token_and_ends_old_sessions(client, users):
    farmer = _make("farmer")
    old = login(client, farmer.name)
    resp = client.post("/auth/password", headers=auth_headers(old),
                       json={"current_password": PW, "new_password": "a-new-password-22"})
    assert resp.status_code == 200, resp.get_json()
    new = resp.get_json()["token"]

    assert client.get("/auth/me", headers=auth_headers(new)).status_code == 200
    assert client.get("/auth/me", headers=auth_headers(old)).status_code == 401
    assert login(client, farmer.name, "a-new-password-22") is not None
    assert login(client, farmer.name, PW) is None


def test_wrong_current_password_is_400_not_401(client, users):
    """A typo must not sign the person out of the device they are using."""
    farmer = _make("farmer")
    token = login(client, farmer.name)
    resp = client.post("/auth/password", headers=auth_headers(token),
                       json={"current_password": "not-it-at-all", "new_password": "whatever-long-1"})
    assert resp.status_code == 400
    assert client.get("/auth/me", headers=auth_headers(token)).status_code == 200


def test_new_password_must_meet_policy_and_differ(client, users):
    farmer = _make("farmer")
    token = login(client, farmer.name)
    short = client.post("/auth/password", headers=auth_headers(token),
                        json={"current_password": PW, "new_password": "short"})
    assert short.status_code == 400
    same = client.post("/auth/password", headers=auth_headers(token),
                       json={"current_password": PW, "new_password": PW})
    assert same.status_code == 400


# ------------------------------------------------------------ admin actions


def test_admin_reset_ends_the_users_sessions(client, users):
    admin = login(client, "t_admin")
    farmer = _make("farmer")
    farmer_token = login(client, farmer.name)
    resp = client.post(f"/users/{farmer.id}/password", headers=auth_headers(admin),
                       json={"password": "reset-by-admin-1"})
    assert resp.status_code == 200, resp.get_json()
    assert client.get("/auth/me", headers=auth_headers(farmer_token)).status_code == 401
    assert login(client, farmer.name, "reset-by-admin-1") is not None


def test_deactivate_takes_effect_immediately(client, users):
    admin = login(client, "t_admin")
    tech = _make("technician")
    tech_token = login(client, tech.name)
    resp = client.put(f"/users/{tech.id}", headers=auth_headers(admin), json={"active": False})
    assert resp.status_code == 200
    assert resp.get_json()["active"] is False
    assert client.get("/auth/me", headers=auth_headers(tech_token)).status_code == 401
    assert login(client, tech.name) is None

    client.put(f"/users/{tech.id}", headers=auth_headers(admin), json={"active": True})
    assert login(client, tech.name) is not None


def test_admin_cannot_deactivate_or_demote_self(client, users):
    me = _make("admin")
    token = login(client, me.name)
    assert client.put(f"/users/{me.id}", headers=auth_headers(token),
                      json={"active": False}).status_code == 400
    assert client.put(f"/users/{me.id}", headers=auth_headers(token),
                      json={"role": "farmer"}).status_code == 400


def test_create_user_validates_role_and_duplicates(client, users):
    admin = login(client, "t_admin")
    bad = client.post("/users", headers=auth_headers(admin),
                      json={"name": "Role Probe", "role": "superuser", "password": "long-enough-pw"})
    assert bad.status_code == 400
    name = f"Dup {uuid.uuid4().hex[:6]}"
    first = client.post("/users", headers=auth_headers(admin),
                        json={"name": name, "role": "farmer", "password": "long-enough-pw"})
    assert first.status_code == 201
    again = client.post("/users", headers=auth_headers(admin),
                        json={"name": name, "role": "farmer", "password": "long-enough-pw"})
    assert again.status_code == 409


def test_non_admin_cannot_manage_accounts(client, users):
    tech = login(client, "t_tech")
    target = _make("farmer")
    assert client.put(f"/users/{target.id}", headers=auth_headers(tech),
                      json={"active": False}).status_code == 403
    assert client.post(f"/users/{target.id}/password", headers=auth_headers(tech),
                       json={"password": "something-long"}).status_code == 403


def test_account_changes_are_audited(client, users):
    from sqlalchemy import text

    admin = login(client, "t_admin")
    target = _make("farmer")
    client.put(f"/users/{target.id}", headers=auth_headers(admin), json={"barangay": "Naci"})
    client.post(f"/users/{target.id}/password", headers=auth_headers(admin),
                json={"password": "audited-reset-1"})
    actions = [r[0] for r in SessionLocal().execute(text(
        "SELECT action FROM audit_log WHERE object_id = :i ORDER BY id"), {"i": str(target.id)})]
    assert "update_user" in actions and "reset_password" in actions


# ------------------------------------------------------------ sign-in limit


@pytest.fixture()
def strict_client():
    cfg = get_config()
    cfg.LOGIN_MAX_FAILURES_PER_NAME = 3
    cfg.LOGIN_MAX_FAILURES_PER_IP = 5
    application = create_app(cfg)
    yield application.test_client()
    SessionLocal.remove()


def _attempt(client, name, password, ip):
    return client.post("/auth/login", json={"name": name, "password": password},
                       environ_base={"REMOTE_ADDR": ip})


def test_repeated_failures_for_one_name_are_throttled(strict_client, users):
    victim = _make("farmer")
    ip = f"10.21.{uuid.uuid4().int % 250}.1"
    for _ in range(3):
        assert _attempt(strict_client, victim.name, "wrong-wrong-wrong", ip).status_code == 401
    blocked = _attempt(strict_client, victim.name, PW, ip)
    assert blocked.status_code == 429
    assert "Too many failed sign-ins" in blocked.get_json()["error"]


def test_repeated_failures_from_one_address_are_throttled(strict_client, users):
    ip = f"10.22.{uuid.uuid4().int % 250}.2"
    for i in range(5):
        assert _attempt(strict_client, f"nobody-{uuid.uuid4().hex}", "x-password-x", ip).status_code == 401
    real = _make("farmer")
    assert _attempt(strict_client, real.name, PW, ip).status_code == 429
    # A different address is unaffected.
    other_ip = f"10.23.{uuid.uuid4().int % 250}.3"
    assert _attempt(strict_client, real.name, PW, other_ip).status_code == 200


def test_unknown_name_and_wrong_password_get_the_same_answer(client, users):
    a = client.post("/auth/login", json={"name": f"ghost-{uuid.uuid4().hex}", "password": "pw-pw-pw-pw"})
    b = client.post("/auth/login", json={"name": "t_farmer_a", "password": "pw-pw-pw-pw"})
    assert a.status_code == b.status_code == 401
    assert a.get_json() == b.get_json()
