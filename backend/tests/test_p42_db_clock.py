"""p42: the database clock and the application clock must be the same clock.

Every DATETIME column in this schema holds naive UTC, written by
app.utils.clock.utc_now(). SQL NOW(), CURRENT_TIMESTAMP and the schema's
DEFAULT CURRENT_TIMESTAMP columns read the database server's clock instead,
which is its system timezone unless the session says otherwise.

When those two disagree, nothing errors. Queries just quietly stop matching:

  - app/auth: "created_at > NOW() - INTERVAL 15 MINUTE" matched no audit rows
    at all on a server running ahead of UTC, so the login-failure throttle
    never fired and brute-force protection was off.
  - worker: "started_at < NOW() - INTERVAL :mins MINUTE" judged every running
    job stale the moment it started.

app.extensions pins every connection's session timezone to +00:00, which makes
the server clock agree with the application clock everywhere, DEFAULT
CURRENT_TIMESTAMP included. These tests fail if that pinning is removed.

Run the whole suite with the server itself on a different offset to prove it:
    AGRISCAN_TEST_DB_TZ=+08:00 TZ=Asia/Manila python -m pytest
(scripts/run_tests_offset_tz.sh does exactly that.)
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import text

from app.extensions import SessionLocal
from app.utils.clock import utc_now

# Generous enough for a slow CI runner, far tighter than any real timezone offset
# (the smallest in use is 15 minutes).
TOLERANCE = dt.timedelta(seconds=30)


def test_connection_session_timezone_is_utc(app):
    session = SessionLocal()
    value = session.execute(text("SELECT @@session.time_zone")).scalar()
    assert value == "+00:00", (
        f"session time_zone is {value!r}; SQL NOW() will not agree with utc_now()"
    )


def test_sql_now_agrees_with_the_application_clock(app):
    session = SessionLocal()
    db_now = session.execute(text("SELECT NOW()")).scalar()
    drift = abs(db_now - utc_now())
    assert drift < TOLERANCE, (
        f"database clock and application clock differ by {drift}; "
        "a WHERE ... > NOW() - INTERVAL window will match the wrong rows"
    )


def test_default_current_timestamp_columns_are_written_in_utc(app):
    """The column default, not an app-supplied value — this is the subtler half."""
    session = SessionLocal()
    session.execute(text("DROP TEMPORARY TABLE IF EXISTS _clock_probe"))
    session.execute(
        text(
            "CREATE TEMPORARY TABLE _clock_probe ("
            "  id INT AUTO_INCREMENT PRIMARY KEY,"
            "  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
    )
    session.execute(text("INSERT INTO _clock_probe () VALUES ()"))
    stored = session.execute(text("SELECT created_at FROM _clock_probe")).scalar()
    session.execute(text("DROP TEMPORARY TABLE _clock_probe"))
    session.commit()

    drift = abs(stored - utc_now())
    assert drift < TOLERANCE, (
        f"DEFAULT CURRENT_TIMESTAMP wrote a value {drift} away from UTC"
    )


def test_an_interval_window_selects_a_row_the_app_just_wrote(app):
    """The exact shape of the query that broke the login throttle."""
    session = SessionLocal()
    session.execute(text("DROP TEMPORARY TABLE IF EXISTS _window_probe"))
    session.execute(
        text(
            "CREATE TEMPORARY TABLE _window_probe ("
            "  id INT AUTO_INCREMENT PRIMARY KEY,"
            "  created_at DATETIME NOT NULL)"
        )
    )
    # Written by the application, in UTC, exactly as audit rows are.
    session.execute(
        text("INSERT INTO _window_probe (created_at) VALUES (:t)"),
        {"t": utc_now()},
    )
    found = session.execute(
        text(
            "SELECT COUNT(*) FROM _window_probe "
            "WHERE created_at > NOW() - INTERVAL 15 MINUTE"
        )
    ).scalar()
    session.execute(text("DROP TEMPORARY TABLE _window_probe"))
    session.commit()

    assert found == 1, (
        "a row the application wrote one moment ago fell outside a 15-minute "
        "NOW() window; this is the login throttle failing open"
    )
