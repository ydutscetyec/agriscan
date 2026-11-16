"""Verification workflow and recommendation engine (Prompt 4)."""

from __future__ import annotations

import io
import itertools

import pytest
from sqlalchemy import select, text

from app.extensions import SessionLocal
from app.models import Condition, Detection, KnowledgeBase, Recommendation, Verification
from app.services.recommendations import FALLBACK, severity_band, validate_output
from tests.conftest import auth_headers, login
from tests.factories import sharp_image
from tests.test_ingest import _drain_worker, production_models, taxonomy  # noqa: F401


_SEED = itertools.count(9000)


def _make_detection(client, users, cfg, source="phone", size=226):
    """Each call uploads genuinely distinct bytes; identical bytes would dedupe."""
    token = login(client, "t_tech")
    seed = next(_SEED)
    resp = client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(size, seed)), "v.jpg", "image/jpeg"),
            "field_id": str(users["field_farm_a"].id),
            "source": source,
        },
        content_type="multipart/form-data",
    )
    _drain_worker(cfg)
    session = SessionLocal()
    det = session.execute(
        select(Detection).where(Detection.image_id == resp.get_json()["image_id"])
    ).scalars().first()
    return det


@pytest.fixture()
def detection(client, users, cfg, production_models):
    return _make_detection(client, users, cfg)


def _snapshot(detection_id: int) -> dict:
    """Every column of a detection except status, which is workflow state."""
    session = SessionLocal()
    row = session.execute(
        text(
            "SELECT id, image_id, condition_id, confidence, bbox, severity_value, "
            "severity_method, model_version_id, is_demo, created_at "
            "FROM detections WHERE id = :i"
        ),
        {"i": detection_id},
    ).fetchone()
    return dict(row._mapping)


# --------------------------------------------------------------------- farmer feedback


def test_farmer_feedback_cannot_change_the_condition(client, users, detection):
    before = _snapshot(detection.id)
    farmer = login(client, "t_farmer_a")
    resp = client.post(
        f"/detections/{detection.id}/feedback",
        headers=auth_headers(farmer),
        json={"agrees": True, "comment": "Looks right to me"},
    )
    assert resp.status_code == 201
    after = _snapshot(detection.id)
    assert before["condition_id"] == after["condition_id"]
    assert before["confidence"] == after["confidence"]


def test_farmer_agreement_sets_farmer_confirmed_only(client, users, detection):
    farmer = login(client, "t_farmer_a")
    body = client.post(
        f"/detections/{detection.id}/feedback",
        headers=auth_headers(farmer),
        json={"agrees": True},
    ).get_json()
    assert body["status"] == "farmer_confirmed"
    assert body["status"] != "technician_verified"


def test_farmer_disagreement_does_not_change_status(client, users, detection):
    farmer = login(client, "t_farmer_a")
    body = client.post(
        f"/detections/{detection.id}/feedback",
        headers=auth_headers(farmer),
        json={"agrees": False, "comment": "I think this is something else"},
    ).get_json()
    assert body["status"] == "ai_detected"


def test_farmer_feedback_produces_no_verification_row(client, users, detection):
    farmer = login(client, "t_farmer_a")
    client.post(
        f"/detections/{detection.id}/feedback",
        headers=auth_headers(farmer),
        json={"agrees": True},
    )
    session = SessionLocal()
    rows = session.execute(
        select(Verification).where(Verification.detection_id == detection.id)
    ).scalars().all()
    assert rows == []


# ----------------------------------------------------------------------- verification


def test_corrected_verification_leaves_diagnosis_untouched(client, users, detection):
    """Everything except workflow status must survive a correction byte for byte."""
    before = _snapshot(detection.id)
    tech = login(client, "t_tech")
    resp = client.post(
        f"/detections/{detection.id}/verify",
        headers=auth_headers(tech),
        json={
            "decision": "corrected",
            "corrected_condition": "hopperburn",
            "severity_score": 2,
            "notes": "Planthopper damage, not brown spot",
        },
    )
    assert resp.status_code == 201
    after = _snapshot(detection.id)
    assert before == after, "the detection's diagnosis fields must not change"

    session = SessionLocal()
    ver = session.execute(
        select(Verification).where(Verification.detection_id == detection.id)
    ).scalars().one()
    corrected = session.get(Condition, ver.corrected_condition_id)
    assert corrected.code == "hopperburn"
    assert ver.severity_score == 2


