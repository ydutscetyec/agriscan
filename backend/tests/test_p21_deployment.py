"""p21: the production site wrapper, /health, worker reliability, config checks."""

from __future__ import annotations

import io
import json
import pathlib
import types

import pytest
from sqlalchemy import text
from werkzeug.test import Client

from app.config import BACKEND_DIR, get_config, resolve_path
from app.extensions import SessionLocal
from app.inference import Prediction, YoloDetector, _classification_predictions, compute_severity
from tests.conftest import auth_headers, login
from tests.factories import sharp_image


# ------------------------------------------------------------------ site wrapper


@pytest.fixture()
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>AGRISCAN</title><div id=root></div>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "sw.js").write_text("self.addEventListener('fetch',()=>{})")
    (tmp_path / "manifest.webmanifest").write_text("{}")
    return tmp_path


@pytest.fixture()
def site(dist):
    from app.site import create_site

    cfg = get_config()
    cfg.WEB_DIST = str(dist)
    return Client(create_site(cfg))


def test_root_serves_index_with_security_headers(site):
    resp = site.get("/")
    assert resp.status_code == 200
    assert b"AGRISCAN" in resp.data
    csp = resp.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert resp.headers["Cache-Control"] == "no-cache"
    assert "camera=(self)" in resp.headers["Permissions-Policy"]


def test_client_routes_fall_back_to_index(site):
    """A reload on a deep link must open the app, not a 404."""
    for path in ("/field/results/12", "/camera", "/detections/4", "/users"):
        resp = site.get(path)
        assert resp.status_code == 200, path
        assert b"id=root" in resp.data


def test_hashed_assets_are_cached_and_typed(site):
    resp = site.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/javascript")
    assert "immutable" in resp.headers["Cache-Control"]


def test_missing_asset_is_404_not_index(site):
    """HTML in place of a missing chunk gives a MIME error instead of a reload."""
    assert site.get("/assets/index-gone999.js").status_code == 404
    assert site.get("/favicon-missing.png").status_code == 404


def test_service_worker_is_never_cached(site):
    resp = site.get("/sw.js")
    assert resp.status_code == 200
    assert resp.headers["Cache-Control"] == "no-cache"


def test_manifest_has_its_type(site):
    resp = site.get("/manifest.webmanifest")
    assert resp.headers["Content-Type"].startswith("application/manifest+json")


def test_path_traversal_is_refused(site):
    resp = site.get("/../../backend/.env")
    assert b"AGRISCAN_SECRET_KEY" not in resp.data
    resp = site.get("/assets/..%2F..%2Fbackend%2F.env")
    assert b"AGRISCAN_SECRET_KEY" not in resp.data


def test_api_is_mounted_under_api(site, users):
    resp = site.post("/api/auth/login", json={"name": "t_admin", "password": "correct-horse-battery"})
    assert resp.status_code == 200
    token = resp.get_json()["token"]
    me = site.get("/api/auth/me", headers=auth_headers(token))
    assert me.get_json()["name"] == "t_admin"
    assert me.headers["Cache-Control"] == "no-store"


def test_unknown_api_path_is_json_404(site):
    resp = site.get("/api/not-a-thing")
    assert resp.status_code == 404
    assert resp.get_json() == {"error": "Not found."}


def test_missing_build_says_how_to_fix_it(tmp_path):
    from app.site import create_site

    cfg = get_config()
    cfg.WEB_DIST = str(tmp_path / "nope")
    resp = Client(create_site(cfg)).get("/")
    assert resp.status_code == 503
    assert b"npm run build" in resp.data


def test_proxy_hops_use_forwarded_client_address(dist, users):
    """Behind one proxy, the sign-in limit must see the phone's address, not 127.0.0.1."""
    from app.site import create_site

    cfg = get_config()
    cfg.WEB_DIST = str(dist)
    cfg.PROXY_HOPS = 1
    client = Client(create_site(cfg))
    client.post("/api/auth/login", json={"name": "proxy-probe-name", "password": "wrong-wrong-1"},
                headers={"X-Forwarded-For": "203.0.113.77", "X-Forwarded-Proto": "https"})
    row = SessionLocal().execute(text(
        "SELECT JSON_UNQUOTE(JSON_EXTRACT(detail, '$.ip')) FROM audit_log "
        "WHERE action='login_failed' AND object_id='proxy-probe-name' ORDER BY id DESC LIMIT 1"
    )).scalar_one()
    assert row == "203.0.113.77"


def test_hsts_only_in_production_over_https(dist):
    from app.site import create_web_app

    cfg = get_config()
    cfg.WEB_DIST = str(dist)
    cfg.ENV = "production"
    web = create_web_app(cfg).test_client()
    assert "Strict-Transport-Security" in web.get("/", base_url="https://agriscan.example").headers
    assert "Strict-Transport-Security" not in web.get("/", base_url="http://agriscan.example").headers


