"""API blueprint registration."""

from __future__ import annotations

from app.api.capture import bp as capture_bp, fields_summary_bp
from app.api.conditions import bp as conditions_bp
from app.api.dashboard import detail_bp, files_bp, models_bp, people_bp
from app.api.images import detections_bp, images_bp
from app.api.recommendations import bp as recommendations_bp
from app.api.trackb import bp as trackb_bp
from app.api.resources import farms_bp, fields_bp, missions_bp, users_bp
from app.api.verification import analysis_bp, queue_bp, verify_bp

ALL_BLUEPRINTS = (
    users_bp, farms_bp, fields_bp, missions_bp, conditions_bp,
    images_bp, detections_bp,
    files_bp, detail_bp, models_bp, people_bp,
    verify_bp, queue_bp, analysis_bp,
    recommendations_bp,
    trackb_bp,
    capture_bp, fields_summary_bp,
)
