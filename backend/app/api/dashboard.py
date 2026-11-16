"""Read-only endpoints the dashboard needs.

Added in Prompt 3 because the detection detail page cannot exist without them: an
image the browser can load, the verification history attached to a detection, and the
model registry. Nothing here writes; verification writes arrive in Prompt 4.
"""

from __future__ import annotations

import pathlib

from flask import Blueprint, current_app, g, jsonify, request, send_file
from sqlalchemy import select

from app.auth.decorators import requires_auth, requires_role
from app.extensions import SessionLocal
from app.models import (
    ProcessingVersion,
    Condition,
    Detection,
    FarmerFeedback,
    Field,
    Image,
    ModelVersion,
    User,
    Verification,
)
from app.services.growth_stage import derive_growth_stage
from app.services.ownership import assert_can_access_field
from app.services.storage import ensure_thumbnail, resolve_stored
from app.utils.errors import ApiError

files_bp = Blueprint("image_files", __name__, url_prefix="/images")
detail_bp = Blueprint("detection_detail", __name__, url_prefix="/detections")
models_bp = Blueprint("models", __name__, url_prefix="/models")
people_bp = Blueprint("people", __name__, url_prefix="/people")


@files_bp.get("/<int:image_id>/thumb")
@requires_auth
def serve_thumbnail(image_id: int):
    """A small JPEG for list views. Same ownership check as the full file."""
    session = SessionLocal()
    image = session.get(Image, image_id)
    if image is None:
        raise ApiError("Image not found.", 404)
    assert_can_access_field(g.current_user, session.get(Field, image.field_id))

    cfg = current_app.config["AGRISCAN"]
    path = resolve_stored(image.file_path)
    root = cfg.image_root_path
    if root not in path.parents or not path.exists():
        raise ApiError("Image file is not available on this server.", 404)
    # If the thumbnail cannot be made (an odd format, a damaged file), send the original
    # rather than a broken picture.
    served = ensure_thumbnail(cfg, image_id, path) or path
    response = send_file(served, mimetype="image/jpeg", conditional=True)
    response.headers["Cache-Control"] = "private, max-age=604800, immutable"
    return response


@files_bp.get("/<int:image_id>/file")
@requires_auth
def serve_image(image_id: int):
    """Serve the stored JPEG. Ownership is checked before the file is opened."""
    session = SessionLocal()
    image = session.get(Image, image_id)
    if image is None:
        raise ApiError("Image not found.", 404)
    assert_can_access_field(g.current_user, session.get(Field, image.field_id))

    cfg = current_app.config["AGRISCAN"]
    path = resolve_stored(image.file_path)
    root = cfg.image_root_path
    # Refuse anything that resolves outside the image root, whatever the DB says.
    if root not in path.parents or not path.exists():
        raise ApiError("Image file is not available on this server.", 404)
    response = send_file(path, mimetype="image/jpeg", conditional=True)
    # The bytes behind an image id never change (server UUID, re-encoded once), so the
    # browser may keep them. 'private' keeps shared caches and proxies from storing a
    # farmer's photo.
    response.headers["Cache-Control"] = "private, max-age=604800, immutable"
    return response


