"""SQLAlchemy models. These mirror migrations/001_core_schema.sql exactly.

The SQL migrations are the source of truth for the schema; these classes are the
application's view of it. If you change one, change the other in the same commit.
"""

from __future__ import annotations

import datetime as dt

from app.utils.clock import utc_now

from sqlalchemy import (
    BigInteger,
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


ROLES = ("farmer", "technician", "researcher", "admin")
CONDITION_CATEGORIES = (
    "healthy", "fungal", "bacterial", "viral", "pest",
    "nutritional", "abiotic", "physical", "weed", "unknown",
)
DETECTION_STATUSES = (
    "ai_detected", "low_confidence", "farmer_confirmed",
    "technician_verified", "rejected",
)
CAPABILITY_STATUSES = (
    "DESIGNED", "IMPLEMENTED", "DATA_REQUIRED", "HARDWARE_REQUIRED",
    "EXPERIMENTAL", "VALIDATED", "NOT_VALIDATED", "DEMO",
)


def _now() -> dt.datetime:
    """Kept as a name for the column defaults; the definition lives in one place."""
    return utc_now()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(Enum(*ROLES), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    barangay: Mapped[str | None] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Tokens carry this as their password version; a mismatch is refused (migration 010).
    # Naive UTC, microsecond precision.
    password_changed_at: Mapped[dt.datetime | None] = mapped_column(DATETIME(fsp=6))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    farms: Mapped[list["Farm"]] = relationship(back_populates="owner")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "name": self.name,
            "barangay": self.barangay,
            "active": self.active,
            "is_demo": self.is_demo,
        }


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    barangay: Mapped[str | None] = mapped_column(String(120))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    owner: Mapped[User] = relationship(back_populates="farms")
    fields: Mapped[list["Field"]] = relationship(back_populates="farm")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "name": self.name,
            "barangay": self.barangay,
            "is_demo": self.is_demo,
        }


class Field(Base):
    __tablename__ = "fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # none_as_null: clearing a boundary stores SQL NULL, not the JSON text 'null'.
    boundary_geojson: Mapped[dict | None] = mapped_column(JSON(none_as_null=True))
    area_ha: Mapped[float | None] = mapped_column(Numeric(10, 4))
    variety: Mapped[str | None] = mapped_column(String(120))
    planting_date: Mapped[dt.date | None] = mapped_column(Date)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    farm: Mapped[Farm] = relationship(back_populates="fields")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "farm_id": self.farm_id,
            "name": self.name,
            "boundary_geojson": self.boundary_geojson,
            "area_ha": float(self.area_ha) if self.area_ha is not None else None,
            "variety": self.variety,
            "planting_date": self.planting_date.isoformat() if self.planting_date else None,
            "is_demo": self.is_demo,
        }


class Mission(Base):
    __tablename__ = "missions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), nullable=False)
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    flown_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    altitude_m: Mapped[float | None] = mapped_column(Numeric(6, 2))
    pattern: Mapped[str | None] = mapped_column(String(60))
    weather: Mapped[str | None] = mapped_column(String(160))
    wind_ms: Mapped[float | None] = mapped_column(Numeric(5, 2))
    aborted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abort_reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_id": self.field_id,
            "operator_id": self.operator_id,
            "flown_at": self.flown_at.isoformat() if self.flown_at else None,
            "altitude_m": float(self.altitude_m) if self.altitude_m is not None else None,
            "pattern": self.pattern,
            "weather": self.weather,
            "wind_ms": float(self.wind_ms) if self.wind_ms is not None else None,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "notes": self.notes,
            "is_demo": self.is_demo,
        }


