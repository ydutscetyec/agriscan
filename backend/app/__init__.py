"""Application factory."""

from __future__ import annotations

import datetime as dt
import logging
import os

from flask import Flask, jsonify, request
from sqlalchemy import text

from app.utils.clock import utc_now
from app.api import ALL_BLUEPRINTS
from app.auth import bp as auth_bp
from app.config import Config, get_config
from app.extensions import SessionLocal, init_engine
from app.providers import ProviderRegistry
from app.utils.errors import register_error_handlers

log = logging.getLogger("agriscan")

# A queued photo older than this, with nothing running, means the worker is not working.
QUEUE_STALL_SECONDS = 300


def create_app(config: Config | None = None, wrap_proxy: bool = True) -> Flask:
    """wrap_proxy=False when app.site wraps the whole site (API and web) instead."""
    cfg = config or get_config()
    cfg.validate()

    app = Flask(__name__)
    app.config["AGRISCAN"] = cfg
    # Werkzeug rejects an oversized body before the view reads it into memory. Without
    # this, a 2 GB POST would be read in full and only then refused by validate_upload.
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_request_bytes
    # Providers default to Null everywhere; see app/providers/__init__.py.
    app.config["AGRISCAN_PROVIDERS"] = ProviderRegistry.from_env(os.environ)
    init_engine(cfg.sqlalchemy_uri)

    if wrap_proxy and cfg.PROXY_HOPS > 0:
        # Only behind a proxy we run (Caddy, cloudflared). Trusting X-Forwarded-For with
        # no proxy in front would let any client choose its own IP for the rate limit.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=cfg.PROXY_HOPS, x_proto=cfg.PROXY_HOPS,
            x_host=cfg.PROXY_HOPS,
        )

    app.register_blueprint(auth_bp)
    for bp in ALL_BLUEPRINTS:
        app.register_blueprint(bp)
    register_error_handlers(app)

    @app.get("/health")
    def health():
        """What an operator needs to know before a flight: is the database up, and is
        anything actually analysing the photos. 503 only when the database is down.

        Reachable without signing in, because an uptime check has no token — but then it
        answers with liveness alone. Model names, queue depth and which build is running
        are free reconnaissance for anyone who finds the address, so the detail is only
        returned to a signed-in operator.
        """
        from app.auth.decorators import current_user_or_none

        viewer = current_user_or_none()
        detailed = viewer is not None and viewer.role in ("admin", "technician", "researcher")
        body = {"status": "ok"}
        if detailed:
            body.update({
                "environment": cfg.ENV,
                "demo_mode": cfg.DEMO_MODE,
                "detector": cfg.DETECTOR_IMPL,
                "server_time": utc_now().isoformat(timespec="seconds"),
            })
        try:
            session = SessionLocal()
            session.execute(text("SELECT 1"))
            row = session.execute(text(
                "SELECT "
                " SUM(status IN ('QUEUED','RETRYING')), "
                " SUM(status = 'RUNNING'), "
                " SUM(status = 'FAILED' AND completed_at > NOW() - INTERVAL 1 DAY), "
                " TIMESTAMPDIFF(SECOND, MIN(IF(status IN ('QUEUED','RETRYING'), created_at, NULL)), NOW()), "
                " MAX(completed_at) "
                "FROM jobs"
            )).fetchone()
            models = session.execute(text(
                "SELECT imaging_mode, name FROM model_versions "
                "WHERE deployment_status = 'production' ORDER BY id DESC"
            )).fetchall()
        except Exception:  # noqa: BLE001
            log.exception("Health check could not reach the database")
            return jsonify({**body, "status": "degraded", "database": "unreachable",
                            "error": "The database is not reachable."}), 503

        if not detailed:
            # Liveness only: the database answered, so the service is up.
            return jsonify(body)

        waiting = int(row[0] or 0)
        running = int(row[1] or 0)
        oldest = int(row[3]) if row[3] is not None else None
        production = {}
        for mode, name in models:
            production.setdefault(mode, name)
        stalled = bool(waiting and running == 0 and oldest is not None
                       and oldest > QUEUE_STALL_SECONDS)
        body.update({
            "database": "ok",
            "model": production.get("ground", "MODEL_NOT_AVAILABLE"),
            "models_in_production": production,
            "queue": {
                "waiting": waiting,
                "running": running,
                "failed_last_24h": int(row[2] or 0),
                "oldest_waiting_seconds": oldest,
                "last_completed_at": row[4].isoformat() if row[4] else None,
                "stalled": stalled,
            },
        })
        if stalled:
            body["status"] = "degraded"
        return jsonify(body)

    @app.after_request
    def _headers(response):
        # Dev-server CORS only. The origin is configuration, never a wildcard, because
        # these responses carry farmer data. Production is same-origin and needs none.
        origin = request.headers.get("Origin")
        if origin and origin in cfg.CORS_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Vary"] = "Origin"

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # API data is per-user and changes as technicians verify. No browser, proxy or
        # CDN may keep a copy. Image files set their own private cache header.
        if response.mimetype == "application/json":
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.teardown_appcontext
    def _remove_session(_exc=None):
        SessionLocal.remove()

    return app
