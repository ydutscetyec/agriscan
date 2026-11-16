"""Track B: providers, planner, spectral indices, risk, dataset validation."""

from __future__ import annotations

import json
import math
import subprocess
import sys

import pytest

from app.providers import DATA_REQUIRED, HARDWARE_REQUIRED, ProviderRegistry
from app.services import spectral
from app.services.mission_planner import (
    CameraSpec, PlannerError, ground_sample_distance, plan_lawnmower, waypoints_to_qgc_wpl,
)
from app.services.risk import (
    INSUFFICIENT_DATA, build_forecast_model, build_risk_model,
)
from scripts.validate_split import check_field_leakage, check_minimum_samples, validate
from tests.conftest import auth_headers, login

CAMERA = CameraSpec(
    pixel_pitch_um=1.0, focal_length_mm=4.7,
    image_width_px=4000, image_height_px=3000, label="TEST_CAMERA",
)

# A small square roughly in Surallah, about 300 m on a side.
SQUARE = [
    (6.3700, 124.7450),
    (6.3700, 124.7477),
    (6.3727, 124.7477),
    (6.3727, 124.7450),
]


# ------------------------------------------------------------------------ providers


def test_every_provider_defaults_to_null():
    registry = ProviderRegistry.from_env({})
    report = registry.status_report()
    assert len(report) == 11
    for row in report:
        assert row["available"] is False
        assert row["capability_status"] in (HARDWARE_REQUIRED, DATA_REQUIRED)
        assert row["provider"].startswith("Null")


def test_provider_names_cover_the_required_set():
    registry = ProviderRegistry.from_env({})
    assert set(registry.implementations) == {
        "flight_controller", "telemetry", "mission", "mavlink", "rtk", "thermal",
        "multispectral", "terrain", "soil", "irrigation_sensor", "weather",
    }


def test_unknown_provider_name_falls_back_to_null():
    registry = ProviderRegistry.from_env({"AGRISCAN_PROVIDER_RTK": "some-device-we-lack"})
    assert registry.get("rtk").name == "NullRTK"


def test_null_rtk_refuses_rather_than_reporting_a_fix():
    result = ProviderRegistry.from_env({}).get("rtk").fix()
    assert result.available is False
    assert "RTK" in result.detail


def test_null_mission_upload_points_at_file_export():
    result = ProviderRegistry.from_env({}).get("mission").upload([])
    assert result.available is False
    assert "export" in result.detail.lower()


def test_providers_endpoint_reports_everything_unavailable(client, users):
    token = login(client, "t_tech")
    body = client.get("/trackb/providers", headers=auth_headers(token)).get_json()
    assert len(body["providers"]) == 11
    assert all(p["available"] is False for p in body["providers"])


# -------------------------------------------------------------------------- planner


def test_gsd_matches_the_formula():
    """GSD = (H x s) / f, with 1 um pitch, 4.7 mm lens, 20 m altitude."""
    out = ground_sample_distance(20.0, CAMERA)
    expected = 20.0 * 1.0 / 4.7  # mm per pixel
    # The planner reports GSD to 4 decimal places (0.1 um); assert to that precision.
    assert out["gsd_mm_per_px"] == pytest.approx(expected, abs=1e-4)
    assert out["status"] == "ESTIMATED"


def test_gsd_scales_linearly_with_altitude():
    low = ground_sample_distance(15.0, CAMERA)["gsd_mm_per_px"]
    high = ground_sample_distance(30.0, CAMERA)["gsd_mm_per_px"]
    assert high == pytest.approx(low * 2, abs=2e-4)


def test_gsd_shows_a_blast_lesion_is_subpixel_scale():
    """At 20 m a lesion a few millimetres across is one or two pixels.

    This is the arithmetic behind the rule that a drone frame may not carry a
    lesion-level disease label.
    """
    gsd = ground_sample_distance(20.0, CAMERA)["gsd_mm_per_px"]
    lesion_mm = 5.0
    assert lesion_mm / gsd < 3


def test_gsd_rejects_zero_altitude():
    with pytest.raises(PlannerError):
        ground_sample_distance(0, CAMERA)


def test_plan_produces_waypoints_and_estimates():
    plan = plan_lawnmower(SQUARE, altitude_m=20.0, camera=CAMERA)
    assert plan["status"] == "ESTIMATED"
    assert len(plan["waypoints"]) >= 4
    assert plan["line_count"] >= 2
    assert plan["path_length_m"] > 0
    assert plan["estimated_flight_minutes"] > 0
    assert plan["estimated_batteries"] >= 1


