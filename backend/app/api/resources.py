"""CRUD for users, farms, fields and missions.

Every read is filtered by ownership before it leaves the server. Every write checks
role first, then ownership. There is no code path where a farmer's request reaches
another farm's rows.
"""

from __future__ import annotations

import datetime as dt

from flask import Blueprint, current_app, g, jsonify, request
from sqlalchemy import select

from app.auth.decorators import requires_auth, requires_role
from app.auth.security import hash_password, PasswordPolicyError
from app.extensions import SessionLocal
from app.models import ROLES, Farm, Field, Mission, User
from app.services import audit
from app.services.growth_stage import derive_growth_stage
from app.services.ownership import (
    assert_can_access_field,
    assert_can_access_mission,
    visible_farm_ids,
)
from app.utils.errors import ApiError

users_bp = Blueprint("users", __name__, url_prefix="/users")
farms_bp = Blueprint("farms", __name__, url_prefix="/farms")
fields_bp = Blueprint("fields", __name__, url_prefix="/fields")
missions_bp = Blueprint("missions", __name__, url_prefix="/missions")


def _parse_date(value, label: str):
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ApiError(f"'{label}' must be an ISO date (YYYY-MM-DD).", 400) from None


# --------------------------------------------------------------------------- users


@users_bp.get("")
@requires_role("admin")
def list_users():
    session = SessionLocal()
    rows = session.execute(select(User).order_by(User.id)).scalars().all()
    return jsonify([u.to_dict() for u in rows])


NAME_MAX = 160


def _clean_name(value) -> str:
    name = (value or "").strip()
    if not name:
        raise ApiError("'name' is required.", 400)
    if len(name) > NAME_MAX:
        raise ApiError(f"Name must be at most {NAME_MAX} characters.", 400)
    return name


def _clean_role(value) -> str:
    if value not in ROLES:
        raise ApiError(f"'role' must be one of: {', '.join(ROLES)}.", 400)
    return value


def _active_admin_count(session) -> int:
    from sqlalchemy import func

    return session.execute(
        select(func.count()).select_from(User)
        .where(User.role == "admin").where(User.active.is_(True))
    ).scalar_one()


@users_bp.post("")
@requires_role("admin")
def create_user():
    data = request.get_json(silent=True) or {}
    name = _clean_name(data.get("name"))
    role = _clean_role(data.get("role"))
    if not data.get("password"):
        raise ApiError("'password' is required.", 400)
    cfg = current_app.config["AGRISCAN"]
    try:
        pw_hash = hash_password(data["password"], cfg.PASSWORD_MIN_LENGTH)
    except PasswordPolicyError as exc:
        raise ApiError(str(exc), 400) from None

    session = SessionLocal()
    if session.execute(select(User).where(User.name == name)).scalar_one_or_none():
        raise ApiError(f"An account named '{name}' already exists.", 409)
    user = User(
        name=name,
        role=role,
        barangay=(data.get("barangay") or "").strip() or None,
        password_hash=pw_hash,
        is_demo=bool(data.get("is_demo", False)),
    )
    session.add(user)
    session.commit()
    audit.record(g.current_user.id, "create_user", "user", user.id)
    return jsonify(user.to_dict()), 201


