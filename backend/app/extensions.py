"""Shared SQLAlchemy engine/session, configured per application factory call."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

SessionLocal = scoped_session(sessionmaker(autoflush=False, expire_on_commit=False))


def init_engine(uri: str, echo: bool = False):
    engine = create_engine(uri, echo=echo, pool_pre_ping=True, future=True)
    SessionLocal.configure(bind=engine)
    return engine
