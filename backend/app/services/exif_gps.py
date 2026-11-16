"""EXIF GPS extraction.

Phone EXIF is the source of record for image position; the APM flight log is a
cross-check, not the primary source. Decided 18 Sep 2026, see the master plan.

The hemisphere bug is the one that matters here: Surallah is north of the equator and
east of the meridian, so a sign error is invisible in local testing and catastrophic in
a dataset. Both hemispheres are handled and tested explicitly.
"""

from __future__ import annotations

import datetime as dt
import logging
from fractions import Fraction

import exifread

log = logging.getLogger(__name__)

GPS_MISSING = "missing"
GPS_EXIF = "exif"


def _ratio_to_float(value) -> float:
    """exifread yields Ratio objects; ints and floats may also appear."""
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(Fraction(value.num, value.den))
    except (AttributeError, ZeroDivisionError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


def dms_to_decimal(dms, ref: str) -> float | None:
    """Convert [degrees, minutes, seconds] + hemisphere ref to signed decimal degrees.

    ref 'S' (south) and 'W' (west) produce NEGATIVE values. Anything else is positive.
    """
    if not dms or len(dms) < 2:
        return None
    degrees = _ratio_to_float(dms[0])
    minutes = _ratio_to_float(dms[1])
    seconds = _ratio_to_float(dms[2]) if len(dms) > 2 else 0.0

    decimal = degrees + minutes / 60.0 + seconds / 3600.0
    if str(ref).strip().upper().startswith(("S", "W")):
        decimal = -decimal
    return round(decimal, 7)


def _in_range(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def extract_gps_and_time(path: str) -> dict:
    """Return lat/lon/captured_at/gps_source. Never raises on a bad file.

    A missing or unreadable GPS block is a legitimate state: the image is still
    accepted and flagged 'Position missing.'
    """
    result = {
        "lat": None,
        "lon": None,
        "gps_source": GPS_MISSING,
        "captured_at": None,
    }
    try:
        with open(path, "rb") as fh:
            tags = exifread.process_file(fh, details=False)
    except Exception as exc:  # noqa: BLE001
        log.warning("EXIF read failed for %s: %s", path, exc)
        return result

    lat_tag = tags.get("GPS GPSLatitude")
    lat_ref = tags.get("GPS GPSLatitudeRef")
    lon_tag = tags.get("GPS GPSLongitude")
    lon_ref = tags.get("GPS GPSLongitudeRef")

    if lat_tag and lon_tag:
        lat = dms_to_decimal(lat_tag.values, str(lat_ref) if lat_ref else "N")
        lon = dms_to_decimal(lon_tag.values, str(lon_ref) if lon_ref else "E")
        if _in_range(lat, lon):
            result["lat"] = lat
            result["lon"] = lon
            result["gps_source"] = GPS_EXIF
        else:
            log.warning("EXIF GPS out of range for %s: %s, %s", path, lat, lon)

    for tag_name in ("EXIF DateTimeOriginal", "Image DateTime"):
        raw = tags.get(tag_name)
        if raw:
            try:
                result["captured_at"] = dt.datetime.strptime(
                    str(raw), "%Y:%m:%d %H:%M:%S"
                )
                break
            except ValueError:
                continue

    return result