@detail_bp.get("/<int:detection_id>")
@requires_auth
def detection_detail(detection_id: int):
    """One detection with everything needed to judge it, and nothing invented.

    Verification history and farmer feedback are returned as they stand. An empty list
    means nobody has reviewed this yet, and the client says exactly that.
    """
    session = SessionLocal()
    det = session.get(Detection, detection_id)
    if det is None:
        raise ApiError("Detection not found.", 404)

    image = session.get(Image, det.image_id)
    field = session.get(Field, image.field_id) if image else None
    assert_can_access_field(g.current_user, field)

    cfg = current_app.config["AGRISCAN"]
    cond = session.get(Condition, det.condition_id) if det.condition_id else None
    model = session.get(ModelVersion, det.model_version_id)

    observation = image.captured_at.date() if image and image.captured_at else None
    growth = derive_growth_stage(field.planting_date if field else None, observation, cfg)

    verifications = session.execute(
        select(Verification)
        .where(Verification.detection_id == det.id)
        .order_by(Verification.verified_at.desc())
    ).scalars().all()

    feedback = session.execute(
        select(FarmerFeedback)
        .where(FarmerFeedback.detection_id == det.id)
        .order_by(FarmerFeedback.created_at.desc())
    ).scalars().all()

    def _user_name(user_id: int | None) -> str:
        user = session.get(User, user_id) if user_id else None
        return user.name if user else "NOT_AVAILABLE"

    return jsonify(
        {
            "id": det.id,
            "condition": cond.code if cond else "unknown",
            "condition_name": cond.common_name if cond else "Unknown",
            "condition_category": cond.category if cond else "unknown",
            "confidence": float(det.confidence) if det.confidence is not None else None,
            "confidence_label": (
                f"{float(det.confidence) * 100:.1f}% model confidence"
                if det.confidence is not None
                else "NOT_AVAILABLE"
            ),
            "bbox": det.bbox,
            "severity": (
                float(det.severity_value) if det.severity_value is not None else None
            ),
            "severity_method": det.severity_method or "NOT_AVAILABLE",
            "severity_status": "EXPERIMENTAL",
            "severity_note": (
                "Affected-area proxy from detection boxes; NOT_VALIDATED against "
                "technician severity scoring."
            ),
            "model_version": model.name if model else "MODEL_NOT_AVAILABLE",
            "model_architecture": model.architecture if model else "NOT_AVAILABLE",
            "model_dataset_version": (
                (model.dataset_version or "DATA_REQUIRED") if model else "DATA_REQUIRED"
            ),
            "processing_version": _pv_summary(session, det),
            "verification_status": det.status,
            "created_at": det.created_at.isoformat() if det.created_at else None,
            "is_demo": det.is_demo,
            "image": {
                "id": image.id if image else None,
                "source": image.source if image else None,
                "lat": float(image.lat) if image and image.lat is not None else None,
                "lon": float(image.lon) if image and image.lon is not None else None,
                "gps_source": image.gps_source if image else "missing",
                "gps_note": (
                    "Position missing."
                    if not image or image.gps_source == "missing"
                    else None
                ),
                "captured_at": (
                    image.captured_at.isoformat() if image and image.captured_at else None
                ),
                "quality_flag": (image.quality_flag if image else None) or "DATA_REQUIRED",
                "uploaded_by": _user_name(image.uploaded_by if image else None),
            },
            "field": {
                "id": field.id if field else None,
                "name": field.name if field else "NOT_AVAILABLE",
                "variety": (field.variety if field else None) or "DATA_REQUIRED",
            },
            "growth_stage": growth,
            "verifications": [
                {
                    "id": v.id,
                    "technician": _user_name(v.technician_id),
                    "decision": v.decision,
                    "corrected_condition": (
                        session.get(Condition, v.corrected_condition_id).code
                        if v.corrected_condition_id
                        else None
                    ),
                    "severity_score": v.severity_score,
                    "notes": v.notes,
                    "verified_at": v.verified_at.isoformat() if v.verified_at else None,
                }
                for v in verifications
            ],
            "farmer_feedback": [
                {
                    "id": f.id,
                    "user": _user_name(f.user_id),
                    "agrees": f.agrees,
                    "comment": f.comment,
                    "created_at": f.created_at.isoformat() if f.created_at else None,
                }
                for f in feedback
            ],
        }
    )


@models_bp.get("")
@requires_auth
def list_models():
    session = SessionLocal()
    rows = session.execute(
        select(ModelVersion).order_by(ModelVersion.id.desc())
    ).scalars().all()
    return jsonify([m.to_dict() for m in rows])


def _pv_summary(session, det) -> dict | None:
    """Which gate settings and severity method produced this detection, or None for
    rows written before processing versions were tracked. Never guessed."""
    if not det.processing_version_id:
        return None
    row = session.get(ProcessingVersion, det.processing_version_id)
    if row is None:
        return None
    return {
        "id": row.id,
        "pipeline_version": row.pipeline_version,
        "config_hash": row.config_hash[:12],
    }


def _pv_dict(row: ProcessingVersion, with_config: bool = False) -> dict:
    out = {
        "id": row.id,
        "pipeline_version": row.pipeline_version,
        "config_hash": row.config_hash,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if with_config:
        import json

        out["config"] = json.loads(row.config_json)
    return out


@models_bp.get("/processing-versions")
@requires_role("admin", "technician", "researcher")
def list_processing_versions():
    """Every configuration the pipeline has run under, newest first."""
    session = SessionLocal()
    rows = session.execute(
        select(ProcessingVersion).order_by(ProcessingVersion.id.desc())
    ).scalars().all()
    return jsonify([_pv_dict(r) for r in rows])


@models_bp.get("/processing-versions/<int:version_id>")
@requires_role("admin", "technician", "researcher")
def get_processing_version(version_id: int):
    session = SessionLocal()
    row = session.get(ProcessingVersion, version_id)
    if row is None:
        raise ApiError("Processing version not found.", 404)
    return jsonify(_pv_dict(row, with_config=True))


@people_bp.get("/farmers")
@requires_role("admin", "technician", "researcher")
def list_farmers():
    """Farmers only, for the field-management screens.

    Deliberately narrower than /users, which stays admin-only: a technician needs to
    know whose field they are standing in, not the whole account list.
    """
    session = SessionLocal()
    rows = session.execute(
        select(User).where(User.role == "farmer").order_by(User.name)
    ).scalars().all()
    return jsonify(
        [
            {"id": u.id, "name": u.name, "barangay": u.barangay, "is_demo": u.is_demo}
            for u in rows
        ]
    )