def test_verification_requires_technician_role(client, users, detection):
    farmer = login(client, "t_farmer_a")
    resp = client.post(
        f"/detections/{detection.id}/verify",
        headers=auth_headers(farmer),
        json={"decision": "correct"},
    )
    assert resp.status_code == 403


def test_correction_requires_a_condition(client, users, detection):
    tech = login(client, "t_tech")
    resp = client.post(
        f"/detections/{detection.id}/verify",
        headers=auth_headers(tech),
        json={"decision": "corrected"},
    )
    assert resp.status_code == 400


def test_severity_score_is_bounded(client, users, detection):
    tech = login(client, "t_tech")
    resp = client.post(
        f"/detections/{detection.id}/verify",
        headers=auth_headers(tech),
        json={"decision": "correct", "severity_score": 9},
    )
    assert resp.status_code == 400


def test_verify_writes_an_audit_row(client, users, detection):
    tech = login(client, "t_tech")
    client.post(
        f"/detections/{detection.id}/verify",
        headers=auth_headers(tech),
        json={"decision": "correct"},
    )
    session = SessionLocal()
    count = session.execute(
        text(
            "SELECT COUNT(*) FROM audit_log WHERE action='verify_detection' "
            "AND object_id = :i"
        ),
        {"i": str(detection.id)},
    ).scalar_one()
    assert count == 1


# ----------------------------------------------------------------------------- queue


def test_queue_labels_the_reason_for_each_item(client, users, cfg, production_models):
    _make_detection(client, users, cfg, size=231)
    tech = login(client, "t_tech")
    body = client.get("/verification-queue", headers=auth_headers(tech)).get_json()
    assert body["count"] >= 1
    for item in body["items"]:
        assert item["queue_reason"] in (
            "low_confidence", "high_severity", "farmer_rejected", "confidence_sample"
        )
        assert item["queue_reason_label"]
        # The invariant is that a confidence is never a bare number. A detection with
        # no confidence at all (the no-detections path) legitimately reads NOT_AVAILABLE.
        label = item["confidence_label"]
        assert "model confidence" in label or label == "NOT_AVAILABLE"


def test_queue_excludes_already_verified(client, users, cfg, production_models):
    det = _make_detection(client, users, cfg, size=233)
    tech = login(client, "t_tech")
    client.post(
        f"/detections/{det.id}/verify", headers=auth_headers(tech),
        json={"decision": "correct"},
    )
    body = client.get("/verification-queue", headers=auth_headers(tech)).get_json()
    assert all(item["detection_id"] != det.id for item in body["items"])


def test_queue_sample_rate_is_configurable(client, users, cfg, production_models):
    tech = login(client, "t_tech")
    body = client.get(
        "/verification-queue?sample_rate=0.5", headers=auth_headers(tech)
    ).get_json()
    assert body["sample_rate"] == 0.5


def test_farmer_cannot_see_the_queue(client, users):
    farmer = login(client, "t_farmer_a")
    assert client.get("/verification-queue", headers=auth_headers(farmer)).status_code == 403


# ------------------------------------------------------------------ confusion matrix


