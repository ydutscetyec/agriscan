"""Test fixtures. These run against a REAL MariaDB, not SQLite.

The immutability trigger is a MariaDB feature; testing it on SQLite would prove nothing.
The test database is created, migrated and dropped per session.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest
from sqlalchemy import select, text

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_DB = os.environ.get("AGRISCAN_TEST_DB_NAME", "agriscan_test")
os.environ["AGRISCAN_DB_NAME"] = TEST_DB
os.environ.setdefault("AGRISCAN_SECRET_KEY", "test-secret-not-for-production")

from app import create_app  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.config import get_config  # noqa: E402
from app.extensions import SessionLocal  # noqa: E402
from app.models import Farm, Field, User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = get_config()
    import pymysql

    conn = pymysql.connect(
        host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER,
        password=cfg.DB_PASSWORD, autocommit=True,
    )

    # Optionally run the *server* on a non-UTC clock for this session. The schema
    # stores naive UTC, so if any query or column default were to read the server
    # clock instead of app.utils.clock, this is what exposes it. Set
    # AGRISCAN_TEST_DB_TZ=+08:00 (scripts/run_tests_offset_tz.sh does) and the whole
    # suite must still pass. Restored on teardown so a developer's local server is
    # left as it was found.
    db_tz = os.environ.get("AGRISCAN_TEST_DB_TZ")
    previous_tz = None
    if db_tz:
        with conn.cursor() as cur:
            cur.execute("SELECT @@global.time_zone")
            previous_tz = cur.fetchone()[0]
            cur.execute("SET GLOBAL time_zone = %s", (db_tz,))

    with conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS `{TEST_DB}`")
    conn.close()

    result = subprocess.run(
        [sys.executable, "-m", "migrations.run_migrations"],
        cwd=ROOT, capture_output=True, text=True, env={**os.environ},
    )
    assert result.returncode == 0, f"migrations failed:\n{result.stdout}\n{result.stderr}"
    yield

    if previous_tz is not None:
        restore = pymysql.connect(
            host=cfg.DB_HOST, port=cfg.DB_PORT, user=cfg.DB_USER,
            password=cfg.DB_PASSWORD, autocommit=True,
        )
        with restore.cursor() as cur:
            cur.execute("SET GLOBAL time_zone = %s", (previous_tz,))
        restore.close()


@pytest.fixture()
def app():
    application = create_app(get_config())
    yield application
    SessionLocal.remove()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def cfg():
    return get_config()


@pytest.fixture()
def users(app, cfg):
    """Two farmers with one farm and one field each, plus a technician and an admin."""
    session = SessionLocal()
    made = {}
    spec = [
        ("t_admin", "admin"), ("t_tech", "technician"),
        ("t_farmer_a", "farmer"), ("t_farmer_b", "farmer"),
    ]
    for name, role in spec:
        user = session.execute(select(User).where(User.name == name)).scalar_one_or_none()
        if user is None:
            user = User(
                name=name, role=role, barangay="Test",
                password_hash=hash_password("correct-horse-battery", cfg.PASSWORD_MIN_LENGTH),
                is_demo=True,
            )
            session.add(user)
            session.flush()
        made[name] = user

    for fname, owner in [("farm_a", "t_farmer_a"), ("farm_b", "t_farmer_b")]:
        farm = session.execute(select(Farm).where(Farm.name == fname)).scalar_one_or_none()
        if farm is None:
            farm = Farm(name=fname, owner_user_id=made[owner].id, is_demo=True)
            session.add(farm)
            session.flush()
        made[fname] = farm
        field_name = f"field_{fname}"
        field = session.execute(
            select(Field).where(Field.name == field_name)
        ).scalar_one_or_none()
        if field is None:
            import datetime as dt

            field = Field(
                farm_id=farm.id, name=field_name,
                planting_date=dt.date(2026, 7, 1), is_demo=True,
            )
            session.add(field)
            session.flush()
        made[field_name] = field
    session.commit()
    return made


def login(client, name: str, password: str = "correct-horse-battery") -> str | None:
    resp = client.post("/auth/login", json={"name": name, "password": password})
    if resp.status_code != 200:
        return None
    return resp.get_json()["token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