def test_plan_lines_alternate_direction():
    """A lawnmower pattern must reverse each pass, or the drone flies the return leg dry."""
    plan = plan_lawnmower(SQUARE, altitude_m=20.0, camera=CAMERA)
    wps = plan["waypoints"]
    first_eastward = wps[1]["lon"] > wps[0]["lon"]
    second_eastward = wps[3]["lon"] > wps[2]["lon"]
    assert first_eastward != second_eastward


def test_more_side_overlap_means_more_lines():
    sparse = plan_lawnmower(SQUARE, 20.0, CAMERA, side_overlap=0.2)
    dense = plan_lawnmower(SQUARE, 20.0, CAMERA, side_overlap=0.8)
    assert dense["line_count"] > sparse["line_count"]


def test_full_side_overlap_is_rejected():
    with pytest.raises(PlannerError):
        plan_lawnmower(SQUARE, 20.0, CAMERA, side_overlap=1.0)


def test_polygon_needs_three_corners():
    with pytest.raises(PlannerError):
        plan_lawnmower([(6.37, 124.74), (6.38, 124.75)], 20.0, CAMERA)


def test_waypoint_export_is_qgc_format():
    plan = plan_lawnmower(SQUARE, 20.0, CAMERA)
    text = waypoints_to_qgc_wpl(plan)
    assert text.startswith("QGC WPL 110")
    assert len(text.strip().splitlines()) == len(plan["waypoints"]) + 2  # header + home


