"""p32: the ghost-device fault.

Pairing a phone twice leaves two device rows for one physical phone, and the phone only
ever polls as the most recent. Arming the older row looked entirely normal and did
nothing at all — the session sat armed until it expired, which is a wasted flight found
out about after landing.
"""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import SessionLocal
from tests.conftest import auth_headers, login


def _device(client, token, name):
    return client.post("/capture/devices", headers=auth_headers(token),
                       json={"name": name}).get_json()["id"]


def _age(device_id, seconds):
    """Backdate the device's last contact, as a phone that stopped polling would."""
    s = SessionLocal()
    s.execute(
        text("UPDATE capture_devices SET last_seen_at = NOW() - INTERVAL :n SECOND WHERE id = :i"),
        {"n": seconds, "i": device_id},
    )
    s.commit()


def _arm(client, token, device_id, users):
    return client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 60},
    )


def test_a_phone_that_is_polling_can_be_armed(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token, "Live phone")
    resp = _arm(client, token, device_id, users)
    assert resp.status_code == 201
    client.post(f"/capture/sessions/{resp.get_json()['id']}/stop", headers=auth_headers(token))


def test_arming_a_silent_phone_is_refused_with_the_reason(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token, "Ghost phone")
    _age(device_id, 600)
    resp = _arm(client, token, device_id, users)
    assert resp.status_code == 409
    message = resp.get_json()["error"]
    assert "Ghost phone" in message
    assert "last seen" in message
    # The actual remedy, not just a complaint.
    assert "/camera" in message


def test_a_phone_that_never_connected_is_refused_too(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token, "Never phone")
    s = SessionLocal()
    s.execute(text("UPDATE capture_devices SET last_seen_at = NULL WHERE id = :i"),
              {"i": device_id})
    s.commit()
    resp = _arm(client, token, device_id, users)
    assert resp.status_code == 409
    assert "never connected" in resp.get_json()["error"]


def test_a_brief_gap_does_not_block_arming(client, users):
    """A phone polls every few seconds; a short stutter must not stop a flight."""
    token = login(client, "t_tech")
    device_id = _device(client, token, "Blinking phone")
    _age(device_id, 30)
    resp = _arm(client, token, device_id, users)
    assert resp.status_code == 201
    client.post(f"/capture/sessions/{resp.get_json()['id']}/stop", headers=auth_headers(token))


def test_polling_makes_a_stale_device_armable_again(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token, "Returning phone")
    _age(device_id, 600)
    assert _arm(client, token, device_id, users).status_code == 409

    client.post(f"/capture/devices/{device_id}/poll", headers=auth_headers(token), json={})
    resp = _arm(client, token, device_id, users)
    assert resp.status_code == 201
    client.post(f"/capture/sessions/{resp.get_json()['id']}/stop", headers=auth_headers(token))


def test_an_old_pairing_can_be_removed(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin, "Old pairing")
    _age(device_id, 600)
    assert client.delete(f"/capture/devices/{device_id}",
                         headers=auth_headers(admin)).status_code == 200
    listed = client.get("/capture/devices", headers=auth_headers(admin)).get_json()
    assert device_id not in [d["id"] for d in listed]


def test_a_device_with_a_live_session_cannot_be_removed(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin, "Busy phone")
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    assert client.delete(f"/capture/devices/{device_id}",
                         headers=auth_headers(admin)).status_code == 409
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))


def test_only_an_admin_removes_a_pairing(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin, "Protected phone")
    _age(device_id, 600)
    assert client.delete(f"/capture/devices/{device_id}",
                         headers=auth_headers(login(client, "t_tech"))).status_code == 403


def test_removing_a_pairing_keeps_the_flights_it_made(client, users):
    """Deleting a pairing must not rewrite the record of what was actually flown."""
    admin = login(client, "t_admin")
    device_id = _device(client, admin, "Historic phone")
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))
    client.delete(f"/capture/devices/{device_id}", headers=auth_headers(admin))

    sessions = client.get("/capture/sessions", headers=auth_headers(admin)).get_json()
    assert session_id in [s["id"] for s in sessions]


def test_an_online_pairing_can_be_removed_too(client, users):
    """The button used to be hidden on online cards, so the phone you were actually
    holding was the one pairing you could never clear."""
    admin = login(client, "t_admin")
    device_id = _device(client, admin, "Live pairing")
    client.post(f"/capture/devices/{device_id}/poll", headers=auth_headers(admin), json={})
    assert client.delete(f"/capture/devices/{device_id}",
                         headers=auth_headers(admin)).status_code == 200


def test_the_refusal_names_the_session_in_the_way(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin, "Busy pairing")
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    resp = client.delete(f"/capture/devices/{device_id}", headers=auth_headers(admin))
    assert resp.status_code == 409
    message = resp.get_json()["error"]
    assert str(session_id) in message
    assert "Busy pairing" in message
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))
    assert client.delete(f"/capture/devices/{device_id}",
                         headers=auth_headers(admin)).status_code == 200
