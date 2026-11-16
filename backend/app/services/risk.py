"""Risk and forecast interfaces.

Both are EXPERIMENTAL and NOT_VALIDATED, and neither has the history to run on. They
return INSUFFICIENT_DATA rather than a number, because a risk score computed from three
weeks of detections would look exactly like one computed from three seasons.

Every output records its inputs, method, model version and timestamp, so any figure that
ever does appear can be traced to what produced it.
"""

from __future__ import annotations

import datetime as dt

from app.utils.clock import utc_now
from abc import ABC, abstractmethod

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
EXPERIMENTAL = "EXPERIMENTAL"
NOT_VALIDATED = "NOT_VALIDATED"

# Minimum history before either engine will produce anything at all.
MIN_OBSERVATION_DAYS = 60
MIN_VERIFIED_DETECTIONS = 30


class RiskModel(ABC):
    name = "abstract"
    version = "0"
    method = "abstract"

    @abstractmethod
    def score(self, field_id: int, inputs: dict) -> dict: ...

    def _envelope(self, field_id: int, inputs: dict, **extra) -> dict:
        return {
            "field_id": field_id,
            "computed_at": utc_now().isoformat(timespec="seconds"),
            "method": self.method,
            "model_version": f"{self.name}-v{self.version}",
            "inputs": inputs,
            "capability_status": NOT_VALIDATED,
            "experimental": True,
            **extra,
        }


class InsufficientDataRiskModel(RiskModel):
    """The only risk model today. It refuses, and says why."""

    name = "InsufficientDataRiskModel"
    version = "1"
    method = "history_threshold_check"

    def score(self, field_id: int, inputs: dict) -> dict:
        verified = int(inputs.get("verified_detections", 0) or 0)
        days = int(inputs.get("observation_days", 0) or 0)
        enough = verified >= MIN_VERIFIED_DETECTIONS and days >= MIN_OBSERVATION_DAYS
        return self._envelope(
            field_id,
            inputs,
            risk_score=None,
            risk_band=INSUFFICIENT_DATA,
            detail=(
                f"Needs at least {MIN_VERIFIED_DETECTIONS} technician-verified detections "
                f"across {MIN_OBSERVATION_DAYS} days. Have {verified} across {days} days."
                if not enough
                else "History thresholds met, but no validated scoring method exists yet."
            ),
        )


class ForecastModel(ABC):
    name = "abstract"
    version = "0"
    method = "abstract"

    @abstractmethod
    def predict(self, field_id: int, horizon_days: int, inputs: dict) -> dict: ...

    def _envelope(self, field_id: int, horizon_days: int, inputs: dict, **extra) -> dict:
        return {
            "field_id": field_id,
            "horizon_days": horizon_days,
            "computed_at": utc_now().isoformat(timespec="seconds"),
            "method": self.method,
            "model_version": f"{self.name}-v{self.version}",
            "inputs": inputs,
            "capability_status": NOT_VALIDATED,
            "experimental": True,
            **extra,
        }


class InsufficientDataForecastModel(ForecastModel):
    name = "InsufficientDataForecastModel"
    version = "1"
    method = "history_threshold_check"

    def predict(self, field_id: int, horizon_days: int, inputs: dict) -> dict:
        days = int(inputs.get("observation_days", 0) or 0)
        return self._envelope(
            field_id,
            horizon_days,
            inputs,
            predicted_value=None,
            uncertainty=None,
            status=INSUFFICIENT_DATA,
            detail=(
                "Forecasting needs repeated observations of the same fields across a "
                f"season. Have {days} days of history; need {MIN_OBSERVATION_DAYS}. "
                "Historical comparison is not forecasting and must not be described as it."
            ),
        )


def build_risk_model(cfg=None) -> RiskModel:
    return InsufficientDataRiskModel()


def build_forecast_model(cfg=None) -> ForecastModel:
    return InsufficientDataForecastModel()