def test_planner_endpoint_returns_estimates(client, users):
    token = login(client, "t_tech")
    resp = client.post(
        "/trackb/planner/mission",
        headers=auth_headers(token),
        json={"polygon": [list(p) for p in SQUARE], "altitude_m": 20},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ESTIMATED"
    assert "assumptions" in body


# ------------------------------------------------------------------------- spectral


def test_ndvi_on_rgb_image_raises():
    """The airframe carries an RGB camera. NDVI from red, green and blue is not a
    conservative estimate; it is a fabricated number."""
    with pytest.raises(spectral.MissingBandsError):
        spectral.ndvi({"RED": 0.2, "GREEN": 0.3, "BLUE": 0.1}, present_bands=["RED", "GREEN", "BLUE"])


def test_every_index_refuses_rgb_only():
    rgb = ["RED", "GREEN", "BLUE"]
    for name in ("NDVI", "GNDVI", "NDRE", "NDWI"):
        with pytest.raises(spectral.MissingBandsError):
            spectral.require_bands(name, rgb)


def test_missing_bands_error_carries_the_documented_message():
    with pytest.raises(spectral.MissingBandsError) as exc:
        spectral.require_bands("NDVI", ["RED", "GREEN", "BLUE"])
    assert spectral.BANDS_UNAVAILABLE_MESSAGE in str(exc.value)


def test_ndvi_computes_when_the_bands_exist():
    value = spectral.ndvi({"NIR": 0.6, "RED": 0.2}, present_bands=["NIR", "RED"])
    assert value == pytest.approx((0.6 - 0.2) / (0.6 + 0.2))


def test_ndre_needs_red_edge_specifically():
    with pytest.raises(spectral.MissingBandsError):
        spectral.ndre({"NIR": 0.6, "RED": 0.2}, present_bands=["NIR", "RED"])


def test_unknown_index_rejected():
    with pytest.raises(ValueError):
        spectral.require_bands("NDXX", ["NIR", "RED"])


def test_spectral_endpoint_returns_the_documented_string(client, users):
    token = login(client, "t_tech")
    body = client.get("/trackb/spectral/NDVI", headers=auth_headers(token)).get_json()
    assert body["available"] is False
    assert body["message"] == "Required spectral bands unavailable."


# ------------------------------------------------------------------- risk / forecast


def test_risk_returns_insufficient_data_with_thin_history():
    out = build_risk_model().score(1, {"verified_detections": 4, "observation_days": 10})
    assert out["risk_band"] == INSUFFICIENT_DATA
    assert out["risk_score"] is None
    assert out["capability_status"] == "NOT_VALIDATED"


def test_risk_output_records_its_provenance():
    out = build_risk_model().score(1, {"verified_detections": 0, "observation_days": 0})
    for key in ("method", "model_version", "inputs", "computed_at"):
        assert out[key] is not None


def test_forecast_refuses_and_says_it_is_not_history():
    out = build_forecast_model().predict(1, 14, {"observation_days": 12})
    assert out["status"] == INSUFFICIENT_DATA
    assert out["predicted_value"] is None
    assert "not forecasting" in out["detail"]


def test_risk_endpoint(client, users):
    token = login(client, "t_tech")
    body = client.get("/trackb/risk/1", headers=auth_headers(token)).get_json()
    assert body["risk_band"] == INSUFFICIENT_DATA


# ------------------------------------------------------------- dataset validation


def _manifest(rows):
    return {"version": "TEST-DS-v1", "images": rows}


def test_split_validation_catches_field_leakage():
    manifest = _manifest([
        {"image_id": 1, "field_id": 7, "split": "train", "condition": "brown_spot"},
        {"image_id": 2, "field_id": 7, "split": "test", "condition": "brown_spot"},
    ])
    report = check_field_leakage(manifest)
    assert report["ok"] is False
    assert report["leaks"][0]["field_id"] == 7


def test_split_validation_passes_on_clean_field_split():
    manifest = _manifest([
        {"image_id": 1, "field_id": 1, "split": "train", "condition": "brown_spot"},
        {"image_id": 2, "field_id": 2, "split": "validation", "condition": "brown_spot"},
        {"image_id": 3, "field_id": 3, "split": "test", "condition": "brown_spot"},
    ])
    assert check_field_leakage(manifest)["ok"] is True


def test_minimum_sample_rule_marks_thin_classes_insufficient():
    rows = [
        {"image_id": i, "field_id": 1, "split": "train", "condition": "rice_blast",
         "captured_on": "2026-09-01", "verified": True}
        for i in range(10)
    ]
    report = check_minimum_samples(_manifest(rows))
    assert report["classes"]["rice_blast"]["status"] == "INSUFFICIENT_DATA"
    assert report["trainable"] == []


def test_minimum_sample_rule_accepts_a_class_that_meets_every_threshold():
    rows = []
    for i in range(150):
        rows.append({
            "image_id": i, "field_id": (i % 3) + 1, "split": "train",
            "condition": "brown_spot",
            "captured_on": "2026-09-01" if i % 2 else "2026-10-01",
            "verified": True,
        })
    report = check_minimum_samples(_manifest(rows))
    assert report["classes"]["brown_spot"]["status"] == "TRAINABLE"


def test_unverified_samples_do_not_count_toward_the_threshold():
    rows = [
        {"image_id": i, "field_id": (i % 3) + 1, "split": "train",
         "condition": "brown_spot", "captured_on": "2026-09-0%d" % ((i % 2) + 1),
         "verified": False}
        for i in range(200)
    ]
    report = check_minimum_samples(_manifest(rows))
    assert report["classes"]["brown_spot"]["status"] == "INSUFFICIENT_DATA"


def test_validate_script_exits_nonzero_on_a_leaked_manifest(tmp_path):
    """The acceptance criterion: a deliberately leaked manifest must fail loudly."""
    manifest = _manifest([
        {"image_id": 1, "field_id": 9, "split": "train", "condition": "brown_spot"},
        {"image_id": 2, "field_id": 9, "split": "test", "condition": "brown_spot"},
    ])
    path = tmp_path / "leaked.json"
    path.write_text(json.dumps(manifest))

    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_split", str(path)],
        capture_output=True, text=True, cwd=str(__import__("pathlib").Path(__file__).parents[1]),
    )
    assert result.returncode == 1
    assert "field-level split violated" in result.stderr


def test_validate_script_passes_a_clean_manifest(tmp_path):
    manifest = _manifest([
        {"image_id": 1, "field_id": 1, "split": "train", "condition": "brown_spot"},
        {"image_id": 2, "field_id": 2, "split": "test", "condition": "brown_spot"},
    ])
    path = tmp_path / "clean.json"
    path.write_text(json.dumps(manifest))

    result = subprocess.run(
        [sys.executable, "-m", "scripts.validate_split", str(path)],
        capture_output=True, text=True, cwd=str(__import__("pathlib").Path(__file__).parents[1]),
    )
    assert result.returncode == 0
    assert "PASS" in result.stdout
