"""Mission planning. Pure computation — no hardware, no network, no database.

Every number this module produces is an ESTIMATE and is labelled as one. Flight time in
particular is a calculation from assumed speed and assumed endurance; the real figure
comes from a logged flight with a watt meter, and until then nothing here may be quoted
in Chapter 4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ESTIMATED = "ESTIMATED"
EARTH_RADIUS_M = 6_378_137.0


class PlannerError(ValueError):
    pass


@dataclass
class CameraSpec:
    """Camera parameters are configuration, never constants.

    The AGRISCAN airframe carries a smartphone, and handsets differ. Measure the actual
    sensor and lens before planning a real survey; the defaults below are placeholders
    for arithmetic, not a description of your phone.
    """

    pixel_pitch_um: float
    focal_length_mm: float
    image_width_px: int
    image_height_px: int
    label: str = "UNVERIFIED_CAMERA"

    @classmethod
    def from_config(cls, cfg) -> "CameraSpec":
        return cls(
            pixel_pitch_um=cfg.CAMERA_PIXEL_PITCH_UM,
            focal_length_mm=cfg.CAMERA_FOCAL_LENGTH_MM,
            image_width_px=cfg.CAMERA_IMAGE_WIDTH_PX,
            image_height_px=cfg.CAMERA_IMAGE_HEIGHT_PX,
            label=cfg.CAMERA_LABEL,
        )


def ground_sample_distance(altitude_m: float, camera: CameraSpec) -> dict:
    """GSD = (H x s) / f.

    H = altitude above the canopy, s = sensor pixel pitch, f = focal length.
    Units are reconciled explicitly: pitch in micrometres, focal length in millimetres,
    altitude in metres, result in millimetres per pixel.

        GSD (mm/px) = altitude(m) x 1000 x pitch(um) / 1000 / focal(mm)
                    = altitude(m) x pitch(um) / focal(mm)
    """
    if altitude_m <= 0:
        raise PlannerError("Altitude above canopy must be greater than zero.")
    if camera.focal_length_mm <= 0 or camera.pixel_pitch_um <= 0:
        raise PlannerError("Camera pixel pitch and focal length must be positive.")

    gsd_mm_px = altitude_m * camera.pixel_pitch_um / camera.focal_length_mm
    swath_m = gsd_mm_px * camera.image_width_px / 1000.0
    footprint_height_m = gsd_mm_px * camera.image_height_px / 1000.0

    return {
        "gsd_mm_per_px": round(gsd_mm_px, 4),
        "swath_m": round(swath_m, 3),
        "footprint_height_m": round(footprint_height_m, 3),
        "altitude_m": altitude_m,
        "camera": camera.label,
        "status": ESTIMATED,
        "note": (
            "Calculated from the configured camera parameters. Verify the pixel pitch "
            "and focal length of the actual handset before using this for a survey."
        ),
    }


def _metres_per_degree(latitude_deg: float) -> tuple[float, float]:
    lat_rad = math.radians(latitude_deg)
    m_per_deg_lat = 111_132.92 - 559.82 * math.cos(2 * lat_rad) + 1.175 * math.cos(4 * lat_rad)
    m_per_deg_lon = 111_412.84 * math.cos(lat_rad) - 93.5 * math.cos(3 * lat_rad)
    return m_per_deg_lat, abs(m_per_deg_lon)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def polygon_bounds(polygon: list[tuple[float, float]]) -> dict:
    lats = [p[0] for p in polygon]
    lons = [p[1] for p in polygon]
    return {"min_lat": min(lats), "max_lat": max(lats), "min_lon": min(lons), "max_lon": max(lons)}


def polygon_area_ha(polygon: list[tuple[float, float]]) -> float:
    """Spherical excess approximation, adequate at field scale."""
    if len(polygon) < 3:
        return 0.0
    total = 0.0
    for i in range(len(polygon)):
        lat1, lon1 = polygon[i]
        lat2, lon2 = polygon[(i + 1) % len(polygon)]
        total += (math.radians(lon2) - math.radians(lon1)) * (
            2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2))
        )
    return abs(total * EARTH_RADIUS_M * EARTH_RADIUS_M / 2.0) / 10_000.0


def plan_lawnmower(
    polygon: list[tuple[float, float]],
    altitude_m: float,
    camera: CameraSpec,
    *,
    front_overlap: float = 0.70,
    side_overlap: float = 0.60,
    speed_ms: float = 3.0,
    usable_flight_minutes: float = 8.0,
) -> dict:
    """Generate a boustrophedon (lawnmower) waypoint list over a field polygon.

    Lines run east-west and step north by the side-overlap spacing. This is the pattern
    the team already flies manually; the planner exists to make the spacing and the
    expected coverage explicit rather than eyeballed.
    """
    if len(polygon) < 3:
        raise PlannerError("A field polygon needs at least three corners.")
    if not 0 <= front_overlap < 1 or not 0 <= side_overlap < 1:
        raise PlannerError("Overlap values must be between 0 and 1.")
    if speed_ms <= 0:
        raise PlannerError("Ground speed must be greater than zero.")

    geometry = ground_sample_distance(altitude_m, camera)
    swath_m = geometry["swath_m"]
    line_spacing_m = swath_m * (1.0 - side_overlap)
    if line_spacing_m <= 0:
        raise PlannerError("Side overlap of 100% would never advance the survey.")

    bounds = polygon_bounds(polygon)
    centre_lat = (bounds["min_lat"] + bounds["max_lat"]) / 2.0
    m_per_deg_lat, m_per_deg_lon = _metres_per_degree(centre_lat)

    lat_step = line_spacing_m / m_per_deg_lat
    lines = []
    lat = bounds["min_lat"]
    flip = False
    while lat <= bounds["max_lat"] + lat_step / 2:
        west = (lat, bounds["min_lon"])
        east = (lat, bounds["max_lon"])
        lines.append((east, west) if flip else (west, east))
        flip = not flip
        lat += lat_step

    waypoints = []
    for start, end in lines:
        waypoints.append(start)
        waypoints.append(end)

    path_m = sum(haversine_m(waypoints[i], waypoints[i + 1]) for i in range(len(waypoints) - 1))

    # Trigger spacing along track, from the front overlap.
    trigger_spacing_m = geometry["footprint_height_m"] * (1.0 - front_overlap)
    expected_images = int(path_m / trigger_spacing_m) if trigger_spacing_m > 0 else 0

    flight_seconds = path_m / speed_ms
    batteries = math.ceil(flight_seconds / (usable_flight_minutes * 60.0)) if flight_seconds else 0

    return {
        "status": ESTIMATED,
        "waypoints": [
            {
                "sequence": i,
                "lat": round(lat, 7),
                "lon": round(lon, 7),
                "altitude_m": altitude_m,
                "action": "survey",
            }
            for i, (lat, lon) in enumerate(waypoints)
        ],
        "line_count": len(lines),
        "line_spacing_m": round(line_spacing_m, 2),
        "trigger_spacing_m": round(trigger_spacing_m, 2),
        "path_length_m": round(path_m, 1),
        "expected_images": expected_images,
        "estimated_flight_minutes": round(flight_seconds / 60.0, 1),
        "estimated_batteries": batteries,
        "area_ha": round(polygon_area_ha(polygon), 4),
        "geometry": geometry,
        "assumptions": {
            "speed_ms": speed_ms,
            "usable_flight_minutes": usable_flight_minutes,
            "front_overlap": front_overlap,
            "side_overlap": side_overlap,
            "note": (
                "Flight time ignores turns, wind, climb and repositioning, and assumes "
                "the configured endurance. Replace these with logged figures before "
                "planning a real survey."
            ),
        },
    }


def waypoints_to_qgc_wpl(plan: dict, home: tuple[float, float] | None = None) -> str:
    """Export to QGroundControl WPL 110 text.

    A file the operator loads in ground station software. This is NOT a MAVLink upload:
    nothing here talks to the aircraft.
    """
    lines = ["QGC WPL 110"]
    waypoints = plan["waypoints"]
    if not waypoints:
        return "\n".join(lines) + "\n"

    origin = home or (waypoints[0]["lat"], waypoints[0]["lon"])
    lines.append(
        f"0\t1\t0\t16\t0\t0\t0\t0\t{origin[0]:.7f}\t{origin[1]:.7f}\t0.000000\t1"
    )
    for wp in waypoints:
        lines.append(
            f"{wp['sequence'] + 1}\t0\t3\t16\t0.000000\t0.000000\t0.000000\t0.000000\t"
            f"{wp['lat']:.7f}\t{wp['lon']:.7f}\t{wp['altitude_m']:.6f}\t1"
        )
    return "\n".join(lines) + "\n"
