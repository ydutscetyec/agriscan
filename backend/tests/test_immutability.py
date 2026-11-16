"""Rule 1: a detection is immutable once written.

These tests hit the database directly, not the API, because the guarantee must hold
even against a buggy service layer or a technician with a SQL client.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select, text

from app.extensions import SessionLocal
from app.models import Condition, Detection, Image, ModelVersion


@pytest.fixture()
def a_detection(app, users):
    session = SessionLocal()
    model = session.execute(
        select(ModelVersion).where(ModelVersion.name == "test-model")
    ).scalar_one_or_none()
    if model is None:
        model = ModelVersion(
            name="test-model", architecture="StubDetector",
            deployment_status="staged", capability_status="DEMO",
        )
        session.add(model)
        session.flush()

    cond = session.execute(
        select(Condition).where(Condition.code == "brown_spot")
    ).scalar_one_or_none()
    if cond is None:
        cond = Condition(
            code="brown_spot", common_name="Brown spot",
            category="fungal", tier=1,
        )
        session.add(cond)
        session.flush()

    other = session.execute(
        select(Condition).where(Condition.code == "healthy")
    ).scalar_one_or_none()
    if other is None:
        other = Condition(code="healthy", common_name="Healthy", category="healthy", tier=1)
        session.add(other)
        session.flush()

    img = session.execute(
        select(Image).where(Image.content_hash == "hash-immutability-test")
    ).scalar_one_or_none()
    if img is None:
        img = Image(
            uuid="11111111-1111-1111-1111-111111111111",
            field_id=users["field_farm_a"].id,
            source="phone",
            file_path="/tmp/test.jpg",
            content_hash="hash-immutability-test",
            gps_source="missing",
            captured_at=dt.datetime(2026, 9, 1, 10, 0, 0),
            uploaded_by=users["t_tech"].id,
            is_demo=True,
        )
        session.add(img)
        session.flush()

    det = Detection(
        image_id=img.id, condition_id=cond.id, confidence=0.9140,
        model_version_id=model.id, status="ai_detected",
        severity_method="bbox_area_fraction", is_demo=True,
    )
    session.add(det)
    session.commit()
    return {"detection": det, "other_condition": other}


def test_updating_condition_raises(a_detection):
    session = SessionLocal()
    det = a_detection["detection"]
    with pytest.raises(Exception) as exc:
        session.execute(
            text("UPDATE detections SET condition_id = :c WHERE id = :i"),
            {"c": a_detection["other_condition"].id, "i": det.id},
        )
        session.commit()
    assert "immutable" in str(exc.value).lower()
    session.rollback()


def test_updating_confidence_raises(a_detection):
    session = SessionLocal()
    with pytest.raises(Exception) as exc:
        session.execute(
            text("UPDATE detections SET confidence = 0.1 WHERE id = :i"),
            {"i": a_detection["detection"].id},
        )
        session.commit()
    assert "immutable" in str(exc.value).lower()
    session.rollback()


def test_updating_model_version_raises(a_detection):
    session = SessionLocal()
    with pytest.raises(Exception) as exc:
        session.execute(
            text("UPDATE detections SET model_version_id = 99999 WHERE id = :i"),
            {"i": a_detection["detection"].id},
        )
        session.commit()
    assert "immutable" in str(exc.value).lower()
    session.rollback()


def test_status_may_still_change(a_detection):
    """Verification changes status, not the diagnosis. This must NOT raise."""
    session = SessionLocal()
    session.execute(
        text("UPDATE detections SET status = 'technician_verified' WHERE id = :i"),
        {"i": a_detection["detection"].id},
    )
    session.commit()
    row = session.execute(
        text("SELECT status FROM detections WHERE id = :i"),
        {"i": a_detection["detection"].id},
    ).scalar_one()
    assert row == "technician_verified"


def test_audit_log_is_append_only(app, users):
    session = SessionLocal()
    session.execute(
        text("INSERT INTO audit_log (user_id, action) VALUES (:u, 'test_action')"),
        {"u": users["t_admin"].id},
    )
    session.commit()
    row_id = session.execute(
        text("SELECT id FROM audit_log WHERE action = 'test_action' LIMIT 1")
    ).scalar_one()

    with pytest.raises(Exception):
        session.execute(
            text("UPDATE audit_log SET action = 'tampered' WHERE id = :i"), {"i": row_id}
        )
        session.commit()
    session.rollback()

    with pytest.raises(Exception):
        session.execute(text("DELETE FROM audit_log WHERE id = :i"), {"i": row_id})
        session.commit()
    session.rollback()
