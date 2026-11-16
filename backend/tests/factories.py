"""Synthetic image builders for gate tests.

Generated, not photographed: a blur test needs a known-blurry frame, and a real field
photo cannot supply a known ground truth for Laplacian variance.
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image as PILImage


def _to_jpeg_bytes(array: np.ndarray, quality: int = 95) -> bytes:
    buf = io.BytesIO()
    PILImage.fromarray(array.astype("uint8"), mode="RGB").save(
        buf, format="JPEG", quality=quality
    )
    return buf.getvalue()


def sharp_image(size: int = 256, seed: int | None = None) -> bytes:
    """High-frequency checkerboard: large Laplacian variance.

    `seed` varies the pixels so two calls produce different bytes. Without it the
    content hash is identical and the upload endpoint correctly treats the second
    image as a duplicate — which silently collapses separate test cases onto one
    detection.
    """
    rng = np.random.default_rng(42 if seed is None else seed)
    base = rng.integers(60, 200, size=(size, size, 3))
    base[::4, :, :] = 20
    base[:, ::4, :] = 235
    return _to_jpeg_bytes(base)


def blurred_image(size: int = 256, seed: int | None = None) -> bytes:
    """Heavily smoothed: Laplacian variance near zero, mid luminance."""
    import cv2

    arr = np.array(PILImage.open(io.BytesIO(sharp_image(size, seed))).convert("RGB"))
    blurred = cv2.GaussianBlur(arr, (51, 51), 0)
    return _to_jpeg_bytes(blurred)


def dark_image(size: int = 256) -> bytes:
    arr = np.full((size, size, 3), 6)
    return _to_jpeg_bytes(arr)


def bright_image(size: int = 256) -> bytes:
    arr = np.full((size, size, 3), 252)
    return _to_jpeg_bytes(arr)


def jpeg_with_gps(lat_dms, lat_ref, lon_dms, lon_ref) -> bytes:
    """A real JPEG carrying a GPS IFD, written with piexif-free manual EXIF.

    Uses Pillow's exif support so the bytes are genuinely parseable by exifread.
    """
    img = PILImage.fromarray(
        np.full((64, 64, 3), 128, dtype="uint8"), mode="RGB"
    )
    from PIL.TiffImagePlugin import IFDRational

    exif = img.getexif()
    # GPS degrees/minutes/seconds are EXIF RATIONALs. Pillow needs IFDRational values,
    # not (numerator, denominator) tuples — the tuple form fails at save time.
    gps_ifd = exif.get_ifd(0x8825)
    gps_ifd[1] = lat_ref
    gps_ifd[2] = tuple(IFDRational(int(v), 1) for v in lat_dms)
    gps_ifd[3] = lon_ref
    gps_ifd[4] = tuple(IFDRational(int(v), 1) for v in lon_dms)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()
