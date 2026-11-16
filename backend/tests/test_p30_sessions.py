"""p30: deleting a session, the lower interval floor, and the viewfinder flag surviving
a second server process."""

from __future__ import annotations

import io

from sqlalchemy import text

from app.extensions import SessionLocal
from tests.conftest import auth_headers, login
from tests.factories import sharp_image


def _device(client, token, name="Test phone"):
    return client.post("/capture/devices", headers=auth_headers(token),
                       json={"name": name}).get_json()["id"]


def _arm(client, token, device_id, users, interval=2.0):
    return client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={
            "device_id": device_id,
            "field_id": users["field_farm_a"].id,
            "interval_s": interval,
            "max_duration_s": 60,
        },
    )


def test_interval_floor_is_now_point_three(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token)
    ok = _arm(client, token, device_id, users, interval=0.3)
    assert ok.status_code == 201, ok.get_json()
    client.post(f"/capture/sessions/{ok.get_json()['id']}/stop", headers=auth_headers(token))


def test_an_interval_below_the_floor_is_still_refused(client, users):
    token = login(client, "t_tech")
    device_id = _device(client, token)
    resp = _arm(client, token, device_id, users, interval=0.05)
    assert resp.status_code == 400
    assert "0.3" in resp.get_json()["error"]


def test_admin_can_delete_a_finished_session(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin)
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))

    resp = client.delete(f"/capture/sessions/{session_id}", headers=auth_headers(admin))
    assert resp.status_code == 200, resp.get_json()
    rows = client.get("/capture/sessions", headers=auth_headers(admin)).get_json()
    assert session_id not in [r["id"] for r in rows]


def test_a_running_session_cannot_be_deleted(client, users):
    """Deleting one still running would leave the phone shooting for a session nobody
    can see or stop."""
    admin = login(client, "t_admin")
    device_id = _device(client, admin)
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    resp = client.delete(f"/capture/sessions/{session_id}", headers=auth_headers(admin))
    assert resp.status_code == 409
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))


def test_deleting_a_session_keeps_its_photos(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin)
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    upload = client.post(
        "/images",
        headers=auth_headers(admin),
        data={
            "file": (io.BytesIO(sharp_image(seed=31)), "s.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": "phone",
            "capture_session_id": str(session_id),
        },
        content_type="multipart/form-data",
    )
    image_id = upload.get_json()["image_id"]
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))

    body = client.delete(f"/capture/sessions/{session_id}",
                         headers=auth_headers(admin)).get_json()
    assert body["deleted"] == session_id
    # The photos are the work; the session row is only the record of a command.
    assert client.get(f"/images/{image_id}", headers=auth_headers(admin)).status_code == 200


def test_only_an_admin_may_delete_a_session(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin)
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))
    resp = client.delete(f"/capture/sessions/{session_id}",
                         headers=auth_headers(login(client, "t_tech")))
    assert resp.status_code == 403


def test_images_can_be_filtered_to_one_session(client, users):
    admin = login(client, "t_admin")
    device_id = _device(client, admin)
    session_id = _arm(client, admin, device_id, users).get_json()["id"]
    client.post(
        "/images",
        headers=auth_headers(admin),
        data={
            "file": (io.BytesIO(sharp_image(seed=32)), "in.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": "phone",
            "capture_session_id": str(session_id),
        },
        content_type="multipart/form-data",
    )
    body = client.get(f"/images?capture_session_id={session_id}",
                      headers=auth_headers(admin)).get_json()
    assert body["count"] >= 1
    assert body["total"] >= 1
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(admin))


def test_the_viewfinder_flag_survives_a_second_server_process(client, users, app):
    """It used to live in a Python dictionary, so a dashboard on one process set it
    while the phone polled another and was never asked for a frame."""
    from app import create_app
    from app.config import get_config

    token = login(client, "t_tech")
    device_id = _device(client, token, "Two process phone")

    # A different application object, as a second server would be.
    other = create_app(get_config()).test_client()
    before = other.post(f"/capture/devices/{device_id}/poll",
                        headers=auth_headers(token), json={}).get_json()
    assert before["preview_wanted"] is False

    client.get(f"/capture/devices/{device_id}/preview", headers=auth_headers(token))

    after = other.post(f"/capture/devices/{device_id}/poll",
                       headers=auth_headers(token), json={}).get_json()
    assert after["preview_wanted"] is True


def test_a_session_records_whether_the_phone_ever_reported(client, users):
    """Expired with no report means the phone never picked it up; expired with reports
    means it ran and the camera produced nothing. Different faults."""
    token = login(client, "t_tech")
    device_id = _device(client, token)
    session_id = _arm(client, token, device_id, users).get_json()["id"]

    rows = client.get("/capture/sessions", headers=auth_headers(token)).get_json()
    row = next(r for r in rows if r["id"] == session_id)
    assert row["phone_ever_reported"] is False

    client.post(f"/capture/devices/{device_id}/poll", headers=auth_headers(token),
                json={"session_report": {"session_id": session_id, "state": "running", "shots": 0}})
    rows = client.get("/capture/sessions", headers=auth_headers(token)).get_json()
    row = next(r for r in rows if r["id"] == session_id)
    assert row["phone_ever_reported"] is True
    assert row["last_report_at"]

    SessionLocal().execute(
        text("UPDATE capture_sessions SET status='stopped' WHERE id=:i"), {"i": session_id})
    SessionLocal().commit()
