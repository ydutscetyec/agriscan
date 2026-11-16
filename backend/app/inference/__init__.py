"""Inference interfaces S2-S5.

Nothing here knows about Flask or HTTP. The worker owns the database; these classes
own the pixels. Swapping StubDetector for YoloDetector changes no API contract.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.config import Config

log = logging.getLogger(__name__)

MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
SEVERITY_METHOD = "bbox_area_fraction"


# --------------------------------------------------------------------------- types


@dataclass
class Prediction:
    condition_code: str
    confidence: float
    bbox: list[float] = field(default_factory=list)  # [x1, y1, x2, y2] in pixels

    def to_dict(self) -> dict:
        return {
            "condition_code": self.condition_code,
            "confidence": round(float(self.confidence), 4),
            "bbox": [round(float(v), 2) for v in self.bbox] if self.bbox else None,
        }


# ----------------------------------------------------------------------- palay gate


class PalayGate(ABC):
    """S2. Answers one question: is this rice at all?"""

    @abstractmethod
    def is_palay(self, image_path: str) -> tuple[bool, float]:
        """Return (is_palay, confidence)."""


class StubPalayGate(PalayGate):
    """Development stand-in. Always True, confidence 1.0.

    This is a STUB, not a classifier. Any result it produces is DEMO_DATA and must
    never be reported as a gate performance figure.
    """

    def is_palay(self, image_path: str) -> tuple[bool, float]:
        return True, 1.0


class ClassifierPalayGate(PalayGate):
    """Slot for a trained binary classifier (MobileNetV3 or a YOLO class).

    Not implemented: no model has been trained, because no non-palay negative set has
    been collected. Raises rather than guessing.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.weights = cfg.model_root_path / "palay_gate" / "weights.pt"

    def is_palay(self, image_path: str) -> tuple[bool, float]:
        if not self.weights.exists():
            raise RuntimeError(
                f"{MODEL_NOT_AVAILABLE}: palay gate weights absent at {self.weights}"
            )
        raise NotImplementedError(
            "ClassifierPalayGate is a wired interface, not a trained model. "
            "Train it once a non-palay negative set exists."
        )


def build_palay_gate(cfg: Config) -> PalayGate:
    if cfg.PALAY_GATE_IMPL == "classifier":
        return ClassifierPalayGate(cfg)
    return StubPalayGate()


# ------------------------------------------------------------------------ detectors


class Detector(ABC):
    """S3. Locate and label conditions in one image."""

    name: str = "abstract"

    @abstractmethod
    def predict(self, image_path: str, source: str) -> list[Prediction]:
        """source is 'phone' or 'drone'."""


class StubDetector(Detector):
    """Configurable synthetic detector for development and tests.

    Output is DEMO_DATA. Set AGRISCAN_STUB_DETECTOR_RESULT to a JSON list, e.g.
    [{"condition_code": "brown_spot", "confidence": 0.91, "bbox": [10,10,110,110]}]
    """

    name = "StubDetector"

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def predict(self, image_path: str, source: str) -> list[Prediction]:
        raw = (self.cfg.STUB_DETECTOR_RESULT or "").strip()
        if not raw:
            # Default: one confident ground detection, or a zone flag for aerial.
            if source == "drone":
                return [Prediction("anomaly_zone", 0.78, [0, 0, 200, 200])]
            return [Prediction("brown_spot", 0.9140, [12, 18, 212, 218])]
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("STUB_DETECTOR_RESULT is not valid JSON; returning no detections")
            return []
        return [
            Prediction(
                condition_code=i["condition_code"],
                confidence=float(i.get("confidence", 0.0)),
                bbox=i.get("bbox") or [],
            )
            for i in items
        ]


class YoloDetector(Detector):
    """Ultralytics YOLO, weights loaded from ml/models/<model_name>/weights.pt.

    Import and load are lazy so the backend and its tests run on a machine with no
    torch installed and no weights present.
    """

    name = "YoloDetector"

    def __init__(self, cfg: Config, model_name: str):
        self.cfg = cfg
        self.model_name = model_name
        self.weights = cfg.model_root_path / model_name / "weights.pt"
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        if not self.weights.exists():
            raise RuntimeError(
                f"{MODEL_NOT_AVAILABLE}: no weights at {self.weights}"
            )
        try:
            from ultralytics import YOLO  # imported lazily on purpose
        except ImportError as exc:
            raise RuntimeError(
                f"{MODEL_NOT_AVAILABLE}: ultralytics is not installed"
            ) from exc
        self._model = YOLO(str(self.weights))
        return self._model

    # A classification model gives one score per class for the whole image. Only the
    # top few are kept: S4 needs the top two for its margin test, and a long tail of
    # near-zero classes is noise in the job log.
    CLASSIFY_TOP_K = 3

    def predict(self, image_path: str, source: str) -> list[Prediction]:
        model = self._load()
        results = model.predict(source=image_path, verbose=False)
        out: list[Prediction] = []
        for result in results:
            names = getattr(result, "names", {}) or {}
            probs = getattr(result, "probs", None)
            if probs is not None:
                # YOLO-cls, trained from one folder per condition. There is no box, so
                # severity cannot be measured from it and is reported as not measured.
                out.extend(_classification_predictions(probs, names, self.CLASSIFY_TOP_K))
                continue
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls.item())
                out.append(
                    Prediction(
                        condition_code=str(names.get(cls_id, cls_id)),
                        confidence=float(box.conf.item()),
                        bbox=[float(v) for v in box.xyxy[0].tolist()],
                    )
                )
        return out


