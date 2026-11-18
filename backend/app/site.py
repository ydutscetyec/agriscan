"""The whole website as one WSGI application: the built React app at /, the API at /api.

This is what makes a single `python serve.py` enough for a real deployment. The browser
only ever talks to one origin, exactly as it does through the Vite dev proxy, so the
frontend needs no build-time API address and there is no CORS in production.

    /api/...      the Flask API, unchanged (it sees /auth/login, not /api/auth/login)
    /assets/...   hashed build files, cached for a year
    /sw.js        the service worker, never cached, so an update is picked up
    anything else a file from web/dist if one exists, otherwise index.html, so a
                  reload on /field/results/12 or /camera opens the right screen
"""

from __future__ import annotations

import logging
import mimetypes
import os
import time

from flask import Flask, Response, request, send_file
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.security import safe_join

from app import create_app
from app.config import Config, get_config

log = logging.getLogger("agriscan.site")

# Windows takes MIME types from the registry, and some machines map .js to text/plain.
# A browser then refuses to run the app ("expected a JavaScript module script") and the
# page is blank. Set the types the build actually produces, explicitly.
for _type, _ext in (
    ("text/javascript", ".js"),
    ("text/css", ".css"),
    ("image/svg+xml", ".svg"),
    ("application/manifest+json", ".webmanifest"),
    ("application/json", ".json"),
    ("font/woff2", ".woff2"),
    ("font/woff", ".woff"),
    ("image/png", ".png"),
    ("image/jpeg", ".jpg"),
    ("video/mp4", ".mp4"),
):
    mimetypes.add_type(_type, _ext)

# The origins the map loads tile imagery from. These must stay in step with LAYERS in
# web/src/components/BaseMap.jsx.
#
# Getting this wrong is silent and total: the browser blocks every tile, the map renders
# blank with its controls and markers still drawn on nothing, no request reaches the
# network tab as a failure, and the only clue is a Content Security Policy line in the
# console. That is exactly what happened when the base map moved off OpenStreetMap's
# servers and this list stayed behind — both layers were blocked, so switching base map
# looked broken too.
#
# tests/test_p43_csp_tiles.py reads BaseMap.jsx and fails if the two ever drift apart.
DEFAULT_TILE_ORIGINS = (
    "https://server.arcgisonline.com",   # Esri World Imagery — the satellite layer
    "https://tile.openstreetmap.de",     # OpenStreetMap Germany — the streets layer
    "https://*.tile.openstreetmap.org",  # OSM standard, for deployments still on it
)


def tile_origins() -> tuple[str, ...]:
    """Tile origins allowed by the CSP.

    AGRISCAN_TILE_ORIGINS (space- or comma-separated) adds more, so a deployed server
    can move to a different tile provider without a code change.
    """
    raw = os.environ.get("AGRISCAN_TILE_ORIGINS", "").replace(",", " ").split()
    extra = tuple(o for o in raw if o not in DEFAULT_TILE_ORIGINS)
    return DEFAULT_TILE_ORIGINS + extra


def build_csp() -> str:
    """What the dashboard actually loads. Map tiles are the only third-party origin:
    fonts are bundled, scripts are same-origin, and the API is same-origin."""
    return "; ".join([
        "default-src 'self'",
        "script-src 'self'",
        # Leaflet and React position elements with inline style attributes.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: " + " ".join(tile_origins()),
        "font-src 'self' data:",
        "connect-src 'self'",
        "media-src 'self' blob:",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])

# The drone phone needs the camera, location and wake lock; nothing needs the microphone.
PERMISSIONS_POLICY = (
    "camera=(self), geolocation=(self), screen-wake-lock=(self), "
    "microphone=(), payment=(), usb=()"
)

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>AGRISCAN</title>
<body style="font-family:system-ui;max-width:40rem;margin:4rem auto;padding:0 1rem;line-height:1.5">
<h1>The web app has not been built</h1>
<p>The API is running, but there is no <code>web/dist</code> folder to serve.</p>
<p>On the server: <code>cd web</code>, <code>npm ci</code>, <code>npm run build</code>,
then restart <code>python serve.py</code>.</p>
<p>Looked in: <code>{path}</code></p>
</body>"""


def create_web_app(cfg: Config) -> Flask:
    dist = cfg.web_dist_path
    web = Flask("agriscan_web", static_folder=None)

    def _file_response(path: str, cache: str) -> Response:
        response = send_file(path, conditional=True, max_age=None)
        response.headers["Cache-Control"] = cache
        return response

    def _index() -> Response:
        index = dist / "index.html"
        if not index.is_file():
            return Response(NOT_BUILT.format(path=dist), status=503, mimetype="text/html")
        return _file_response(str(index), "no-cache")

    @web.route("/", defaults={"path": ""})
    @web.route("/<path:path>")
    def spa(path: str):
        if request.method not in ("GET", "HEAD"):
            return Response("Method not allowed.", status=405)
        if not path or path == "index.html":
            return _index()

        target = safe_join(str(dist), path)
        if target is not None:
            from pathlib import Path

            candidate = Path(target)
            if candidate.is_file():
                if path.startswith("assets/"):
                    return _file_response(target, "public, max-age=31536000, immutable")
                if path == "sw.js":
                    return _file_response(target, "no-cache")
                return _file_response(target, "public, max-age=3600")

        # A missing hashed file is a real 404. Answering with index.html would hand the
        # browser HTML where it expects JavaScript, and the app would fail with a
        # confusing MIME error instead of reloading to the new build.
        if path.startswith("assets/") or "." in path.rsplit("/", 1)[-1]:
            return Response("Not found.", status=404, mimetype="text/plain")
        return _index()

    # Built here, not at import, so AGRISCAN_TILE_ORIGINS from .env is already loaded.
    content_security_policy = build_csp()

    @web.after_request
    def _headers(response: Response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
        if response.mimetype == "text/html":
            response.headers.setdefault("Content-Security-Policy", content_security_policy)
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if cfg.is_production and request.scheme == "https":
            # Only once HTTPS is confirmed, and only for this host: a subdomain of the
            # same domain may still need plain HTTP.
            response.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
        return response

    return web


class AccessLog:
    """One line per API request: method, path, status, time. Assets are not logged."""

    def __init__(self, app, logger: logging.Logger):
        self.app = app
        self.log = logger

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if not path.startswith("/api/"):
            return self.app(environ, start_response)
        started = time.perf_counter()
        status_holder = {}

        def _start(status, headers, exc_info=None):
            status_holder["status"] = status.split(" ", 1)[0]
            return start_response(status, headers, exc_info)

        try:
            return self.app(environ, _start)
        finally:
            self.log.info(
                "%s %s %s %.0fms %s",
                environ.get("REQUEST_METHOD"), path, status_holder.get("status", "-"),
                (time.perf_counter() - started) * 1000,
                environ.get("REMOTE_ADDR", "-"),
            )


def create_site(cfg: Config | None = None):
    """The deployable WSGI callable."""
    cfg = cfg or get_config()
    api = create_app(cfg, wrap_proxy=False)
    web = create_web_app(cfg)
    site = DispatcherMiddleware(web.wsgi_app, {"/api": api.wsgi_app})
    site = AccessLog(site, logging.getLogger("agriscan.access"))
    if cfg.PROXY_HOPS > 0:
        from werkzeug.middleware.proxy_fix import ProxyFix

        site = ProxyFix(site, x_for=cfg.PROXY_HOPS, x_proto=cfg.PROXY_HOPS,
                        x_host=cfg.PROXY_HOPS)
    return site