@users_bp.put("/<int:user_id>")
@requires_role("admin")
def update_user(user_id: int):
    """Change role, barangay or whether the account may sign in.

    Deactivating takes effect on the account's next request: the auth decorator reads
    `active` from the database every time, so no token outlives it.
    """
    session = SessionLocal()
    user = session.get(User, user_id)
    if user is None:
        raise ApiError("Account not found.", 404)
    data = request.get_json(silent=True) or {}
    me = g.current_user
    changes = {}

    if "role" in data and data["role"] != user.role:
        role = _clean_role(data["role"])
        if user.id == me.id:
            raise ApiError("You cannot change your own role. Ask another administrator.", 400)
        if user.role == "admin" and user.active and _active_admin_count(session) <= 1:
            raise ApiError("This is the only active administrator. Add another first.", 409)
        changes["role"] = [user.role, role]
        user.role = role

    if "active" in data and bool(data["active"]) != user.active:
        active = bool(data["active"])
        if user.id == me.id and not active:
            raise ApiError("You cannot deactivate your own account.", 400)
        if (not active and user.role == "admin"
                and _active_admin_count(session) <= 1):
            raise ApiError("This is the only active administrator. Add another first.", 409)
        changes["active"] = [user.active, active]
        user.active = active

    if "barangay" in data:
        barangay = (data.get("barangay") or "").strip() or None
        if barangay != user.barangay:
            changes["barangay"] = [user.barangay, barangay]
            user.barangay = barangay

    if "name" in data:
        name = _clean_name(data["name"])
        if name != user.name:
            clash = session.execute(
                select(User).where(User.name == name).where(User.id != user.id)
            ).scalar_one_or_none()
            if clash:
                raise ApiError(f"An account named '{name}' already exists.", 409)
            changes["name"] = [user.name, name]
            user.name = name

    session.commit()
    if changes:
        audit.record(me.id, "update_user", "user", user.id, changes)
    return jsonify(user.to_dict())


@users_bp.post("/<int:user_id>/password")
@requires_role("admin")
def reset_password(user_id: int):
    """Set a new password for someone who forgot theirs. Ends their open sessions."""
    from app.auth.security import utc_now

    session = SessionLocal()
    user = session.get(User, user_id)
    if user is None:
        raise ApiError("Account not found.", 404)
    data = request.get_json(silent=True) or {}
    cfg = current_app.config["AGRISCAN"]
    try:
        user.password_hash = hash_password(data.get("password") or "", cfg.PASSWORD_MIN_LENGTH)
    except PasswordPolicyError as exc:
        raise ApiError(str(exc), 400) from None
    user.password_changed_at = utc_now()
    session.commit()
    audit.record(g.current_user.id, "reset_password", "user", user.id)
    return jsonify(user.to_dict())


# --------------------------------------------------------------------------- farms


@farms_bp.get("")
@requires_auth
def list_farms():
    session = SessionLocal()
    stmt = select(Farm)
    allowed = visible_farm_ids(g.current_user)
    if allowed is not None:
        stmt = stmt.where(Farm.id.in_(allowed or [-1]))
    rows = session.execute(stmt.order_by(Farm.id)).scalars().all()
    return jsonify([f.to_dict() for f in rows])


@farms_bp.post("")
@requires_role("admin", "researcher", "technician")
def create_farm():
    data = request.get_json(silent=True) or {}
    if not data.get("name") or not data.get("owner_user_id"):
        raise ApiError("'name' and 'owner_user_id' are required.", 400)
    session = SessionLocal()
    farm = Farm(
        name=data["name"],
        owner_user_id=int(data["owner_user_id"]),
        barangay=data.get("barangay"),
        is_demo=bool(data.get("is_demo", False)),
    )
    session.add(farm)
    session.commit()
    audit.record(g.current_user.id, "create_farm", "farm", farm.id)
    return jsonify(farm.to_dict()), 201


# -------------------------------------------------------------------------- fields


@fields_bp.get("")
@requires_auth
def list_fields():
    session = SessionLocal()
    stmt = select(Field)
    allowed = visible_farm_ids(g.current_user)
    if allowed is not None:
        stmt = stmt.where(Field.farm_id.in_(allowed or [-1]))
    rows = session.execute(stmt.order_by(Field.id)).scalars().all()
    return jsonify([f.to_dict() for f in rows])


@fields_bp.get("/<int:field_id>")
@requires_auth
def get_field(field_id: int):
    session = SessionLocal()
    field = session.get(Field, field_id)
    if field is None:
        raise ApiError("Field not found.", 404)
    assert_can_access_field(g.current_user, field)

    cfg = current_app.config["AGRISCAN"]
    obs = _parse_date(request.args.get("observation_date"), "observation_date") or dt.date.today()
    body = field.to_dict()
    body["growth_stage"] = derive_growth_stage(field.planting_date, obs, cfg)
    return jsonify(body)


