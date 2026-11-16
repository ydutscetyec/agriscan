"""p37: one unprocessable photo must not take the worker down with it.

A drone image with no 'aerial' model registered killed the whole worker on the first job,
so every queued phone photo stopped being analysed too — and the only clue was one line
in a terminal.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from sqlalchemy import select, text

from app.config import get_config
from app.extensions import SessionLocal
from app.models import Field, Image, ModelVersion, User
from worker.run import NoProductionModel, production_model, run_once


@pytest.fixture()
def only_ground(app):
    """A database with a production ground model and no aerial one."""
    session = SessionLocal()
    retired = []
    for row in session.execute(
        select(ModelVersion)
        .where(ModelVersion.deployment_status == "production")
        .where(ModelVersion.imaging_mode == "aerial")
    ).scalars():
        row.deployment_status = "retired"
        retired.append(row.id)
    ground = session.execute(
        select(ModelVersion)
        .where(ModelVersion.deployment_status == "production")
        .where(ModelVersion.imaging_mode == "ground")
    ).scalars().first()
    if ground is None:
        ground = ModelVersion(
            name=f"test-ground-{uuid.uuid4().hex[:6]}", architecture="YOLO26n",
            imaging_mode="ground", deployment_status="production",
            capability_status="NOT_VALIDATED",
        )
        session.add(ground)
    session.commit()
    yield ground
    session = SessionLocal()
    for model_id in retired:
        session.get(ModelVersion, model_id).deployment_status = "production"
    session.commit()


def _queued_image(session, users, source: str) -> int:
    """Our job must be the only one waiting, or run_once picks up someone else's and the
    assertions below describe a different job entirely."""
    session.execute(text("UPDATE jobs SET status='COMPLETED' WHERE status IN ('QUEUED','RETRYING')"))
    session.commit()
    user = session.execute(select(User)).scalars().first()
    field = users["field_farm_a"]
    image = Image(
        uuid=str(uuid.uuid4()), field_id=field.id, source=source,
        file_path="data/images/none/missing.jpg", content_hash=uuid.uuid4().hex * 2,
        gps_source="missing", captured_at=dt.datetime.now(), quality_flag="ok",
        uploaded_by=user.id, is_demo=True,
    )
    session.add(image)
    session.flush()
    session.execute(
        text("INSERT INTO jobs (type, status, payload) "
             "VALUES ('inference', 'QUEUED', JSON_OBJECT('image_id', :i))"),
        {"i": image.id},
    )
    session.commit()
    return image.id


def test_a_mode_with_no_model_raises_a_named_error(only_ground):
    session = SessionLocal()
    with pytest.raises(NoProductionModel) as caught:
        production_model(session, "aerial")
    # The message has to name the mode: "no model" alone sent me looking in the wrong
    # place for an afternoon.
    assert "aerial" in str(caught.value)
    assert production_model(session, "ground") is not None


def test_a_drone_photo_with_no_aerial_model_does_not_stop_the_worker(only_ground, users):
    session = SessionLocal()
    image_id = _queued_image(session, users, "drone")
    cfg = get_config()

    # Used to raise out of run_once and end the process.
    did_work = run_once(session, cfg, "test-worker")
    assert did_work is False

    status = session.execute(
        text("SELECT status FROM jobs WHERE image_id = :i"), {"i": image_id}
    ).scalar_one()
    # Back on the queue, not burned: it is analysed as soon as an aerial model exists.
    assert status == "QUEUED"


def test_the_queued_photo_keeps_its_attempts(only_ground, users):
    session = SessionLocal()
    image_id = _queued_image(session, users, "drone")
    cfg = get_config()
    for _ in range(3):
        run_once(session, cfg, "test-worker")
    row = session.execute(
        text("SELECT status, attempts FROM jobs WHERE image_id = :i"), {"i": image_id}
    ).fetchone()
    assert row[0] == "QUEUED"
    # Repeatedly meeting a missing model must not exhaust the retry budget and fail a
    # photo that was never actually attempted.
    assert row[1] <= 3


def test_the_error_recorded_on_the_job_names_the_mode(only_ground, users):
    session = SessionLocal()
    image_id = _queued_image(session, users, "drone")
    run_once(session, get_config(), "test-worker")
    error = session.execute(
        text("SELECT error FROM jobs WHERE image_id = :i"), {"i": image_id}
    ).scalar_one()
    assert "aerial" in (error or "")
