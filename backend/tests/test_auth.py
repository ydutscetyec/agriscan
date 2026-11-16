"""Login, token rejection, and role enforcement."""

from __future__ import annotations

import jwt
from tests.conftest import auth_headers, login


def test_login_succeeds_with_correct_password(client, users):
    token = login(client, "t_farmer_a")
    assert token is not None


def test_login_rejects_wrong_password(client, users):
    resp = client.post("/auth/login", json={"name": "t_farmer_a", "password": "wrong"})
    assert resp.status_code == 401
    assert "Invalid credentials" in resp.get_json()["error"]


def test_login_rejects_unknown_user_with_same_message(client, users):
    resp = client.post("/auth/login", json={"name": "no_such_user", "password": "x"})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "Invalid credentials."


def test_protected_route_requires_token(client, users):
    assert client.get("/auth/me").status_code == 401


def test_garbage_token_rejected(client, users):
    resp = client.get("/auth/me", headers=auth_headers("not.a.token"))
    assert resp.status_code == 401


def test_token_signed_with_wrong_secret_rejected(client, users, cfg):
    forged = jwt.encode(
        {"sub": str(users["t_admin"].id), "role": "admin", "exp": 9999999999},
        "attacker-secret", algorithm="HS256",
    )
    assert client.get("/auth/me", headers=auth_headers(forged)).status_code == 401


def test_role_claim_cannot_be_escalated(client, users, cfg):
    """A validly-signed token claiming a higher role is refused: the DB row wins."""
    escalated = jwt.encode(
        {"sub": str(users["t_farmer_a"].id), "role": "admin", "exp": 9999999999},
        cfg.SECRET_KEY, algorithm="HS256",
    )
    assert client.get("/users", headers=auth_headers(escalated)).status_code == 401


def test_farmer_cannot_list_users(client, users):
    token = login(client, "t_farmer_a")
    assert client.get("/users", headers=auth_headers(token)).status_code == 403


def test_admin_can_list_users(client, users):
    token = login(client, "t_admin")
    assert client.get("/users", headers=auth_headers(token)).status_code == 200


def test_password_is_never_returned(client, users):
    token = login(client, "t_admin")
    body = client.get("/users", headers=auth_headers(token)).get_json()
    for user in body:
        assert "password_hash" not in user and "password" not in user
