"""p31: the flight video kept beside the stills, and frames pulled out of it."""

from __future__ import annotations

import io

from tests.conftest import auth_headers, login
from tests.factories import sharp_image


def _session(client, token, users, interval=2.0):
    device_id = client.post("/capture/devices", headers=auth_headers(token),
                            json={"name": "Video phone"}).get_json()["id"]
    resp = client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": interval, "max_duration_s": 60},
    )
    session_id = resp.get_json()["id"]
    client.post(f"/capture/sessions/{session_id}/stop", headers=auth_headers(token))
    return session_id


def _put_video(client, token, session_id, mime="video/mp4", body=b"\x00\x00\x00\x18ftypmp42fake"):
    return client.post(
        f"/capture/sessions/{session_id}/video",
        headers=auth_headers(token),
        data={"video": (io.BytesIO(body), "flight.mp4", mime), "duration_s": "123.5"},
        content_type="multipart/form-data",
    )


TRACK = [
    {"t": 0, "lat": 6.3800000, "lon": 124.7400000, "acc": 5},
    {"t": 10, "lat": 6.3801000, "lon": 124.7401000, "acc": 7},
]


def test_video_uploads_and_comes_back(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    assert _put_video(client, token, session_id).status_code == 201

    got = client.get(f"/capture/sessions/{session_id}/video", headers=auth_headers(token))
    assert got.status_code == 200
    assert got.data.startswith(b"\x00\x00\x00\x18ftyp")

    rows = client.get("/capture/sessions", headers=auth_headers(token)).get_json()
    row = next(r for r in rows if r["id"] == session_id)
    assert row["has_video"] is True
    assert row["video_duration_s"] == 123.5


def test_a_second_video_does_not_silently_replace_the_first(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _put_video(client, token, session_id)
    assert _put_video(client, token, session_id).status_code == 409


def test_an_unsupported_container_is_refused(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    assert _put_video(client, token, session_id, mime="video/avi").status_code == 415


def test_an_empty_video_is_refused(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    assert _put_video(client, token, session_id, body=b"").status_code == 400


def test_the_track_round_trips(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    resp = client.post(f"/capture/sessions/{session_id}/track",
                       headers=auth_headers(token), json={"points": TRACK})
    assert resp.status_code == 201
    assert resp.get_json()["points"] == 2
    back = client.get(f"/capture/sessions/{session_id}/track",
                      headers=auth_headers(token)).get_json()["points"]
    assert len(back) == 2
    assert back[0]["lat"] == 6.38


def test_a_session_with_no_track_returns_an_empty_list(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    assert client.get(f"/capture/sessions/{session_id}/track",
                      headers=auth_headers(token)).get_json()["points"] == []


def _frame(client, token, session_id, offset, seed=7141):
    return client.post(
        "/images/from-video",
        headers=auth_headers(token),
        data={
            "frame": (io.BytesIO(sharp_image(seed=seed)), "frame.jpg", "image/jpeg"),
            "capture_session_id": str(session_id),
            "offset_s": str(offset),
        },
        content_type="multipart/form-data",
    )


def test_a_frame_is_marked_as_coming_from_video(client, users):
    """The whole point: a video frame must never be mistaken for a camera still."""
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    client.post(f"/capture/sessions/{session_id}/track",
                headers=auth_headers(token), json={"points": TRACK})

    body = _frame(client, token, session_id, 5).get_json()
    assert body["gps_source"] == "video_interpolated"
    # Halfway between the two fixes.
    assert abs(body["lat"] - 6.38005) < 1e-6
    assert abs(body["lon"] - 124.74005) < 1e-6

    detail = client.get(f"/images/{body['image_id']}", headers=auth_headers(token)).get_json()
    assert detail["gps_source"] == "video_interpolated"


def test_a_frame_outside_the_track_takes_the_nearest_fix(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    client.post(f"/capture/sessions/{session_id}/track",
                headers=auth_headers(token), json={"points": TRACK})
    body = _frame(client, token, session_id, 99, seed=7142).get_json()
    assert abs(body["lat"] - 6.3801) < 1e-6


def test_a_frame_with_no_track_has_no_position_rather_than_a_guess(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    body = _frame(client, token, session_id, 3, seed=7143).get_json()
    assert body["lat"] is None
    assert body["gps_source"] == "missing"


def test_the_same_frame_twice_is_not_two_images(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    first = _frame(client, token, session_id, 7, seed=7144).get_json()
    again = _frame(client, token, session_id, 7, seed=7144).get_json()
    assert again["image_id"] == first["image_id"]
    assert again["duplicate"] is True


def test_a_video_frame_is_queued_for_analysis_like_any_image(client, users):
    from sqlalchemy import text

    from app.extensions import SessionLocal

    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    image_id = _frame(client, token, session_id, 2, seed=7145).get_json()["image_id"]
    queued = SessionLocal().execute(
        text("SELECT COUNT(*) FROM jobs WHERE image_id = :i"), {"i": image_id}
    ).scalar_one()
    assert queued == 1


def test_farmers_cannot_save_frames_or_fetch_video(client, users):
    operator = login(client, "t_tech")
    session_id = _session(client, operator, users)
    _put_video(client, operator, session_id)
    farmer = login(client, "t_farmer_a")
    assert _frame(client, farmer, session_id, 1, seed=7146).status_code == 403
    assert client.get(f"/capture/sessions/{session_id}/video",
                      headers=auth_headers(farmer)).status_code == 403
