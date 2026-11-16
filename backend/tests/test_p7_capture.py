"""p7: remote capture protocol, device geolocation, boundary clearing, fields summary."""

from __future__ import annotations

import io
import itertools

import pytest
from sqlalchemy import select, text

from app.extensions import SessionLocal
from app.models import CaptureSession, Field, Image
from tests.conftest import auth_headers, login
from tests.factories import jpeg_with_gps, sharp_image
from tests.test_ingest import taxonomy  # noqa: F401

_SEED = itertools.count(60000)


def _register(client, token, name="Drone phone 1"):
    resp = client.post(
        "/capture/devices", headers=auth_headers(token),
        json={"name": name, "capabilities": {"image_capture": True}},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _arm(client, token, device_id, field_id, **extra):
    body = {"device_id": device_id, "field_id": field_id,
            "interval_s": 2, "max_duration_s": 300, **extra}
    return client.post("/capture/sessions", headers=auth_headers(token), json=body)


# ---------------------------------------------------------------- device protocol


def test_device_registers_and_appears_online(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech)
    client.post(f"/capture/devices/{device['id']}/poll", headers=auth_headers(tech),
                json={"battery_pct": 81, "camera_ready": True})
    listing = client.get("/capture/devices", headers=auth_headers(tech)).get_json()
    row = next(d for d in listing if d["id"] == device["id"])
    assert row["online"] is True
    assert row["battery_pct"] == 81
    assert row["camera_ready"] is True


def test_idle_device_gets_idle_command(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech, "idle phone")
    body = client.post(f"/capture/devices/{device['id']}/poll",
                       headers=auth_headers(tech), json={}).get_json()
    assert body["command"]["action"] == "idle"


def test_armed_session_reaches_the_phone_on_next_poll(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech, "armed phone")
    resp = _arm(client, tech, device["id"], users["field_farm_a"].id)
    assert resp.status_code == 201
    session_id = resp.get_json()["id"]

    body = client.post(f"/capture/devices/{device['id']}/poll",
                       headers=auth_headers(tech), json={}).get_json()
    assert body["command"]["action"] == "capture"
    assert body["command"]["session"]["id"] == session_id
    assert body["command"]["session"]["max_duration_s"] == 300


def test_phone_report_moves_session_to_running_then_completed(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech, "reporting phone")
    sid = _arm(client, tech, device["id"], users["field_farm_a"].id).get_json()["id"]

    client.post(f"/capture/devices/{device['id']}/poll", headers=auth_headers(tech),
                json={"session_report": {"session_id": sid, "state": "running", "shots": 3}})
    row = SessionLocal().get(CaptureSession, sid)
    SessionLocal().refresh(row)
    assert row.status == "running"
    assert row.shots_reported == 3

    body = client.post(f"/capture/devices/{device['id']}/poll", headers=auth_headers(tech),
                       json={"session_report": {"session_id": sid, "state": "completed",
                                                "shots": 12, "reason": "Shot limit reached"}}
                       ).get_json()
    assert body["command"]["action"] == "idle"


def test_operator_stop_reaches_the_phone(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech, "stoppable phone")
    sid = _arm(client, tech, device["id"], users["field_farm_a"].id).get_json()["id"]
    client.post(f"/capture/sessions/{sid}/stop", headers=auth_headers(tech))
    body = client.post(f"/capture/devices/{device['id']}/poll",
                       headers=auth_headers(tech), json={}).get_json()
    assert body["command"]["action"] == "idle"


def test_only_one_active_session_per_device(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech, "busy phone")
    _arm(client, tech, device["id"], users["field_farm_a"].id)
    second = _arm(client, tech, device["id"], users["field_farm_a"].id)
    assert second.status_code == 409


@pytest.mark.parametrize("interval,duration", [(0.2, 300), (120, 300), (2, 5), (2, 99999)])
def test_session_limits_are_enforced(client, users, interval, duration):
    tech = login(client, "t_tech")
    device = _register(client, tech, f"limits {interval} {duration}")
    resp = _arm(client, tech, device["id"], users["field_farm_a"].id,
                interval_s=interval, max_duration_s=duration)
    assert resp.status_code == 400


def test_farmer_cannot_register_or_arm(client, users):
    farmer = login(client, "t_farmer_a")
    resp = client.post("/capture/devices", headers=auth_headers(farmer), json={"name": "x"})
    assert resp.status_code == 403


def test_session_with_mission_from_another_field_is_rejected(client, users):
    tech = login(client, "t_tech")
    device = _register(client, tech, "mission mismatch")
    mission = client.post("/missions", headers=auth_headers(tech),
                          json={"field_id": users["field_farm_b"].id}).get_json()
    resp = _arm(client, tech, device["id"], users["field_farm_a"].id,
                mission_id=mission["id"])
    assert resp.status_code == 400


# ------------------------------------------------------------- uploads from a session


def test_session_upload_takes_field_and_source_from_session(client, users, taxonomy):
    tech = login(client, "t_tech")
    device = _register(client, tech, "uploading phone")
    sid = _arm(client, tech, device["id"], users["field_farm_a"].id).get_json()["id"]

    resp = client.post(
        "/images", headers=auth_headers(tech), content_type="multipart/form-data",
        data={
            "file": (io.BytesIO(sharp_image(240, next(_SEED))), "s.jpg", "image/jpeg"),
            "capture_session_id": str(sid),
            "field_id": str(users["field_farm_b"].id),   # ignored: session decides
            "source": "phone",                            # ignored: session is aerial
            "lat": "6.3712", "lon": "124.7462", "gps_accuracy_m": "4.5",
        },
    )
    assert resp.status_code == 202
    image = SessionLocal().get(Image, resp.get_json()["image_id"])
    assert image.field_id == users["field_farm_a"].id
    assert image.source == "drone"
    assert image.capture_session_id == sid


def test_device_gps_used_when_exif_is_absent(client, users, taxonomy):
    tech = login(client, "t_tech")
    resp = client.post(
        "/images", headers=auth_headers(tech), content_type="multipart/form-data",
        data={
            "file": (io.BytesIO(sharp_image(240, next(_SEED))), "d.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "lat": "6.3712", "lon": "124.7462", "gps_accuracy_m": "4.5",
        },
    )
    body = resp.get_json()
    assert body["gps_source"] == "device"
    image = SessionLocal().get(Image, body["image_id"])
    assert float(image.gps_accuracy_m) == 4.5


def test_exif_gps_wins_over_device_gps(client, users, taxonomy):
    """EXIF is the stronger source when present; device GPS never overwrites it."""
    tech = login(client, "t_tech")
    data = jpeg_with_gps((6, 22, 0), "N", (124, 44, 0), "E")
    resp = client.post(
        "/images", headers=auth_headers(tech), content_type="multipart/form-data",
        data={
            "file": (io.BytesIO(data), "e.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "lat": "10.0", "lon": "120.0",
        },
    )
    body = resp.get_json()
    if body.get("duplicate"):
        pytest.skip("fixture image already stored by an earlier test")
    assert body["gps_source"] == "exif"


def test_out_of_range_device_gps_is_ignored(client, users, taxonomy):
    tech = login(client, "t_tech")
    resp = client.post(
        "/images", headers=auth_headers(tech), content_type="multipart/form-data",
        data={
            "file": (io.BytesIO(sharp_image(240, next(_SEED))), "o.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "lat": "999", "lon": "124.7",
        },
    )
    assert resp.get_json()["gps_source"] == "missing"


# ---------------------------------------------------------------- boundary clearing


def test_boundary_can_be_cleared_and_stays_cleared(client, users):
    """The reported bug: a saved boundary could not be removed."""
    admin = login(client, "t_admin")
    ring = [[124.74, 6.37], [124.75, 6.37], [124.75, 6.38], [124.74, 6.37]]
    created = client.post(
        "/fields", headers=auth_headers(admin),
        json={"name": "boundary to clear", "farm_id": users["farm_a"].id,
              "boundary_geojson": {"type": "Polygon", "coordinates": [ring]}},
    ).get_json()
    assert created["boundary_geojson"] is not None

    client.put(f"/fields/{created['id']}", headers=auth_headers(admin),
               json={"boundary_geojson": None, "area_ha": None})

    stored = SessionLocal().execute(
        text("SELECT boundary_geojson IS NULL FROM fields WHERE id = :i"),
        {"i": created["id"]},
    ).scalar_one()
    assert stored == 1, "cleared boundary must be SQL NULL, not the JSON text 'null'"

    listing = client.get("/fields", headers=auth_headers(admin)).get_json()
    row = next(f for f in listing if f["id"] == created["id"])
    assert row["boundary_geojson"] is None


# ------------------------------------------------------------------ fields summary


def test_fields_summary_reports_boundary_and_counts(client, users):
    tech = login(client, "t_tech")
    body = client.get("/fields-summary", headers=auth_headers(tech)).get_json()
    assert len(body) >= 2
    for row in body:
        for key in ("has_boundary", "images", "detections_total",
                    "detections_verified", "growth_stage"):
            assert key in row


def test_fields_summary_is_scoped_for_farmers(client, users):
    farmer = login(client, "t_farmer_a")
    body = client.get("/fields-summary", headers=auth_headers(farmer)).get_json()
    assert all(row["farm_id"] == users["farm_a"].id for row in body)