def test_confusion_matrix_matches_a_hand_computed_fixture(
    client, users, cfg, production_models
):
    """Three verifications, known by hand: 2 correct brown_spot, 1 corrected to hopperburn."""
    tech = login(client, "t_tech")
    dets = [_make_detection(client, users, cfg, size=s) for s in (240, 241, 242)]

    client.post(f"/detections/{dets[0].id}/verify", headers=auth_headers(tech),
                json={"decision": "correct"})
    client.post(f"/detections/{dets[1].id}/verify", headers=auth_headers(tech),
                json={"decision": "correct"})
    client.post(f"/detections/{dets[2].id}/verify", headers=auth_headers(tech),
                json={"decision": "corrected", "corrected_condition": "hopperburn"})

    body = client.get(
        "/analysis/confusion-matrix?include_demo=true", headers=auth_headers(tech)
    ).get_json()
    matrix = body["matrix"]

    assert matrix["brown_spot"]["brown_spot"] >= 2
    assert matrix["brown_spot"]["hopperburn"] >= 1
    assert body["verified_pairs"] >= 3


def test_confusion_matrix_is_a_query_not_a_table(client, users, cfg, production_models):
    """Deleting the verifications must empty the matrix; nothing is cached."""
    tech = login(client, "t_tech")
    det = _make_detection(client, users, cfg, size=243)
    client.post(f"/detections/{det.id}/verify", headers=auth_headers(tech),
                json={"decision": "correct"})

    before = client.get(
        "/analysis/confusion-matrix?include_demo=true", headers=auth_headers(tech)
    ).get_json()
    assert before["verified_pairs"] >= 1

    session = SessionLocal()
    session.execute(text("DELETE FROM verifications"))
    session.commit()

    after = client.get(
        "/analysis/confusion-matrix?include_demo=true", headers=auth_headers(tech)
    ).get_json()
    assert after["verified_pairs"] == 0
    assert after["matrix"] == {}


def test_agreement_endpoint_reports_both_rates(client, users, cfg, production_models):
    tech = login(client, "t_tech")
    farmer = login(client, "t_farmer_a")
    det = _make_detection(client, users, cfg, size=244)
    client.post(f"/detections/{det.id}/feedback", headers=auth_headers(farmer),
                json={"agrees": True})
    client.post(f"/detections/{det.id}/verify", headers=auth_headers(tech),
                json={"decision": "correct"})

    body = client.get("/analysis/agreement", headers=auth_headers(tech)).get_json()
    assert "model_vs_technician" in body
    assert "farmer_vs_technician" in body


# -------------------------------------------------------------------- recommendations


@pytest.fixture()
def knowledge(app):
    session = SessionLocal()
    cond = session.execute(
        select(Condition).where(Condition.code == "brown_spot")
    ).scalar_one()
    row = session.execute(
        select(KnowledgeBase).where(KnowledgeBase.condition_id == cond.id)
    ).scalar_one_or_none()
    if row is None:
        session.add(
            KnowledgeBase(
                condition_id=cond.id,
                identification_cues="Oval brown lesions on the leaf blade.",
                cultural_measures="Improve drainage and keep the crop evenly fertilised.",
                preventive_measures="Use clean seed and avoid water stress.",
                monitoring_guidance="Check ten hills per corner of the field weekly.",
                when_to_call="Call a technician if lesions spread to the flag leaf.",
                content_status="REVIEWED",
            )
        )
        session.commit()
    return True


def _verified_detection(client, users, cfg):
    det = _make_detection(client, users, cfg, size=250)
    tech = login(client, "t_tech")
    client.post(f"/detections/{det.id}/verify", headers=auth_headers(tech),
                json={"decision": "correct"})
    return det


def test_generate_refuses_unverified_detection(client, users, cfg, production_models):
    det = _make_detection(client, users, cfg, size=251)
    tech = login(client, "t_tech")
    resp = client.post(
        f"/recommendations/{det.id}/generate", headers=auth_headers(tech)
    )
    assert resp.status_code == 409


def test_generated_recommendation_starts_pending(client, users, cfg, production_models, knowledge):
    det = _verified_detection(client, users, cfg)
    tech = login(client, "t_tech")
    body = client.post(
        f"/recommendations/{det.id}/generate", headers=auth_headers(tech)
    ).get_json()
    assert body["status"] == "pending"
    assert body["approved"] is False


