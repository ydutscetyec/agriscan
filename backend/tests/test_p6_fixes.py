"""p6 backend fixes: .env loading, pagination totals, safe field deletion, metrics guard."""

from __future__ import annotations

import io
import itertools
import os
import pathlib
import subprocess
import sys

import pytest

from app.extensions import SessionLocal
from app.models import Field
from tests.conftest import auth_headers, login
from tests.factories import sharp_image
from tests.test_ingest import _drain_worker, production_models, taxonomy  # noqa: F401

BACKEND = pathlib.Path(__file__).resolve().parents[1]
_SEED = itertools.count(40000)


def _upload(client, token, field_id):
    return client.post(
        "/images",
        headers=auth_headers(token),
        data={
            "file": (io.BytesIO(sharp_image(240, next(_SEED))), "p6.jpg", "image/jpeg"),
            "field_id": str(field_id),
            "source": "phone",
        },
        content_type="multipart/form-data",
    )


# --------------------------------------------------------------------- .env loading


def test_env_file_is_read_by_config(tmp_path):
    """The bug found on 26 Sep: .env existed but nothing loaded it.

    Runs in a subprocess from a scratch copy so the real environment is untouched.
    """
    scratch = tmp_path / "backend"
    (scratch / "app").mkdir(parents=True)
    (scratch / "app" / "__init__.py").write_text("")
    (scratch / "app" / "config.py").write_text(
        (BACKEND / "app" / "config.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (scratch / ".env").write_text("AGRISCAN_DB_USER=from_dotenv_file\n")

    env = {k: v for k, v in os.environ.items() if not k.startswith("AGRISCAN_")}
    result = subprocess.run(
        [sys.executable, "-c",
         "from app.config import get_config; print(get_config().DB_USER)"],
        cwd=scratch, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "from_dotenv_file"


def test_shell_variable_beats_env_file(tmp_path):
    """override=False: a value set in the shell must win over the file."""
    scratch = tmp_path / "backend"
    (scratch / "app").mkdir(parents=True)
    (scratch / "app" / "__init__.py").write_text("")
    (scratch / "app" / "config.py").write_text(
        (BACKEND / "app" / "config.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (scratch / ".env").write_text("AGRISCAN_DB_USER=from_file\n")

    env = {k: v for k, v in os.environ.items() if not k.startswith("AGRISCAN_")}
    env["AGRISCAN_DB_USER"] = "from_shell"
    result = subprocess.run(
        [sys.executable, "-c",
         "from app.config import get_config; print(get_config().DB_USER)"],
        cwd=scratch, capture_output=True, text=True, env=env,
    )
    assert result.stdout.strip() == "from_shell"


# ------------------------------------------------------------------------ pagination


def test_detections_report_total_across_pages(client, users, cfg, production_models):
    token = login(client, "t_tech")
    for _ in range(3):
        _upload(client, token, users["field_farm_a"].id)
    _drain_worker(cfg)

    body = client.get(
        "/detections?include_demo=true&limit=1&offset=0", headers=auth_headers(token)
    ).get_json()
    assert body["count"] == 1
    assert body["total"] >= 3


def test_pages_do_not_overlap(client, users, cfg, production_models):
    token = login(client, "t_tech")
    first = client.get(
        "/detections?include_demo=true&limit=1&offset=0", headers=auth_headers(token)
    ).get_json()["detections"]
    second = client.get(
        "/detections?include_demo=true&limit=1&offset=1", headers=auth_headers(token)
    ).get_json()["detections"]
    if first and second:
        assert first[0]["id"] != second[0]["id"]


def test_total_respects_farmer_scoping(client, users, cfg, production_models):
    tech = login(client, "t_tech")
    _upload(client, tech, users["field_farm_b"].id)
    _drain_worker(cfg)

    farmer = login(client, "t_farmer_a")
    body = client.get(
        "/detections?include_demo=true&limit=500", headers=auth_headers(farmer)
    ).get_json()
    assert body["total"] == body["count"]
    assert all(d["field_id"] == users["field_farm_a"].id for d in body["detections"])


# ---------------------------------------------------------------------- field delete


def test_admin_can_delete_an_empty_field(client, users):
    admin = login(client, "t_admin")
    created = client.post(
        "/fields", headers=auth_headers(admin),
        json={"name": "p6 scratch field", "farm_id": users["farm_a"].id},
    ).get_json()
    resp = client.delete(f"/fields/{created['id']}", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert SessionLocal().get(Field, created["id"]) is None


def test_field_with_images_cannot_be_deleted(client, users, taxonomy):
    tech = login(client, "t_tech")
    admin = login(client, "t_admin")
    field_id = users["field_farm_a"].id
    _upload(client, tech, field_id)

    resp = client.delete(f"/fields/{field_id}", headers=auth_headers(admin))
    assert resp.status_code == 409
    assert "research data" in resp.get_json()["error"]
    assert SessionLocal().get(Field, field_id) is not None


def test_technician_cannot_delete_fields(client, users):
    tech = login(client, "t_tech")
    admin = login(client, "t_admin")
    created = client.post(
        "/fields", headers=auth_headers(admin),
        json={"name": "p6 guarded field", "farm_id": users["farm_a"].id},
    ).get_json()
    resp = client.delete(f"/fields/{created['id']}", headers=auth_headers(tech))
    assert resp.status_code == 403


# --------------------------------------------------------------------- metrics guard


def test_metrics_withheld_below_minimum(client, users, cfg, production_models):
    """A handful of verifications must not produce a quotable precision figure."""
    tech = login(client, "t_tech")
    resp = _upload(client, tech, users["field_farm_a"].id)
    _drain_worker(cfg)

    body = client.get(
        "/analysis/confusion-matrix?include_demo=true", headers=auth_headers(tech)
    ).get_json()
    if body["verified_pairs"] < body["min_required"]:
        assert body["sufficient"] is False
        assert body["overall_accuracy"] is None
        assert body["metrics_message"] == (
            "Metrics unavailable — insufficient validated samples."
        )
        for stats in body["per_class"].values():
            assert stats["precision"] is None
            assert stats["recall"] is None
            assert stats["f1"] is None


def test_counts_are_still_returned_when_metrics_are_withheld(client, users):
    tech = login(client, "t_tech")
    body = client.get(
        "/analysis/confusion-matrix?include_demo=true", headers=auth_headers(tech)
    ).get_json()
    assert "matrix" in body
    assert "verified_pairs" in body
    assert "min_required" in body


def test_metrics_carry_a_sampling_caveat(client, users):
    tech = login(client, "t_tech")
    body = client.get(
        "/analysis/confusion-matrix?include_demo=true", headers=auth_headers(tech)
    ).get_json()
    assert "held-out test fields" in body["sampling_note"]
