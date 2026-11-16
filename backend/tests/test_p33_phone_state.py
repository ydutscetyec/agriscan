"""p33: what the phone says it is doing.

"Expired, 0 frames, the phone never picked this up" had two causes that looked identical
from the dashboard — the phone was not polling at all, or it was polling and ignoring the
command. The second is a fault in the phone's own state and nothing on the server could
see it.
"""

from __future__ import annotations

from tests.conftest import auth_headers, login


def _device(client, token, name="State phone"):
    return client.post("/capture/devices", headers=auth_headers(token),
                       json={"name": name}).get_json()["id"]


def _arm(client, token, device_id, users):
    return client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 120},
    ).get_json()["id"]


def _poll(client, token, device_id, **body):
    return client.post(f"/capture/devices/{device_id}/poll",
                       headers=auth_headers(token), json=body).get_json()


def _card(client, token, device_id):
    devices = client.get("/capture/devices", headers=auth_headers(token)).get_json()
    return next(d for d in devices if d["id"] == device_id)


def test_an_idle_phone_reports_idle(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token)
    _poll(client, token, device_id, local_session_id=None)
    card = _card(client, token, device_id)
    assert card["reported_state"] == "idle"
    assert card["ignoring_command"] is False


def test_a_capturing_phone_reports_the_session_it_is_running(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token)
    session_id = _arm(client, token, device_id, users)
    _poll(client, token, device_id, local_session_id=session_id)
    card = _card(client, token, device_id)
    assert card["reported_state"] == "capturing"
    assert card["reported_session_id"] == session_id
    assert card["ignoring_command"] is False
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))


def test_a_phone_ignoring_its_session_is_flagged(client, users):
    """The case that cost a flight: polling happily, says idle, session armed for it."""
    token = login(client, "t_tech")
    device_id = _device(client, token)
    session_id = _arm(client, token, device_id, users)
    _poll(client, token, device_id, local_session_id=None)
    assert _card(client, token, device_id)["ignoring_command"] is True
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))


def test_a_phone_running_the_wrong_session_is_flagged_too(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token)
    session_id = _arm(client, token, device_id, users)
    _poll(client, token, device_id, local_session_id=session_id + 9999)
    assert _card(client, token, device_id)["ignoring_command"] is True
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))


def test_no_flag_without_a_session_to_ignore(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token)
    _poll(client, token, device_id, local_session_id=None)
    assert _card(client, token, device_id)["ignoring_command"] is False


def test_the_poll_still_commands_the_session(client, users):
    """The diagnostic must not change what the phone is told to do."""
    token = login(client, "t_tech")
    device_id = _device(client, token)
    session_id = _arm(client, token, device_id, users)
    body = _poll(client, token, device_id, local_session_id=None)
    assert body["command"]["action"] == "capture"
    assert body["command"]["session"]["id"] == session_id
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))
