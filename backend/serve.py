"""Production entrypoint: the whole website on one port.

    python serve.py                 # http://127.0.0.1:8080, API under /api
    python serve.py --check         # run the preflight checks and exit

Waitress, not Flask's development server: it handles concurrent requests, has no
debugger to expose, and runs on Windows (gunicorn does not). Put HTTPS in front of it
with Cloudflare Tunnel or Caddy; see DEPLOY.md. The camera, GPS and wake lock on the
drone phone only work over HTTPS.

Run the analysis worker beside it:  python -m worker.run
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import sys

from app.config import get_config
from app.services import preflight


def setup_logging(cfg) -> None:
    cfg.log_dir_path.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(
        cfg.log_dir_path / "agriscan.log", maxBytes=5 * 1024 * 1024, backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers[:] = [file_handler, console]


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve AGRISCAN (web app + API).")
    parser.add_argument("--host", default=os.environ.get("AGRISCAN_HOST", "127.0.0.1"),
                        help="127.0.0.1 behind a tunnel or proxy (default). 0.0.0.0 exposes "
                             "plain HTTP to the network.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("AGRISCAN_PORT", "8080")))
    parser.add_argument("--threads", type=int, default=int(os.environ.get("AGRISCAN_THREADS", "8")))
    parser.add_argument("--check", action="store_true", help="Run preflight checks and exit.")
    args = parser.parse_args()

    cfg = get_config()
    results = preflight.run_all(cfg)
    passed = preflight.print_report(results)
    if args.check:
        return 0 if passed else 1
    if not passed and cfg.is_production:
        print("Not starting: fix the FAIL lines above first.")
        return 1

    setup_logging(cfg)
    log = logging.getLogger("agriscan")

    from waitress import serve

    from app.site import create_site

    site = create_site(cfg)
    log.info("AGRISCAN %s on http://%s:%d (API at /api)", cfg.ENV, args.host, args.port)
    if args.host not in ("127.0.0.1", "localhost"):
        log.warning("Listening on %s over plain HTTP. Phones on this network can open the "
                    "dashboard, but the drone camera needs HTTPS.", args.host)
    serve(
        site,
        host=args.host,
        port=args.port,
        threads=args.threads,
        # Same ceiling as the app, enforced before the body is buffered.
        max_request_body_size=cfg.max_request_bytes,
        # A phone on one bar of signal uploading a 6 MB photo needs time.
        channel_timeout=180,
        ident="AGRISCAN",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
