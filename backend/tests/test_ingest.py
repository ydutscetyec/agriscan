"""Upload path, duplicates, and the worker pipeline end to end."""

from __future__ import annotations

import io
import json

import pytest
from sqlalchemy import select, text

from app.extensions import SessionLocal
from app.models import Condition, Detection, Image, ModelVersion
from tests.conftest import auth_headers, login
from tests.factories import blurred_image, sharp_image


def _upload(client, token, data, field_id, filename="shot.jpg", source="phone",
            mimetype="image/jpeg"):
    return client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(data), filename, mimetype),
            "field_id": str(field_id),
            "source": source,
        },
        content_type="multipart/form-data",
    )


@pytest.fixture()
def taxonomy(app):
    """Tier 1 rows the worker needs, with aerial_allowed set as migration 003 does."""
    session = SessionLocal()
    wanted = [
        ("unknown", "Unknown", "unknown", False),
        ("brown_spot", "Brown spot", "fungal", False),
        ("hopperburn", "Hopperburn", "pest", False),
        ("lodging", "Lodging", "physical", True),
        ("anomaly_zone", "Anomalous zone", "unknown", True),
    ]
    for code, name, cat, aerial in wanted:
        row = session.execute(
            select(Condition).where(Condition.code == code)
        ).scalar_one_or_none()
        if row is None:
            session.add(Condition(code=code, common_name=name, category=cat,
                                  tier=1, aerial_allowed=aerial))
        else:
            row.aerial_allowed = aerial
    session.commit()
    return True


@pytest.fixture()
def production_models(app, taxonomy):
    session = SessionLocal()
    for name, mode in [("TEST-GROUND-v1", "ground"), ("TEST-AERIAL-v1", "aerial")]:
        row = session.execute(
            select(ModelVersion).where(ModelVersion.name == name)
        ).scalar_one_or_none()
        if row is None:
            session.add(ModelVersion(
                name=name, architecture="StubDetector", imaging_mode=mode,
                deployment_status="production", capability_status="DEMO",
            ))
        else:
            row.deployment_status = "production"
    session.commit()
    return True


# ------------------------------------------------------------------ upload endpoint


def test_upload_returns_202_and_job(client, users, taxonomy):
    token = login(client, "t_tech")
    resp = _upload(client, token, sharp_image(), users["field_farm_a"].id)
    assert resp.status_code == 202
    body = resp.get_json()
    assert body["job_id"] is not None
    assert body["duplicate"] is False
    assert body["message"] == "Inference queued."


def test_duplicate_upload_returns_same_id_and_no_second_row(client, users, taxonomy):
    token = login(client, "t_tech")
    data = sharp_image(size=200)
    first = _upload(client, token, data, users["field_farm_a"].id)
    assert first.status_code == 202
    image_id = first.get_json()["image_id"]

    second = _upload(client, token, data, users["field_farm_a"].id, filename="other.jpg")
    assert second.status_code == 200
    assert second.get_json()["image_id"] == image_id
    assert second.get_json()["duplicate"] is True
    assert second.get_json()["message"] == "Image already exists."

    session = SessionLocal()
    count = session.execute(
        text("SELECT COUNT(*) FROM images WHERE id = :i"), {"i": image_id}
    ).scalar_one()
    assert count == 1


def test_missing_gps_is_accepted_and_flagged(client, users, taxonomy):
    token = login(client, "t_tech")
    resp = _upload(client, token, sharp_image(size=180), users["field_farm_a"].id)
    body = resp.get_json()
    assert body["gps_source"] == "missing"
    assert body["gps_note"] == "Position missing."


def test_disallowed_extension_rejected(client, users, taxonomy):
    token = login(client, "t_tech")
    resp = _upload(client, token, b"MZ\x00\x00", users["field_farm_a"].id,
                   filename="payload.exe", mimetype="application/octet-stream")
    assert resp.status_code == 415


def test_corrupt_jpeg_rejected(client, users, taxonomy):
    token = login(client, "t_tech")
    resp = _upload(client, token, b"\xff\xd8\xff\xe0broken-tail",
                   users["field_farm_a"].id)
    assert resp.status_code == 400


def test_farmer_cannot_upload_to_another_farm(client, users, taxonomy):
    token = login(client, "t_farmer_a")
    resp = _upload(client, token, sharp_image(size=150), users["field_farm_b"].id)
    assert resp.status_code == 403


# ------------------------------------------------------------------------- worker


def _drain_worker(cfg, max_jobs: int = 50) -> int:
    """Process every queued job.

    The worker deliberately claims the OLDEST queued job, so a test that ran one
    iteration would process a previous test's image. Draining is the correct harness,
    and it also exercises the claim loop the way the real process does.
    """
    from worker.run import run_once

    session = SessionLocal()
    processed = 0
    while processed < max_jobs and run_once(session, cfg, "test-worker"):
        processed += 1
    return processed