# ------------------------------------------------------------------ API hardening


def test_oversized_body_is_refused_before_reading(app, client, users):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    token = login(client, "t_tech")
    resp = client.post(
        "/images", headers=auth_headers(token),
        data={"file": (io.BytesIO(b"x" * 4096), "big.jpg", "image/jpeg"), "field_id": "1"},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 413
    assert "limit" in resp.get_json()["error"]


def test_wrong_method_is_json(client):
    resp = client.delete("/auth/login")
    assert resp.status_code == 405
    assert "error" in resp.get_json()


def test_bad_date_filter_is_400(client, users):
    token = login(client, "t_tech")
    resp = client.get("/detections?date_from=yesterday", headers=auth_headers(token))
    assert resp.status_code == 400


# ------------------------------------------------------------------ health


def test_health_reports_database_and_queue(client, users):
    body = client.get("/health", headers=auth_headers(login(client, "t_admin"))).get_json()
    assert body["database"] == "ok"
    assert set(body["queue"]) >= {"waiting", "running", "oldest_waiting_seconds", "stalled"}


def test_health_without_a_token_says_only_that_it_is_alive(client):
    """An uptime check has no token, so it still gets an answer — but model names,
    queue depth and the build's environment are reconnaissance for anyone who finds
    the address, so those need a signed-in operator."""
    body = client.get("/health").get_json()
    assert body["status"] == "ok"
    for leaked in ("queue", "model", "models_in_production", "environment", "detector"):
        assert leaked not in body, leaked


def test_health_flags_a_stalled_queue(client, users):
    token = login(client, "t_admin")
    session = SessionLocal()
    session.execute(text(
        "INSERT INTO jobs (type, status, priority, payload, created_at) "
        "VALUES ('inference', 'QUEUED', 0, '{\"image_id\": 999999}', NOW() - INTERVAL 20 MINUTE)"
    ))
    session.commit()
    try:
        body = client.get("/health", headers=auth_headers(token)).get_json()
        assert body["queue"]["stalled"] is True
        assert body["status"] == "degraded"
    finally:
        session.execute(text("DELETE FROM jobs WHERE image_id = 999999"))
        session.commit()


def test_job_image_id_column_is_filled_from_payload(client):
    session = SessionLocal()
    session.execute(text(
        "INSERT INTO jobs (type, status, payload) VALUES ('inference', 'COMPLETED', '{\"image_id\": 424242}')"
    ))
    session.commit()
    found = session.execute(text("SELECT COUNT(*) FROM jobs WHERE image_id = 424242")).scalar_one()
    session.execute(text("DELETE FROM jobs WHERE image_id = 424242"))
    session.commit()
    assert found == 1


# ------------------------------------------------------------------ worker


def test_stale_running_jobs_are_recovered(app):
    from worker.run import recover_stale_jobs

    cfg = get_config()
    session = SessionLocal()
    session.execute(text(
        "INSERT INTO jobs (type, status, payload, claimed_by, attempts, started_at) VALUES "
        "('inference','RUNNING','{\"image_id\": 777001}','worker-dead',1, NOW() - INTERVAL 30 MINUTE),"
        "('inference','RUNNING','{\"image_id\": 777002}','worker-dead',3, NOW() - INTERVAL 30 MINUTE),"
        "('inference','RUNNING','{\"image_id\": 777003}','worker-live',1, NOW())"
    ))
    session.commit()
    try:
        assert recover_stale_jobs(session, cfg) == 2
        rows = dict(session.execute(text(
            "SELECT image_id, status FROM jobs WHERE image_id IN (777001, 777002, 777003)"
        )).all())
        assert rows == {777001: "RETRYING", 777002: "FAILED", 777003: "RUNNING"}
    finally:
        session.execute(text("DELETE FROM jobs WHERE image_id IN (777001, 777002, 777003)"))
        session.commit()


def test_production_worker_refuses_the_stub():
    from worker.run import stub_refused

    cfg = get_config()
    cfg.DETECTOR_IMPL = "stub"
    cfg.ENV = "production"
    assert "synthetic" in stub_refused(cfg)
    cfg.ALLOW_STUB_DETECTOR = True
    assert stub_refused(cfg) is None
    cfg.ENV = "development"
    cfg.ALLOW_STUB_DETECTOR = False
    assert stub_refused(cfg) is None


def test_yolo_detector_is_built_once_per_model():
    from worker.run import _DETECTORS, detector_for

    cfg = get_config()
    cfg.DETECTOR_IMPL = "yolo"
    _DETECTORS.clear()
    first = detector_for(cfg, "M1")
    assert isinstance(first, YoloDetector)
    assert detector_for(cfg, "M1") is first
    assert detector_for(cfg, "M2") is not first
    _DETECTORS.clear()


# ------------------------------------------------------------------ classification


class _Tensor:
    def __init__(self, values):
        self._v = values

    def tolist(self):
        return list(self._v)


def test_classification_output_becomes_ranked_boxless_predictions():
    probs = types.SimpleNamespace(data=_Tensor([0.05, 0.80, 0.15]))
    names = {0: "healthy", 1: "brown_spot", 2: "rice_blast"}
    preds = _classification_predictions(probs, names, top_k=2)
    assert [p.condition_code for p in preds] == ["brown_spot", "rice_blast"]
    assert preds[0].bbox == []


def test_yolo_detector_reads_classification_results(tmp_path):
    cfg = get_config()
    det = YoloDetector(cfg, "cls")
    fake_result = types.SimpleNamespace(
        names={0: "healthy", 1: "brown_spot"},
        probs=types.SimpleNamespace(data=_Tensor([0.3, 0.7])), boxes=None,
    )
    det._model = types.SimpleNamespace(predict=lambda **_: [fake_result])
    preds = det.predict("unused.jpg", "phone")
    assert preds[0].condition_code == "brown_spot"
    assert abs(preds[0].confidence - 0.7) < 1e-9


def test_severity_is_not_measured_without_boxes():
    out = compute_severity([Prediction("brown_spot", 0.9, [])], 640, 640)
    assert out["severity_value"] is None
    assert "Not measured" in out["severity_note"]
    # With a box it is still the area proxy, unchanged.
    assert compute_severity([Prediction("x", 0.9, [0, 0, 320, 640])], 640, 640)["severity_value"] == 50.0


# ------------------------------------------------------------------ config


def test_relative_paths_resolve_against_backend_not_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert resolve_path("./data/images") == (BACKEND_DIR / "data" / "images").resolve()
    absolute = tmp_path / "elsewhere"
    assert resolve_path(str(absolute)) == absolute


def test_production_refuses_weak_settings():
    cfg = get_config()
    cfg.ENV = "production"
    cfg.SECRET_KEY = "test-secret-not-for-production"
    cfg.DB_PASSWORD = ""
    problems = cfg.production_problems()
    assert any("SECRET_KEY" in p for p in problems)
    assert any("DB_PASSWORD" in p for p in problems)
    with pytest.raises(RuntimeError):
        cfg.validate()
    cfg.SECRET_KEY = "x" * 48
    cfg.DB_PASSWORD = "a-real-database-password"
    assert cfg.production_problems() == []


def test_unknown_environment_name_is_refused():
    cfg = get_config()
    cfg.ENV = "prod"
    with pytest.raises(RuntimeError):
        cfg.validate()


# ------------------------------------------------------------------ preflight


def test_preflight_fails_production_on_published_demo_password(users, tmp_path):
    from app.services import preflight
    from app.auth.security import hash_password
    from app.models import User

    session = SessionLocal()
    demo = User(name="DEMO preflight probe", role="admin", password_hash=hash_password(
        preflight.DEMO_PASSWORD, 10), is_demo=True)
    session.add(demo)
    session.commit()
    try:
        cfg = get_config()
        cfg.ENV = "production"
        results = preflight.check_database(cfg)
        fails = [m for lvl, m in results if lvl == preflight.FAIL]
        assert any("DEMO preflight probe" in m for m in fails)
    finally:
        session.delete(session.get(User, demo.id))
        session.commit()


def test_preflight_reports_missing_build(tmp_path):
    from app.services import preflight

    cfg = get_config()
    cfg.WEB_DIST = str(tmp_path / "no-build")
    cfg.IMAGE_ROOT = str(tmp_path / "images")
    results = preflight.check_paths(cfg)
    assert any(lvl == preflight.FAIL and "npm run build" in m for lvl, m in results)
    assert any(lvl == preflight.OK and "writable" in m for lvl, m in results)


def test_create_admin_upsert(app):
    from scripts.create_admin import upsert_admin

    session = SessionLocal()
    user, created = upsert_admin(session, "p21 cli admin", "first-password-1", 10)
    assert created and user.role == "admin" and not user.is_demo
    user, created = upsert_admin(session, "p21 cli admin", "second-password-2", 10)
    assert not created and user.password_changed_at is not None


def test_import_conditions_validates_categories(tmp_path):
    from scripts.import_conditions import load_rows

    csv_path = tmp_path / "c.csv"
    csv_path.write_text(
        "code,common_name,category,scientific_name,plant_part,aerial_allowed\n"
        "leaf_folder,Leaf folder,pest,Cnaphalocrocis medinalis,leaf,false\n"
        "mystery,Mystery,alien,,,\n"
    )
    rows, errors = load_rows(csv_path)
    assert len(rows) == 2
    assert len(errors) == 1 and "alien" in errors[0]
