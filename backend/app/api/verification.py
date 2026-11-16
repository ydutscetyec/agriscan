"""Human-in-the-loop verification.

Two things are kept strictly apart here, because collapsing them poisons the dataset:

  farmer feedback   is EVIDENCE about a detection
  technician review is the only thing that produces a LABEL

A farmer confirming a wrong diagnosis must never become a training example.
"""

from __future__ import annotations

import datetime as dt

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import func, select, text

from app.auth.decorators import requires_auth, requires_role
from app.extensions import SessionLocal
from app.models import (
    Condition,
    Detection,
    FarmerFeedback,
    Field,
    Image,
    ModelVersion,
    User,
    Verification,
)
from app.services import audit
from app.services.ownership import assert_can_access_field
from app.utils.errors import ApiError

verify_bp = Blueprint("verification", __name__, url_prefix="/detections")
queue_bp = Blueprint("queue", __name__, url_prefix="/verification-queue")
analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis")

QUEUE_REASONS = {
    "low_confidence": "Below the confidence threshold",
    "high_severity": "High severity estimate",
    "farmer_rejected": "Farmer disagreed",
    "confidence_sample": "Random sample of confident predictions",
}


def _detection_or_404(session, detection_id: int) -> Detection:
    det = session.get(Detection, detection_id)
    if det is None:
        raise ApiError("Detection not found.", 404)
    return det


def _field_of(session, det: Detection) -> Field | None:
    image = session.get(Image, det.image_id)
    return session.get(Field, image.field_id) if image else None


# ------------------------------------------------------------------ farmer feedback


@verify_bp.post("/<int:detection_id>/feedback")
@requires_auth
def submit_feedback(detection_id: int):
    """Farmer agrees or disagrees. This never changes the condition.

    A 'yes' moves the status to farmer_confirmed, which is weaker than verified and is
    drawn differently everywhere. A 'no' leaves the status alone and pushes the case up
    the technician queue: a disagreement is a reason to look, not a verdict.
    """
    session = SessionLocal()
    det = _detection_or_404(session, detection_id)
    assert_can_access_field(g.current_user, _field_of(session, det))

    data = request.get_json(silent=True) or {}
    if "agrees" not in data:
        raise ApiError("'agrees' is required (true or false).", 400)
    agrees = bool(data["agrees"])

    session.add(
        FarmerFeedback(
            detection_id=det.id,
            user_id=g.current_user.id,
            agrees=agrees,
            comment=(data.get("comment") or None),
            is_demo=det.is_demo,
        )
    )

    # Never downgrade a technician decision with farmer feedback.
    if agrees and det.status in ("ai_detected", "low_confidence"):
        session.execute(
            text("UPDATE detections SET status='farmer_confirmed' WHERE id=:i"),
            {"i": det.id},
        )
    session.commit()

    audit.record(
        g.current_user.id, "farmer_feedback", "detection", det.id, {"agrees": agrees}
    )
    session.refresh(det)
    return jsonify(
        {
            "detection_id": det.id,
            "status": det.status,
            "recorded": True,
            "note": (
                "Farmer feedback is evidence about this detection. It is not a verified "
                "label and cannot change the diagnosis."
            ),
        }
    ), 201


# ------------------------------------------------------------ technician verification


@verify_bp.post("/<int:detection_id>/verify")
@requires_role("technician", "admin")
def verify_detection(detection_id: int):
    """Write a verification row. The detection's diagnosis fields are never touched.

    Corrections live in `verifications.corrected_condition_id`. The original prediction
    stays exactly as the model produced it, which is what makes the confusion matrix in
    Chapter 4 a query rather than a claim.
    """
    session = SessionLocal()
    det = _detection_or_404(session, detection_id)

    data = request.get_json(silent=True) or {}
    decision = data.get("decision")
    if decision not in ("correct", "corrected", "cannot_determine"):
        raise ApiError(
            "'decision' must be one of: correct, corrected, cannot_determine.", 400
        )

    corrected_id = None
    if decision == "corrected":
        code = data.get("corrected_condition")
        if not code:
            raise ApiError("'corrected_condition' is required when correcting.", 400)
        cond = session.execute(
            select(Condition).where(Condition.code == code)
        ).scalar_one_or_none()
        if cond is None:
            raise ApiError(f"Unknown condition code '{code}'.", 400)
        corrected_id = cond.id

    severity_score = data.get("severity_score")
    if severity_score is not None:
        severity_score = int(severity_score)
        if severity_score < 0 or severity_score > 3:
            raise ApiError("'severity_score' must be 0, 1, 2 or 3.", 400)

    session.add(
        Verification(
            detection_id=det.id,
            technician_id=g.current_user.id,
            decision=decision,
            corrected_condition_id=corrected_id,
            severity_score=severity_score,
            notes=(data.get("notes") or None),
            is_demo=det.is_demo,
        )
    )

    # cannot_determine leaves the case unresolved rather than forcing a verdict.
    if decision == "correct":
        new_status = "technician_verified"
    elif decision == "corrected":
        new_status = "rejected"
    else:
        new_status = "low_confidence"

    session.execute(
        text("UPDATE detections SET status=:s WHERE id=:i"),
        {"s": new_status, "i": det.id},
    )
    session.commit()

    audit.record(
        g.current_user.id,
        "verify_detection",
        "detection",
        det.id,
        {"decision": decision, "corrected_condition_id": corrected_id,
         "severity_score": severity_score},
    )
    session.refresh(det)
    return jsonify({"detection_id": det.id, "status": det.status, "decision": decision}), 201