def test_worker_refuses_without_production_model(client, users, taxonomy, cfg):
    """No production model must stop the worker, not produce an untraceable detection."""
    from worker.run import NoProductionModel, production_model

    session = SessionLocal()
    session.execute(text("UPDATE model_versions SET deployment_status='staged'"))
    session.commit()
    with pytest.raises(NoProductionModel) as exc:
        production_model(session, "ground")
    assert "MODEL_NOT_AVAILABLE" in str(exc.value)


def test_end_to_end_detection_has_full_provenance(client, users, cfg, production_models):
    token = login(client, "t_tech")
    resp = _upload(client, token, sharp_image(size=224), users["field_farm_a"].id)
    image_id = resp.get_json()["image_id"]

    assert _drain_worker(cfg) >= 1

    body = client.get(f"/images/{image_id}", headers=auth_headers(token)).get_json()
    assert body["quality_flag"] == "ok"
    assert len(body["detections"]) >= 1
    det = body["detections"][0]
    assert det["model_version"] == "TEST-GROUND-v1"
    assert det["confidence"] is not None
    assert "model confidence" in det["confidence_label"]
    assert det["verification_status"] == "ai_detected"
    assert det["severity_method"] == "bbox_area_fraction"
    assert det["severity_status"] == "EXPERIMENTAL"


def test_blurred_image_produces_no_detection(client, users, cfg, production_models):
    token = login(client, "t_tech")
    resp = _upload(client, token, blurred_image(size=240), users["field_farm_a"].id)
    image_id = resp.get_json()["image_id"]

    assert _drain_worker(cfg) >= 1

    body = client.get(f"/images/{image_id}", headers=auth_headers(token)).get_json()
    assert body["quality_flag"] == "blurred"
    assert body["detections"] == []
    assert body["job"]["status"] == "COMPLETED"


def test_drone_image_cannot_get_fine_grained_label(client, users, cfg, production_models,
                                                   monkeypatch):
    """A 15-30 m RGB frame may not claim a lesion-level disease."""
    monkeypatch.setenv(
        "AGRISCAN_STUB_DETECTOR_RESULT",
        json.dumps([{"condition_code": "brown_spot", "confidence": 0.95,
                     "bbox": [0, 0, 60, 60]}]),
    )
    from app.config import get_config

    drone_cfg = get_config()

    token = login(client, "t_tech")
    resp = _upload(client, token, sharp_image(size=210), users["field_farm_a"].id,
                   source="drone")
    image_id = resp.get_json()["image_id"]

    assert _drain_worker(drone_cfg) >= 1

    session = SessionLocal()
    dets = session.execute(
        select(Detection).where(Detection.image_id == image_id)
    ).scalars().all()
    codes = set()
    for d in dets:
        cond = session.get(Condition, d.condition_id) if d.condition_id else None
        codes.add(cond.code if cond else None)
    assert "brown_spot" not in codes
    assert codes <= {"unknown", None}


def test_low_confidence_writes_unknown(client, users, cfg, production_models, monkeypatch):
    monkeypatch.setenv(
        "AGRISCAN_STUB_DETECTOR_RESULT",
        json.dumps([{"condition_code": "brown_spot", "confidence": 0.21,
                     "bbox": [0, 0, 40, 40]}]),
    )
    from app.config import get_config

    low_cfg = get_config()

    token = login(client, "t_tech")
    resp = _upload(client, token, sharp_image(size=205), users["field_farm_a"].id)
    image_id = resp.get_json()["image_id"]

    assert _drain_worker(low_cfg) >= 1

    session = SessionLocal()
    det = session.execute(
        select(Detection).where(Detection.image_id == image_id)
    ).scalars().first()
    assert det is not None
    assert det.status == "low_confidence"
    cond = session.get(Condition, det.condition_id)
    assert cond.code == "unknown"


def test_detections_filtering(client, users, cfg, production_models):
    token = login(client, "t_tech")
    resp = _upload(client, token, sharp_image(size=232), users["field_farm_a"].id)
    _drain_worker(cfg)

    url = f"/detections?field_id={users['field_farm_a'].id}&include_demo=true&min_confidence=0.1"
    body = client.get(url, headers=auth_headers(token)).get_json()
    assert body["count"] >= 1
    for det in body["detections"]:
        assert det["field_id"] == users["field_farm_a"].id
        assert "model_version" in det and "verification_status" in det


def test_farmer_detections_are_scoped(client, users, cfg, production_models):
    tech = login(client, "t_tech")
    _upload(client, tech, sharp_image(size=198), users["field_farm_b"].id)
    _drain_worker(cfg)

    farmer_a = login(client, "t_farmer_a")
    body = client.get("/detections?include_demo=true",
                      headers=auth_headers(farmer_a)).get_json()
    for det in body["detections"]:
        assert det["field_id"] == users["field_farm_a"].id
