"""Condition taxonomy. Read-only for everyone; only admin/researcher may write.

The taxonomy lives in the database, never hardcoded in frontend code.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.auth.decorators import requires_auth, requires_role
from app.extensions import SessionLocal
from app.models import Condition
from app.utils.errors import ApiError

bp = Blueprint("conditions", __name__, url_prefix="/conditions")


@bp.get("")
@requires_auth
def list_conditions():
    session = SessionLocal()
    stmt = select(Condition)
    tier = request.args.get("tier", type=int)
    if tier is not None:
        stmt = stmt.where(Condition.tier == tier)
    rows = session.execute(stmt.order_by(Condition.tier, Condition.code)).scalars().all()
    return jsonify([c.to_dict() for c in rows])


@bp.post("")
@requires_role("admin", "researcher")
def create_condition():
    data = request.get_json(silent=True) or {}
    for key in ("code", "common_name", "category"):
        if not data.get(key):
            raise ApiError(f"'{key}' is required.", 400)
    session = SessionLocal()
    cond = Condition(
        code=data["code"],
        common_name=data["common_name"],
        scientific_name=data.get("scientific_name"),
        category=data["category"],
        tier=data.get("tier"),
        plant_part=data.get("plant_part"),
    )
    session.add(cond)
    session.commit()
    return jsonify(cond.to_dict()), 201