# ----------------------------------------------------------------- verification queue


@queue_bp.get("")
@requires_role("technician", "admin", "researcher")
def verification_queue():
    """Priority order, with the reason each item is here.

    The fourth stream is the important one: a random sample of HIGH-confidence
    predictions. Without it the queue only ever contains cases the model already found
    hard, the verified set becomes biased, and confident errors are never discovered.
    """
    session = SessionLocal()
    cfg = current_app.config["AGRISCAN"]
    limit = min(request.args.get("limit", default=50, type=int), 200)
    sample_rate = request.args.get(
        "sample_rate", default=cfg.QUEUE_CONFIDENCE_SAMPLE_RATE, type=float
    )

    reviewed = select(Verification.detection_id)
    open_detections = (
        select(Detection)
        .where(Detection.id.not_in(reviewed))
        .where(Detection.status.not_in(("technician_verified", "rejected")))
    )

    picked: dict[int, str] = {}
    rows: list[Detection] = []

    def take(stmt, reason: str, cap: int):
        for det in session.execute(stmt.limit(cap)).scalars().all():
            if det.id not in picked:
                picked[det.id] = reason
                rows.append(det)

    # a. low confidence first
    take(
        open_detections.where(Detection.status == "low_confidence")
        .order_by(Detection.created_at.asc()),
        "low_confidence",
        limit,
    )
    # b. high severity
    take(
        open_detections.where(Detection.severity_value.is_not(None))
        .order_by(Detection.severity_value.desc()),
        "high_severity",
        limit,
    )
    # c. farmer disagreed
    disagreed = select(FarmerFeedback.detection_id).where(FarmerFeedback.agrees.is_(False))
    take(
        open_detections.where(Detection.id.in_(disagreed))
        .order_by(Detection.created_at.asc()),
        "farmer_rejected",
        limit,
    )
    # d. random sample of confident predictions
    confident = (
        open_detections.where(Detection.status == "ai_detected")
        .where(Detection.confidence >= cfg.QUEUE_CONFIDENT_MIN)
        .order_by(func.rand())
    )
    sample_cap = max(1, int(limit * max(0.0, min(sample_rate, 1.0))))
    take(confident, "confidence_sample", sample_cap)

    out = []
    for det in rows[:limit]:
        image = session.get(Image, det.image_id)
        cond = session.get(Condition, det.condition_id) if det.condition_id else None
        model = session.get(ModelVersion, det.model_version_id)
        reason = picked[det.id]
        out.append(
            {
                "detection_id": det.id,
                "image_id": det.image_id,
                "queue_reason": reason,
                "queue_reason_label": QUEUE_REASONS[reason],
                "condition": cond.code if cond else "unknown",
                "condition_name": cond.common_name if cond else "Unknown",
                "confidence": float(det.confidence) if det.confidence is not None else None,
                "confidence_label": (
                    f"{float(det.confidence) * 100:.1f}% model confidence"
                    if det.confidence is not None
                    else "NOT_AVAILABLE"
                ),
                "severity": (
                    float(det.severity_value) if det.severity_value is not None else None
                ),
                "severity_method": det.severity_method or "NOT_AVAILABLE",
                "severity_status": "EXPERIMENTAL",
                "verification_status": det.status,
                "model_version": model.name if model else "MODEL_NOT_AVAILABLE",
                "bbox": det.bbox,
                "source": image.source if image else None,
                "field_id": image.field_id if image else None,
                "created_at": det.created_at.isoformat() if det.created_at else None,
            }
        )

    return jsonify(
        {
            "count": len(out),
            "sample_rate": sample_rate,
            "confident_min": cfg.QUEUE_CONFIDENT_MIN,
            "items": out,
        }
    )


# ------------------------------------------------------------------------- analysis


