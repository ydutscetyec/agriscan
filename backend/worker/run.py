"""Inference worker. Separate process, polls the jobs table, no Redis.

Run with:  python -m worker.run

Refuses to start if no model_versions row is marked 'production'. Guessing which model
produced a detection is worse than not running, because an untraceable detection cannot
appear in Chapter 4 at all.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import signal
import sys
import time
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.exc import DBAPIError, OperationalError  # noqa: E402

from app.config import Config, get_config  # noqa: E402
from app.extensions import SessionLocal, init_engine  # noqa: E402
from app.inference import (  # noqa: E402
    MODEL_NOT_AVAILABLE,
    apply_uncertainty,
    build_detector,
    build_palay_gate,
    compute_severity,
)
from app.models import Condition, Detection, Image, ModelVersion  # noqa: E402
from app.services import processing_version as pv_service
from app.services import quality  # noqa: E402
from app.services.storage import resolve_stored  # noqa: E402

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s [worker] %(message)s"
)
log = logging.getLogger("worker")

NON_PALAY_MESSAGE = "Non-palay image detected."
UNKNOWN_MESSAGE = "Unknown condition — technician review required."

_running = True


class NoProductionModel(RuntimeError):
    pass


# The same missing model would otherwise be logged every poll — twice a second of
# identical lines, which buries everything else.
_WARNED: dict[str, float] = {}
WARN_EVERY_S = 300


def _warn_once(message: str) -> None:
    now = time.monotonic()
    if now - _WARNED.get(message, -1e9) >= WARN_EVERY_S:
        _WARNED[message] = now
        log.warning("%s Queued jobs for that mode wait; the rest carry on.", message)


# Loading YOLO weights takes seconds and hundreds of MB. Building a detector per job
# reloaded them for every photo. One detector per model name, kept for the process.
# The stub is deliberately not cached: it is cheap, and tests change its configured
# output between runs.
_DETECTORS: dict[tuple[str, str], object] = {}


def detector_for(cfg: Config, model_name: str):
    if cfg.DETECTOR_IMPL != "yolo":
        return build_detector(cfg, model_name)
    key = (cfg.DETECTOR_IMPL, model_name)
    if key not in _DETECTORS:
        _DETECTORS[key] = build_detector(cfg, model_name)
    return _DETECTORS[key]


def recover_stale_jobs(session, cfg: Config) -> int:
    """Put back jobs left RUNNING by a worker that died mid-job.

    Without this a crash, a closed terminal or a laptop going to sleep leaves the job
    claimed forever and its photo never gets a result. A recovered job keeps its attempt
    count, so a photo that crashes the worker every time still ends as FAILED.
    """
    result = session.execute(
        text(
            "UPDATE jobs SET status = IF(attempts >= :max, 'FAILED', 'RETRYING'), "
            "claimed_by = NULL, "
            "error = CONCAT('Recovered after the worker stopped mid-job. ', COALESCE(error, '')) "
            "WHERE status = 'RUNNING' "
            "AND started_at < NOW() - INTERVAL :mins MINUTE"
        ),
        {"max": cfg.WORKER_MAX_ATTEMPTS, "mins": cfg.WORKER_STALE_JOB_MINUTES},
    )
    session.commit()
    return result.rowcount or 0


def stub_refused(cfg: Config) -> str | None:
    """Why this worker must not run, or None. Production only."""
    if cfg.is_production and cfg.DETECTOR_IMPL == "stub" and not cfg.ALLOW_STUB_DETECTOR:
        return (
            "AGRISCAN_DETECTOR_IMPL is 'stub' on a production server. The stub writes the "
            "same synthetic diagnosis for every photo, and farmers would see it as real. "
            "Register a trained model (python -m scripts.register_model) and set "
            "AGRISCAN_DETECTOR_IMPL=yolo. Photos stay queued until then."
        )
    return None


def _stop(*_args):
    global _running
    _running = False
    log.info("Shutdown requested; finishing current job.")


def production_model(session, imaging_mode: str) -> ModelVersion:
    """The only source of model_version_id. No fallback, no default."""
    model = session.execute(
        select(ModelVersion)
        .where(ModelVersion.deployment_status == "production")
        .where(ModelVersion.imaging_mode == imaging_mode)
        .order_by(ModelVersion.id.desc())
    ).scalars().first()
    if model is None:
        raise NoProductionModel(
            f"{MODEL_NOT_AVAILABLE}: no model_versions row with "
            f"deployment_status='production' and imaging_mode='{imaging_mode}'. "
            "Worker refuses to run rather than guess."
        )
    return model


def thresholds_for(model: ModelVersion, cfg: Config) -> tuple[float, float]:
    """Model row overrides config, so a threshold is traceable to its model."""
    conf = float(model.conf_threshold) if model.conf_threshold is not None else cfg.CONF_THRESHOLD
    margin = (
        float(model.margin_threshold)
        if model.margin_threshold is not None
        else cfg.MARGIN_THRESHOLD
    )
    return conf, margin


def condition_by_code(session, code: str) -> Condition | None:
    return session.execute(
        select(Condition).where(Condition.code == code)
    ).scalar_one_or_none()


def filter_aerial_predictions(session, predictions, source: str):
    """Rule 6: a drone frame may not produce a fine-grained disease label.

    Which codes are aerial-legal is taxonomy (conditions.aerial_allowed), not worker
    logic, so widening it is a deliberate, reviewable database change.
    """
    if source != "drone":
        return predictions, []
    kept, dropped = [], []
    for pred in predictions:
        cond = condition_by_code(session, pred.condition_code)
        if cond is not None and cond.aerial_allowed:
            kept.append(pred)
        else:
            dropped.append(pred.condition_code)
            log.warning(
                "Dropped aerial prediction '%s': not aerial_allowed. A 15-30 m RGB "
                "frame cannot resolve lesion-level disease.",
                pred.condition_code,
            )
    return kept, dropped


def claim_job(session, worker_id: str) -> dict | None:
    """Claim one queued job atomically: UPDATE first, then read it back."""
    session.execute(
        text(
            "UPDATE jobs SET status='RUNNING', claimed_by=:w, started_at=NOW(), "
            "attempts = attempts + 1 "
            "WHERE status IN ('QUEUED','RETRYING') "
            "ORDER BY priority DESC, id ASC LIMIT 1"
        ),
        {"w": worker_id},
    )
    session.commit()
    row = session.execute(
        text(
            "SELECT id, payload, attempts FROM jobs "
            "WHERE claimed_by=:w AND status='RUNNING' ORDER BY id ASC LIMIT 1"
        ),
        {"w": worker_id},
    ).fetchone()
    if row is None:
        return None
    payload = row[1]
    if isinstance(payload, (str, bytes)):
        payload = json.loads(payload)
    return {"id": row[0], "payload": payload or {}, "attempts": row[2]}


def finish_job(
    session, job_id: int, status: str,
    error: str | None = None, result: str | None = None,
) -> None:
    """Results and errors go in different columns: a completed job with a summary in
    `error` reads as a failure to anyone scanning the table."""
    session.execute(
        text(
            "UPDATE jobs SET status=:s, error=:e, result=:r, completed_at=NOW(), "
            "claimed_by=NULL WHERE id=:i"
        ),
        {"s": status, "e": error, "r": result, "i": job_id},
    )
    session.commit()


def process_image(session, image: Image, cfg: Config) -> dict:
    """S1 -> S2 -> S3 -> S4 -> S5. Returns a summary for the job log."""
    model = production_model(session, "aerial" if image.source == "drone" else "ground")
    conf_threshold, margin_threshold = thresholds_for(model, cfg)

    # --- S1 quality -------------------------------------------------------------
    path = str(resolve_stored(image.file_path))
    verdict = quality.assess(path, cfg)
    image.quality_flag = verdict["flag"]
    session.commit()
    if not verdict["passed"]:
        log.info("Image %s rejected by quality gate: %s", image.id, verdict["flag"])
        return {"outcome": "quality_rejected", "quality": verdict, "detections": 0}

    # --- S2 palay gate ----------------------------------------------------------
    gate = build_palay_gate(cfg)
    is_palay, palay_conf = gate.is_palay(path)
    if not is_palay:
        log.info("Image %s rejected by palay gate (conf %.3f)", image.id, palay_conf)
        return {
            "outcome": "not_palay",
            "message": NON_PALAY_MESSAGE,
            "palay_confidence": round(palay_conf, 4),
            "detections": 0,
        }

    # --- S3 detection -----------------------------------------------------------
    detector = detector_for(cfg, model.name)
    predictions = detector.predict(path, image.source)
    predictions, dropped = filter_aerial_predictions(session, predictions, image.source)

    # --- S4 uncertainty ---------------------------------------------------------
    decision = apply_uncertainty(predictions, conf_threshold, margin_threshold)

    # --- S5 severity ------------------------------------------------------------
    width, height = _image_dimensions(path)
    severity = compute_severity(predictions, width, height)

    # Record WHICH configuration produced these rows (PROMISE pp. xviii, 21, adapted).
    pv_id = pv_service.get_or_create(
        session,
        pv_service.snapshot(cfg, conf_threshold, margin_threshold, severity["severity_method"]),
    )

    unknown = condition_by_code(session, "unknown")
    rows = 0

    if decision["low_confidence"] or decision["answer"] is None:
        session.add(
            Detection(
                image_id=image.id,
                condition_id=unknown.id if unknown else None,
                confidence=(
                    round(decision["answer"].confidence, 4) if decision["answer"] else None
                ),
                bbox=decision["answer"].bbox if decision["answer"] else None,
                severity_value=severity["severity_value"],
                severity_method=severity["severity_method"],
                model_version_id=model.id,
                processing_version_id=pv_id,
                status="low_confidence",
                is_demo=image.is_demo,
            )
        )
        rows = 1
    else:
        for pred in predictions:
            cond = condition_by_code(session, pred.condition_code)
            if cond is None:
                log.warning("Unknown condition code '%s' from detector", pred.condition_code)
                continue
            session.add(
                Detection(
                    image_id=image.id,
                    condition_id=cond.id,
                    confidence=round(pred.confidence, 4),
                    bbox=pred.bbox or None,
                    severity_value=severity["severity_value"],
                    severity_method=severity["severity_method"],
                    model_version_id=model.id,
                processing_version_id=pv_id,
                    status="ai_detected",
                    is_demo=image.is_demo,
                )
            )
            rows += 1
    session.commit()

    return {
        "outcome": "low_confidence" if decision["low_confidence"] else "detected",
        "reason": decision["reason"],
        "dropped_aerial_labels": dropped,
        "model_version": model.name,
        "processing_version_id": pv_id,
        "detections": rows,
        "severity": severity,
    }


def _image_dimensions(path: str) -> tuple[int, int]:
    try:
        from PIL import Image as PILImage

        with PILImage.open(path) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001
        return 0, 0


def run_once(session, cfg: Config, worker_id: str) -> bool:
    job = claim_job(session, worker_id)
    if job is None:
        return False
    image_id = job["payload"].get("image_id")
    log.info("Job %s: image %s", job["id"], image_id)
    try:
        image = session.get(Image, int(image_id))
        if image is None:
            finish_job(session, job["id"], "FAILED", f"image {image_id} not found")
            return True
        summary = process_image(session, image, cfg)
        finish_job(session, job["id"], "COMPLETED", result=json.dumps(summary)[:60000])
    except NoProductionModel as exc:
        # Not the job's fault, and not a reason to stop the worker: a drone photo with no
        # aerial model registered must not take the phone photos down with it. The job
        # goes back on the queue untouched, so it is analysed the moment a model for its
        # mode exists, and the worker carries on with everything else.
        session.execute(
            text("UPDATE jobs SET status='QUEUED', claimed_by=NULL, error=:e WHERE id=:i"),
            {"e": str(exc), "i": job["id"]},
        )
        session.commit()
        _warn_once(str(exc))
        return False
    except Exception as exc:  # noqa: BLE001
        log.exception("Job %s failed", job["id"])
        status = "RETRYING" if job["attempts"] < cfg.WORKER_MAX_ATTEMPTS else "FAILED"
        finish_job(session, job["id"], status, str(exc)[:60000])
    return True


def main() -> int:
    cfg = get_config()
    cfg.validate()
    refused = stub_refused(cfg)
    if refused:
        log.error(refused)
        return 2
    init_engine(cfg.sqlalchemy_uri)
    session = SessionLocal()
    worker_id = f"worker-{uuid.uuid4().hex[:12]}"

    # Fail fast and loudly, before touching the queue.
    # At least one production model must exist, or there is nothing this worker can do.
    # A mode that is missing only parks that mode's jobs; it is not a reason to refuse
    # to start, because the other mode's photos are still analysable.
    available = []
    for mode in ("ground", "aerial"):
        try:
            model = production_model(session, mode)
            available.append(mode)
            log.info("Production %s model: %s (%s)", mode, model.name, model.architecture)
        except NoProductionModel as exc:
            log.warning("No %s model. %s", mode, exc)
    if not available:
        log.error("No production model for any imaging mode. Register one: "
                  "python -m scripts.register_model")
        return 2

    recovered = recover_stale_jobs(session, cfg)
    if recovered:
        log.warning("Recovered %d job(s) left running by a stopped worker.", recovered)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    log.info("%s polling every %.1fs", worker_id, cfg.WORKER_POLL_SECONDS)

    # A database restart (XAMPP stopped, laptop asleep) must not kill the worker: it
    # waits and reconnects. Backoff from the poll interval up to one minute.
    db_backoff = cfg.WORKER_POLL_SECONDS
    idle_polls = 0
    while _running:
        try:
            did_work = run_once(session, cfg, worker_id)
            db_backoff = cfg.WORKER_POLL_SECONDS
        except NoProductionModel as exc:
            # Reached only if a model is retired while the worker runs. Park it and keep
            # going; stopping would leave every other queued photo unanalysed too.
            _warn_once(str(exc))
            did_work = False
        except (OperationalError, DBAPIError) as exc:
            log.warning("Database unavailable (%s). Retrying in %.0fs.",
                        exc.__class__.__name__, db_backoff)
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
            SessionLocal.remove()
            session = SessionLocal()
            time.sleep(db_backoff)
            db_backoff = min(db_backoff * 2, 60.0)
            continue
        if did_work:
            idle_polls = 0
            continue
        idle_polls += 1
        # Roughly every five minutes of idling, sweep for jobs another worker abandoned.
        if idle_polls * cfg.WORKER_POLL_SECONDS >= 300:
            idle_polls = 0
            try:
                n = recover_stale_jobs(session, cfg)
                if n:
                    log.warning("Recovered %d stale job(s).", n)
            except (OperationalError, DBAPIError):
                session.rollback()
        time.sleep(cfg.WORKER_POLL_SECONDS)
    SessionLocal.remove()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
