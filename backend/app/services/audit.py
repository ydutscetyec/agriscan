"""Append-only audit trail. Enforced at the database level by migration 002."""

from __future__ import annotations

from app.extensions import SessionLocal
from app.models import AuditLog


def record(user_id: int | None, action: str, object_type: str | None = None,
           object_id: str | int | None = None, detail: dict | None = None) -> None:
    session = SessionLocal()
    session.add(
        AuditLog(
            user_id=user_id,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id is not None else None,
            detail=detail,
        )
    )
    session.commit()
