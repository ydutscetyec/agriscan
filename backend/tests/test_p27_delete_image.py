"""p27: removing a captured photo, and what must survive it."""

from __future__ import annotations

from sqlalchemy import text

from app.extensions import SessionLocal
from tests.conftest import auth_headers, login
from tests.factories import sharp_image


def _image_id(client, token, users, source="phone"):
    """Upload one real JPEG and return its id."""
    import io

    resp = client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(seed=7)), "shot.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": source,
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code in (200, 201, 202), resp.get_json()
    return resp.get_json()["image_id"]


def test_admin_can_delete_a_photo_with_no_results(client, users):
    token = login(client, "t_admin")
    image_id = _image_id(client, token, users)
    assert client.delete(f"/images/{image_id}", headers=auth_headers(token)).status_code == 200
    assert client.get(f"/images/{image_id}", headers=auth_headers(token)).status_code == 404


def test_delete_removes_the_file_from_disk(client, users, app):
    import pathlib

    from app.config import get_config
    from app.models import Image

    token = login(client, "t_admin")
    image_id = _image_id(client, token, users)
    session = SessionLocal()
    path = session.get(Image, image_id).file_path
    from app.services.storage import resolve_stored

    on_disk = resolve_stored(path)
    assert on_disk.is_file()
    body = client.delete(f"/images/{image_id}", headers=auth_headers(token)).get_json()
    assert body["file_removed"] is True
    assert not on_disk.exists()
    assert get_config().image_root_path.is_dir()


def test_delete_takes_the_jobs_and_detections_with_it(client, users):
    token = login(client, "t_admin")
    image_id = _image_id(client, token, users)
    session = SessionLocal()
    before = session.execute(
        text("SELECT COUNT(*) FROM jobs WHERE image_id = :i"), {"i": image_id}
    ).scalar_one()
    assert before >= 1
    assert client.delete(f"/images/{image_id}", headers=auth_headers(token)).status_code == 200
    for table in ("jobs", "detections"):
        left = session.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE image_id = :i"), {"i": image_id}
        ).scalar_one()
        assert left == 0, f"{table} rows left behind"


def test_only_an_admin_may_delete(client, users):
    admin = login(client, "t_admin")
    image_id = _image_id(client, admin, users)
    for name in ("t_tech", "t_farmer_a"):
        resp = client.delete(f"/images/{image_id}", headers=auth_headers(login(client, name)))
        assert resp.status_code == 403, name
    # still there
    assert client.get(f"/images/{image_id}", headers=auth_headers(admin)).status_code == 200


def test_missing_image_is_404(client, users):
    token = login(client, "t_admin")
    assert client.delete("/images/99999999", headers=auth_headers(token)).status_code == 404


def test_the_deletion_itself_is_recorded(client, users):
    token = login(client, "t_admin")
    image_id = _image_id(client, token, users)
    client.delete(f"/images/{image_id}", headers=auth_headers(token))
    # audit_log is append-only (migration 002), so what was removed stays answerable.
    row = SessionLocal().execute(
        text("SELECT detail FROM audit_log WHERE action = 'delete_image' AND object_id = :i"),
        {"i": str(image_id)},
    ).fetchone()
    assert row is not None
    assert "file_path" in row[0]