class Condition(Base):
    __tablename__ = "conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    common_name: Mapped[str] = mapped_column(String(160), nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(Enum(*CONDITION_CATEGORIES), nullable=False)
    tier: Mapped[int | None] = mapped_column(SmallInteger)
    plant_part: Mapped[str | None] = mapped_column(String(60))
    # Rule 6: may a drone frame carry this label? Taxonomy, not worker logic.
    aerial_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code": self.code,
            "common_name": self.common_name,
            "scientific_name": self.scientific_name,
            "category": self.category,
            "tier": self.tier,
            "plant_part": self.plant_part,
            "aerial_allowed": self.aerial_allowed,
        }


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    architecture: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_version: Mapped[str | None] = mapped_column(String(120))
    trained_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    conf_threshold: Mapped[float | None] = mapped_column(Numeric(5, 4))
    margin_threshold: Mapped[float | None] = mapped_column(Numeric(5, 4))
    imaging_mode: Mapped[str] = mapped_column(
        Enum("ground", "aerial"), default="ground", nullable=False
    )
    deployment_status: Mapped[str] = mapped_column(
        Enum("training", "staged", "production", "retired"),
        default="training", nullable=False,
    )
    capability_status: Mapped[str] = mapped_column(
        Enum(*CAPABILITY_STATUSES), default="NOT_VALIDATED", nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "architecture": self.architecture,
            "dataset_version": self.dataset_version or "DATA_REQUIRED",
            "trained_at": self.trained_at.isoformat() if self.trained_at else None,
            "metrics": self.metrics_json or "NOT_VALIDATED",
            "imaging_mode": self.imaging_mode,
            "deployment_status": self.deployment_status,
            "capability_status": self.capability_status,
        }


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    # Generated on the phone before upload; makes an offline retry idempotent.
    client_uuid: Mapped[str | None] = mapped_column(String(36), unique=True)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"))
    capture_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("capture_sessions.id")
    )
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), nullable=False)
    source: Mapped[str] = mapped_column(Enum("drone", "phone"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    lat: Mapped[float | None] = mapped_column(Numeric(10, 7))
    lon: Mapped[float | None] = mapped_column(Numeric(10, 7))
    gps_accuracy_m: Mapped[float | None] = mapped_column(Numeric(8, 2))
    gps_altitude_m: Mapped[float | None] = mapped_column(Numeric(8, 2))
    from_video_offset_s: Mapped[float | None] = mapped_column(Numeric(8, 2))
    gps_source: Mapped[str] = mapped_column(
        Enum("exif", "apm_log", "manual", "device", "missing", "video_interpolated"),
        default="missing", nullable=False,
    )
    captured_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    growth_stage: Mapped[str | None] = mapped_column(String(40))
    quality_flag: Mapped[str | None] = mapped_column(
        Enum("ok", "blurred", "dark", "overexposed", "unreadable")
    )
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CaptureDevice(Base):
    """A phone registered to take photos on command. Not a user account."""

    __tablename__ = "capture_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    registered_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    # Set whenever an operator pulls a viewfinder frame (migration 011). In the database
    # rather than in process memory, so the dashboard and the phone can be talking to
    # two different server processes and still agree.
    preview_requested_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    # What the phone itself says it is doing, reported on every poll (migration 013).
    reported_session_id: Mapped[int | None] = mapped_column(BigInteger)
    reported_state: Mapped[str | None] = mapped_column(String(20))
    battery_pct: Mapped[int | None] = mapped_column(SmallInteger)
    charging: Mapped[bool | None] = mapped_column(Boolean)
    gps_accuracy_m: Mapped[float | None] = mapped_column(Numeric(8, 2))
    camera_ready: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    capabilities: Mapped[dict | None] = mapped_column(JSON)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CaptureSession(Base):
    """One armed capture run. max_duration_s is mandatory — see migration 008."""

    __tablename__ = "capture_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("capture_devices.id"), nullable=False)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), nullable=False)
    mission_id: Mapped[int | None] = mapped_column(ForeignKey("missions.id"))
    interval_s: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    max_duration_s: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    max_shots: Mapped[int | None] = mapped_column(SmallInteger)
    # The last time the phone reported progress for this session. Distinguishes "the
    # phone ran it and captured nothing" from "the phone never picked it up".
    last_report_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    # Flight video and its 1 Hz position track (migration 012). Both are files on disk;
    # only the pointers live here.
    video_path: Mapped[str | None] = mapped_column(String(512))
    video_bytes: Mapped[int | None] = mapped_column(BigInteger)
    video_duration_s: Mapped[float | None] = mapped_column(Numeric(8, 2))
    video_mime: Mapped[str | None] = mapped_column(String(80))
    video_uploaded_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    track_path: Mapped[str | None] = mapped_column(String(512))
    track_points: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        Enum("armed", "running", "stopped", "completed", "expired", "failed"),
        default="armed", nullable=False,
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    end_reason: Mapped[str | None] = mapped_column(String(160))
    shots_reported: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ProcessingVersion(Base):
    """Immutable snapshot of the pipeline configuration. See migration 009."""

    __tablename__ = "processing_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Detection(Base):
    """Immutable once written. Corrections go to Verification. See migration 002."""

    __tablename__ = "detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), nullable=False)
    condition_id: Mapped[int | None] = mapped_column(ForeignKey("conditions.id"))
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4))
    bbox: Mapped[dict | None] = mapped_column(JSON)
    severity_value: Mapped[float | None] = mapped_column(Numeric(6, 3))
    severity_method: Mapped[str | None] = mapped_column(String(60))
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("model_versions.id"), nullable=False
    )
    # Which gate settings and severity method produced this row. NULL only for rows
    # written before migration 009. See app/services/processing_version.py.
    processing_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("processing_versions.id")
    )
    status: Mapped[str] = mapped_column(
        Enum(*DETECTION_STATUSES), default="ai_detected", nullable=False
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Verification(Base):
    __tablename__ = "verifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detection_id: Mapped[int] = mapped_column(ForeignKey("detections.id"), nullable=False)
    technician_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(
        Enum("correct", "corrected", "cannot_determine"), nullable=False
    )
    corrected_condition_id: Mapped[int | None] = mapped_column(ForeignKey("conditions.id"))
    severity_score: Mapped[int | None] = mapped_column(SmallInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class FarmerFeedback(Base):
    __tablename__ = "farmer_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detection_id: Mapped[int] = mapped_column(ForeignKey("detections.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    agrees: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    publisher: Mapped[str] = mapped_column(String(160), nullable=False)
    year: Mapped[int | None] = mapped_column(SmallInteger)
    url: Mapped[str | None] = mapped_column(String(512))
    locator: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    detection_id: Mapped[int] = mapped_column(ForeignKey("detections.id"), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_refs: Mapped[dict | None] = mapped_column(JSON)
    generated_by: Mapped[str | None] = mapped_column(String(120))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(
        Enum("pending", "approved", "rejected"), default="pending", nullable=False
    )
    cache_key: Mapped[str | None] = mapped_column(String(160))
    severity_band: Mapped[str | None] = mapped_column(String(20))
    growth_stage: Mapped[str | None] = mapped_column(String(40))
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    @property
    def is_visible_to_farmer(self) -> bool:
        """Rule 4: unapproved recommendations are never shown as advice."""
        return self.approved_by is not None and self.status == "approved"


class KnowledgeBase(Base):
    """Curated agronomic guidance, one record per condition.

    content_status is the honesty flag: PLACEHOLDER rows are seeded stubs and must
    never reach a farmer as advice, even after a technician approves the wrapper text.
    """

    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    condition_id: Mapped[int] = mapped_column(ForeignKey("conditions.id"), nullable=False)
    identification_cues: Mapped[str | None] = mapped_column(Text)
    cultural_measures: Mapped[str | None] = mapped_column(Text)
    preventive_measures: Mapped[str | None] = mapped_column(Text)
    monitoring_guidance: Mapped[str | None] = mapped_column(Text)
    when_to_call: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_sources.id"))
    content_status: Mapped[str] = mapped_column(
        Enum("PLACEHOLDER", "DRAFT", "REVIEWED"), default="PLACEHOLDER", nullable=False
    )
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    def to_record(self) -> dict:
        return {
            "identification_cues": self.identification_cues,
            "cultural_measures": self.cultural_measures,
            "preventive_measures": self.preventive_measures,
            "monitoring_guidance": self.monitoring_guidance,
            "when_to_call": self.when_to_call,
            "content_status": self.content_status,
            "source_id": self.source_id,
        }


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), nullable=False)
    annotator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    condition_id: Mapped[int] = mapped_column(ForeignKey("conditions.id"), nullable=False)
    bbox: Mapped[dict | None] = mapped_column(JSON)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(80))
    object_id: Mapped[str | None] = mapped_column(String(80))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
