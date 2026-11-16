"""p40: every photo from one flight, as one file."""

from __future__ import annotations

import io
import zipfile

from tests.conftest import auth_headers, login
from tests.factories import sharp_image


def _session(client, token, users):
    device_id = client.post("/capture/devices", headers=auth_headers(token),
                            json={"name": "Zip phone"}).get_json()["id"]
    session_id = client.post(
        "/capture/sessions",
        headers=auth_headers(token),
        json={"device_id": device_id, "field_id": users["field_farm_a"].id,
              "interval_s": 2, "max_duration_s": 300},
    ).get_json()["id"]
    return session_id


def _upload(client, token, users, session_id, seed):
    return client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(seed=seed)), f"f{seed}.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": "drone",
            "capture_session_id": str(session_id),
        },
        content_type="multipart/form-data",
    ).get_json()["image_id"]


def test_a_session_downloads_as_one_archive(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    for seed in (8101, 8102, 8103):
        _upload(client, token, users, session_id, seed)

    resp = client.get(f"/capture/sessions/{session_id}/images.zip",
                      headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"
    assert f"agriscan-session-{session_id}.zip" in resp.headers["Content-Disposition"]

    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    photos = [n for n in archive.namelist() if n.endswith(".jpg")]
    assert len(photos) == 3
    # Ordered and named so the archive still means something away from the database.
    assert photos == sorted(photos)
    assert all(n.startswith(f"session-{session_id}/") for n in archive.namelist())
    assert archive.read(photos[0])[:2] == b"\xff\xd8"


def test_the_archive_explains_itself(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    _upload(client, token, users, session_id, 8110)
    resp = client.get(f"/capture/sessions/{session_id}/images.zip", headers=auth_headers(token))
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    readme = archive.read(f"session-{session_id}/README.txt").decode()
    assert str(session_id) in readme
    assert "UTC" in readme


def test_an_empty_session_says_so_rather_than_sending_an_empty_file(client, users):
    token = login(client, "t_tech")
    session_id = _session(client, token, users)
    resp = client.get(f"/capture/sessions/{session_id}/images.zip", headers=auth_headers(token))
    assert resp.status_code == 404
    assert "no photos" in resp.get_json()["error"]


def test_farmers_cannot_download_a_flight(client, users):
    operator = login(client, "t_tech")
    session_id = _session(client, operator, users)
    _upload(client, operator, users, session_id, 8120)
    farmer = login(client, "t_farmer_a")
    assert client.get(f"/capture/sessions/{session_id}/images.zip",
                      headers=auth_headers(farmer)).status_code == 403


def test_an_unknown_session_is_404(client, users):
    token = login(client, "t_tech")
    assert client.get("/capture/sessions/99999999/images.zip",
                      headers=auth_headers(token)).status_code == 404
