"""Uncertainty rule S4, severity S5, and the aerial label restriction."""

from __future__ import annotations

from app.inference import Prediction, _union_area, apply_uncertainty, compute_severity


def test_confident_single_prediction_accepted():
    out = apply_uncertainty([Prediction("brown_spot", 0.91)], 0.5, 0.1)
    assert out["low_confidence"] is False
    assert out["answer"].condition_code == "brown_spot"


def test_below_threshold_is_low_confidence():
    out = apply_uncertainty([Prediction("brown_spot", 0.31)], 0.5, 0.1)
    assert out["low_confidence"] is True
    assert out["reason"] == "below_conf_threshold"


def test_narrow_margin_is_low_confidence():
    """Nitrogen deficiency vs hopperburn: both yellowing, opposite actions."""
    out = apply_uncertainty(
        [Prediction("nitrogen_deficiency", 0.61), Prediction("hopperburn", 0.58)],
        0.5, 0.1,
    )
    assert out["low_confidence"] is True
    assert out["reason"] == "top2_margin_too_small"


def test_wide_margin_accepted():
    out = apply_uncertainty(
        [Prediction("nitrogen_deficiency", 0.88), Prediction("hopperburn", 0.20)],
        0.5, 0.1,
    )
    assert out["low_confidence"] is False


def test_no_detections_is_low_confidence():
    out = apply_uncertainty([], 0.5, 0.1)
    assert out["low_confidence"] is True
    assert out["answer"] is None


def test_union_area_does_not_double_count_overlap():
    boxes = [[0, 0, 10, 10], [5, 5, 15, 15]]
    # naive sum would be 200; true union is 175
    assert _union_area(boxes) == 175.0


def test_union_area_disjoint():
    assert _union_area([[0, 0, 10, 10], [20, 20, 30, 30]]) == 200.0


def test_union_area_contained_box():
    assert _union_area([[0, 0, 10, 10], [2, 2, 4, 4]]) == 100.0


def test_severity_is_fraction_of_image():
    preds = [Prediction("brown_spot", 0.9, [0, 0, 50, 50])]
    out = compute_severity(preds, 100, 100)
    assert out["severity_value"] == 25.0
    assert out["severity_method"] == "bbox_area_fraction"


def test_severity_is_labelled_experimental():
    out = compute_severity([Prediction("x", 0.9, [0, 0, 10, 10])], 100, 100)
    assert out["severity_status"] == "EXPERIMENTAL"
    assert "NOT_VALIDATED" in out["severity_note"]


def test_severity_caps_at_100():
    preds = [Prediction("x", 0.9, [0, 0, 500, 500])]
    assert compute_severity(preds, 100, 100)["severity_value"] == 100.0
