"""Quality gate S1."""

from __future__ import annotations

import pytest

from app.services import quality
from tests.factories import blurred_image, bright_image, dark_image, sharp_image


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_sharp_image_passes(tmp_path, cfg):
    out = quality.assess(_write(tmp_path, "sharp.jpg", sharp_image()), cfg)
    assert out["flag"] == "ok"
    assert out["passed"] is True


def test_blurred_image_rejected(tmp_path, cfg):
    out = quality.assess(_write(tmp_path, "blur.jpg", blurred_image()), cfg)
    assert out["flag"] == "blurred"
    assert out["passed"] is False
    assert out["message"] == "Image rejected — recapture required."


def test_dark_image_rejected(tmp_path, cfg):
    out = quality.assess(_write(tmp_path, "dark.jpg", dark_image()), cfg)
    assert out["flag"] == "dark"
    assert out["passed"] is False


def test_overexposed_image_rejected(tmp_path, cfg):
    out = quality.assess(_write(tmp_path, "bright.jpg", bright_image()), cfg)
    assert out["flag"] == "overexposed"
    assert out["passed"] is False


def test_unreadable_file(tmp_path, cfg):
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"\xff\xd8not-a-jpeg")
    out = quality.assess(str(path), cfg)
    assert out["flag"] == "unreadable"


def test_measurements_are_returned(tmp_path, cfg):
    out = quality.assess(_write(tmp_path, "s.jpg", sharp_image()), cfg)
    assert out["laplacian_variance"] is not None
    assert out["mean_luminance"] is not None
    assert out["clipped_fraction"] is not None


def test_thresholds_are_configurable(tmp_path, cfg):
    path = _write(tmp_path, "s2.jpg", sharp_image())
    cfg.QG_BLUR_LAPLACIAN_VAR_MIN = 10_000_000.0
    out = quality.assess(path, cfg)
    assert out["flag"] == "blurred"
