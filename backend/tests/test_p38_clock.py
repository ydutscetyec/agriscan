"""p38: one clock.

Stored timestamps are naive UTC. Several places compared them against
`datetime.now()`, which is local time. On a UTC machine — which is every machine the
test suite had ever run on — the two agree exactly and nothing is wrong. At UTC+8, every
row is born reading eight hours old, and a capture session expired within seconds of
starting.

Run the whole suite under a non-UTC timezone and these fail without the fix:

    TZ=Asia/Manila python -m pytest tests/
"""

from __future__ import annotations

import datetime as dt
import time

from sqlalchemy import select

from app.api.capture import _active_session, _now
from app.extensions import SessionLocal
from app.models import CaptureSession
from app.utils.clock import utc_now
from tests.conftest import auth_headers, login


def test_the_clock_is_utc_wherever_the_machine_is(app):
    gap = abs((utc_now() - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)).total_seconds())
    assert gap < 2, "utc_now() is not UTC on this machine"


def test_capture_uses_the_same_clock_as_the_stored_defaults(app):
    """`_now()` in the capture API is compared against `created_at`. If they disagree by
    a timezone offset, every expiry calculation is wrong by that amount."""
    from app.models import _now as model_now

    assert abs((_now() - model_now()).total_seconds()) < 2


def test_a_new_session_is_not_already_expired(client, users):
    """The bug exactly: the session was created, the phone polled seconds later, and the
    server had already expired it because its age appeared to be the UTC offset."""
    token = login(client, "t_tech")
    device_id = client.post("/capture/devices", headers=auth_headers(token),
                            json={"name": "Clock phone"}).get_json()["id"]
    session_id = client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 60},
    ).get_json()["id"]

    time.sleep(1)
    db = SessionLocal()
    active = _active_session(db, device_id)
    assert active is not None, "a one-minute session expired within a second of starting"
    assert active.id == session_id

    row = db.execute(select(CaptureSession).where(CaptureSession.id == session_id)).scalar_one()
    assert row.status in ("armed", "running")
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))


def test_the_phone_is_commanded_to_capture_rather_than_told_idle(client, users):
    """What the phone saw: 'Stopped from the dashboard' seconds after starting."""
    token = login(client, "t_tech")
    device_id = client.post("/capture/devices", headers=auth_headers(token),
                            json={"name": "Clock phone 2"}).get_json()["id"]
    session_id = client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 60},
    ).get_json()["id"]

    time.sleep(1)
    body = client.post(f"/capture/devices/{device_id}/poll",
                       headers=auth_headers(token), json={"local_session_id": session_id})
    command = body.get_json()["command"]
    assert command["action"] == "capture", "the server told the phone to stop immediately"
    assert command["session"]["id"] == session_id
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))


def test_a_session_does_expire_once_it_is_genuinely_over(client, users):
    """The expiry still has to work; this is not a licence to never expire anything."""
    from sqlalchemy import text

    token = login(client, "t_tech")
    device_id = client.post("/capture/devices", headers=auth_headers(token),
                            json={"name": "Clock phone 3"}).get_json()["id"]
    session_id = client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 60},
    ).get_json()["id"]

    db = SessionLocal()
    db.execute(
        text("UPDATE capture_sessions SET created_at = created_at - INTERVAL 400 SECOND, "
             "started_at = NULL WHERE id = :i"),
        {"i": session_id},
    )
    db.commit()
    assert _active_session(db, device_id) is None
    assert db.get(CaptureSession, session_id).status == "expired"
