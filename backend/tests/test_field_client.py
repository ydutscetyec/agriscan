"""Field client server contract (Prompt 5): idempotent retries and ownership scoping."""

from __future__ import annotations

import io
import itertools

import pytest
from sqlalchemy import select, text

from app.extensions import SessionLocal
from app.models import Image
from tests.conftest import auth_headers, login
from tests.factories import sharp_image
from tests.test_ingest import _drain_worker, production_models, taxonomy  # noqa: F401

_SEED = itertools.count(20000)


def _upload(client, token, field_id, *, client_uuid=None, data=None, seed=None):
    payload = {
        "file": (
            io.BytesIO(data if data is not None else sharp_image(240, seed or next(_SEED))),
            "capture.jpg",
            "image/jpeg",
        ),
        "field_id": str(field_id),
        "source": "phone",
    }
    if client_uuid:
        payload["client_uuid"] = client_uuid
    return client.post(
        "/images", headers=auth_headers(token), data=payload,
        content_type="multipart/form-data",
    )


def test_retry_with_same_client_uuid_creates_one_record(client, users, taxonomy):
    """The offline queue resends after a dropped connection. One photo, one row."""
    token = login(client, "t_tech")
    uid = "11111111-2222-4333-8444-555555555555"
    payload = sharp_image(240, next(_SEED))

    first = _upload(client, token, users["field_farm_a"].id, client_uuid=uid, data=payload)
    assert first.status_code == 202
    image_id = first.get_json()["image_id"]

    second = _upload(client, token, users["field_farm_a"].id, client_uuid=uid, data=payload)
    assert second.status_code == 200
    assert second.get_json()["image_id"] == image_id
    assert second.get_json()["duplicate"] is True

    session = SessionLocal()
    count = session.execute(
        text("SELECT COUNT(*) FROM images WHERE client_uuid = :u"), {"u": uid}
    ).scalar_one()
    assert count == 1


def test_retry_dedupes_even_if_bytes_were_reencoded(client, users, taxonomy):
    """A re-encoded retry has a different hash; the client uuid still catches it."""
    token = login(client, "t_tech")
    uid = "99999999-2222-4333-8444-555555555555"

    first = _upload(client, token, users["field_farm_a"].id, client_uuid=uid,
                    data=sharp_image(240, 31337))
    assert first.status_code == 202

    second = _upload(client, token, users["field_farm_a"].id, client_uuid=uid,
                     data=sharp_image(200, 4242))  # genuinely different bytes
    assert second.status_code == 200
    assert second.get_json()["image_id"] == first.get_json()["image_id"]


def test_three_queued_captures_upload_once_each(client, users, taxonomy):
    token = login(client, "t_tech")
    uids = [f"aaaaaaaa-0000-4000-8000-00000000000{i}" for i in (1, 2, 3)]
    payloads = [sharp_image(240, next(_SEED)) for _ in uids]

    ids = []
    for uid, payload in zip(uids, payloads):
        resp = _upload(client, token, users["field_farm_a"].id, client_uuid=uid, data=payload)
        assert resp.status_code == 202
        ids.append(resp.get_json()["image_id"])

    # The queue retries all three after a flaky connection.
    for uid, payload in zip(uids, payloads):
        resp = _upload(client, token, users["field_farm_a"].id, client_uuid=uid, data=payload)
        assert resp.status_code == 200

    assert len(set(ids)) == 3
    session = SessionLocal()
    count = session.execute(
        text("SELECT COUNT(*) FROM images WHERE client_uuid IN (:a,:b,:c)"),
        {"a": uids[0], "b": uids[1], "c": uids[2]},
    ).scalar_one()
    assert count == 3


def test_upload_without_client_uuid_still_works(client, users, taxonomy):
    token = login(client, "t_tech")
    resp = _upload(client, token, users["field_farm_a"].id)
    assert resp.status_code == 202
    assert resp.get_json()["client_uuid"] is None


def test_my_captures_lists_own_uploads(client, users, cfg, production_models):
    token = login(client, "t_tech")
    _upload(client, token, users["field_farm_a"].id)
    _drain_worker(cfg)
    body = client.get("/images?mine=true", headers=auth_headers(token)).get_json()
    assert body["count"] >= 1
    for capture in body["captures"]:
        assert "job_status" in capture
        if capture["detection"]:
            assert "model confidence" in capture["detection"]["confidence_label"]


def test_capture_with_no_detection_still_appears(client, users, taxonomy):
    """A farmer who just uploaded must see the photo arrived, not an empty list."""
    token = login(client, "t_tech")
    resp = _upload(client, token, users["field_farm_a"].id)
    image_id = resp.get_json()["image_id"]
    body = client.get("/images?mine=true", headers=auth_headers(token)).get_json()
    entry = next(c for c in body["captures"] if c["image_id"] == image_id)
    assert entry["detection"] is None
    assert entry["job_status"] in ("QUEUED", "RUNNING", "RETRYING", None)


def test_farmer_cannot_see_another_farms_captures(client, users, cfg, production_models):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_b"].id)
    _drain_worker(cfg)

    farmer_a = login(client, "t_farmer_a")
    body = client.get("/images", headers=auth_headers(farmer_a)).get_json()
    for capture in body["captures"]:
        assert capture["field_id"] == users["field_farm_a"].id


def test_farmer_cannot_upload_to_another_farm(client, users, taxonomy):
    farmer = login(client, "t_farmer_a")
    resp = _upload(client, farmer, users["field_farm_b"].id)
    assert resp.status_code == 403
