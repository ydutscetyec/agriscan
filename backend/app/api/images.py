"""Image ingestion and detection retrieval.

The upload endpoint never blocks on inference: it validates, stores, enqueues and
returns 202. A farmer on a weak connection must not wait for a model to load.
"""

from __future__ import annotations

import datetime as dt
import json

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import bindparam, func, select, text

from app.utils.clock import utc_now
from app.auth.decorators import requires_auth, requires_role
from app.extensions import SessionLocal
from app.models import Condition, Detection, Field, Image
from app.services import audit, storage
from app.services.storage import drop_thumbnail, resolve_stored
from app.services.exif_gps import extract_gps_and_time
from app.services.ownership import assert_can_access_field, visible_farm_ids
from app.utils.errors import ApiError

images_bp = Blueprint("images", __name__, url_prefix="/images")
detections_bp = Blueprint("detections", __name__, url_prefix="/detections")

POSITION_MISSING = "Position missing."
QUEUED_MESSAGE = "Inference queued."
DUPLICATE_MESSAGE = "Image already exists."


def _parse_datetime(value: str | None, label: str) -> dt.datetime | None:
    """A malformed filter is the caller's mistake: 400 with the reason, not a 500."""
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        raise ApiError(f"'{label}' must be an ISO date or date-time.", 400) from None


def _detection_payload(session, det: Detection, lookups: dict | None = None) -> dict:
    """Rule 2: model_version, confidence, verification_status and severity_method
    are present on every detection response, always.

    `lookups` is an optional {table: {id: row}} map for list endpoints, which would
    otherwise issue three SELECTs per row. One detection at a time passes nothing and
    reads straight from the session.
    """
    from app.models import ModelVersion, ProcessingVersion

    def fetch(model, key):
        if not key:
            return None
        if lookups is not None:
            return lookups.get(model.__name__, {}).get(key)
        return session.get(model, key)

    cond = fetch(Condition, det.condition_id)
    mv = fetch(ModelVersion, det.model_version_id)
    pv = fetch(ProcessingVersion, det.processing_version_id)
    return {
        "id": det.id,
        "image_id": det.image_id,
        "condition": cond.code if cond else "unknown",
        "condition_name": cond.common_name if cond else "Unknown",
        "confidence": float(det.confidence) if det.confidence is not None else None,
        "confidence_label": (
            f"{float(det.confidence) * 100:.1f}% model confidence"
            if det.confidence is not None
            else "NOT_AVAILABLE"
        ),
        "bbox": det.bbox,
        "severity": float(det.severity_value) if det.severity_value is not None else None,
        "severity_method": det.severity_method or "NOT_AVAILABLE",
        "severity_status": "EXPERIMENTAL",
        "severity_note": (
            "Affected-area proxy from detection boxes; NOT_VALIDATED against "
            "technician severity scoring."
        ),
        "model_version": mv.name if mv else "MODEL_NOT_AVAILABLE",
        # Which gate settings and severity method produced this row. None only for rows
        # written before migration 009; never guessed for them.
        "processing_version": (
            {
                "id": pv.id,
                "pipeline_version": pv.pipeline_version,
                "config_hash": pv.config_hash[:12],
            }
            if pv
            else None
        ),
        "verification_status": det.status,
        "source": None,
        "is_demo": det.is_demo,
        "created_at": det.created_at.isoformat() if det.created_at else None,
    }