def test_unapproved_recommendation_is_invisible_to_farmer(
    client, users, cfg, production_models, knowledge
):
    det = _verified_detection(client, users, cfg)
    tech = login(client, "t_tech")
    client.post(f"/recommendations/{det.id}/generate", headers=auth_headers(tech))

    farmer = login(client, "t_farmer_a")
    body = client.get(
        f"/recommendations/{det.id}", headers=auth_headers(farmer)
    ).get_json()
    for rec in body["recommendations"]:
        assert rec["text"] is None
        assert rec["message"] == "Pending technician review."


def test_approved_recommendation_becomes_visible(client, users, cfg, production_models, knowledge):
    det = _verified_detection(client, users, cfg)
    tech = login(client, "t_tech")
    rec = client.post(
        f"/recommendations/{det.id}/generate", headers=auth_headers(tech)
    ).get_json()
    client.post(f"/recommendations/{rec['id']}/approve", headers=auth_headers(tech))

    farmer = login(client, "t_farmer_a")
    body = client.get(
        f"/recommendations/{det.id}", headers=auth_headers(farmer)
    ).get_json()
    assert body["recommendations"][0]["text"]
    assert body["recommendations"][0]["approved"] is True


def test_no_knowledge_base_match_returns_exact_fallback(
    client, users, cfg, production_models
):
    session = SessionLocal()
    session.execute(text("DELETE FROM recommendations"))
    session.execute(text("DELETE FROM knowledge_base"))
    session.commit()

    det = _verified_detection(client, users, cfg)
    tech = login(client, "t_tech")
    body = client.post(
        f"/recommendations/{det.id}/generate", headers=auth_headers(tech)
    ).get_json()
    assert body["text"] == FALLBACK
    assert body["knowledge_base_matched"] is False


def test_approve_writes_audit_row(client, users, cfg, production_models, knowledge):
    det = _verified_detection(client, users, cfg)
    tech = login(client, "t_tech")
    rec = client.post(
        f"/recommendations/{det.id}/generate", headers=auth_headers(tech)
    ).get_json()
    client.post(f"/recommendations/{rec['id']}/approve", headers=auth_headers(tech))

    session = SessionLocal()
    count = session.execute(
        text("SELECT COUNT(*) FROM audit_log WHERE action='recommendation_approved'")
    ).scalar_one()
    assert count >= 1


def test_farmer_cannot_approve(client, users, cfg, production_models, knowledge):
    det = _verified_detection(client, users, cfg)
    tech = login(client, "t_tech")
    rec = client.post(
        f"/recommendations/{det.id}/generate", headers=auth_headers(tech)
    ).get_json()
    farmer = login(client, "t_farmer_a")
    resp = client.post(f"/recommendations/{rec['id']}/approve", headers=auth_headers(farmer))
    assert resp.status_code == 403


# ------------------------------------------------------------------------- validator


def test_validator_rejects_ungrounded_dosage():
    ok, problems = validate_output(
        "Spray 250 ml per hectare every 7 days.", "Improve drainage."
    )
    assert ok is False
    assert problems


def test_validator_rejects_ungrounded_product_name():
    ok, problems = validate_output(
        "Apply mancozeb to the affected area.", "Improve drainage and use clean seed."
    )
    assert ok is False


def test_validator_allows_text_present_in_sources():
    source = "Apply mancozeb 250 ml per hectare as directed by your technician."
    ok, problems = validate_output("Apply mancozeb 250 ml per hectare.", source)
    assert ok is True, problems


def test_validator_allows_plain_cultural_advice():
    ok, _ = validate_output(
        "Improve drainage and keep the crop evenly fertilised.",
        "Improve drainage and keep the crop evenly fertilised.",
    )
    assert ok is True


def test_severity_bands():
    assert severity_band(None) == "not_measured"
    assert severity_band(0.0) == "none"
    assert severity_band(5.0) == "mild"
    assert severity_band(18.7) == "moderate"
    assert severity_band(55.0) == "severe"
