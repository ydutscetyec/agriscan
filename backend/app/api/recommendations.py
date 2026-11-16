"""Recommendation endpoints.

The approval gate is a database state, not a policy: `approved_by IS NULL` means the
farmer-facing response carries the pending placeholder and no advice text at all.
That check lives in exactly one function, `_farmer_view`, so it cannot be forgotten
on a new endpoint.
"""

from __future__ import annotations

import datetime as dt

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select

from app.utils.clock import utc_now
from app.auth.decorators import requires_auth, requires_role
from app.extensions import SessionLocal
from app.models import (
    Condition,
    Detection,
    Field,
    Image,
    KnowledgeBase,
    KnowledgeSource,
    Recommendation,
)
from app.services import audit
from app.services.growth_stage import derive_growth_stage
from app.services.ownership import assert_can_access_field
from app.services.recommendations import FALLBACK, cache_key, generate, severity_band
from app.utils.errors import ApiError

bp = Blueprint("recommendations", __name__, url_prefix="/recommendations")

PENDING_MESSAGE = "Pending technician review."


def _facts(session, det: Detection, cfg) -> dict:
    cond = session.get(Condition, det.condition_id) if det.condition_id else None
    image = session.get(Image, det.image_id)
    field = session.get(Field, image.field_id) if image else None
    observation = image.captured_at.date() if image and image.captured_at else None
    growth = derive_growth_stage(field.planting_date if field else None, observation, cfg)
    band = severity_band(
        float(det.severity_value) if det.severity_value is not None else None
    )
    return {
        "condition_code": cond.code if cond else "unknown",
        "condition_name": cond.common_name if cond else "Unknown",
        "condition_id": cond.id if cond else None,
        "severity_band": band,
        "growth_stage": growth["growth_stage"],
        "field_id": field.id if field else None,
    }


def _records(session, condition_id: int | None) -> list[dict]:
    if condition_id is None:
        return []
    row = session.execute(
        select(KnowledgeBase).where(KnowledgeBase.condition_id == condition_id)
    ).scalar_one_or_none()
    return [row.to_record()] if row else []


def _source_refs(session, records: list[dict]) -> list[dict]:
    refs = []
    for record in records:
        source = (
            session.get(KnowledgeSource, record["source_id"])
            if record.get("source_id")
            else None
        )
        refs.append(
            {
                "title": source.title if source else "NOT_AVAILABLE",
                "publisher": source.publisher if source else "NOT_AVAILABLE",
                "year": source.year if source else None,
                "locator": source.locator if source else None,
                "content_status": record.get("content_status", "PLACEHOLDER"),
            }
        )
    return refs


