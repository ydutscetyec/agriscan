"""p28: the fixes that stop Captured images falling over on a real flight."""

from __future__ import annotations

import io

from sqlalchemy import event, text

from app.config import get_config
from app.extensions import SessionLocal  # noqa: F401
from tests.conftest import auth_headers, login
from tests.factories import sharp_image


def _upload(client, token, users, name="shot.jpg", seed=3):
    resp = client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(seed=seed)), name, "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": "phone",
        },
        content_type="multipart/form-data",
    )
    assert resp.status_code in (200, 201, 202), resp.get_json()
    return resp.get_json()["image_id"]


def test_thumbnail_is_smaller_than_the_original(client, users):
    token = login(client, "t_admin")
    image_id = _upload(client, token, users, seed=200)
    full = client.get(f"/images/{image_id}/file", headers=auth_headers(token))
    thumb = client.get(f"/images/{image_id}/thumb", headers=auth_headers(token))
    assert thumb.status_code == 200
    assert thumb.mimetype == "image/jpeg"
    # The whole point: a list view must not pull the full capture for every row.
    assert len(thumb.data) < len(full.data)


def test_thumbnail_is_cached_on_disk_and_reused(client, users):
    from app.services.storage import thumb_path

    token = login(client, "t_admin")
    image_id = _upload(client, token, users, seed=201)
    cached = thumb_path(get_config(), image_id)
    # The cache outlives the test database, so an id can come round again with a stale
    # file already sitting there.
    cached.unlink(missing_ok=True)
    client.get(f"/images/{image_id}/thumb", headers=auth_headers(token))
    assert cached.is_file()
    first = cached.stat().st_mtime_ns
    client.get(f"/images/{image_id}/thumb", headers=auth_headers(token))
    assert cached.stat().st_mtime_ns == first, "regenerated instead of reused"


def test_thumbnail_obeys_the_same_ownership_rule_as_the_file(client, users):
    admin = login(client, "t_admin")
    image_id = _upload(client, admin, users, seed=202)
    other = login(client, "t_farmer_b")
    assert client.get(f"/images/{image_id}/thumb", headers=auth_headers(other)).status_code in (403, 404)


def test_deleting_an_image_removes_its_thumbnail(client, users):
    from app.services.storage import thumb_path

    token = login(client, "t_admin")
    image_id = _upload(client, token, users, seed=203)
    client.get(f"/images/{image_id}/thumb", headers=auth_headers(token))
    cached = thumb_path(get_config(), image_id)
    assert cached.is_file()
    client.delete(f"/images/{image_id}", headers=auth_headers(token))
    assert not cached.exists()


def test_listing_does_not_scale_its_queries_with_the_number_of_images(client, users, app):
    """The bug this replaces: three extra queries per image, so one flight of 300
    photos was ~900 queries for one page."""
    token = login(client, "t_admin")
    for n in range(4):
        _upload(client, token, users, name=f"many-{n}.jpg", seed=100 + n)

    from app.extensions import SessionLocal as S

    counts = []

    def count(conn, cursor, statement, params, context, executemany):
        counts.append(statement)

    bind = S().get_bind()
    event.listen(bind, "before_cursor_execute", count)
    try:
        counts.clear()
        body = client.get("/images?limit=50", headers=auth_headers(token)).get_json()
    finally:
        event.remove(bind, "before_cursor_execute", count)

    assert len(body["captures"]) >= 4
    # A fixed set of lookups for the page, not a multiple of the row count.
    # A fixed handful of queries for the whole page, whatever the row count. Before
    # this it was three per image on top of the listing: a 50-image page cost over 150.
    assert len(counts) < 15, f"{len(counts)} queries for {len(body['captures'])} images"


def test_listing_reports_the_total_so_truncation_is_visible(client, users):
    token = login(client, "t_admin")
    _upload(client, token, users, seed=204)
    body = client.get("/images?limit=1", headers=auth_headers(token)).get_json()
    assert len(body["captures"]) == 1
    assert body["total"] >= 1
    assert body["total"] >= body["count"]


def test_schema_errors_say_to_run_the_migrations(client, users, monkeypatch):
    """An unknown column means a migration has not been run. That used to reach the
    browser as 'Internal server error' with the reason only in the terminal."""
    from sqlalchemy.exc import OperationalError

    import app.api.images as images_api

    def boom(*_a, **_k):
        raise OperationalError("SELECT 1", {}, Exception(1054, "Unknown column 'x'"))

    monkeypatch.setattr(images_api, "visible_farm_ids", boom)
    resp = client.get("/images", headers=auth_headers(login(client, "t_admin")))
    assert resp.status_code == 503
    assert "run_migrations" in resp.get_json()["error"]