@analysis_bp.get("/confusion-matrix")
@requires_role("technician", "admin", "researcher")
def confusion_matrix():
    """Predicted versus technician-verified counts, built by JOIN.

    Never a maintained table. Regenerating it from the database is the whole point:
    if the numbers cannot be reproduced by a query, they cannot go in Chapter 4.
    """
    session = SessionLocal()

    stmt = (
        select(
            Detection.condition_id,
            Verification.decision,
            Verification.corrected_condition_id,
            func.count().label("n"),
        )
        .join(Verification, Verification.detection_id == Detection.id)
        .group_by(
            Detection.condition_id,
            Verification.decision,
            Verification.corrected_condition_id,
        )
    )

    model_version = request.args.get("model_version")
    if model_version:
        model = session.execute(
            select(ModelVersion).where(ModelVersion.name == model_version)
        ).scalar_one_or_none()
        stmt = stmt.where(Detection.model_version_id == (model.id if model else -1))

    date_from = request.args.get("date_from")
    if date_from:
        stmt = stmt.where(Verification.verified_at >= dt.datetime.fromisoformat(date_from))
    date_to = request.args.get("date_to")
    if date_to:
        stmt = stmt.where(Verification.verified_at <= dt.datetime.fromisoformat(date_to))

    if request.args.get("include_demo", "false").lower() != "true":
        stmt = stmt.where(Detection.is_demo.is_(False))

    codes = {
        c.id: c.code
        for c in session.execute(select(Condition)).scalars().all()
    }

    matrix: dict[str, dict[str, int]] = {}
    undetermined = 0
    for predicted_id, decision, corrected_id, count in session.execute(stmt).all():
        predicted = codes.get(predicted_id, "unknown")
        if decision == "cannot_determine":
            undetermined += count
            continue
        actual = (
            predicted if decision == "correct" else codes.get(corrected_id, "unknown")
        )
        matrix.setdefault(predicted, {})
        matrix[predicted][actual] = matrix[predicted].get(actual, 0) + count

    labels = sorted({*matrix.keys(), *(a for row in matrix.values() for a in row)})
    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix.get(label, {}).get(label, 0) for label in labels)

    per_class = {}
    for label in labels:
        tp = matrix.get(label, {}).get(label, 0)
        predicted_total = sum(matrix.get(label, {}).values())
        actual_total = sum(row.get(label, 0) for row in matrix.values())
        precision = tp / predicted_total if predicted_total else None
        recall = tp / actual_total if actual_total else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision and recall
            else None
        )
        per_class[label] = {
            "support_predicted": predicted_total,
            "support_verified": actual_total,
            "precision": round(precision, 4) if precision is not None else None,
            "recall": round(recall, 4) if recall is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        }

    # Counts are facts and are always returned. Derived metrics are claims, and are
    # withheld below the minimum sample size so a thin result cannot be quoted.
    min_required = current_app.config["AGRISCAN"].METRICS_MIN_VERIFIED
    sufficient = total >= min_required
    if not sufficient:
        for stats in per_class.values():
            stats["precision"] = stats["recall"] = stats["f1"] = None

    return jsonify(
        {
            "labels": labels,
            "matrix": matrix,
            "per_class": per_class,
            "verified_pairs": total,
            "min_required": min_required,
            "sufficient": sufficient,
            "metrics_message": (
                None if sufficient
                else "Metrics unavailable — insufficient validated samples."
            ),
            "overall_accuracy": (
                round(correct / total, 4) if total and sufficient else None
            ),
            "sampling_note": (
                "Computed over technician-reviewed detections. The review queue "
                "deliberately over-samples low-confidence and high-severity cases, so "
                "these figures describe the reviewed set, not the model on all images. "
                "Report model performance from the held-out test fields."
            ),
            "cannot_determine": undetermined,
            "note": (
                "Rows are the model's prediction, columns the technician's verified "
                "label. Built by query from detections joined to verifications."
                if total
                else "DATA_REQUIRED: no verified detections yet."
            ),
        }
    )


@analysis_bp.get("/agreement")
@requires_role("technician", "admin", "researcher")
def agreement():
    """Two research findings, cheap to collect and easy to forget to report."""
    session = SessionLocal()
    include_demo = request.args.get("include_demo", "false").lower() == "true"

    verifications = select(Verification).join(
        Detection, Detection.id == Verification.detection_id
    )
    if not include_demo:
        verifications = verifications.where(Detection.is_demo.is_(False))
    rows = session.execute(verifications).scalars().all()

    model_agreements = sum(1 for v in rows if v.decision == "correct")
    model_decided = sum(1 for v in rows if v.decision in ("correct", "corrected"))

    # Farmer versus technician: only detections where both have spoken.
    pairs = 0
    farmer_matches = 0
    for v in rows:
        if v.decision == "cannot_determine":
            continue
        feedback = session.execute(
            select(FarmerFeedback)
            .where(FarmerFeedback.detection_id == v.detection_id)
            .order_by(FarmerFeedback.created_at.desc())
        ).scalars().first()
        if feedback is None:
            continue
        pairs += 1
        technician_agreed = v.decision == "correct"
        if feedback.agrees == technician_agreed:
            farmer_matches += 1

    return jsonify(
        {
            "model_vs_technician": {
                "decided_cases": model_decided,
                "model_correct": model_agreements,
                "agreement_rate": (
                    round(model_agreements / model_decided, 4) if model_decided else None
                ),
                "note": (
                    "Share of technician-reviewed detections the model got right. "
                    "Not an accuracy figure for the model overall: the queue is "
                    "deliberately biased toward hard cases."
                ),
            },
            "farmer_vs_technician": {
                "paired_cases": pairs,
                "agreements": farmer_matches,
                "agreement_rate": round(farmer_matches / pairs, 4) if pairs else None,
                "note": (
                    "How often a farmer's judgement matched the technician's. "
                    "DATA_REQUIRED until farmers and technicians have reviewed the "
                    "same detections."
                ),
            },
        }
    )
