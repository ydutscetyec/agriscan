"""Ownership checks, kept separate from role checks.

Role says what KIND of thing you may do. Ownership says WHICH rows you may do it to.
A farmer with the farmer role may read fields; ownership decides whose.
"""

from __future__ import annotations

from sqlalchemy import select

from app.extensions import SessionLocal
from app.models import Farm, Field, Mission, User
from app.utils.errors import ApiError


def visible_farm_ids(user: User) -> list[int] | None:
    """None means 'no restriction' (technician, researcher, admin)."""
    if user.role == "farmer":
        session = SessionLocal()
        rows = session.execute(
            select(Farm.id).where(Farm.owner_user_id == user.id)
        ).scalars().all()
        return list(rows)
    return None


def assert_can_access_farm(user: User, farm: Farm) -> None:
    if user.role == "farmer" and farm.owner_user_id != user.id:
        raise ApiError("Not permitted for this farm.", 403)


def assert_can_access_field(user: User, field: Field) -> None:
    if user.role != "farmer":
        return
    session = SessionLocal()
    farm = session.get(Farm, field.farm_id)
    if farm is None or farm.owner_user_id != user.id:
        raise ApiError("Not permitted for this field.", 403)


def assert_can_access_mission(user: User, mission: Mission) -> None:
    if user.role != "farmer":
        return
    session = SessionLocal()
    field = session.get(Field, mission.field_id)
    if field is None:
        raise ApiError("Not permitted for this mission.", 403)
    assert_can_access_field(user, field)


def assert_can_write(user: User, *, roles: tuple[str, ...]) -> None:
    if user.role not in roles:
        raise ApiError(f"Role '{user.role}' may not modify this resource.", 403)