def _payload(rec: Recommendation, *, for_farmer: bool) -> dict:
    """The one place the approval gate is applied."""
    approved = rec.approved_by is not None and rec.status == "approved"
    body = {
        "id": rec.id,
        "detection_id": rec.detection_id,
        "status": rec.status,
        "approved": approved,
        "severity_band": rec.severity_band,
        "growth_stage": rec.growth_stage,
        "generated_by": rec.generated_by,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
    if for_farmer and not approved:
        body["text"] = None
        body["message"] = PENDING_MESSAGE
        body["source_refs"] = None
        return body
    body["text"] = rec.text
    body["message"] = None if approved else PENDING_MESSAGE
    body["source_refs"] = rec.source_refs
    body["approved_by"] = rec.approved_by
    body["approved_at"] = rec.approved_at.isoformat() if rec.approved_at else None
    body["rejected_reason"] = rec.rejected_reason
    return body


def _guard_access(session, det: Detection) -> None:
    image = session.get(Image, det.image_id)
    assert_can_access_field(
        g.current_user, session.get(Field, image.field_id) if image else None
    )


@bp.get("/<int:detection_id>")
@requires_auth
def get_for_detection(detection_id: int):
    session = SessionLocal()
    det = session.get(Detection, detection_id)
    if det is None:
        raise ApiError("Detection not found.", 404)
    _guard_access(session, det)

    for_farmer = g.current_user.role == "farmer"
    rows = session.execute(
        select(Recommendation)
        .where(Recommendation.detection_id == det.id)
        .order_by(Recommendation.id.desc())
    ).scalars().all()

    if for_farmer:
        rows = [r for r in rows if r.status != "rejected"]

    if not rows:
        return jsonify(
            {
                "detection_id": det.id,
                "recommendations": [],
                "message": PENDING_MESSAGE if for_farmer else None,
            }
        )
    return jsonify(
        {
            "detection_id": det.id,
            "recommendations": [_payload(r, for_farmer=for_farmer) for r in rows],
        }
    )


@bp.post("/<int:detection_id>/generate")
@requires_role("technician", "admin", "researcher")
def generate_for_detection(detection_id: int):
    """Generate candidate text for a technician-verified detection.

    Refuses on anything not technician-verified: advice built on an unverified
    diagnosis is advice about a guess.
    """
    session = SessionLocal()
    cfg = current_app.config["AGRISCAN"]
    det = session.get(Detection, detection_id)
    if det is None:
        raise ApiError("Detection not found.", 404)
    if det.status != "technician_verified":
        raise ApiError(
            "Recommendations are generated only for technician-verified detections. "
            f"This one is '{det.status}'.",
            409,
        )

    facts = _facts(session, det, cfg)
    key = cache_key(facts["condition_code"], facts["severity_band"], facts["growth_stage"])

    # An approved recommendation for the same condition, band and stage is reused.
    # No model call, works offline, and the farmer sees text a technician already signed.
    cached = session.execute(
        select(Recommendation)
        .where(Recommendation.cache_key == key)
        .where(Recommendation.status == "approved")
        .order_by(Recommendation.id.desc())
    ).scalars().first()

    if cached is not None and not request.args.get("force"):
        rec = Recommendation(
            detection_id=det.id,
            text=cached.text,
            source_refs=cached.source_refs,
            generated_by=f"cache:{cached.id}",
            approved_by=cached.approved_by,
            approved_at=cached.approved_at,
            status="approved",
            cache_key=key,
            severity_band=facts["severity_band"],
            growth_stage=facts["growth_stage"],
            is_demo=det.is_demo,
        )
        session.add(rec)
        session.commit()
        audit.record(
            g.current_user.id, "recommendation_from_cache", "recommendation", rec.id,
            {"cache_key": key, "source": cached.id},
        )
        return jsonify({**_payload(rec, for_farmer=False), "from_cache": True}), 201

    records = _records(session, facts["condition_id"])
    result = generate(facts, records, cfg)

    rec = Recommendation(
        detection_id=det.id,
        text=result["text"],
        source_refs=_source_refs(session, records) or None,
        generated_by=result["generated_by"],
        approved_by=None,
        status="pending",
        cache_key=key,
        severity_band=facts["severity_band"],
        growth_stage=facts["growth_stage"],
        is_demo=det.is_demo,
    )
    session.add(rec)
    session.commit()
    audit.record(
        g.current_user.id, "recommendation_generated", "recommendation", rec.id,
        {"validated": result["validated"], "problems": result["problems"]},
    )

    return jsonify(
        {
            **_payload(rec, for_farmer=False),
            "from_cache": False,
            "validated": result["validated"],
            "validator_problems": result["problems"],
            "note": result["note"],
            "knowledge_base_matched": bool(records),
            "placeholder_content": any(
                r.get("content_status") == "PLACEHOLDER" for r in records
            ),
        }
    ), 201


@bp.post("/<int:recommendation_id>/approve")
@requires_role("technician", "admin")
def approve(recommendation_id: int):
    session = SessionLocal()
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ApiError("Recommendation not found.", 404)

    data = request.get_json(silent=True) or {}
    edited = data.get("text")
    if edited:
        rec.text = edited
    if rec.text.strip() == FALLBACK:
        # Approving the fallback is allowed, but it is never cached as guidance.
        rec.cache_key = None

    rec.approved_by = g.current_user.id
    rec.approved_at = utc_now()
    rec.status = "approved"
    session.commit()

    audit.record(
        g.current_user.id, "recommendation_approved", "recommendation", rec.id,
        {"edited": bool(edited)},
    )
    return jsonify(_payload(rec, for_farmer=False))


@bp.post("/<int:recommendation_id>/reject")
@requires_role("technician", "admin")
def reject(recommendation_id: int):
    session = SessionLocal()
    rec = session.get(Recommendation, recommendation_id)
    if rec is None:
        raise ApiError("Recommendation not found.", 404)
    data = request.get_json(silent=True) or {}
    rec.status = "rejected"
    rec.approved_by = None
    rec.approved_at = None
    rec.rejected_reason = data.get("reason") or None
    session.commit()
    audit.record(
        g.current_user.id, "recommendation_rejected", "recommendation", rec.id,
        {"reason": rec.rejected_reason},
    )
    return jsonify(_payload(rec, for_farmer=False))


@bp.get("/pending")
@requires_role("technician", "admin", "researcher")
def pending_queue():
    session = SessionLocal()
    rows = session.execute(
        select(Recommendation)
        .where(Recommendation.status == "pending")
        .order_by(Recommendation.id.asc())
        .limit(200)
    ).scalars().all()

    out = []
    for rec in rows:
        det = session.get(Detection, rec.detection_id)
        cond = (
            session.get(Condition, det.condition_id)
            if det and det.condition_id
            else None
        )
        out.append(
            {
                **_payload(rec, for_farmer=False),
                "condition_name": cond.common_name if cond else "Unknown",
                "is_fallback": rec.text.strip() == FALLBACK,
            }
        )
    return jsonify({"count": len(out), "recommendations": out})
