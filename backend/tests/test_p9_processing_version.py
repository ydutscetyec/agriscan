"""p9: a result records which pipeline configuration produced it.

Adapted from PROMISE (pp. xviii, 21), where each result carries its rule version.
"""

from __future__ import annotations

import io
import itertools

import pymysql
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.extensions import SessionLocal
from app.models import Detection, ProcessingVersion
from app.services import processing_version as pv
from tests.conftest import auth_headers, login
from tests.factories import sharp_image
from tests.test_ingest import _drain_worker, production_models, taxonomy  # noqa: F401

_SEED = itertools.count(91000)


def _upload(client, token, field_id):
    return client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(240, next(_SEED))), "p9.jpg", "image/jpeg"),
            "field_id": str(field_id),
            "source": "phone",
        },
        content_type="multipart/form-data",
    )


def _latest_detection(session):
    return session.execute(select(Detection).order_by(Detection.id.desc())).scalars().first()


# --------------------------------------------------------------------- the snapshot


def test_same_configuration_gives_the_same_hash(cfg):
    a = pv.snapshot(cfg, 0.5, 0.1, "affected_area_proxy_v1")
    b = pv.snapshot(cfg, 0.5, 0.1, "affected_area_proxy_v1")
    assert pv.config_hash(a) == pv.config_hash(b)


def test_each_part_of_the_configuration_changes_the_hash(cfg):
    base = pv.config_hash(pv.snapshot(cfg, 0.5, 0.1, "affected_area_proxy_v1"))
    assert pv.config_hash(pv.snapshot(cfg, 0.6, 0.1, "affected_area_proxy_v1")) != base
    assert pv.config_hash(pv.snapshot(cfg, 0.5, 0.2, "affected_area_proxy_v1")) != base
    assert pv.config_hash(pv.snapshot(cfg, 0.5, 0.1, "affected_area_proxy_v2")) != base


def test_float_representation_cannot_split_equal_settings(cfg):
    a = pv.config_hash(pv.snapshot(cfg, 0.1 + 0.2, 0.1, "m"))
    b = pv.config_hash(pv.snapshot(cfg, 0.3, 0.1, "m"))
    assert a == b


def test_get_or_create_is_idempotent(cfg, users):
    session = SessionLocal()
    snap = pv.snapshot(cfg, 0.5, 0.1, "idempotency-check")
    first = pv.get_or_create(session, snap)
    second = pv.get_or_create(session, snap)
    session.commit()
    assert first == second
    count = session.execute(
        select(ProcessingVersion).where(ProcessingVersion.config_hash == pv.config_hash(snap))
    ).scalars().all()
    assert len(count) == 1


# ---------------------------------------------------------------- end to end


def test_every_new_detection_carries_a_processing_version(
    client, users, cfg, production_models
):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)

    session = SessionLocal()
    session.expire_all()
    det = _latest_detection(session)
    assert det is not None
    assert det.processing_version_id is not None


def test_a_changed_setting_produces_a_new_version_and_keeps_the_old(
    client, users, cfg, production_models
):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)
    session = SessionLocal()
    session.expire_all()
    before = _latest_detection(session)
    before_id, old_id = before.id, before.processing_version_id

    original = cfg.QG_CLIP_FRACTION_MAX
    cfg.QG_CLIP_FRACTION_MAX = original + 0.05
    try:
        _upload(client, tech, users["field_farm_a"].id)
        _drain_worker(cfg)
    finally:
        cfg.QG_CLIP_FRACTION_MAX = original

    session.expire_all()
    after = _latest_detection(session)
    assert after.processing_version_id != old_id
    # The earlier detection still points at the configuration it was made under.
    assert session.get(Detection, before_id).processing_version_id == old_id


def test_detection_payload_names_its_processing_version(
    client, users, cfg, production_models
):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)
    body = client.get(
        "/detections?include_demo=true&limit=1", headers=auth_headers(tech)
    ).get_json()
    proc = body["detections"][0]["processing_version"]
    assert proc is not None
    assert proc["pipeline_version"] == pv.PIPELINE_VERSION
    assert len(proc["config_hash"]) == 12


def test_the_stored_snapshot_can_be_read_back(client, users, cfg, production_models):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)
    session = SessionLocal()
    session.expire_all()
    det = _latest_detection(session)
    body = client.get(
        f"/models/processing-versions/{det.processing_version_id}", headers=auth_headers(tech)
    ).get_json()
    assert body["config"]["pipeline_version"] == pv.PIPELINE_VERSION
    assert "quality_gate" in body["config"]
    assert body["config"]["severity"]["method"]


# ------------------------------------------------------------------ immutability


def test_a_processing_version_cannot_be_edited_or_deleted(cfg, users):
    session = SessionLocal()
    vid = pv.get_or_create(session, pv.snapshot(cfg, 0.5, 0.1, "immutability-check"))
    session.commit()
    with pytest.raises(DBAPIError):
        session.execute(
            text("UPDATE processing_versions SET pipeline_version='x' WHERE id=:i"), {"i": vid}
        )
    session.rollback()
    with pytest.raises(DBAPIError):
        session.execute(text("DELETE FROM processing_versions WHERE id=:i"), {"i": vid})
    session.rollback()


def test_a_detections_processing_version_is_fixed_once_set(
    client, users, cfg, production_models
):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)
    session = SessionLocal()
    session.expire_all()
    det = _latest_detection(session)
    other = pv.get_or_create(session, pv.snapshot(cfg, 0.9, 0.9, "tamper-check"))
    session.commit()
    assert other != det.processing_version_id
    with pytest.raises(DBAPIError):
        session.execute(
            text("UPDATE detections SET processing_version_id=:p WHERE id=:d"),
            {"p": other, "d": det.id},
        )
    session.rollback()


def test_a_legacy_row_may_be_given_a_version_once(
    client, users, cfg, production_models
):
    """Rows written before migration 009 have no version; backfilling one is allowed once."""
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)
    session = SessionLocal()
    session.expire_all()
    template = _latest_detection(session)

    legacy = Detection(
        image_id=template.image_id,
        condition_id=template.condition_id,
        confidence=template.confidence,
        model_version_id=template.model_version_id,
        processing_version_id=None,
        status="ai_detected",
        is_demo=True,
    )
    session.add(legacy)
    session.commit()

    vid = pv.get_or_create(session, pv.snapshot(cfg, 0.5, 0.1, "backfill-check"))
    session.commit()
    session.execute(
        text("UPDATE detections SET processing_version_id=:p WHERE id=:d"),
        {"p": vid, "d": legacy.id},
    )
    session.commit()

    with pytest.raises(DBAPIError):
        session.execute(
            text("UPDATE detections SET processing_version_id=:p WHERE id=:d"),
            {"p": template.processing_version_id, "d": legacy.id},
        )
    session.rollback()


# ----------------------------------------------------------------------- access


def test_a_farmer_cannot_read_processing_versions(client, users):
    farmer = login(client, "t_farmer_a")
    resp = client.get("/models/processing-versions", headers=auth_headers(farmer))
    assert resp.status_code == 403

def test_the_detail_page_payload_names_its_processing_version(
    client, users, cfg, production_models
):
    """The detection page reads /detections/<id>, which builds its own payload."""
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)
    listed = client.get(
        "/detections?include_demo=true&limit=1", headers=auth_headers(tech)
    ).get_json()["detections"][0]
    detail = client.get(f"/detections/{listed['id']}", headers=auth_headers(tech)).get_json()
    assert detail["processing_version"]["pipeline_version"] == pv.PIPELINE_VERSION
    assert detail["processing_version"] == listed["processing_version"]
