"""Uniform API errors.

Every error leaves the server as JSON with an `error` message a person can act on. A
stack trace never reaches the browser; it goes to the log with the request that caused it.
"""

from __future__ import annotations

import logging

from flask import jsonify, request
from werkzeug.exceptions import HTTPException

log = logging.getLogger("agriscan")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code

    def to_response(self):
        body = {"error": self.message}
        if self.code:
            body["code"] = self.code
        return jsonify(body), self.status


# MySQL/MariaDB client and server codes that mean "cannot talk to the database",
# as opposed to "the database rejected this statement".
_CONNECTION_CODES = {1040, 1045, 1049, 2002, 2003, 2005, 2006, 2013, 2055}
# Unknown column, unknown table, bad field in a condition. All three mean the database
# does not match the code, which in practice means a migration has not been run.
_SCHEMA_CODES = {1054, 1146, 1109}


def _db_code(err) -> int | None:
    orig = getattr(err, "orig", None)
    args = getattr(orig, "args", None) or ()
    return args[0] if args and isinstance(args[0], int) else None


def _rollback():
    try:
        from app.extensions import SessionLocal

        SessionLocal.rollback()
    except Exception:  # noqa: BLE001
        pass


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def _handle(err: ApiError):
        return err.to_response()

    @app.errorhandler(404)
    def _not_found(_):
        return jsonify({"error": "Not found."}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_):
        return jsonify({"error": f"{request.method} is not allowed on this address."}), 405

    @app.errorhandler(413)
    def _too_large(_):
        cfg = app.config["AGRISCAN"]
        mb = cfg.MAX_UPLOAD_BYTES // (1024 * 1024)
        return jsonify({"error": f"File exceeds the {mb} MB limit."}), 413

    @app.errorhandler(HTTPException)
    def _http(err: HTTPException):
        return jsonify({"error": err.description or err.name}), err.code or 500

    @app.errorhandler(Exception)
    def _unhandled(err: Exception):
        _rollback()
        from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError

        assert ProgrammingError  # both map onto _db_code below
        if isinstance(err, IntegrityError):
            # A unique key or foreign key said no. That is a conflict with existing data,
            # not a server fault.
            log.info("Integrity conflict on %s %s: %s", request.method, request.path,
                     getattr(err, "orig", err))
            return jsonify({"error": "That conflicts with an existing record."}), 409
        if isinstance(err, OperationalError) and _db_code(err) == 1644:
            # SIGNAL from an immutability trigger: the database refused to rewrite a
            # protected record. Correct behaviour, reported as a conflict.
            log.warning("Protected record on %s %s: %s", request.method, request.path,
                        getattr(err, "orig", err))
            return jsonify({"error": "This record is protected and cannot be changed."}), 409
        if _db_code(err) in _SCHEMA_CODES:
            log.error("Database schema is behind the code on %s %s: %s",
                      request.method, request.path, getattr(err, "orig", err))
            return jsonify({
                "error": "The database schema is out of date, so this request cannot be "
                         "served. On the server run: python -m migrations.run_migrations"
            }), 503
        if isinstance(err, OperationalError) and _db_code(err) in _CONNECTION_CODES:
            log.error("Database unavailable on %s %s: %s", request.method, request.path,
                      getattr(err, "orig", err))
            return jsonify({
                "error": "The database is not reachable. If this is the laptop server, "
                         "check that MySQL is running in XAMPP."
            }), 503
        log.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": "Internal server error."}), 500
