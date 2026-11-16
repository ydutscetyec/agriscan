"""Vegetation indices.

Every index here needs bands the AGRISCAN airframe does not capture. The drone carries
an RGB smartphone camera; NIR and red-edge are not recorded, and no arithmetic on red,
green and blue can recover them.

So each function checks `image_bands` FIRST and raises if the bands are absent. It raises
rather than returning a sentinel number, because a number is the one thing that could be
plotted, averaged, or written into a results table by mistake.
"""

from __future__ import annotations

BANDS_UNAVAILABLE_MESSAGE = "Required spectral bands unavailable."


class MissingBandsError(RuntimeError):
    """Raised when an index is requested without the bands it needs."""

    def __init__(self, index: str, required: list[str], present: list[str]):
        self.index = index
        self.required = required
        self.present = present
        missing = [b for b in required if b not in present]
        super().__init__(
            f"{BANDS_UNAVAILABLE_MESSAGE} {index} needs {', '.join(required)}; "
            f"missing {', '.join(missing) or 'none'}. "
            f"Present: {', '.join(present) or 'none'}."
        )


# Index -> the bands it genuinely requires.
INDEX_REQUIREMENTS = {
    "NDVI": ["NIR", "RED"],
    "GNDVI": ["NIR", "GREEN"],
    "NDRE": ["NIR", "RED_EDGE"],
    "NDWI": ["GREEN", "NIR"],
}

RGB_ONLY = {"RED", "GREEN", "BLUE"}


def _normalised_difference(a: float, b: float) -> float:
    denominator = a + b
    if denominator == 0:
        raise ZeroDivisionError("Band sum is zero; the index is undefined here.")
    return (a - b) / denominator


def require_bands(index: str, present_bands) -> None:
    """Gate every index behind an explicit band check."""
    index = index.upper()
    if index not in INDEX_REQUIREMENTS:
        raise ValueError(f"Unknown index '{index}'. Known: {', '.join(INDEX_REQUIREMENTS)}.")
    present = sorted({str(b).upper() for b in present_bands})
    required = INDEX_REQUIREMENTS[index]
    if not all(band in present for band in required):
        raise MissingBandsError(index, required, present)


def ndvi(reflectance: dict, present_bands=None) -> float:
    """(NIR - RED) / (NIR + RED). Never computable from an RGB photograph."""
    require_bands("NDVI", present_bands if present_bands is not None else reflectance.keys())
    return _normalised_difference(reflectance["NIR"], reflectance["RED"])


def gndvi(reflectance: dict, present_bands=None) -> float:
    require_bands("GNDVI", present_bands if present_bands is not None else reflectance.keys())
    return _normalised_difference(reflectance["NIR"], reflectance["GREEN"])


def ndre(reflectance: dict, present_bands=None) -> float:
    require_bands("NDRE", present_bands if present_bands is not None else reflectance.keys())
    return _normalised_difference(reflectance["NIR"], reflectance["RED_EDGE"])


def ndwi(reflectance: dict, present_bands=None) -> float:
    require_bands("NDWI", present_bands if present_bands is not None else reflectance.keys())
    return _normalised_difference(reflectance["GREEN"], reflectance["NIR"])


INDEX_FUNCTIONS = {"NDVI": ndvi, "GNDVI": gndvi, "NDRE": ndre, "NDWI": ndwi}


def compute(index: str, reflectance: dict, present_bands=None) -> float:
    index = index.upper()
    if index not in INDEX_FUNCTIONS:
        raise ValueError(f"Unknown index '{index}'.")
    return INDEX_FUNCTIONS[index](reflectance, present_bands)