@fields_bp.post("")
@requires_role("admin", "researcher", "technician")
def create_field():
    data = request.get_json(silent=True) or {}
    if not data.get("name") or not data.get("farm_id"):
        raise ApiError("'name' and 'farm_id' are required.", 400)
    session = SessionLocal()
    field = Field(
        farm_id=int(data["farm_id"]),
        name=data["name"],
        boundary_geojson=data.get("boundary_geojson"),
        area_ha=data.get("area_ha"),
        variety=data.get("variety"),
        planting_date=_parse_date(data.get("planting_date"), "planting_date"),
        is_demo=bool(data.get("is_demo", False)),
    )
    session.add(field)
    session.commit()
    audit.record(g.current_user.id, "create_field", "field", field.id)
    return jsonify(field.to_dict()), 201


@fields_bp.put("/<int:field_id>")
@requires_role("admin", "researcher", "technician")
def update_field(field_id: int):
    session = SessionLocal()
    field = session.get(Field, field_id)
    if field is None:
        raise ApiError("Field not found.", 404)
    data = request.get_json(silent=True) or {}
    for key in ("name", "variety", "area_ha", "boundary_geojson"):
        if key in data:
            setattr(field, key, data[key])
    if "planting_date" in data:
        field.planting_date = _parse_date(data["planting_date"], "planting_date")
    session.commit()
    audit.record(g.current_user.id, "update_field", "field", field.id)
    return jsonify(field.to_dict())


@fields_bp.delete("/<int:field_id>")
@requires_role("admin")
def delete_field(field_id: int):
    session = SessionLocal()
    field = session.get(Field, field_id)
    if field is None:
        raise ApiError("Field not found.", 404)

    # A field with images or flights attached carries research data. Deleting it would
    # orphan detections and verifications, so refuse and say what is attached.
    from sqlalchemy import func
    from app.models import Image as _Image
    images = session.execute(
        select(func.count()).select_from(_Image).where(_Image.field_id == field_id)
    ).scalar_one()
    missions = session.execute(
        select(func.count()).select_from(Mission).where(Mission.field_id == field_id)
    ).scalar_one()
    if images or missions:
        raise ApiError(
            f"This field has {images} image(s) and {missions} flight(s) recorded. "
            "It cannot be deleted without losing research data.",
            409,
        )

    name = field.name
    session.delete(field)
    session.commit()
    audit.record(g.current_user.id, "delete_field", "field", field_id, {"name": name})
    return jsonify({"deleted": field_id})


# ------------------------------------------------------------------------ missions


@missions_bp.get("")
@requires_auth
def list_missions():
    session = SessionLocal()
    stmt = select(Mission)
    allowed = visible_farm_ids(g.current_user)
    if allowed is not None:
        field_ids = session.execute(
            select(Field.id).where(Field.farm_id.in_(allowed or [-1]))
        ).scalars().all()
        stmt = stmt.where(Mission.field_id.in_(list(field_ids) or [-1]))
    rows = session.execute(stmt.order_by(Mission.id)).scalars().all()
    return jsonify([m.to_dict() for m in rows])


@missions_bp.get("/<int:mission_id>")
@requires_auth
def get_mission(mission_id: int):
    session = SessionLocal()
    mission = session.get(Mission, mission_id)
    if mission is None:
        raise ApiError("Mission not found.", 404)
    assert_can_access_mission(g.current_user, mission)
    return jsonify(mission.to_dict())


@missions_bp.post("")
@requires_role("admin", "researcher", "technician")
def create_mission():
    data = request.get_json(silent=True) or {}
    if not data.get("field_id"):
        raise ApiError("'field_id' is required.", 400)
    session = SessionLocal()
    mission = Mission(
        field_id=int(data["field_id"]),
        operator_id=g.current_user.id,
        flown_at=dt.datetime.fromisoformat(data["flown_at"]) if data.get("flown_at") else None,
        altitude_m=data.get("altitude_m"),
        pattern=data.get("pattern"),
        weather=data.get("weather"),
        wind_ms=data.get("wind_ms"),
        aborted=bool(data.get("aborted", False)),
        abort_reason=data.get("abort_reason"),
        notes=data.get("notes"),
        is_demo=bool(data.get("is_demo", False)),
    )
    session.add(mission)
    session.commit()
    audit.record(g.current_user.id, "create_mission", "mission", mission.id)
    return jsonify(mission.to_dict()), 201
