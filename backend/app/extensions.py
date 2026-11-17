"""Shared SQLAlchemy engine/session, configured per application factory call."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import scoped_session, sessionmaker

SessionLocal = scoped_session(sessionmaker(autoflush=False, expire_on_commit=False))

# Every DATETIME column in this schema holds naive UTC, written by
# app.utils.clock.utc_now(). But SQL NOW(), CURRENT_TIMESTAMP and
# DEFAULT CURRENT_TIMESTAMP read the *database server's* clock, which is its
# system timezone unless told otherwise — PST on this container, Asia/Manila
# under XAMPP on a Philippine laptop. Two clocks, one column type, and the
# difference is silent: a query like
#
#     WHERE created_at > NOW() - INTERVAL 15 MINUTE
#
# matches nothing at all when the server clock runs ahead of UTC, and matches
# far too much when it runs behind. That is how the login throttle stopped
# throttling and how the worker decided every running job was stale.
#
# Pinning the session timezone to UTC on connect makes the server clock and
# the application clock the same clock, everywhere, including the schema's
# DEFAULT CURRENT_TIMESTAMP columns. A numeric offset is used rather than a
# named zone because named zones need the mysql time zone tables loaded,
# which a stock XAMPP install does not have.
UTC_SESSION_SQL = "SET time_zone = '+00:00'"


def init_engine(uri: str, echo: bool = False):
    engine = create_engine(uri, echo=echo, pool_pre_ping=True, future=True)

    @event.listens_for(engine, "connect")
    def _force_utc_session(dbapi_connection, connection_record):  # noqa: ARG001
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(UTC_SESSION_SQL)
        finally:
            cursor.close()

    SessionLocal.configure(bind=engine)
    return engine
