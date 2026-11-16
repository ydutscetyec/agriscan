"""Endpoints the dashboard depends on (Prompt 3)."""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from app.extensions import SessionLocal
from app.models import Detection, Image, ModelVersion
from tests.conftest import auth_headers, login
from tests.factories import sharp_image
from tests.test_ingest import _drain_worker, production_models, taxonomy  # noqa: F401


@pytest.fixture()
def a_processed_detection(client, users, cfg, production_models):
    token = login(client, "t_tech")
    resp = client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(220)), "d.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": "phone",
        },
        content_type="multipart/form-data",
    )
    _drain_worker(cfg)
    image_id = resp.get_json()["image_id"]
    session = SessionLocal()
    det = session.execute(
        select(Detection).where(Detection.image_id == image_id)
    ).scalars().first()
    return {"token": token, "image_id": image_id, "detection": det}


def test_detection_detail_carries_full_provenance(client, a_processed_detection):
    det = a_processed_detection["detection"]
    body = client.get(
        f"/detections/{det.id}", headers=auth_headers(a_processed_detection["token"])
    ).get_json()
    for key in ("model_version", "verification_status", "severity_method", "confidence_label"):
        assert key in body
    assert "model confidence" in body["confidence_label"]
    assert body["severity_status"] == "EXPERIMENTAL"
    assert body["growth_stage"]["rule_version"]


def test_detection_detail_reports_no_review_honestly(client, a_processed_detection):
    body = client.get(
        f"/detections/{a_processed_detection['detection'].id}",
        headers=auth_headers(a_processed_detection["token"]),
    ).get_json()
    assert body["verifications"] == []
    assert body["farmer_feedback"] == []


def test_farmer_cannot_open_another_farms_detection(client, users, a_processed_detection):
    other = login(client, "t_farmer_b")
    resp = client.get(
        f"/detections/{a_processed_detection['detection'].id}", headers=auth_headers(other)
    )
    assert resp.status_code == 403


def test_image_file_requires_auth(client, a_processed_detection):
    assert client.get(f"/images/{a_processed_detection['image_id']}/file").status_code == 401


def test_image_file_served_to_owner(client, a_processed_detection):
    resp = client.get(
        f"/images/{a_processed_detection['image_id']}/file",
        headers=auth_headers(a_processed_detection["token"]),
    )
    assert resp.status_code == 200
    assert resp.mimetype == "image/jpeg"


def test_image_file_blocked_for_other_farm(client, users, a_processed_detection):
    other = login(client, "t_farmer_b")
    resp = client.get(
        f"/images/{a_processed_detection['image_id']}/file", headers=auth_headers(other)
    )
    assert resp.status_code == 403


def test_models_registry_readable(client, users, production_models):
    token = login(client, "t_tech")
    body = client.get("/models", headers=auth_headers(token)).get_json()
    assert any(m["name"] == "TEST-GROUND-v1" for m in body)
    for model in body:
        assert "capability_status" in model and "deployment_status" in model


def test_farmers_list_excludes_non_farmers(client, users):
    token = login(client, "t_tech")
    body = client.get("/people/farmers", headers=auth_headers(token)).get_json()
    names = {u["name"] for u in body}
    assert "t_farmer_a" in names
    assert "t_admin" not in names


def test_farmer_cannot_list_farmers(client, users):
    token = login(client, "t_farmer_a")
    assert client.get("/people/farmers", headers=auth_headers(token)).status_code == 403


def test_bbox_filter_excludes_outside_points(client, users, cfg, a_processed_detection):
    """The map asks only for its viewport; a detection outside it must not come back."""
    session = SessionLocal()
    image = session.get(Image, a_processed_detection["image_id"])
    image.lat, image.lon = 6.3711, 124.7461
    image.gps_source = "manual"
    session.commit()

    token = a_processed_detection["token"]
    inside = client.get(
        "/detections?include_demo=true&min_lat=6.3&max_lat=6.4&min_lon=124.7&max_lon=124.8",
        headers=auth_headers(token),
    ).get_json()
    assert any(d["image_id"] == image.id for d in inside["detections"])

    outside = client.get(
        "/detections?include_demo=true&min_lat=10.0&max_lat=11.0&min_lon=120.0&max_lon=121.0",
        headers=auth_headers(token),
    ).get_json()
    assert all(d["image_id"] != image.id for d in outside["detections"])
