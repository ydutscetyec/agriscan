"""Track B endpoints.

These exist so a connected device or data source has somewhere to arrive. They are NOT
referenced by any dashboard page, and no navigation entry points at them.

Every response says plainly what is missing. None of them invents a value.
"""

from __future__ import annotations

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select

from app.auth.decorators import requires_auth, requires_role
from app.extensions import SessionLocal
from app.models import Field
from app.services import spectral
from app.services.mission_planner import (
    CameraSpec, PlannerError, ground_sample_distance, plan_lawnmower, waypoints_to_qgc_wpl,
)
from app.services.risk import build_forecast_model, build_risk_model
from app.utils.errors import ApiError

bp = Blueprint("trackb", __name__, url_prefix="/trackb")


@bp.get("/providers")
@requires_auth
def providers():
    """What is actually connected. Every entry reads HARDWARE_REQUIRED or DATA_REQUIRED
    until a real adapter is registered."""
    registry = current_app.config["AGRISCAN_PROVIDERS"]
    return jsonify({"providers": registry.status_report()})


@bp.get("/planner/gsd")
@requires_role("admin", "technician", "researcher")
def gsd():
    cfg = current_app.config["AGRISCAN"]
    altitude = request.args.get("altitude_m", type=float)
    if altitude is None:
        raise ApiError("'altitude_m' is required.", 400)
    try:
        return jsonify(ground_sample_distance(altitude, CameraSpec.from_config(cfg)))
    except PlannerError as exc:
        raise ApiError(str(exc), 400) from None


@bp.post("/planner/mission")
@requires_role("admin", "technician", "researcher")
def plan_mission():
    """Pure computation. Produces a waypoint list and an ESTIMATED flight time.

    Nothing is uploaded to an aircraft: the waypoints are exported as a file the
    operator loads in ground station software.
    """
    cfg = current_app.config["AGRISCAN"]
    data = request.get_json(silent=True) or {}
    session = SessionLocal()

    polygon = data.get("polygon")
    if not polygon and data.get("field_id"):
        field = session.get(Field, int(data["field_id"]))
        if field is None:
            raise ApiError("Field not found.", 404)
        geometry = field.boundary_geojson or {}
        geometry = geometry.get("geometry", geometry)
        ring = (geometry.get("coordinates") or [[]])[0]
        polygon = [[lat, lon] for lon, lat in ring]  # GeoJSON is [lon, lat]
    if not polygon:
        raise ApiError("Supply 'polygon' as [[lat, lon], ...] or a 'field_id'.", 400)

    try:
        plan = plan_lawnmower(
            [(float(a), float(b)) for a, b in polygon],
            altitude_m=float(data.get("altitude_m", 20.0)),
            camera=CameraSpec.from_config(cfg),
            front_overlap=float(data.get("front_overlap", 0.70)),
            side_overlap=float(data.get("side_overlap", 0.60)),
            speed_ms=float(data.get("speed_ms", 3.0)),
            usable_flight_minutes=float(data.get("usable_flight_minutes", 8.0)),
        )
    except PlannerError as exc:
        raise ApiError(str(exc), 400) from None

    if request.args.get("format") == "wpl":
        return current_app.response_class(
            waypoints_to_qgc_wpl(plan),
            mimetype="text/plain",
            headers={"Content-Disposition": "attachment; filename=agriscan_mission.waypoints"},
        )
    return jsonify(plan)


@bp.get("/spectral/<index_name>")
@requires_role("admin", "technician", "researcher")
def spectral_index(index_name: str):
    """Always unavailable today: the airframe carries an RGB camera.

    The index functions raise rather than return a number. This endpoint converts that
    into the documented message.
    """
    bands = request.args.getlist("band") or ["RED", "GREEN", "BLUE"]
    try:
        spectral.require_bands(index_name, bands)
    except spectral.MissingBandsError as exc:
        return jsonify(
            {
                "index": index_name.upper(),
                "available": False,
                "status": "DATA_REQUIRED",
                "message": spectral.BANDS_UNAVAILABLE_MESSAGE,
                "detail": str(exc),
            }
        ), 200
    except ValueError as exc:
        raise ApiError(str(exc), 400) from None

    return jsonify(
        {
            "index": index_name.upper(),
            "available": True,
            "status": "EXPERIMENTAL",
            "message": "Bands present. Supply per-pixel reflectance to compute values.",
        }
    )


@bp.get("/risk/<int:field_id>")
@requires_role("admin", "technician", "researcher")
def risk(field_id: int):
    model = build_risk_model()
    inputs = {
        "verified_detections": request.args.get("verified_detections", default=0, type=int),
        "observation_days": request.args.get("observation_days", default=0, type=int),
    }
    return jsonify(model.score(field_id, inputs))


@bp.get("/forecast/<int:field_id>")
@requires_role("admin", "technician", "researcher")
def forecast(field_id: int):
    model = build_forecast_model()
    horizon = request.args.get("horizon_days", default=14, type=int)
    inputs = {"observation_days": request.args.get("observation_days", default=0, type=int)}
    return jsonify(model.predict(field_id, horizon, inputs))
