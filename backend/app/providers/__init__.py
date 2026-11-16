"""Hardware and external-data provider interfaces.

Every provider here has exactly one implementation today: a Null one that reports
HARDWARE_REQUIRED or DATA_REQUIRED. That is the honest state of the project — the
airframe carries a phone camera, there is no RTK receiver, no thermal or multispectral
sensor, no soil laboratory feed, no DEM and no weather station.

The interfaces exist so that connecting a real device later is an adapter, not a rewrite.
They are deliberately NOT wired to any dashboard page: a screen fed by a simulator
invites a question that has no honest answer.

A Null provider never returns a plausible-looking number. It returns its status, and the
caller must handle that.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field as dc_field

HARDWARE_REQUIRED = "HARDWARE_REQUIRED"
DATA_REQUIRED = "DATA_REQUIRED"


@dataclass
class ProviderResult:
    """Every provider call returns one of these. `available` is the only way in."""

    available: bool
    status: str
    provider: str
    data: dict | list | None = None
    detail: str | None = None

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "status": self.status,
            "provider": self.provider,
            "data": self.data,
            "detail": self.detail,
        }


class BaseProvider(ABC):
    """Common shape. `kind` names the subsystem; `reason` says what is missing."""

    kind: str = "abstract"
    reason: str = HARDWARE_REQUIRED

    @property
    def name(self) -> str:
        return type(self).__name__

    def unavailable(self, detail: str | None = None) -> ProviderResult:
        return ProviderResult(
            available=False,
            status=self.reason,
            provider=self.name,
            data=None,
            detail=detail or f"No {self.kind} provider is connected.",
        )

    @abstractmethod
    def status(self) -> ProviderResult:
        """Report whether this subsystem can be used at all."""


# --------------------------------------------------------------------- interfaces


class FlightControllerProvider(BaseProvider):
    kind = "flight controller"

    @abstractmethod
    def arm_state(self) -> ProviderResult: ...

    @abstractmethod
    def parameters(self) -> ProviderResult: ...


class TelemetryProvider(BaseProvider):
    kind = "telemetry"

    @abstractmethod
    def latest(self) -> ProviderResult: ...

    @abstractmethod
    def stream_since(self, since) -> ProviderResult: ...


class MissionProvider(BaseProvider):
    kind = "mission upload"

    @abstractmethod
    def upload(self, waypoints: list[dict]) -> ProviderResult: ...

    @abstractmethod
    def download(self) -> ProviderResult: ...


class MAVLinkProvider(BaseProvider):
    kind = "MAVLink link"

    @abstractmethod
    def connect(self, endpoint: str) -> ProviderResult: ...

    @abstractmethod
    def send_command(self, command: str, params: dict | None = None) -> ProviderResult: ...


class RTKProvider(BaseProvider):
    kind = "RTK positioning"

    @abstractmethod
    def fix(self) -> ProviderResult: ...

    @abstractmethod
    def correction_status(self) -> ProviderResult: ...


class ThermalCameraProvider(BaseProvider):
    kind = "thermal camera"

    @abstractmethod
    def capture(self) -> ProviderResult: ...

    @abstractmethod
    def calibration(self) -> ProviderResult: ...


class MultispectralProvider(BaseProvider):
    kind = "multispectral camera"

    @abstractmethod
    def capture(self) -> ProviderResult: ...

    @abstractmethod
    def bands(self) -> ProviderResult: ...


class TerrainProvider(BaseProvider):
    kind = "terrain / DEM"
    reason = DATA_REQUIRED

    @abstractmethod
    def elevation(self, lat: float, lon: float) -> ProviderResult: ...

    @abstractmethod
    def tile_for(self, bounds: dict) -> ProviderResult: ...


class SoilProvider(BaseProvider):
    kind = "soil laboratory"
    reason = DATA_REQUIRED

    @abstractmethod
    def results_for(self, sample_reference: str) -> ProviderResult: ...


class IrrigationSensorProvider(BaseProvider):
    kind = "irrigation sensor"

    @abstractmethod
    def readings(self, device_id: int) -> ProviderResult: ...


class WeatherProvider(BaseProvider):
    kind = "weather"
    reason = DATA_REQUIRED

    @abstractmethod
    def observations(self, lat: float, lon: float, since=None) -> ProviderResult: ...

    @abstractmethod
    def forecast(self, lat: float, lon: float, days: int = 7) -> ProviderResult: ...


# ---------------------------------------------------------------- null providers


class NullFlightController(FlightControllerProvider):
    def status(self): return self.unavailable()
    def arm_state(self): return self.unavailable()
    def parameters(self): return self.unavailable()


class NullTelemetry(TelemetryProvider):
    def status(self): return self.unavailable()
    def latest(self): return self.unavailable()
    def stream_since(self, since): return self.unavailable()


class NullMission(MissionProvider):
    def status(self): return self.unavailable()

    def upload(self, waypoints):
        return self.unavailable(
            "Mission upload needs a MAVLink link. Waypoints can be exported to a file "
            "and loaded with ground station software instead."
        )

    def download(self): return self.unavailable()


class NullMAVLink(MAVLinkProvider):
    def status(self): return self.unavailable()
    def connect(self, endpoint): return self.unavailable()
    def send_command(self, command, params=None): return self.unavailable()


class NullRTK(RTKProvider):
    def status(self): return self.unavailable()

    def fix(self):
        return self.unavailable(
            "No RTK receiver is connected. A standard GPS fix is never reported as RTK."
        )

    def correction_status(self): return self.unavailable()


class NullThermalCamera(ThermalCameraProvider):
    def status(self): return self.unavailable()
    def capture(self): return self.unavailable()
    def calibration(self): return self.unavailable()


class NullMultispectral(MultispectralProvider):
    def status(self): return self.unavailable()
    def capture(self): return self.unavailable()

    def bands(self):
        return self.unavailable(
            "The airframe carries an RGB smartphone camera. Red-edge and near-infrared "
            "bands are not captured."
        )


class NullTerrain(TerrainProvider):
    def status(self): return self.unavailable()
    def elevation(self, lat, lon): return self.unavailable("Terrain data unavailable.")
    def tile_for(self, bounds): return self.unavailable("Terrain data unavailable.")


class NullSoil(SoilProvider):
    def status(self): return self.unavailable()
    def results_for(self, sample_reference): return self.unavailable()


class NullIrrigationSensor(IrrigationSensorProvider):
    def status(self): return self.unavailable()
    def readings(self, device_id): return self.unavailable()


class NullWeather(WeatherProvider):
    def status(self): return self.unavailable()
    def observations(self, lat, lon, since=None): return self.unavailable()
    def forecast(self, lat, lon, days=7): return self.unavailable()


# -------------------------------------------------------------------- registry


@dataclass
class ProviderRegistry:
    """Selected by environment variable, defaulting to Null everywhere.

    Adding a real implementation means registering it here under a name and setting
    the matching environment variable. Nothing else in the codebase changes.
    """

    implementations: dict = dc_field(default_factory=dict)

    IMPLEMENTATIONS = {
        "flight_controller": {"null": NullFlightController},
        "telemetry": {"null": NullTelemetry},
        "mission": {"null": NullMission},
        "mavlink": {"null": NullMAVLink},
        "rtk": {"null": NullRTK},
        "thermal": {"null": NullThermalCamera},
        "multispectral": {"null": NullMultispectral},
        "terrain": {"null": NullTerrain},
        "soil": {"null": NullSoil},
        "irrigation_sensor": {"null": NullIrrigationSensor},
        "weather": {"null": NullWeather},
    }

    ENV_VARS = {
        "flight_controller": "AGRISCAN_PROVIDER_FLIGHT_CONTROLLER",
        "telemetry": "AGRISCAN_PROVIDER_TELEMETRY",
        "mission": "AGRISCAN_PROVIDER_MISSION",
        "mavlink": "AGRISCAN_PROVIDER_MAVLINK",
        "rtk": "AGRISCAN_PROVIDER_RTK",
        "thermal": "AGRISCAN_PROVIDER_THERMAL",
        "multispectral": "AGRISCAN_PROVIDER_MULTISPECTRAL",
        "terrain": "AGRISCAN_PROVIDER_TERRAIN",
        "soil": "AGRISCAN_PROVIDER_SOIL",
        "irrigation_sensor": "AGRISCAN_PROVIDER_IRRIGATION",
        "weather": "AGRISCAN_PROVIDER_WEATHER",
    }

    @classmethod
    def from_env(cls, environ) -> "ProviderRegistry":
        chosen = {}
        for key, env_var in cls.ENV_VARS.items():
            name = (environ.get(env_var) or "null").strip().lower()
            options = cls.IMPLEMENTATIONS[key]
            if name not in options:
                # An unknown name falls back to Null rather than failing at import,
                # and the status endpoint reports what actually loaded.
                name = "null"
            chosen[key] = options[name]()
        return cls(implementations=chosen)

    def get(self, key: str) -> BaseProvider:
        if key not in self.implementations:
            raise KeyError(f"No provider registered for '{key}'.")
        return self.implementations[key]

    def status_report(self) -> list[dict]:
        rows = []
        for key, provider in sorted(self.implementations.items()):
            result = provider.status()
            rows.append(
                {
                    "subsystem": key,
                    "provider": provider.name,
                    "kind": provider.kind,
                    "available": result.available,
                    "capability_status": result.status,
                    "detail": result.detail,
                }
            )
        return rows
