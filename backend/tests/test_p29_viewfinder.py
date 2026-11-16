"""p29: the near-live viewfinder — a frame pushed by the phone, pulled by the dashboard."""

from __future__ import annotations

import io

from tests.conftest import auth_headers, login


def _register(client, token, name="Drone phone 1"):
    resp = client.post("/capture/devices", headers=auth_headers(token), json={"name": name})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def _frame(client, token, device_id, data=b"\xff\xd8\xff\xdb-fake-jpeg"):
    return client.post(
        f"/capture/devices/{device_id}/preview",
        headers=auth_headers(token),
        data={"frame": (io.BytesIO(data), "preview.jpg", "image/jpeg")},
        content_type="multipart/form-data",
    )


def test_a_pushed_frame_comes_back(client, users):
    token = login(client, "t_tech")
    device_id = _register(client, token)
    assert _frame(client, token, device_id).status_code == 200

    got = client.get(f"/capture/devices/{device_id}/preview", headers=auth_headers(token))
    assert got.status_code == 200
    assert got.mimetype == "image/jpeg"
    assert got.data.startswith(b"\xff\xd8")
    # A viewfinder must never be cached: the point is that it is the newest frame.
    assert got.headers["Cache-Control"] == "no-store"
    assert "X-Frame-Age-Seconds" in got.headers


def test_only_the_newest_frame_is_kept(client, users):
    token = login(client, "t_tech")
    device_id = _register(client, token)
    _frame(client, token, device_id, b"\xff\xd8\xff-older-frame")
    _frame(client, token, device_id, b"\xff\xd8\xff-newest-frame")
    got = client.get(f"/capture/devices/{device_id}/preview", headers=auth_headers(token))
    assert b"newest" in got.data
    assert b"older" not in got.data


def test_no_frame_yet_is_a_404_not_an_error(client, users):
    token = login(client, "t_tech")
    device_id = _register(client, token)
    assert client.get(
        f"/capture/devices/{device_id}/preview", headers=auth_headers(token)
    ).status_code == 404


def test_the_phone_is_only_asked_for_frames_while_someone_watches(client, users):
    """The whole data argument for this feature: a flight nobody is watching sends
    nothing at all."""
    token = login(client, "t_tech")
    device_id = _register(client, token)

    first = client.post(f"/capture/devices/{device_id}/poll", headers=auth_headers(token), json={})
    assert first.get_json()["preview_wanted"] is False

    client.get(f"/capture/devices/{device_id}/preview", headers=auth_headers(token))
    after = client.post(f"/capture/devices/{device_id}/poll", headers=auth_headers(token), json={})
    assert after.get_json()["preview_wanted"] is True


def test_watching_one_phone_does_not_wake_another(client, users):
    token = login(client, "t_tech")
    watched = _register(client, token, "Watched phone")
    other = _register(client, token, "Other phone")
    client.get(f"/capture/devices/{watched}/preview", headers=auth_headers(token))
    body = client.post(f"/capture/devices/{other}/poll", headers=auth_headers(token), json={}).get_json()
    assert body["preview_wanted"] is False


def test_an_oversized_frame_is_refused(client, users):
    token = login(client, "t_tech")
    device_id = _register(client, token)
    resp = _frame(client, token, device_id, b"\xff\xd8" + b"x" * (400 * 1024 + 10))
    assert resp.status_code == 413


def test_an_empty_frame_is_refused(client, users):
    token = login(client, "t_tech")
    device_id = _register(client, token)
    assert _frame(client, token, device_id, b"").status_code == 400


def test_farmers_cannot_see_or_push_frames(client, users):
    operator = login(client, "t_tech")
    device_id = _register(client, operator)
    _frame(client, operator, device_id)
    farmer = login(client, "t_farmer_a")
    assert client.get(
        f"/capture/devices/{device_id}/preview", headers=auth_headers(farmer)
    ).status_code == 403
    assert _frame(client, farmer, device_id).status_code == 403


def test_an_unknown_device_is_rejected(client, users):
    token = login(client, "t_tech")
    assert _frame(client, token, 99999999).status_code == 404
