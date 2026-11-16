"""Configuration. Every credential and path comes from the environment."""

from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field

from dotenv import load_dotenv

# backend/. Relative paths in configuration are resolved against this directory, never
# against the current working directory: the web server, the worker and the scripts are
# started from different places, and every one of them must find the same image store.
BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]

# Load backend/.env before any Config field reads os.environ. override=False means a
# variable already set in the shell wins, so tests and one-off overrides still work.
load_dotenv(BACKEND_DIR / ".env", override=False)

# Values that must never reach a public server. The first is the test fixture's secret,
# the rest are the placeholders shipped in the example files.
_KNOWN_BAD_SECRETS = {
    "test-secret-not-for-production",
    "change-me",
    "changeme",
    "secret",
}


def resolve_path(value: str | os.PathLike) -> pathlib.Path:
    """Absolute path for a configured location. Relative means relative to backend/."""
    path = pathlib.Path(value)
    return path if path.is_absolute() else (BACKEND_DIR / path).resolve()


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # --- environment --------------------------------------------------------
    # 'production' turns on the checks a public server needs: a strong secret, a real
    # database password, HSTS, and a worker that refuses to run the stub detector.
    ENV: str = field(default_factory=lambda: os.environ.get("AGRISCAN_ENV", "development").strip().lower())

    # --- database -----------------------------------------------------------
    DB_HOST: str = field(default_factory=lambda: os.environ.get("AGRISCAN_DB_HOST", "127.0.0.1"))
    DB_PORT: int = field(default_factory=lambda: _int("AGRISCAN_DB_PORT", 3306))
    DB_USER: str = field(default_factory=lambda: os.environ.get("AGRISCAN_DB_USER", "agriscan"))
    DB_PASSWORD: str = field(default_factory=lambda: os.environ.get("AGRISCAN_DB_PASSWORD", ""))
    DB_NAME: str = field(default_factory=lambda: os.environ.get("AGRISCAN_DB_NAME", "agriscan"))

    # --- auth ---------------------------------------------------------------
    SECRET_KEY: str = field(default_factory=lambda: os.environ.get("AGRISCAN_SECRET_KEY", ""))
    TOKEN_TTL_MINUTES: int = field(default_factory=lambda: _int("AGRISCAN_TOKEN_TTL_MINUTES", 720))
    PASSWORD_MIN_LENGTH: int = field(default_factory=lambda: _int("AGRISCAN_PASSWORD_MIN_LENGTH", 10))

    # --- storage ------------------------------------------------------------
    IMAGE_ROOT: str = field(default_factory=lambda: os.environ.get("AGRISCAN_IMAGE_ROOT", "./data/images"))
    MODEL_ROOT: str = field(default_factory=lambda: os.environ.get("AGRISCAN_MODEL_ROOT", "./ml/models"))

    # --- growth stage rule (configurable; see services/growth_stage.py) ------
    # Days after transplanting at which each stage ENDS.
    GS_VEGETATIVE_END_DAT: int = field(default_factory=lambda: _int("AGRISCAN_GS_VEGETATIVE_END_DAT", 55))
    GS_REPRODUCTIVE_END_DAT: int = field(default_factory=lambda: _int("AGRISCAN_GS_REPRODUCTIVE_END_DAT", 90))
    GS_RIPENING_END_DAT: int = field(default_factory=lambda: _int("AGRISCAN_GS_RIPENING_END_DAT", 125))
    GS_RULE_VERSION: str = field(default_factory=lambda: os.environ.get("AGRISCAN_GS_RULE_VERSION", "dat-v1"))


    # --- upload / ingest ----------------------------------------------------
    # A ten-minute 1080p clip is roughly 100-150 MB. The ceiling is generous because
    # refusing a flight's only video after it has already been uploaded over mobile data
    # would be the worst possible moment to say no.
    MAX_VIDEO_BYTES: int = field(default_factory=lambda: _int("AGRISCAN_MAX_VIDEO_BYTES", 600 * 1024 * 1024))
    MAX_UPLOAD_BYTES: int = field(default_factory=lambda: _int("AGRISCAN_MAX_UPLOAD_BYTES", 15 * 1024 * 1024))
    ALLOWED_IMAGE_MIME: tuple = field(default_factory=lambda: ("image/jpeg", "image/png"))
    ALLOWED_IMAGE_EXT: tuple = field(default_factory=lambda: (".jpg", ".jpeg", ".png"))

    # --- quality gate S1 (thresholds are configuration, not constants) -------
    QG_BLUR_LAPLACIAN_VAR_MIN: float = field(default_factory=lambda: _float("AGRISCAN_QG_BLUR_VAR_MIN", 100.0))
    QG_LUMA_MIN: float = field(default_factory=lambda: _float("AGRISCAN_QG_LUMA_MIN", 40.0))
    QG_LUMA_MAX: float = field(default_factory=lambda: _float("AGRISCAN_QG_LUMA_MAX", 215.0))
    QG_CLIP_FRACTION_MAX: float = field(default_factory=lambda: _float("AGRISCAN_QG_CLIP_FRACTION_MAX", 0.25))

    # --- palay gate S2 ------------------------------------------------------
    PALAY_GATE_IMPL: str = field(default_factory=lambda: os.environ.get("AGRISCAN_PALAY_GATE_IMPL", "stub"))
    PALAY_CONF_MIN: float = field(default_factory=lambda: _float("AGRISCAN_PALAY_CONF_MIN", 0.50))

    # --- detection S3 / uncertainty S4 --------------------------------------
    # Defaults only. A model_versions row with its own thresholds overrides these,
    # so a threshold is always traceable to the model it was selected for.
    DETECTOR_IMPL: str = field(default_factory=lambda: os.environ.get("AGRISCAN_DETECTOR_IMPL", "stub"))
    CONF_THRESHOLD: float = field(default_factory=lambda: _float("AGRISCAN_CONF_THRESHOLD", 0.50))
    MARGIN_THRESHOLD: float = field(default_factory=lambda: _float("AGRISCAN_MARGIN_THRESHOLD", 0.10))
    STUB_DETECTOR_RESULT: str = field(default_factory=lambda: os.environ.get("AGRISCAN_STUB_DETECTOR_RESULT", ""))

    # --- worker -------------------------------------------------------------
    WORKER_POLL_SECONDS: float = field(default_factory=lambda: _float("AGRISCAN_WORKER_POLL_SECONDS", 2.0))
    WORKER_MAX_ATTEMPTS: int = field(default_factory=lambda: _int("AGRISCAN_WORKER_MAX_ATTEMPTS", 3))

    # --- serving (p21) ------------------------------------------------------
    # How many reverse proxies sit in front of the app (Caddy, cloudflared). 0 means
    # none, so X-Forwarded-* headers are ignored and cannot be spoofed by a client.
    PROXY_HOPS: int = field(default_factory=lambda: _int("AGRISCAN_PROXY_HOPS", 0))
    LOG_DIR: str = field(default_factory=lambda: os.environ.get("AGRISCAN_LOG_DIR", "./logs"))
    WEB_DIST: str = field(default_factory=lambda: os.environ.get("AGRISCAN_WEB_DIST", "../web/dist"))

    # --- sign-in limits (p21) -----------------------------------------------
    # Counted from audit_log, so they hold across server restarts and threads.
    LOGIN_MAX_FAILURES_PER_NAME: int = field(
        default_factory=lambda: _int("AGRISCAN_LOGIN_MAX_FAILURES_PER_NAME", 8))
    LOGIN_MAX_FAILURES_PER_IP: int = field(
        default_factory=lambda: _int("AGRISCAN_LOGIN_MAX_FAILURES_PER_IP", 30))
    LOGIN_WINDOW_MINUTES: int = field(
        default_factory=lambda: _int("AGRISCAN_LOGIN_WINDOW_MINUTES", 15))

    # --- worker reliability (p21) -------------------------------------------
    # A job still RUNNING after this long belongs to a worker that died mid-job.
    WORKER_STALE_JOB_MINUTES: int = field(
        default_factory=lambda: _int("AGRISCAN_WORKER_STALE_JOB_MINUTES", 10))
    # The stub detector writes the same synthetic result for every photo. On a real
    # server that is a fabricated diagnosis, so production refuses it unless this is set.
    ALLOW_STUB_DETECTOR: bool = field(
        default_factory=lambda: os.environ.get("AGRISCAN_ALLOW_STUB_DETECTOR", "false").lower() == "true")

    CORS_ORIGINS: tuple = field(default_factory=lambda: tuple(
        o.strip() for o in os.environ.get(
            "AGRISCAN_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",") if o.strip()
    ))

    # --- verification queue (Prompt 4) --------------------------------------
    # The confident-sample stream is what surfaces confident errors. Rate and the
    # "confident" cutoff are configuration so they can be tuned without a code change.
    QUEUE_CONFIDENCE_SAMPLE_RATE: float = field(
        default_factory=lambda: _float("AGRISCAN_QUEUE_SAMPLE_RATE", 0.10))
    QUEUE_CONFIDENT_MIN: float = field(
        default_factory=lambda: _float("AGRISCAN_QUEUE_CONFIDENT_MIN", 0.80))

    # --- recommendations (Prompt 4) -----------------------------------------
    PHRASER_IMPL: str = field(
        default_factory=lambda: os.environ.get("AGRISCAN_PHRASER_IMPL", "template"))
    LLM_API_KEY: str = field(
        default_factory=lambda: os.environ.get("AGRISCAN_LLM_API_KEY", ""))

    # --- camera geometry (Track B planner) ----------------------------------
    # Placeholders for arithmetic, NOT a description of your handset. Measure the
    # actual sensor and lens before planning a survey.
    CAMERA_PIXEL_PITCH_UM: float = field(
        default_factory=lambda: _float("AGRISCAN_CAMERA_PIXEL_PITCH_UM", 1.0))
    CAMERA_FOCAL_LENGTH_MM: float = field(
        default_factory=lambda: _float("AGRISCAN_CAMERA_FOCAL_LENGTH_MM", 4.7))
    CAMERA_IMAGE_WIDTH_PX: int = field(
        default_factory=lambda: _int("AGRISCAN_CAMERA_IMAGE_WIDTH_PX", 4000))
    CAMERA_IMAGE_HEIGHT_PX: int = field(
        default_factory=lambda: _int("AGRISCAN_CAMERA_IMAGE_HEIGHT_PX", 3000))
    CAMERA_LABEL: str = field(
        default_factory=lambda: os.environ.get("AGRISCAN_CAMERA_LABEL", "UNVERIFIED_CAMERA"))

    # --- research metrics --------------------------------------------------
    # Below this many technician-verified pairs, derived metrics are withheld.
    # A precision figure from eight samples looks exactly like one from eight hundred.
    METRICS_MIN_VERIFIED: int = field(
        default_factory=lambda: _int("AGRISCAN_METRICS_MIN_VERIFIED", 30))

    # --- demo ---------------------------------------------------------------
    DEMO_MODE: bool = field(default_factory=lambda: os.environ.get("AGRISCAN_DEMO_MODE", "false").lower() == "true")

    TESTING: bool = False

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def image_root_path(self) -> pathlib.Path:
        return resolve_path(self.IMAGE_ROOT)

    @property
    def model_root_path(self) -> pathlib.Path:
        return resolve_path(self.MODEL_ROOT)

    @property
    def log_dir_path(self) -> pathlib.Path:
        return resolve_path(self.LOG_DIR)

    @property
    def web_dist_path(self) -> pathlib.Path:
        return resolve_path(self.WEB_DIST)

    @property
    def max_request_bytes(self) -> int:
        """Whole-request ceiling: the image limit plus room for the form fields."""
        return max(self.MAX_UPLOAD_BYTES, self.MAX_VIDEO_BYTES) + 1024 * 1024

    @property
    def sqlalchemy_uri(self) -> str:
        from urllib.parse import quote_plus

        pw = quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{self.DB_USER}:{pw}@{self.DB_HOST}:{self.DB_PORT}/"
            f"{self.DB_NAME}?charset=utf8mb4"
        )

    def validate(self) -> None:
        if not self.SECRET_KEY:
            raise RuntimeError(
                "AGRISCAN_SECRET_KEY is not set. Refusing to start with a default secret."
            )
        if self.ENV not in ("development", "production"):
            raise RuntimeError(
                f"AGRISCAN_ENV is '{self.ENV}'. Use 'development' or 'production'."
            )
        if self.is_production:
            problems = self.production_problems()
            if problems:
                raise RuntimeError(
                    "Refusing to start in production:\n  - " + "\n  - ".join(problems)
                )

    def production_problems(self) -> list[str]:
        """Configuration that is acceptable on a laptop and not on a public server."""
        problems = []
        if len(self.SECRET_KEY) < 32 or self.SECRET_KEY.lower() in _KNOWN_BAD_SECRETS:
            problems.append(
                "AGRISCAN_SECRET_KEY is too short or a known placeholder. Generate one: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        if not self.DB_PASSWORD or self.DB_PASSWORD.lower() in _KNOWN_BAD_SECRETS:
            problems.append("AGRISCAN_DB_PASSWORD is empty or a placeholder.")
        if self.DEMO_MODE:
            problems.append("AGRISCAN_DEMO_MODE is true.")
        return problems


def get_config() -> Config:
    return Config()
