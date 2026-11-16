"""DMS to decimal conversion, both hemispheres.

Surallah is N/E, so a sign error would never show up in local testing. These cases are
the guard against a dataset silently mirrored into the wrong hemisphere.
"""

from __future__ import annotations

from app.services.exif_gps import dms_to_decimal, extract_gps_and_time


def test_north_east_positive():
    assert dms_to_decimal([6, 22, 0], "N") == 6.3666667
    assert dms_to_decimal([124, 44, 0], "E") == 124.7333333


def test_south_negative():
    assert dms_to_decimal([6, 22, 0], "S") == -6.3666667


def test_west_negative():
    assert dms_to_decimal([124, 44, 0], "W") == -124.7333333


def test_seconds_contribute():
    assert dms_to_decimal([10, 30, 36], "N") == 10.51


def test_missing_seconds_tolerated():
    assert dms_to_decimal([10, 30], "N") == 10.5


def test_empty_returns_none():
    assert dms_to_decimal([], "N") is None
    assert dms_to_decimal(None, "N") is None


def test_ref_lowercase_handled():
    assert dms_to_decimal([6, 0, 0], "s") == -6.0


def test_unreadable_file_returns_missing(tmp_path):
    bad = tmp_path / "not-an-image.jpg"
    bad.write_bytes(b"definitely not a jpeg")
    out = extract_gps_and_time(str(bad))
    assert out["gps_source"] == "missing"
    assert out["lat"] is None