@images_bp.post("")
@requires_auth
def upload_image():
    cfg = current_app.config["AGRISCAN"]
    session = SessionLocal()

    upload = request.files.get("file")
    if upload is None:
        raise ApiError("A 'file' part is required.", 400)

    # A photo from a remote capture session takes its field, mission and source from the
    # session, not from the form: the phone on the drone should not be trusted to say
    # which field it is over.
    capture_session = None
    capture_session_id = request.form.get("capture_session_id", type=int)
    if capture_session_id:
        from app.models import CaptureSession

        capture_session = session.get(CaptureSession, capture_session_id)
        if capture_session is None:
            raise ApiError("Capture session not found.", 404)
        if g.current_user.role not in ("admin", "technician", "researcher"):
            raise ApiError("Only an operator account may upload session captures.", 403)
        field_id = capture_session.field_id
    else:
        field_id = request.form.get("field_id", type=int)
    if not field_id:
        raise ApiError("'field_id' is required.", 400)
    field = session.get(Field, field_id)
    if field is None:
        raise ApiError("Field not found.", 404)
    assert_can_access_field(g.current_user, field)

    source = "drone" if capture_session else (request.form.get("source") or "phone").lower()
    if source not in ("phone", "drone"):
        raise ApiError("'source' must be 'phone' or 'drone'.", 400)

    client_uuid = (request.form.get("client_uuid") or "").strip() or None

    # A retried offline upload carries the same client_uuid. Check it BEFORE reading
    # or hashing the file: the whole point is that a retry costs nothing.
    if client_uuid:
        prior = session.execute(
            select(Image).where(Image.client_uuid == client_uuid)
        ).scalar_one_or_none()
        if prior is not None:
            return jsonify(
                {
                    "image_id": prior.id,
                    "duplicate": True,
                    "message": DUPLICATE_MESSAGE,
                    "job_id": None,
                    "client_uuid": client_uuid,
                }
            ), 200

    data = upload.read()
    storage.validate_upload(upload.filename, upload.mimetype, data, cfg)

    # (b) duplicate check before any writing
    content_hash = storage.sha256_hex(data)
    existing = session.execute(
        select(Image).where(Image.content_hash == content_hash)
    ).scalar_one_or_none()
    if existing is not None:
        # Same bytes already stored. Adopt the client id if this is the first time we
        # have seen one, so a later retry short-circuits above.
        if client_uuid and existing.client_uuid is None:
            existing.client_uuid = client_uuid
            session.commit()
        return jsonify(
            {
                "image_id": existing.id,
                "duplicate": True,
                "message": DUPLICATE_MESSAGE,
                "job_id": None,
                "client_uuid": client_uuid,
            }
        ), 200

    # (d) EXIF from the ORIGINAL bytes, before re-encoding discards it
    tmp_path = storage.write_temp_original(data, cfg)
    gps = extract_gps_and_time(tmp_path)
    try:
        import os

        os.unlink(tmp_path)
    except OSError:
        pass

    # Web-captured photos carry no EXIF GPS. If EXIF has no position, accept the one the
    # device reported from the Geolocation API at capture time, and record it as 'device'
    # so the two methods are never confused in the paper.
    gps_accuracy = None
    gps_altitude = None
    if gps["gps_source"] == "missing":
        device_lat = request.form.get("lat", type=float)
        device_lon = request.form.get("lon", type=float)
        if (
            device_lat is not None and device_lon is not None
            and -90 <= device_lat <= 90 and -180 <= device_lon <= 180
        ):
            gps["lat"], gps["lon"] = round(device_lat, 7), round(device_lon, 7)
            gps["gps_source"] = "device"
            gps_accuracy = request.form.get("gps_accuracy_m", type=float)
            gps_altitude = request.form.get("gps_altitude_m", type=float)

    if gps["captured_at"] is None and request.form.get("captured_at"):
        try:
            gps["captured_at"] = dt.datetime.fromisoformat(
                request.form["captured_at"].replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except ValueError:
            pass

    # (c) + (e) sanitise and store under a server-generated UUID
    stored = storage.reencode_and_store(data, cfg)

    mission_id = (
        capture_session.mission_id if capture_session
        else request.form.get("mission_id", type=int)
    )
    image = Image(
        uuid=stored["uuid"],
        client_uuid=client_uuid,
        mission_id=mission_id,
        capture_session_id=capture_session.id if capture_session else None,
        gps_accuracy_m=gps_accuracy,
        gps_altitude_m=gps_altitude,
        field_id=field.id,
        source=source,
        file_path=stored["file_path"],
        content_hash=content_hash,
        lat=gps["lat"],
        lon=gps["lon"],
        gps_source=gps["gps_source"],
        captured_at=gps["captured_at"] or utc_now(),
        uploaded_by=g.current_user.id,
        is_demo=bool(request.form.get("is_demo")) or field.is_demo,
    )
    session.add(image)
    session.commit()

    # (f) enqueue, do not run
    session.execute(
        text(
            "INSERT INTO jobs (type, status, priority, payload) "
            "VALUES ('inference', 'QUEUED', :p, :payload)"
        ),
        {"p": 1 if source == "phone" else 0, "payload": json.dumps({"image_id": image.id})},
    )
    session.commit()
    job_id = session.execute(text("SELECT LAST_INSERT_ID()")).scalar_one()

    audit.record(g.current_user.id, "upload_image", "image", image.id,
                 {"source": source, "gps_source": gps["gps_source"]})

    return jsonify(
        {
            "image_id": image.id,
            "job_id": int(job_id),
            "duplicate": False,
            "status": "QUEUED",
            "message": QUEUED_MESSAGE,
            "gps_source": gps["gps_source"],
            "gps_note": POSITION_MISSING if gps["gps_source"] == "missing" else None,
            "client_uuid": client_uuid,
        }
    ), 202


def _interpolate(points: list[dict], t: float) -> tuple[float | None, float | None, float | None]:
    """Position at time t from a 1 Hz track, by linear interpolation between the two
    surrounding fixes. Returns (lat, lon, accuracy). Outside the track, the nearest
    endpoint, because a frame a second past the last fix is still near it."""
    if not points:
        return None, None, None
    if t <= points[0]["t"]:
        p = points[0]
        return p["lat"], p["lon"], p.get("acc")
    if t >= points[-1]["t"]:
        p = points[-1]
        return p["lat"], p["lon"], p.get("acc")
    for before, after in zip(points, points[1:]):
        if before["t"] <= t <= after["t"]:
            span = after["t"] - before["t"]
            share = 0.0 if span <= 0 else (t - before["t"]) / span
            lat = before["lat"] + (after["lat"] - before["lat"]) * share
            lon = before["lon"] + (after["lon"] - before["lon"]) * share
            # The worse of the two fixes, plus the distance the drone covered between
            # them: an interpolated point cannot be better than what it sits between.
            acc = max(before.get("acc") or 0, after.get("acc") or 0)
            return lat, lon, acc
    return None, None, None


@images_bp.post("/from-video")
@requires_role("admin", "technician")
def image_from_video():
    """Save one frame of a flight video as an image.

    The frame is grabbed in the browser and posted here as a JPEG. It is stored like any
    other image so it can be viewed, verified and discussed — but it is marked twice over
    as not being a camera still: gps_source is 'video_interpolated', and
    from_video_offset_s records where in the clip it came from.

    That matters because a video frame is roughly a sixth of the pixels of a still, is
    inter-frame compressed, and has a position worked out from a 1 Hz track rather than
    written by the camera. Nothing derived from video should ever be counted as ground
    truth without someone deciding so deliberately.
    """
    from app.models import CaptureSession

    session = SessionLocal()
    cfg = current_app.config["AGRISCAN"]

    session_id = request.form.get("capture_session_id", type=int)
    offset = request.form.get("offset_s", type=float)
    if session_id is None or offset is None:
        raise ApiError("'capture_session_id' and 'offset_s' are required.", 400)
    capture_session = session.get(CaptureSession, session_id)
    if capture_session is None:
        raise ApiError("That capture session does not exist.", 404)

    frame = request.files.get("frame")
    if frame is None:
        raise ApiError("No frame supplied.", 400)
    data = frame.read(cfg.MAX_UPLOAD_BYTES + 1)
    if not data:
        raise ApiError("The frame was empty.", 400)
    if len(data) > cfg.MAX_UPLOAD_BYTES:
        raise ApiError("That frame is too large.", 413)

    field = session.get(Field, capture_session.field_id)
    assert_can_access_field(g.current_user, field)

    points = []
    if capture_session.track_path:
        track = storage.resolve_stored(capture_session.track_path)
        if track.is_file():
            points = json.loads(track.read_text(encoding="utf-8"))
    lat, lon, acc = _interpolate(points, offset)

    content_hash = storage.sha256_hex(data)
    existing = session.execute(
        select(Image).where(Image.content_hash == content_hash)
    ).scalar_one_or_none()
    if existing:
        return jsonify({"image_id": existing.id, "duplicate": True}), 200

    stored = storage.reencode_and_store(data, cfg)
    captured = capture_session.started_at or capture_session.created_at
    image = Image(
        uuid=stored["uuid"],
        mission_id=capture_session.mission_id,
        capture_session_id=capture_session.id,
        field_id=field.id,
        source="drone",
        file_path=stored["file_path"],
        content_hash=content_hash,
        lat=lat,
        lon=lon,
        gps_accuracy_m=acc,
        gps_source="video_interpolated" if lat is not None else "missing",
        from_video_offset_s=offset,
        captured_at=(captured + dt.timedelta(seconds=offset)) if captured else utc_now(),
        uploaded_by=g.current_user.id,
        is_demo=field.is_demo,
    )
    session.add(image)
    session.commit()
    session.execute(
        text("INSERT INTO jobs (type, status, payload) "
             "VALUES ('inference', 'QUEUED', JSON_OBJECT('image_id', :i))"),
        {"i": image.id},
    )
    session.commit()
    audit.record(g.current_user.id, "image_from_video", "image", image.id,
                 {"capture_session_id": session_id, "offset_s": offset,
                  "gps_source": image.gps_source})
    return jsonify({
        "image_id": image.id,
        "lat": float(lat) if lat is not None else None,
        "lon": float(lon) if lon is not None else None,
        "gps_source": image.gps_source,
    }), 201


@images_bp.get("")
@requires_auth
def list_images():
    """Captures this user may see, newest first.

    Includes captures with no detection yet: a farmer who just uploaded needs to see
    that the image arrived and is waiting, not an empty list.
    """
    session = SessionLocal()
    stmt = select(Image)

    capture_session_id = request.args.get("capture_session_id", type=int)
    if capture_session_id:
        stmt = stmt.where(Image.capture_session_id == capture_session_id)

    if request.args.get("mine", "false").lower() == "true":
        stmt = stmt.where(Image.uploaded_by == g.current_user.id)

    allowed = visible_farm_ids(g.current_user)
    if allowed is not None:
        field_ids = session.execute(
            select(Field.id).where(Field.farm_id.in_(allowed or [-1]))
        ).scalars().all()
        stmt = stmt.where(Image.field_id.in_(list(field_ids) or [-1]))

    limit = min(request.args.get("limit", default=50, type=int), 200)
    # How many there are in total, so the page can say when it is showing a slice
    # rather than everything. Silently truncating a season of flights is worse than a
    # slow page: nobody can tell the difference between "no more" and "not shown".
    total = session.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()
    rows = session.execute(
        stmt.order_by(Image.id.desc()).limit(limit)
    ).scalars().all()

    # Three lookups per image (field, detections, job) meant 200 images was 600 queries.
    # One query each for the whole page instead.
    image_ids = [image.id for image in rows]
    fields = {}
    detections: dict[int, list[Detection]] = {}
    jobs: dict[int, str] = {}
    if image_ids:
        field_ids = {image.field_id for image in rows if image.field_id}
        if field_ids:
            fields = {
                f.id: f for f in session.execute(
                    select(Field).where(Field.id.in_(field_ids))
                ).scalars()
            }
        for det in session.execute(
            select(Detection)
            .where(Detection.image_id.in_(image_ids))
            .order_by(Detection.image_id, Detection.confidence.desc())
        ).scalars():
            detections.setdefault(det.image_id, []).append(det)
        # The latest job per image, in one pass.
        for image_id, status in session.execute(
            text(
                "SELECT j.image_id, j.status FROM jobs j "
                "JOIN (SELECT image_id, MAX(id) AS id FROM jobs "
                "      WHERE image_id IN :ids GROUP BY image_id) latest "
                "  ON latest.id = j.id"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": image_ids},
        ):
            jobs[image_id] = status

    # One query per related table for the whole page. Without this, _detection_payload
    # issued three SELECTs for every row it rendered: 50 images meant 150 round trips
    # on top of the listing itself.
    lookups: dict[str, dict] = {}
    shown = [d[0] for d in detections.values()]
    if shown:
        from app.models import ModelVersion, ProcessingVersion

        for model, ids in (
            (Condition, {d.condition_id for d in shown if d.condition_id}),
            (ModelVersion, {d.model_version_id for d in shown if d.model_version_id}),
            (ProcessingVersion,
             {d.processing_version_id for d in shown if d.processing_version_id}),
        ):
            if ids:
                lookups[model.__name__] = {
                    row.id: row for row in
                    session.execute(select(model).where(model.id.in_(ids))).scalars()
                }

    out = []
    for image in rows:
        field = fields.get(image.field_id)
        dets = detections.get(image.id, [])
        top = dets[0] if dets else None
        out.append(
            {
                "image_id": image.id,
                "client_uuid": image.client_uuid,
                "field_id": image.field_id,
                "field_name": field.name if field else "NOT_AVAILABLE",
                "source": image.source,
                "captured_at": image.captured_at.isoformat() if image.captured_at else None,
                "quality_flag": image.quality_flag,
                "job_status": jobs.get(image.id),
                "detection": (
                    dict(_detection_payload(session, top, lookups), source=image.source)
                    if top else None
                ),
                "detection_count": len(dets),
            }
        )
    return jsonify({"count": len(out), "total": int(total), "captures": out})


# Everything that points at an image or at its detections, innermost first. Every one
# of these foreign keys is RESTRICT, so the order matters and a missed table shows up as
# a 409 rather than silent data loss.
_DEPENDENTS = (
    ("verifications", "detection_id IN (SELECT id FROM detections WHERE image_id = :i)"),
    ("farmer_feedback", "detection_id IN (SELECT id FROM detections WHERE image_id = :i)"),
    ("recommendations", "detection_id IN (SELECT id FROM detections WHERE image_id = :i)"),
    ("annotations", "image_id = :i"),
    ("image_bands", "image_id = :i"),
    ("rtk_observations", "image_id = :i"),
    ("dataset_images", "image_id = :i"),
    ("detections", "image_id = :i"),
    ("jobs", "image_id = :i"),
)


@images_bp.delete("/<int:image_id>")
@requires_role("admin")
def delete_image(image_id: int):
    """Remove a photo and everything derived from it.

    Admin only, and refused once a technician has verified any detection on it. A
    verified detection is ground truth: it is what the model's reported accuracy is
    measured against, so deleting one silently changes a number in Chapter 4. Rejecting
    the photo through the verification queue is the way to discard a bad result; this is
    for photos that should never have been in the dataset at all — a test shot, a
    misfire, a picture of someone's shoe.

    The audit_log row survives the image, by design: migration 002 makes that table
    append-only, so what was deleted and by whom is still answerable afterwards.
    """
    session = SessionLocal()
    image = session.get(Image, image_id)
    if image is None:
        raise ApiError("That image does not exist.", 404)

    verified = session.execute(
        text(
            "SELECT COUNT(*) FROM verifications v JOIN detections d ON d.id = v.detection_id "
            "WHERE d.image_id = :i"
        ),
        {"i": image_id},
    ).scalar_one()
    if verified:
        raise ApiError(
            "This photo has technician-verified results, which are the ground truth the "
            "model is measured against. It cannot be deleted.",
            409,
        )

    detail = {
        "file_path": image.file_path,
        "field_id": image.field_id,
        "source": image.source,
        "captured_at": image.captured_at.isoformat() if image.captured_at else None,
        "quality_flag": image.quality_flag,
    }
    for table, where in _DEPENDENTS:
        session.execute(text(f"DELETE FROM {table} WHERE {where}"), {"i": image_id})
    session.delete(image)
    session.commit()

    # The row is gone either way; a file left behind is a smaller problem than a row
    # pointing at nothing, so the database comes first and the file is best effort.
    drop_thumbnail(current_app.config["AGRISCAN"], image_id)
    removed_file = False
    try:
        path = resolve_stored(image_file_path := detail["file_path"])
        root = current_app.config["AGRISCAN"].image_root_path
        if root in path.parents and path.is_file():
            path.unlink()
            removed_file = True
    except OSError:
        current_app.logger.warning("Could not remove %s", image_file_path)

    audit.record(g.current_user.id, "delete_image", "image", image_id,
                 {**detail, "file_removed": removed_file})
    return jsonify({"deleted": image_id, "file_removed": removed_file})


@images_bp.get("/<int:image_id>")
@requires_auth
def get_image(image_id: int):
    session = SessionLocal()
    image = session.get(Image, image_id)
    if image is None:
        raise ApiError("Image not found.", 404)
    field = session.get(Field, image.field_id)
    assert_can_access_field(g.current_user, field)

    job = session.execute(
        text(
            "SELECT id, status, error, attempts, result FROM jobs "
            "WHERE image_id = :i ORDER BY id DESC LIMIT 1"
        ),
        {"i": image.id},
    ).fetchone()

    dets = session.execute(
        select(Detection).where(Detection.image_id == image.id).order_by(Detection.id)
    ).scalars().all()

    return jsonify(
        {
            "id": image.id,
            "uuid": image.uuid,
            "field_id": image.field_id,
            "mission_id": image.mission_id,
            "source": image.source,
            "lat": float(image.lat) if image.lat is not None else None,
            "lon": float(image.lon) if image.lon is not None else None,
            "gps_source": image.gps_source,
            "gps_note": POSITION_MISSING if image.gps_source == "missing" else None,
            "captured_at": image.captured_at.isoformat() if image.captured_at else None,
            "quality_flag": image.quality_flag or "DATA_REQUIRED",
            "is_demo": image.is_demo,
            "job": (
                {
                    "id": job[0], "status": job[1], "error": job[2],
                    "attempts": job[3],
                    "result": json.loads(job[4]) if job[4] else None,
                }
                if job
                else None
            ),
            "detections": [
                dict(_detection_payload(session, d), source=image.source) for d in dets
            ],
        }
    )


@detections_bp.get("")
@requires_auth
def list_detections():
    session = SessionLocal()
    stmt = select(Detection).join(Image, Detection.image_id == Image.id)

    allowed = visible_farm_ids(g.current_user)
    if allowed is not None:
        field_ids = session.execute(
            select(Field.id).where(Field.farm_id.in_(allowed or [-1]))
        ).scalars().all()
        stmt = stmt.where(Image.field_id.in_(list(field_ids) or [-1]))

    field_id = request.args.get("field_id", type=int)
    if field_id:
        stmt = stmt.where(Image.field_id == field_id)

    source = request.args.get("source")
    if source:
        stmt = stmt.where(Image.source == source)

    status = request.args.get("status")
    if status:
        stmt = stmt.where(Detection.status == status)

    condition = request.args.get("condition")
    if condition:
        cond = session.execute(
            select(Condition).where(Condition.code == condition)
        ).scalar_one_or_none()
        stmt = stmt.where(Detection.condition_id == (cond.id if cond else -1))

    min_conf = request.args.get("min_confidence", type=float)
    if min_conf is not None:
        stmt = stmt.where(Detection.confidence >= min_conf)

    date_from = _parse_datetime(request.args.get("date_from"), "date_from")
    if date_from:
        stmt = stmt.where(Detection.created_at >= date_from)
    date_to = _parse_datetime(request.args.get("date_to"), "date_to")
    if date_to:
        stmt = stmt.where(Detection.created_at <= date_to)

    if request.args.get("include_demo", "false").lower() != "true":
        stmt = stmt.where(Detection.is_demo.is_(False))

    # Map viewport filter: the browser asks only for what is on screen.
    min_lat = request.args.get("min_lat", type=float)
    max_lat = request.args.get("max_lat", type=float)
    min_lon = request.args.get("min_lon", type=float)
    max_lon = request.args.get("max_lon", type=float)
    if None not in (min_lat, max_lat, min_lon, max_lon):
        stmt = (
            stmt.where(Image.lat.is_not(None))
            .where(Image.lat >= min_lat).where(Image.lat <= max_lat)
            .where(Image.lon >= min_lon).where(Image.lon <= max_lon)
        )

    limit = min(request.args.get("limit", default=200, type=int), 1000)
    offset = request.args.get("offset", default=0, type=int)

    # Total across all pages, for "showing 51-100 of 340". Same filters, no limit.
    from sqlalchemy import func
    total = session.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = session.execute(
        stmt.order_by(Detection.id.desc()).limit(limit).offset(offset)
    ).scalars().all()

    out = []
    for det in rows:
        img = session.get(Image, det.image_id)
        payload = _detection_payload(session, det)
        payload["source"] = img.source if img else None
        payload["field_id"] = img.field_id if img else None
        payload["lat"] = float(img.lat) if img and img.lat is not None else None
        payload["lon"] = float(img.lon) if img and img.lon is not None else None
        out.append(payload)

    return jsonify(
        {"count": len(out), "total": total, "limit": limit, "offset": offset,
         "detections": out}
    )
