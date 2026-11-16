"""Quality gate S1. Pure OpenCV, no ML, no model file needed.

Rejected images are STORED and FLAGGED, never deleted: a discarded frame is part of an
honest reliability figure, and the blur/exposure thresholds themselves need auditing
against real field photos before they are written into Chapter 3.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from app.config import Config

OK = "ok"
BLURRED = "blurred"
DARK = "dark"
OVEREXPOSED = "overexposed"
UNREADABLE = "unreadable"

RECAPTURE_MESSAGE = "Image rejected — recapture required."

log = logging.getLogger(__name__)


def assess(path: str, cfg: Config) -> dict:
    """Return the quality verdict plus the measurements behind it.

    Measurements are returned, not just the verdict, so thresholds can be tuned later
    against stored values instead of re-processing the whole dataset.
    """
    image = cv2.imread(path, cv2.IMREAD_COLOR)
    if image is None:
        return {
            "flag": UNREADABLE,
            "passed": False,
            "message": RECAPTURE_MESSAGE,
            "laplacian_variance": None,
            "mean_luminance": None,
            "clipped_fraction": None,
        }

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Blur: variance of the Laplacian. A sharp image has strong second derivatives.
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    mean_luma = float(np.mean(gray))
    total = gray.size
    clipped_low = int(np.count_nonzero(gray <= 2))
    clipped_high = int(np.count_nonzero(gray >= 253))
    clipped_fraction = float((clipped_low + clipped_high) / total) if total else 0.0

    measurements = {
        "laplacian_variance": round(lap_var, 3),
        "mean_luminance": round(mean_luma, 3),
        "clipped_fraction": round(clipped_fraction, 5),
    }

    # Exposure is checked before blur: a blown-out or black frame also reads as blurred,
    # and the more useful message for the person holding the phone is the exposure one.
    if mean_luma < cfg.QG_LUMA_MIN or (
        clipped_low / total > cfg.QG_CLIP_FRACTION_MAX if total else False
    ):
        return {"flag": DARK, "passed": False, "message": RECAPTURE_MESSAGE, **measurements}

    if mean_luma > cfg.QG_LUMA_MAX or (
        clipped_high / total > cfg.QG_CLIP_FRACTION_MAX if total else False
    ):
        return {
            "flag": OVEREXPOSED, "passed": False, "message": RECAPTURE_MESSAGE, **measurements
        }

    if lap_var < cfg.QG_BLUR_LAPLACIAN_VAR_MIN:
        return {"flag": BLURRED, "passed": False, "message": RECAPTURE_MESSAGE, **measurements}

    return {"flag": OK, "passed": True, "message": None, **measurements}