def _classification_predictions(probs, names: dict, top_k: int) -> list[Prediction]:
    """Turn an Ultralytics Probs object into box-less predictions, highest first."""
    data = getattr(probs, "data", None)
    if data is not None:
        values = [float(v) for v in data.tolist()]
    else:  # older/other Probs shapes expose only top1/top5
        values = []
    if values:
        ranked = sorted(range(len(values)), key=lambda i: values[i], reverse=True)[:top_k]
        return [Prediction(str(names.get(i, i)), values[i], []) for i in ranked]
    top1 = int(getattr(probs, "top1", -1))
    if top1 < 0:
        return []
    conf = float(getattr(probs, "top1conf", 0.0))
    return [Prediction(str(names.get(top1, top1)), conf, [])]


def build_detector(cfg: Config, model_name: str | None = None) -> Detector:
    if cfg.DETECTOR_IMPL == "yolo":
        if not model_name:
            raise RuntimeError(f"{MODEL_NOT_AVAILABLE}: no model name supplied")
        return YoloDetector(cfg, model_name)
    return StubDetector(cfg)


# ------------------------------------------------------------- uncertainty S4 + S5


def apply_uncertainty(
    predictions: list[Prediction], conf_threshold: float, margin_threshold: float
) -> dict:
    """Decide whether the system is allowed to answer at all.

    Returns {'answer': Prediction|None, 'low_confidence': bool, 'reason': str}.
    UNKNOWN is a real answer, not a failure.
    """
    if not predictions:
        return {"answer": None, "low_confidence": True, "reason": "no_detections"}

    ranked = sorted(predictions, key=lambda p: p.confidence, reverse=True)
    top1 = ranked[0]
    top2_conf = ranked[1].confidence if len(ranked) > 1 else 0.0
    margin = top1.confidence - top2_conf

    if top1.confidence < conf_threshold:
        return {"answer": top1, "low_confidence": True, "reason": "below_conf_threshold"}
    if len(ranked) > 1 and margin < margin_threshold:
        return {"answer": top1, "low_confidence": True, "reason": "top2_margin_too_small"}
    return {"answer": top1, "low_confidence": False, "reason": "accepted"}


def _union_area(boxes: list[list[float]]) -> float:
    """Exact area of a union of axis-aligned rectangles, by coordinate compression.

    Summing box areas would double-count overlaps and inflate severity, which is the
    number a technician is asked to check. Worth doing properly.
    """
    rects = [b for b in boxes if b and len(b) == 4]
    if not rects:
        return 0.0
    xs = sorted({c for r in rects for c in (r[0], r[2])})
    ys = sorted({c for r in rects for c in (r[1], r[3])})
    total = 0.0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x1 <= x0:
            continue
        for j in range(len(ys) - 1):
            y0, y1 = ys[j], ys[j + 1]
            if y1 <= y0:
                continue
            for r in rects:
                if r[0] <= x0 and r[2] >= x1 and r[1] <= y0 and r[3] >= y1:
                    total += (x1 - x0) * (y1 - y0)
                    break
    return total


def compute_severity(
    predictions: list[Prediction], image_width: int, image_height: int
) -> dict:
    """EXPERIMENTAL. Affected-area fraction = union(boxes) / image area.

    This is NOT lesion area over canopy area. It over-counts, because a bounding box
    contains healthy tissue, and it has no canopy mask. It is a proxy awaiting
    validation against technician severity scoring, and every response says so.
    """
    if predictions and not any(p.bbox for p in predictions):
        # A classification model labels the whole image. Reporting 0% or 100% affected
        # area here would be a number with nothing behind it.
        return {
            "severity_value": None,
            "severity_method": SEVERITY_METHOD,
            "severity_status": "EXPERIMENTAL",
            "severity_note": (
                "Not measured: the model labels the whole image and gives no affected "
                "area. A technician severity score is the only severity for this case."
            ),
        }
    area = float(image_width * image_height)
    if area <= 0:
        return {
            "severity_value": None,
            "severity_method": SEVERITY_METHOD,
            "severity_status": "EXPERIMENTAL",
            "severity_note": "Image dimensions unavailable.",
        }
    union = _union_area([p.bbox for p in predictions])
    pct = round(min(union / area, 1.0) * 100.0, 3)
    return {
        "severity_value": pct,
        "severity_method": SEVERITY_METHOD,
        "severity_status": "EXPERIMENTAL",
        "severity_note": (
            "Affected-area proxy: union of detection boxes over whole-image area. "
            "NOT_VALIDATED against technician severity scoring."
        ),
    }
